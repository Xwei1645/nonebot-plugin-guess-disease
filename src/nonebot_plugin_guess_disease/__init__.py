from nonebot import get_driver, logger, on_command, on_fullmatch, on_message, require
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

require("nonebot_plugin_localstore")

from .config import Config, is_group_allowed
from .game import init_pool, manager, pool, start_gc_task, stop_gc_task
from .GuessDisease import patient_turn, report

__plugin_meta__ = PluginMetadata(
    name="猜猜病",
    description="你能通过对话猜出病人得了什么病吗？",
    usage="""cmd: 猜猜病/猜病/ccb -> 开始/加入游戏
    cmd: 【具体问题】（仅限玩家） -> 向病人提问
    cmd: 检查 + 具体检查项目（仅限玩家） -> 检查指定项目并输出报告
    cmd: 答案（仅 SUPERUSER） -> 在终端输出答案
    cmd: 结束（仅限玩家） -> 提供答案并结束游戏""",
    homepage="https://github.com/Xwei1645/nonebot-plugin-guess-disease",
    config=Config,
    supported_adapters={"~onebot.v11"},
    type="application",
)

driver = get_driver()


@driver.on_startup
async def _on_startup() -> None:
    counts = await init_pool()
    logger.info(
        f"GuessDisease 词库已加载：common={counts['common']} "
        f"uncommon={counts['uncommon']} rare={counts['rare']}"
    )
    await start_gc_task()


@driver.on_shutdown
async def _on_shutdown() -> None:
    await stop_gc_task()


# ---------- Rule ----------


def _is_group_msg() -> Rule:
    """仅群聊且该群被允许。"""

    async def _rule(event: MessageEvent) -> bool:
        if not isinstance(event, GroupMessageEvent):
            return False
        return is_group_allowed(event.group_id)

    return Rule(_rule)


async def _in_active_game_as_player(event: MessageEvent) -> bool:
    """该群有活跃局 + 发送者是玩家才匹配。

    惰性 GC 在 get_or_none 内执行。
    """
    if not isinstance(event, GroupMessageEvent):
        return False
    if not is_group_allowed(event.group_id):
        return False
    session = await manager.get_or_none(event.group_id)
    if session is None:
        return False
    return session.is_player(event.user_id)


in_active_game_as_player = Rule(_in_active_game_as_player)


# ---------- Handlers ----------


start = on_command(
    "猜猜病",
    aliases={"猜病", "ccb"},
    rule=_is_group_msg(),
    priority=5,
    block=True,
)


@start.handle()
async def start_handler(event: GroupMessageEvent) -> None:
    group_id = event.group_id
    user_id = event.user_id

    session = await manager.get_or_none(group_id)
    if session is not None:
        # 该群已有游戏进行中：加入
        if session.is_player(user_id):
            await start.send("你已加入游戏了。", at_sender=True)
        else:
            session.add_player(user_id)
            await start.send("已加入游戏，快来 CaiCaiBing!!", at_sender=True)
        return

    # 新开一局
    try:
        non_rare_count, disease, pity_triggered = await pool.sample()
    except RuntimeError as e:
        await start.send(f"开局失败：{e}", at_sender=True)
        return

    await manager.start(group_id, disease, user_id)
    await start.send("你好，医生。", at_sender=True)

    # 保底提示
    if pity_triggered:
        await start.send("⚠触发罕见病保底⚠")
    elif non_rare_count >= 10:
        await start.send(f"罕见病保底计数 {non_rare_count} / 30")


asking = on_message(rule=in_active_game_as_player, priority=15, block=False)


@asking.handle()
async def asking_handler(event: GroupMessageEvent) -> None:
    group_id = event.group_id
    msg = event.get_plaintext()

    session = await manager.get_or_none(group_id)
    if session is None or not session.is_player(event.user_id):
        return

    # 同群串行化：锁内完成 touch + AI 调用 + history 追加
    async with session.lock:
        session.touch()
        result = await patient_turn(session.disease, session.history, msg)

        if not result.ok:
            logger.error(f"群 {group_id} patient_turn 失败：{result.error}")
            await asking.send(
                MessageSegment.reply(event.message_id)
                + "病人暂时无法回答，请稍后再试。",
                at_sender=True,
            )
            return

        # 追加历史（先 doctor 后 patient，单调追加）
        session.add_doctor_turn(msg)
        session.add_patient_turn(result.reply)

        if result.is_correct:
            await asking.send(
                MessageSegment.reply(event.message_id)
                + f"猜对了，标准答案是：{session.disease}。",
                at_sender=True,
            )
            await manager.end(group_id)
            return

        await asking.send(MessageSegment.reply(event.message_id) + result.reply)


reporting = on_command("检查", rule=_is_group_msg(), priority=12, block=True)


@reporting.handle()
async def reporting_handler(
    event: GroupMessageEvent, bot: Bot, args: Message = CommandArg()
) -> None:
    group_id = event.group_id
    user_id = event.user_id
    kind = args.extract_plain_text().strip()

    session = await manager.get_or_none(group_id)
    if session is None or not session.is_player(user_id):
        return

    if not kind:
        await reporting.send(
            MessageSegment.reply(event.message_id)
            + "请提供检查项目，例如：检查 血常规",
        )
        return

    initial_msg = await reporting.send(
        MessageSegment.reply(event.message_id)
        + "已收到检查请求，检查即将开始，这可能需要 11-45 秒，请坐和放宽...",
    )

    async with session.lock:
        session.touch()
        result = await report(session.disease, kind)

    # 长调用后二次检查活跃
    still_active = await manager.is_active(group_id)

    if result is None:
        await reporting.send(MessageSegment.reply(event.message_id) + "检查失败。")
    elif still_active:
        await reporting.send(MessageSegment.reply(event.message_id) + result)
    else:
        await reporting.send(
            MessageSegment.reply(event.message_id) + f"{result}\n\n但是......病人好像已经似了。"
        )

    # 撤回初始提示，try/except 容错
    try:
        await bot.delete_msg(message_id=initial_msg["message_id"])
    except Exception as e:
        logger.warning(f"撤回检查初始提示失败：{e}")


end = on_fullmatch("结束", rule=_is_group_msg(), priority=2, block=True)


@end.handle()
async def end_handler(event: GroupMessageEvent) -> None:
    group_id = event.group_id
    user_id = event.user_id

    session = await manager.get_or_none(group_id)
    if session is None or not session.is_player(user_id):
        return

    await end.send(f"已结束。答案是：{session.disease}。")
    await manager.end(group_id)


cheat = on_command(
    "答案",
    rule=_is_group_msg(),
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@cheat.handle()
async def cheat_handler(event: GroupMessageEvent) -> None:
    group_id = event.group_id

    session = await manager.get_or_none(group_id)
    if session is None:
        return

    logger.info(f"群聊 {group_id} 的答案是【{session.disease}】")
    await cheat.send("已输出到终端", at_sender=True)
