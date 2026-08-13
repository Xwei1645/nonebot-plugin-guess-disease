"""游戏状态管理：词库 + 会话 + 多群隔离 + 超时 GC。

- `DiseasePool`：加载/校验/抽样/保底；保底计数文件 `asyncio.Lock` + 临时文件 `os.replace` 原子写。
- `GameSession`：单群一局，含历史/锁/超时；history 用 OpenAI 消息格式（user/assistant）。
- `SessionManager`：多群隔离 + 惰性 GC + 后台 GC。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import random
import time
from typing import Any

import anyio
from nonebot import logger, require
import nonebot_plugin_localstore as store

from .config import plugin_config

require("nonebot_plugin_localstore")

# bundled examples 路径（不依赖 localstore，可在模块级解析）
_BUNDLED_EXAMPLES = Path(__file__).resolve().parent / "examples" / "diseases.json"

# localstore 路径延迟到运行时解析（需要插件上下文）
_DATA_FILE: Path | None = None
_COUNTER_FILE: Path | None = None


def _get_data_file() -> Path:
    global _DATA_FILE
    if _DATA_FILE is None:
        _DATA_FILE = store.get_plugin_data_file("diseases.json")
    return _DATA_FILE


def _get_counter_file() -> Path:
    global _COUNTER_FILE
    if _COUNTER_FILE is None:
        _COUNTER_FILE = store.get_plugin_data_file("random_data.json")
    return _COUNTER_FILE


# 抽样权重：45% common / 44% uncommon / 11% rare
_WEIGHT_COMMON = 0.45
_WEIGHT_UNCOMMON = 0.89  # 0.45 + 0.44
# rare = 1.0 - 0.89 = 0.11

# 保底阈值
_PITY_THRESHOLD = 30


class DiseasePool:
    """疾病词库：加载、运行时去重兜底、加权抽样、保底。"""

    def __init__(self) -> None:
        self.common: list[str] = []
        self.uncommon: list[str] = []
        self.rare: list[str] = []
        self._counter_lock = asyncio.Lock()
        self._loaded = False

    async def load(self) -> None:
        """从 localstore 数据目录加载；不存在则从 bundled examples 复制。"""
        data_file = _get_data_file()
        data: dict[str, list[str]] | None = None
        try:
            if await anyio.Path(data_file).exists():
                text = await anyio.Path(data_file).read_text(encoding="utf-8")
                data = json.loads(text)
            else:
                logger.warning(
                    f"本地数据中 diseases.json 不存在，从 bundled examples 复制：{_BUNDLED_EXAMPLES}"
                )
                text = await anyio.Path(_BUNDLED_EXAMPLES).read_text(encoding="utf-8")
                data = json.loads(text)
                # 复制到数据目录，便于用户后续修改
                await anyio.Path(data_file).parent.mkdir(parents=True, exist_ok=True)
                await anyio.Path(data_file).write_text(text, encoding="utf-8")
                logger.success("已复制 examples/diseases.json 到数据目录")
                logger.warning("请按需修改数据目录中的 diseases.json")
        except Exception as e:
            logger.error(f"读取疾病数据失败：{e}")
            data = None

        if data is None:
            data = {"common_diseases": [], "uncommon_diseases": [], "rare_diseases": []}

        self.common = list(data.get("common_diseases") or [])
        self.uncommon = list(data.get("uncommon_diseases") or [])
        self.rare = list(data.get("rare_diseases") or [])
        self._loaded = True
        self.validate()

    def validate(self) -> None:
        """运行时去重兜底 + 空档告警 + 记录各档数量。

        - 档内去重（保序）
        - 跨档去重（保留首次出现的档位）
        """
        # 档内去重（保序）
        def _dedup(lst: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for d in lst:
                if not isinstance(d, str):
                    continue
                if d in seen:
                    continue
                seen.add(d)
                out.append(d)
            return out

        self.common = _dedup(self.common)
        self.uncommon = _dedup(self.uncommon)
        self.rare = _dedup(self.rare)

        # 跨档去重：保留首次出现档位
        seen_cross: set[str] = set(self.common)
        new_uncommon = []
        for d in self.uncommon:
            if d in seen_cross:
                logger.warning(f"跨档去重：{d} 已在 common 中，从 uncommon 移除")
                continue
            seen_cross.add(d)
            new_uncommon.append(d)
        self.uncommon = new_uncommon

        new_rare = []
        for d in self.rare:
            if d in seen_cross:
                logger.warning(f"跨档去重：{d} 已在更早档位中，从 rare 移除")
                continue
            seen_cross.add(d)
            new_rare.append(d)
        self.rare = new_rare

        logger.info(
            f"DiseasePool 加载完成：common={len(self.common)} "
            f"uncommon={len(self.uncommon)} rare={len(self.rare)}"
        )
        if not self.common:
            logger.warning("common_diseases 为空")
        if not self.uncommon:
            logger.warning("uncommon_diseases 为空")
        if not self.rare:
            logger.warning("rare_diseases 为空")

    async def _read_counter(self) -> int:
        """读取保底计数。"""
        counter_file = _get_counter_file()
        try:
            if await anyio.Path(counter_file).exists():
                text = await anyio.Path(counter_file).read_text(encoding="utf-8")
                data = json.loads(text)
                return int(data.get("non_rare_count", 0))
        except Exception as e:
            logger.error(f"读取保底计数失败：{e}")
        return 0

    async def _write_counter(self, count: int) -> None:
        """原子写保底计数：临时文件 + os.replace。"""
        counter_file = _get_counter_file()
        data = {"non_rare_count": count}
        text = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path = str(counter_file) + ".tmp"
        # 先写临时文件
        await anyio.Path(tmp_path).write_text(text, encoding="utf-8")
        # os.replace 原子替换
        os.replace(tmp_path, counter_file)

    async def sample(self) -> tuple[int, str, bool]:
        """加权抽样 + 保底。

        返回 (non_rare_count, disease, pity_triggered)。
        - `non_rare_count`：本次抽样后的保底计数（0 表示刚抽到罕见病或刚触发保底）。
        - `pity_triggered`：本次是否触发罕见病保底。
        全档为空抛 RuntimeError。
        """
        if not self._loaded:
            await self.load()

        if not self.common and not self.uncommon and not self.rare:
            raise RuntimeError("DiseasePool 全档为空，无法抽样")

        async with self._counter_lock:
            count = await self._read_counter()

            # 保底：连续 >=30 次非罕见病 → 强制罕见病并清零
            if count >= _PITY_THRESHOLD and self.rare:
                disease = random.choice(self.rare)
                await self._write_counter(0)
                logger.info("⚠触发罕见病保底⚠，计数清零")
                return 0, disease, True

            # 加权抽样
            r = random.random()
            if r < _WEIGHT_COMMON and self.common:
                disease = random.choice(self.common)
                count += 1
            elif r < _WEIGHT_UNCOMMON and self.uncommon:
                disease = random.choice(self.uncommon)
                count += 1
            elif self.rare:
                disease = random.choice(self.rare)
                # 抽到罕见病也清零（保底语义：连续非罕见计数）
                count = 0
            elif self.common:
                # rare 为空时回退
                disease = random.choice(self.common)
                count += 1
            elif self.uncommon:
                disease = random.choice(self.uncommon)
                count += 1
            else:
                raise RuntimeError("DiseasePool 全档为空，无法抽样")

            await self._write_counter(count)
            logger.info(f"生成疾病：{disease}，更新后保底计数：{count}")
            return count, disease, False


# 全局单例
pool = DiseasePool()


@dataclass
class GameSession:
    """单群一局会话。"""

    group_id: int
    disease: str
    players: set[int] = field(default_factory=set)
    history: list[dict[str, str]] = field(default_factory=list)
    last_active: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def add_player(self, user_id: int) -> bool:
        """返回 True 表示新加入，False 表示已在玩家列表。"""
        if user_id in self.players:
            return False
        self.players.add(user_id)
        return True

    def is_player(self, user_id: int) -> bool:
        return user_id in self.players

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def is_expired(self, timeout: float) -> bool:
        return (time.monotonic() - self.last_active) > timeout

    def add_doctor_turn(self, msg: str) -> None:
        """追加医生（user）消息。"""
        self.history.append({"role": "user", "content": msg})

    def add_patient_turn(self, reply: str) -> None:
        """追加病人（assistant）消息。"""
        self.history.append({"role": "assistant", "content": reply})


class SessionManager:
    """多群会话管理 + 惰性 GC + 后台 GC。"""

    def __init__(self) -> None:
        self.sessions: dict[int, GameSession] = {}
        # 保护 dict 结构变更（start/end/get_or_none 触发的清理）
        self._lock = asyncio.Lock()

    async def get_or_none(self, group_id: int) -> GameSession | None:
        """惰性 GC：访问时检查过期，过期就地清除。"""
        async with self._lock:
            session = self.sessions.get(group_id)
            if session is None:
                return None
            if session.is_expired(plugin_config.gd_session_timeout_seconds):
                logger.info(f"群 {group_id} 会话超时，惰性清除")
                self.sessions.pop(group_id, None)
                return None
            return session

    async def is_active(self, group_id: int) -> bool:
        return await self.get_or_none(group_id) is not None

    async def start(self, group_id: int, disease: str, host_user_id: int) -> GameSession:
        """新开一局。若已有旧局会被覆盖（理论上调用方应先检查）。"""
        async with self._lock:
            session = GameSession(
                group_id=group_id,
                disease=disease,
                players={host_user_id},
            )
            self.sessions[group_id] = session
            return session

    async def end(self, group_id: int) -> GameSession | None:
        """结束并清除会话，返回被移除的会话（若有）。"""
        async with self._lock:
            return self.sessions.pop(group_id, None)

    async def gc_expired(self) -> list[GameSession]:
        """扫描所有超时会话并清除，返回被清除的会话列表。

        清除时尽力通过 nonebot.get_bot() 发送「已超时结束，答案是 X」；
        Bot 不在线静默清状态不抛错。
        """
        expired: list[GameSession] = []
        async with self._lock:
            timeout = plugin_config.gd_session_timeout_seconds
            for gid in list(self.sessions.keys()):
                session = self.sessions[gid]
                if session.is_expired(timeout):
                    expired.append(session)
                    del self.sessions[gid]

        if not expired:
            return expired

        # 尽力发送超时提示（不持 _lock，避免长 IO 阻塞 start/end）
        try:
            from nonebot import get_bot  # 延迟导入，避免循环依赖

            bot = get_bot()
        except Exception:
            bot = None  # Bot 不在线

        for session in expired:
            if bot is None:
                logger.info(
                    f"群 {session.group_id} 会话超时，Bot 离线，"
                    f"静默清除（答案：{session.disease}）"
                )
                continue
            try:
                await bot.send_group_msg(
                    group_id=session.group_id,
                    message=f"⏰ 已超时结束，答案是：{session.disease}",
                )
                logger.info(
                    f"群 {session.group_id} 会话超时，已发送提示（答案：{session.disease}）"
                )
            except Exception as e:
                logger.warning(
                    f"群 {session.group_id} 会话超时，发送提示失败：{e}，"
                    f"静默清除（答案：{session.disease}）"
                )

        return expired


# 全局单例
manager = SessionManager()


# 后台 GC 任务句柄
_gc_task: asyncio.Task[None] | None = None


async def _gc_loop() -> None:
    """后台 GC 循环：每 gd_gc_interval_seconds 秒扫一次。"""
    interval = plugin_config.gd_gc_interval_seconds
    logger.info(f"启动 GuessDisease 后台 GC，间隔 {interval}s")
    while True:
        try:
            await asyncio.sleep(interval)
            expired = await manager.gc_expired()
            if expired:
                logger.info(f"后台 GC 清理 {len(expired)} 个超时会话")
        except asyncio.CancelledError:
            logger.info("GuessDisease 后台 GC 任务已取消")
            raise
        except Exception as e:
            # GC 循环不可因单次异常退出
            logger.error(f"后台 GC 异常（继续运行）：{e}")


async def start_gc_task() -> None:
    """启动后台 GC 任务（由 driver.on_startup 调用）。"""
    global _gc_task
    if _gc_task is not None and not _gc_task.done():
        return
    _gc_task = asyncio.create_task(_gc_loop())


async def stop_gc_task() -> None:
    """取消后台 GC 任务（由 driver.on_shutdown 调用）。"""
    global _gc_task
    if _gc_task is None:
        return
    _gc_task.cancel()
    try:
        await _gc_task
    except asyncio.CancelledError:
        pass
    _gc_task = None


async def init_pool() -> dict[str, Any]:
    """加载词库（由 driver.on_startup 调用）。返回各档数量。"""
    await pool.load()
    return {
        "common": len(pool.common),
        "uncommon": len(pool.uncommon),
        "rare": len(pool.rare),
    }
