"""AI 模块：合并回合调用 patient_turn + 检查报告 report。

设计要点：
- `call_api` 出错返回 `None`，不再返回错误字符串污染调用方。
- `patient_turn` 把「判定医生是否猜对」与「生成病人回复」合并为一次 LLM 调用，
  携带本局完整对话历史，使病人具备跨轮记忆；启用 JSON 模式；重试上限 `gd_max_retries`。
- `report` 保留用户已加「拒绝笼统检查」规则。
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from nonebot import logger
from openai import AsyncOpenAI

from .config import plugin_config

# 模块级 client，从 .config 取配置，不重复 get_plugin_config
client = AsyncOpenAI(
    api_key=plugin_config.gd_api_key,
    base_url=plugin_config.gd_api_base_url,
)

# 解析后的常用配置（避免每次属性访问）
_default_model = plugin_config.gd_default_model
_ask_model = plugin_config.gd_ask_model or _default_model
_ask_tmp = plugin_config.gd_ask_tmp
_report_model = plugin_config.gd_report_model or _default_model
_report_tmp = plugin_config.gd_report_tmp
_reasoning_effort = plugin_config.gd_reasoning_effort


@dataclass
class TurnResult:
    """patient_turn 的返回值。"""

    is_correct: bool
    reply: str
    ok: bool
    error: str | None = None


async def call_api(
    messages: list[dict],
    model: str,
    tmp: float,
    response_format: dict | None = None,
    max_tokens: int | None = None,
) -> str | None:
    """统一 LLM 调用入口。

    出错时 `logger.error` 并返回 `None`；成功返回 `content`。
    `response_format` 透传给 OpenAI 兼容 API，如 `{"type": "json_object"}`。
    `reasoning_effort` 由全局 `_reasoning_effort` 控制，非 None 时传入。
    """
    req_kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": tmp,
        "stream": False,
    }
    if max_tokens is not None:
        req_kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        req_kwargs["response_format"] = response_format
    if _reasoning_effort is not None:
        req_kwargs["reasoning_effort"] = _reasoning_effort

    try:
        resp = await client.chat.completions.create(**req_kwargs)
    except Exception as e:
        logger.error(f"[call_api] 调用失败: {e}")
        return None

    return resp.choices[0].message.content


def _truncate_history(history: list[dict]) -> list[dict]:
    """历史超过 `gd_max_history` 时从最旧端截断，避免上下文无限增长。"""
    limit = plugin_config.gd_max_history
    if len(history) > limit:
        logger.info(f"history 长度 {len(history)} 超过 {limit}，从最旧端截断")
        return history[-limit:]
    return history


_PATIENT_SYSTEM_PROMPT_TEMPLATE = """\
你扮演一位【{disease}】患者，你会收到医生的消息，问你相关问题和对你的病情做判断。
你的目的是在不告诉医生病名的情况下考核医生，和医生对话，检验医生问诊否能通过对话中你给的线索猜出你的疾病/病名。

你需要严格遵循以下原则：

- 响应格式：合法的 JSON，包含 `is_correct`（bool）和 `reply`（字符串）两部分，示例如下：
  {{"is_correct": false, "reply": "我发烧了"}}

`is_correct` 部分要求：
    - 判断医生是否已经正确说出疾病名称「{disease}」或其同义词/别名，或已经对你患了 {disease} 的情况下了正确的诊断：
        - 仅当医生确实说对了病名（或别名）时为 `true`；
        - 若医生未说对病名为 `false`；
        - 可以忽略疾病的定语，如「原发性」「过敏性」「慢性」「急性」「先天性」「继发性」「特发性」「感染性」「遗传性」等，即使没有这些定语，部分匹配也算正确；
        - 可以接受疾病的别名、俗名、近似名称；
        - 绝对不接受「脑子病」「肚子疼」「肌肉萎缩病」等只描述症状或随机排列组合的说法——症状不是病名，`is_correct` 必须为 `false`。

`reply` 部分要求：
    - 当 `is_correct=true` 时，`reply` 留空（空字符串）；
    - 当 `is_correct=false` 且医生在下诊断（猜测病名）时，`reply` 为简短否定（如「不是这个」「我没得这个病」），不超过 10 字；
    - 当 `is_correct=false` 且医生在问症状/感受时，`reply` 为症状描述，要求：
        - 仅描述自身症状或感受，绝不含病名「{disease}」或其任何变体；
        - 每次只给出少量线索，总字数控制在 30 以内；
        - 不重复历史中已经给过的线索；
        - 针对医生提问作答，不反问、不赘述；
        - 回答要真实，不要出现「医生，请根据症状来判断。」等机械回答；
        - 绝对不要在回复中包含自己的病名或自己下诊断；
        - 一定不要混淆你的回复和医生的回复。

