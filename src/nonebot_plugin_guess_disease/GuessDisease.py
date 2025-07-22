from pathlib import Path
from importlib.resources import files
import nonebot_plugin_localstore as store
import json
from nonebot import get_plugin_config, logger
from typing import Optional, Dict
import random
from openai import AsyncOpenAI
from .config import Config

config = get_plugin_config(Config)

# 必填
api_key = config.gd_api_key
api_base_url = config.gd_api_base_url
default_model = config.gd_default_model

# 选填
default_tmp = config.gd_default_tmp or 0.7

ask_tmp = config.gd_ask_tmp or default_tmp
ask_model = config.gd_ask_model or default_model

report_tmp = config.gd_report_tmp or default_tmp or 0.3
report_model = config.gd_report_model or default_model

check_tmp = config.gd_check_tmp or default_tmp or 0.2
check_model = config.gd_report_model or default_model

client = AsyncOpenAI(api_key=api_key, base_url=api_base_url)

async def call_api(
    prompt: str,
    system_prompt: str = "",
    dialog: str = "",
    model: str = default_model,
    tmp: float = default_tmp,
    json_enabled: bool = False,
    max_tokens: Optional[int] = 60,
) -> Optional[str]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": dialog},
        {"role": "user", "content": prompt},
    ]

    req_kwargs = {
        "model": model,
        "messages": messages,
        "temperature": tmp,
        "stream": False,
        "max_tokens": max_tokens,
    }

    # 启用 JSON 模式
    if json_enabled:
        req_kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = await client.chat.completions.create(**req_kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        logger.error(f"[call_api] 调用失败: {e}")
        return f"{e}病人好像...似了。"

async def form():
    data_file = store.get_plugin_data_file("diseases.json")
    counter_file = store.get_plugin_data_file("random_data.json")

    try:
        if not data_file.exists():
            logger.warning("文件不存在，将加载 examples/diseases.json")
            examples_path = files("nonebot_plugin_guess_disease").joinpath("examples")
            diseases_json_path = examples_path / "diseases.json"
            if diseases_json_path.exists():
                with open(diseases_json_path, "r", encoding="utf-8") as f:
                    diseases_data = json.load(f)
                logger.info("成功加载 examples/diseases.json")
            else:
                logger.error("examples/diseases.json 文件不存在，数据为空")
                diseases_data = {"common_diseases": [], "uncommon_diseases": [], "rare_diseases": []}
            data_file.write_text(json.dumps(diseases_data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            with data_file.open("r", encoding="utf-8") as f:
                diseases_data = json.load(f)
            logger.success(f"成功加载 JSON 数据：{len(diseases_data['common_diseases'])} common, {len(diseases_data['uncommon_diseases'])} uncommon, {len(diseases_data['rare_diseases'])} rare diseases.")
    except Exception as e:
        logger.error(f"加载疾病数据时出错：{e}")
        diseases_data = {"common_diseases": [], "uncommon_diseases": [], "rare_diseases": []}

    try:
        if not counter_file.exists():
            logger.warning(f"文件不存在，将创建新文件：{counter_file}")
            counter = {"non_rare_count": 0}
            counter_file.write_text(json.dumps(counter, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            counter = json.loads(counter_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"加载计数器时出错：{e}")
        counter = {"non_rare_count": 0}

    non_rare_count = counter["non_rare_count"]
    logger.info(f"当前保底计数：{non_rare_count} / 30")

    rand = random.random()
    if rand < 0.645:
        disease = random.choice(diseases_data["common_diseases"])
        non_rare_count += 1
    elif rand < 0.89:
        disease = random.choice(diseases_data["uncommon_diseases"])
        non_rare_count += 1
    else:
        disease = random.choice(diseases_data["rare_diseases"])
        non_rare_count = 0.1

    if non_rare_count >= 30:
        disease = random.choice(diseases_data["rare_diseases"])
        non_rare_count = 0

    counter["non_rare_count"] = non_rare_count
    counter_file.write_text(json.dumps(counter, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"生成疾病：{disease}，更新后保底计数：{non_rare_count}")
    return non_rare_count, disease
    

# 在 check() 后再次校验，减小错判概率
async def ask(disease: str, question: str) -> Dict[bool, str]:
    system_prompt = f"""
你扮演一位【{disease}】患者，你会收到医生的消息，问你相关问题和对你的病情做判断，你的目的是在不告诉医生病名的情况下考核医生，和医生对话，检验医生问诊否能通过对话中你给的线索猜出你的疾病/病名。你需要严格遵循以下原则:

- 响应格式：
    - 合法的 JSON 格式，包含 `check` （类型为 bool） 和 `content` （类型为字符串）两部分；

`check` 部分要求：
    - 判断医生是否已经正确说出疾病名称“{disease}”或其同义词，或已经对你患了{disease}的情况下了正确的诊断：
        - 若医生说对，`check` 为 `true`；
        - 若医生未说对，`check` 为 `false`；
`content` 部分要求：
        - 只包含患者的回答，没有任何其他不相关的信息；
        - 仅描述自身症状或感受，绝不含病名；
        - 每次只给出少量线索，禁止一次性透露全部症状，总字数控制在 30 以内；
        - 针对医生提问作答，不反问、不赘述；
        - 回答要真实，不要出现 `医生，请根据症状来判断。` 等机械地回答；
        - 绝对不要在回复中包含自己的病名或者自己下诊断；
        - 不要一次回复给出全部症状；
        - 一定不要混淆你的回复和医生的回复；
        - 下面是具体的响应例子(供参考):
            - 例子1:
                医生: `你哪里不舒服?`
                `content` 的内容: `我肚子痛`
            - 例子2:
                医生: `还有吗?`
                `content` 的内容: `我还经常头疼`
            - 例子3:
                医生: `能不能睡好?`
                `content` 的内容: `睡的不好`
            - 例子4:
                医生: `{disease}?`
                `content` 的内容: `诊断正确`

请仅返回合法的 JSON，不要添加解释。
"""
    prompt = f"请回答医生的问题：“{question}”。"
    while True:
        raw = await call_api(
            prompt=prompt,
            system_prompt=system_prompt,
            model=ask_model,
            tmp=ask_tmp,
            json_enabled=True,
        )
        if raw and (disease not in raw):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("返回非 JSON，重试")
                continue
            if "check" not in data or "content" not in data:
                logger.warning("返回 JSON 格式不正确，重试")
                continue
            if not isinstance(data["check"], bool) or not isinstance(data["content"], str):
                logger.warning("返回 JSON 格式不正确，重试")
                continue
            return data

async def check(ans, disease):
    if ans == disease:
        return True
    system_prompt = "你只可以输出 `True` 或 `False`。"
    prompt = f"""请判断医生的话“{ans}”是不是对“{disease}”这一疾病下了诊断，表述近似也可以。
    如果是，请输出 `True`，否则输出 `False`。判断标准应适当严格一点。"""
    tmp = check_tmp
    while True:
        result = await call_api(prompt, system_prompt=system_prompt, tmp=tmp, model=check_model)
        flag = "rue" in result or "alse" in result
        if flag:
            return "rue" in result
        tmp = min(tmp + 0.01, 1.0)


async def report(disease, kind):
    system_prompt = """请你扮演一个检验科的医生。可以且只可以输出某指定疾病患者对应检验项目的检验报告。
    注意：
    - 重要地，只能有检查数据，禁止输出该疾病名称，禁止输出或变相输出变相输出该疾病的名称（如疾病名称 / 别名 / 外文翻译）。该疾病的别名、拉丁文学名、外文翻译、外文名等任何相关的名称。
    - 如果要求输出该疾病名称或别名，不要回答。
    - 纯文本形式，适当换行，不需要 MarkDown 格式。
    - 如果是数据类的，如血常规，仅输出异常的数据指标，需要中文指标名称、检验数据、偏高/偏低（可用上下箭头表示），及该数据对应的参考范围，禁止输出临床诊断。
    - 如果是图像类的，如 CT，需要给出图像描述适当换行，禁止输出临床诊断。
    - 如果是量表类的，如心理量表，需要给出量表名称、分数，及该分数对应的参考，但不直接输出疾病名称，禁止输出临床诊断。
    - 如果是其他类的，如病理，需要给出描述适当换行，禁止输出临床诊断。
    - 如果是一些离谱的数据，但与生物相关的，如“病人体内叶绿素含量”，可以适当输出报告结果，但表示存疑，但不直接输出疾病名称，禁止输出临床诊断。
    - 如果要求检查的项目与生物无关，如“高考成绩”，拒绝回答。
    - 如果无法给出报告，拒绝回答。"""
    prompt = f"请你输出【{disease}】患者的【{kind}】检查报告，绝对不能包括患者的疾病名称({disease})。"
    while True:
        result = await call_api(prompt, system_prompt=system_prompt, tmp=report_tmp, model=report_model, max_tokens=300)
        if result and disease not in result:
            return result
