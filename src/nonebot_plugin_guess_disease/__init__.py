from nonebot import get_plugin_config, on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.plugin import PluginMetadata

from .config import Config
from .GuessDisease import ask, check, form, report

__plugin_meta__ = PluginMetadata(
    name="猜猜病",
    description="你能通过对话猜出病人得了什么病吗？",
    usage="""cmd: 猜猜病/猜病 -> 开始/加入游戏
    cmd: 【具体问题】（仅限玩家） -> 向病人提问
    cmd: 检查+具体检查项目（仅限玩家） -> 检查指定项目
    cmd: 结束（仅限玩家） -> 提供答案并结束游戏""",
    homepage="https://github.com/Xwei1645/nonebot-plugin-guess-disease",
    config=Config,
    supported_adapters={"~onebot.v11"},
    type="application",
)

config = get_plugin_config(Config)
allowed_groups = config.gd_allowed_groups or {}  # 不填则都允许

# 游戏状态
starting: dict[int, bool] = {}
players: dict[int, set[int]] = {}
current_disease: dict[int, str] = {}

start = on_command("猜猜病", aliases={"猜病", "ccb", "cb"}, priority=5, block=True)


@start.handle()
async def start_handler(event: Event):
    group_id = event.group_id
    user_id = event.user_id
    if allowed_groups:
        if group_id not in allowed_groups:
            return
    # 该群已有游戏进行中
    if starting.get(group_id, False):
        if user_id in players.setdefault(group_id, set()):
            await start.send("你已加入游戏了。", at_sender=True)
        else:
            players[group_id].add(user_id)
            await start.send("已加入游戏，快来 CaiCaiBing!!", at_sender=True)
    else:
        # 新开一局
        current_disease[group_id] = form()
        players[group_id] = {user_id}
        starting[group_id] = True
        await start.send("你好，医生。", at_sender=True)


asking = on_message(priority=15, block=True)


@asking.handle()
async def asking_handler(bot: Bot, event: Event):
    msg = event.get_plaintext()
    group_id = event.group_id
    user_id = event.user_id

    # 若该群未开局或用户不在玩家列表
    if not starting.get(group_id, False) or user_id not in players.get(group_id, set()):
        return

    # 猜对
    if await check(msg, current_disease[group_id]):
        await asking.send(f"猜对了，标准答案是：{current_disease[group_id]}。", at_sender=True)
        # 清理
        starting.pop(group_id, None)
        players.pop(group_id, None)
        current_disease.pop(group_id, None)
        return

    # 正常提问
    try:
        answer = await ask(current_disease[group_id], msg)
        await asking.send(Message(f"[CQ:reply,id={event.message_id}]{answer}"))
    except KeyError:
        await asking.send(
            Message(f"[CQ:reply,id={event.message_id}]KeyError\n可能是由于游戏已结束或......病人已经死了。")
        )
    except Exception as e:
        await asking.send(Message(f"[CQ:reply,id={event.message_id}]病人死了。\n{e}"))


ans = on_command("结束", priority=2, block=True)


@ans.handle()
async def ans_handler(event: Event):
    group_id = event.group_id
    user_id = event.user_id

    if starting.get(group_id, False) and user_id in players.get(group_id, set()):
        await ans.send(f"已结束。答案是：{current_disease[group_id]}。")
        # 清理
        starting.pop(group_id, None)
        players.pop(group_id, None)
        current_disease.pop(group_id, None)


reporting = on_command("检查", priority=12, block=True)


@reporting.handle()
async def reporting_handler(event: Event, bot: Bot):
    group_id = event.group_id
    user_id = event.user_id
    kind = str(event.get_message()).strip().lstrip("检查")

    if starting.get(group_id, False) and user_id in players.get(group_id, set()):
        initial_msg = await reporting.send(
            Message(f"[CQ:reply,id={event.message_id}]已收到检查请求，检查即将开始，这可能需要 11-45 秒，请坐和放宽...")
        )
        result = await report(current_disease[group_id], kind)
        if starting.get(group_id, False):
            await reporting.send(Message(f"[CQ:reply,id={event.message_id}]{result}"))
        else:
            await reporting.send(Message(f"[CQ:reply,id={event.message_id}]{result}\n\n但是......病人好像已经死了。"))
        await bot.delete_msg(group_id=group_id, message_id=initial_msg["message_id"])