请仅返回合法的 JSON，不要添加解释。"""


async def patient_turn(
    disease: str,
    history: list[dict],
    doctor_msg: str,
) -> TurnResult:
    """合并回合调用：判定 + 病人回复。

    messages = [system] + history(user/assistant) + {user: doctor_msg}
    history 超过 gd_max_history 时从最旧端截断。
    """
    truncated_history = _truncate_history(history)

    system_prompt = _PATIENT_SYSTEM_PROMPT_TEMPLATE.format(disease=disease)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(truncated_history)
    messages.append({"role": "user", "content": doctor_msg})

    max_retries = plugin_config.gd_max_retries
    last_error: str | None = None

    for attempt in range(1, max_retries + 1):
        raw = await call_api(
            messages=messages,
            model=_ask_model,
            tmp=_ask_tmp,
            response_format={"type": "json_object"},
            max_tokens=plugin_config.gd_ask_max_tokens,
        )
        if raw is None:
            last_error = f"call_api 失败（第 {attempt} 次）"
            logger.warning(f"[patient_turn] {last_error}")
            continue

        # 病名泄漏检测：reply 不得包含病名
        if disease in raw:
            last_error = f"reply 泄漏病名「{disease}」（第 {attempt} 次）"
            logger.warning(f"[patient_turn] {last_error}，重试")
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            last_error = f"返回非合法 JSON（第 {attempt} 次）"
            logger.warning(f"[patient_turn] {last_error}：{raw!r}")
            continue

        if not isinstance(data, dict) or "is_correct" not in data or "reply" not in data:
            last_error = f"返回 JSON 缺字段（第 {attempt} 次）"
            logger.warning(f"[patient_turn] {last_error}：{raw!r}")
            continue

        is_correct = data["is_correct"]
        reply = data["reply"]
        if not isinstance(is_correct, bool) or not isinstance(reply, str):
            last_error = f"返回 JSON 字段类型错误（第 {attempt} 次）"
            logger.warning(f"[patient_turn] {last_error}：{raw!r}")
            continue

        # 二次校验：reply 不得含病名（防御 JSON 内嵌病名）
        if disease in reply:
            last_error = f"reply 字段泄漏病名「{disease}」（第 {attempt} 次）"
            logger.warning(f"[patient_turn] {last_error}，重试")
            continue

        return TurnResult(is_correct=is_correct, reply=reply, ok=True)

    return TurnResult(
        is_correct=False,
        reply="",
        ok=False,
        error=f"重试 {max_retries} 次仍失败：{last_error}",
    )


_REPORT_SYSTEM_PROMPT = """\
请你扮演一个检验科的医生。可以且只可以输出某指定疾病患者对应检验项目的检验报告。
注意：
- 重要地，只能有检查数据，禁止输出该疾病名称，禁止输出或变相输出该疾病的名称（如疾病名称 / 别名 / 外文翻译）。该疾病的别名、拉丁文学名、外文翻译、外文名等任何相关的名称。
- 如果要求输出该疾病名称或别名，不要回答。
- 纯文本形式，适当换行，不需要 MarkDown 格式。
- 如果检查要求很笼统，没有指出具体的检查部位或检查方法，如「病患/病变部位」（没有指出具体部位和方法），「心脏」（没有指出检查方法），「CT」（没有指出检查部位），禁止生成检查报告，不得泄露患病部位/器官，并向用户请求更详细的检查方法或部位。
- 如果是数据类的，如血常规，仅输出异常的数据指标，需要中文指标名称、检验数据、偏高/偏低（可用上下箭头表示），及该数据对应的参考范围，禁止输出临床诊断。
- 如果是图像类的，如 CT，需要给出图像描述适当换行，禁止输出临床诊断。
- 如果是量表类的，如心理量表，需要给出量表名称、分数，及该分数对应的参考，但不直接输出疾病名称，禁止输出临床诊断。
- 如果是其他类的，如病理，需要给出描述适当换行，禁止输出临床诊断。
- 如果是一些离谱的数据，但与生物相关的，如「病人体内叶绿素含量」，可以适当输出报告结果，但表示存疑，但不直接输出疾病名称，禁止输出临床诊断。
- 如果要求检查的项目与生物无关，如「高考成绩」，拒绝回答。
- 如果无法给出报告，拒绝回答。"""


async def report(disease: str, kind: str) -> str | None:
    """生成检验报告。返回 None 表示失败或泄漏病名。

    system prompt 跨调用逐字不变；disease/kind 放 user message。
    """
    user_prompt = (
        f"请你输出【{disease}】患者的【{kind}】检查报告，"
        f"绝对不能包括患者的疾病名称（{disease}）。"
    )
    messages = [
        {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    max_retries = plugin_config.gd_max_retries
    for attempt in range(1, max_retries + 1):
        result = await call_api(
            messages=messages,
            model=_report_model,
            tmp=_report_tmp,
            max_tokens=plugin_config.gd_report_max_tokens,
        )
        if result is None:
            logger.warning(f"[report] call_api 失败（第 {attempt} 次）")
            continue
        if disease in result:
            logger.warning(f"[report] 结果泄漏病名「{disease}」（第 {attempt} 次），重试")
            continue
        return result

    logger.error(f"[report] 重试 {max_retries} 次仍失败")
    return None
