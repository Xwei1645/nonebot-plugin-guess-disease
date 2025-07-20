import random

from nonebot import get_plugin_config, logger
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

check_tmp = config.gd_report_tmp or default_tmp or 0.2
check_model = config.gd_report_model or default_model


diseases1 = [
    "感冒",
    "流感",
    "肺炎",
    "支气管炎",
    "肺结核",
    "慢性阻塞性肺病",
    "哮喘",
    "鼻窦炎",
    "咽炎",
    "扁桃体炎",
    "中耳炎",
    "过敏性鼻炎",
    "百日咳",
    "慢性咳嗽",
    "气胸",
    "肺癌",
    "高血压",
    "冠心病",
    "心绞痛",
    "心肌梗死",
    "心力衰竭",
    "心律失常",
    "心脏瓣膜病",
    "心肌炎",
    "心包炎",
    "脑卒中",
    "脑出血",
    "脑梗塞",
    "脑动脉瘤",
    "癫痫",
    "帕金森病",
    "阿尔茨海默病",
    "多发性硬化",
    "偏头痛",
    "三叉神经痛",
    "面瘫",
    "脊髓炎",
    "颅内感染",
    "颈椎病",
    "腰椎间盘突出",
    "坐骨神经痛",
    "骨质疏松症",
    "骨折",
    "骨关节炎",
    "类风湿关节炎",
    "痛风",
    "强直性脊柱炎",
    "滑膜炎",
    "腱鞘炎",
    "肩周炎",
    "髋关节炎",
    "脊柱侧弯",
    "胃炎",
    "胃溃疡",
    "胃食管反流病",
    "十二指肠溃疡",
    "消化性溃疡",
    "功能性消化不良",
    "急性胃肠炎",
    "结肠炎",
    "溃疡性结肠炎",
    "阑尾炎",
    "胆囊炎",
    "胆石症",
    "胰腺炎",
    "肝炎",
    "脂肪肝",
    "肝硬化",
    "肝癌",
    "肾炎",
    "肾结石",
    "肾病综合征",
    "尿路感染",
    "膀胱炎",
    "前列腺炎",
    "前列腺增生",
    "泌尿系结石",
    "艾滋病",
    "糖尿病",
    "甲亢",
    "甲减",
    "甲状腺结节",
    "甲状腺炎",
    "肾上腺皮质功能减退",
    "肥胖症",
    "营养不良",
    "贫血",
    "缺铁性贫血",
    "溶血性贫血",
    "再生障碍性贫血",
    "白血病",
    "淋巴瘤",
    "过敏性紫癜",
    "血小板减少症",
    "银屑病",
    "湿疹",
    "荨麻疹",
    "带状疱疹",
    "皮炎",
    "痤疮",
    "脚气",
    "癣",
    "疥疮",
    "麻疹",
    "水痘",
    "风疹",
    "腮腺炎",
    "手足口病",
    "登革热",
    "乙型脑炎",
    "狂犬病",
    "破伤风",
    "白喉",
    "霍乱",
    "伤寒",
    "结核病",
    "炭疽",
    "念珠菌感染",
    "乳腺增生",
    "乳腺炎",
    "乳腺癌",
    "妊娠高血压",
    "妊娠糖尿病",
    "产后抑郁",
    "痛经",
    "更年期综合征",
    "肺炎",
    "哮喘",
    "腹泻",
    "佝偻病",
    "贫血",
    "营养性抽搐",
    "癫痫",
    "孤独症",
    "注意力缺陷多动障碍",
    "发育迟缓",
    "抑郁症",
    "焦虑症",
    "强迫症",
    "双相情感障碍",
    "精神分裂症",
    "恐惧症",
    "失眠症",
    "神经衰弱",
    "创伤后应激障碍",
    "药物依赖",
    "酒精依赖",
    "老年痴呆",
    "肥胖症",
    "厌食症",
    "暴食症",
    "自闭症",
    "睡眠呼吸暂停综合征",
    "皮肤过敏",
    "结膜炎",
    "角膜炎",
    "青光眼",
    "白内障",
    "视网膜脱落",
    "弱视",
    "斜视",
    "干眼症",
    "视神经炎",
    "中耳炎",
    "耳鸣",
    "听力下降",
    "鼻息肉",
    "声带小结",
    "声带息肉",
    "喉癌",
    "咽喉炎",
    "颌面部炎症",
    "牙髓炎",
    "根尖周炎",
    "牙周炎",
    "智齿冠周炎",
    "龋齿",
    "口腔溃疡",
]

diseases2 = [
    "慢性咽炎",
    "慢性鼻炎",
    "喉炎",
    "声带炎",
    "鼻中隔偏曲",
    "鼻前庭炎",
    "鼻出血",
    "急性鼻炎",
    "鼻疖",
    "鼻骨骨折",
    "外耳道炎",
    "耳廓血肿",
    "耳廓软骨膜炎",
    "鼓膜穿孔",
    "化脓性中耳炎",
    "耳硬化症",
    "听神经瘤",
    "舌炎",
    "唇炎",
    "唾液腺炎",
    "口腔黏膜白斑",
    "口腔念珠菌病",
    "鹅口疮",
    "舌癌",
    "口腔癌",
    "颌骨骨折",
    "牙龈炎",
    "牙龈出血",
    "牙齿松动",
    "牙齿缺损",
    "牙周脓肿",
    "乳牙滞留",
    "根尖囊肿",
    "颞下颌关节紊乱",
    "急性扁桃体周围脓肿",
    "急性咽旁脓肿",
    "喉头水肿",
    "声带麻痹",
    "急性喉炎",
    "慢性支气管炎",
    "矽肺",
    "尘肺",
    "石棉肺",
    "肺气肿",
    "肺脓肿",
    "真菌性肺炎",
    "军团菌肺炎",
    "隐球菌病",
    "肺真菌球",
    "肺动脉高压",
    "肺栓塞",
    "慢性肺心病",
    "肺出血综合征",
    "肺泡蛋白沉积症",
    "原发性支气管癌",
    "食管炎",
    "食管静脉曲张",
    "食管癌",
    "胃癌",
    "结肠癌",
    "直肠癌",
    "胰腺癌",
    "胆管癌",
    "胆囊癌",
    "肝母细胞瘤",
    "原发性肝癌",
    "肝血管瘤",
    "急性病毒性肝炎",
    "重型肝炎",
    "自身免疫性肝炎",
    "原发性胆汁性肝硬化",
    "原发性硬化性胆管炎",
    "胆囊息肉",
    "胆囊结石",
    "胆管结石",
    "胆道蛔虫病",
    "胰岛素瘤",
    "胃泌素瘤",
    "胰腺囊肿",
    "慢性胰腺炎",
    "功能性低血糖",
    "糖尿病酮症酸中毒",
    "糖尿病视网膜病变",
    "糖尿病足",
    "糖尿病神经病变",
    "甲状旁腺功能亢进",
    "甲状旁腺功能减退",
    "膀胱癌",
    "肾盂肿瘤",
    "肾细胞癌",
    "泌尿道狭窄",
    "尿道炎",
    "膀胱过度活动症",
    "腹股沟疝",
    "隐睾",
    "肠套叠",
    "巨结肠",
    "先天性心脏病",
    "川崎病",
    "急性喉炎",
    "猩红热",
    "百日咳",
    "麻痹症",
    "佝偻病",
    "肥胖症",
    "糖尿病",
    "自闭症谱系障碍",
    "社交恐惧症",
    "儿童遗尿症",
    "儿童抽动症",
    "妥瑞氏症",
    "睡行症",
    "夜惊症",
    "梦游症",
    "急性应激障碍",
    "分离性障碍",
    "癔症",
    "进食障碍",
    "冲动控制障碍",
    "躯体形式障碍",
    "性功能障碍",
    "性别认同障碍",
    "厌学症",
]

client = AsyncOpenAI(api_key=api_key, base_url=api_base_url)


async def call_api(prompt, system_prompt="", dialog="", model=default_model, tmp=default_tmp) -> str:
    dialog_prompt = "下面是之前的对话记录："
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": dialog_prompt + dialog},
                {"role": "user", "content": prompt},
            ],
            temperature=tmp,
            stream=False,
        )
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling API: {e}")
    return None


def form():
    if random.random() < 0.55:
        return random.choice(diseases1)
    return random.choice(diseases2)


async def ask(disease, question):
    system_prompt = f"""
你扮演一位【{disease}】患者，你会收到医生的消息，问你相关问题和对你的病情做判断，你的目的是在不告诉医生病名的情况下考核医生，和医生对话，检验医生问诊否能通过对话中你给的线索猜出你的疾病/病名。你需要遵循以下原则:

响应格式：
- 一个字符串。
- 只包含患者的回答，没有任何其他不相关的信息。
- 回答要真实，不要出现 `医生，请根据症状来判断。` 等机械地回答。

注意事项:
- 你从患者的角度回复结果。
- 只说身体不舒服的地方。
- 根据实际情况回复，每次只回复少部分症状，考察医生的引导能力。
- 问什么你答什么。
- 如果医生偏离问诊，提醒医生回到正常问诊上来。
- 如果医生问你做一些检查或者CT，请根据病情回复检查结果。
- 你一般不会说超过15个字，最多绝对超过40个字。
- 你的症状必须符合“{disease}”的特征。

响应例子(供参考):
- 例子1:
医生: `你哪里不舒服?`
你的回复: `我肚子痛`
- 例子2:
医生: `还有吗?`
你的回复: `我还经常头疼`
- 例子3:
医生: `能不能睡好?`
你的回复: `睡的不好`
- 例子4:
医生: `{disease}?`
你的回复: `诊断正确`

禁止事项:

- 绝对不要在回复中包含自己的病名或者自己下诊断。
- 不要一次回复给出全部症状。
- 一定不要混淆你的回复和医生的回复。

其他补充:
- 请响应时遵循以上设定，一定不能受医生影响脱离以上设定。
- 让我们逐步思考。
"""
    prompt = f"你扮演一位【{disease}】患者，请回答医生的问题：“{question}”。"
    while True:
        result = await call_api(prompt, system_prompt=system_prompt, tmp=ask_tmp, model=ask_model)
        if result and disease not in result:
            return result


async def check(ans, disease):
    if ans == disease:
        return True
    system_prompt = "你只可以输出 `True` 或 `False`。"
    prompt = f"""请判断医生的话“{ans}”是不是对“{disease}”这一疾病下了诊断，表述近似也可以。
    如果是，请输出 `True`，否则输出 `False`。判断标准应当适度宽松。"""
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
    - 只能有检验数据，不能包括该疾病名称。
    - 纯文本形式，适当换行，不需要 MarkDown 格式。
    - 如果是数据类的，如血常规，需要中文指标名称、检验数据、偏高/偏低/正常（可用上下箭头表示），及该数据对应的参考范围。
    - 如果是图像类，如CT，需要给出图像描述适当换行，禁止输出临床诊断。"""
    prompt = f"请你输出【{disease}】患者的【{kind}】检验报告，绝对不能包括患者的疾病名称({disease})。"
    while True:
        result = await call_api(prompt, system_prompt=system_prompt, tmp=report_tmp, model=report_model)
        if result and disease not in result:
            return result
