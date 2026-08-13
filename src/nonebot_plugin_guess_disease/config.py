from nonebot import get_plugin_config, require
from pydantic import BaseModel, Field

require("nonebot_plugin_localstore")


class Config(BaseModel):
    model_config = {"extra": "ignore"}

    # 必填
    gd_api_key: str = Field(...)
    gd_api_base_url: str = Field(...)
    gd_default_model: str = Field(...)

    # 模型 / 温度（默认值直接给定，不级联 gd_default_tmp，避免死代码）
    gd_default_tmp: float = 0.7
    gd_ask_tmp: float = 0.7
    gd_ask_model: str | None = None
    gd_report_tmp: float = 0.3
    gd_report_model: str | None = None
    gd_reasoning_effort: str | None = None

    # 行为参数
    gd_allowed_groups: set[int] = Field(default_factory=set)
    gd_session_timeout_seconds: int = 1800
    gd_max_history: int = 60
    gd_max_retries: int = 3
    gd_ask_max_tokens: int = 200
    gd_report_max_tokens: int = 400
    gd_gc_interval_seconds: int = 300


plugin_config = get_plugin_config(Config)


def is_group_allowed(group_id: int | None) -> bool:
    """检查群是否被允许使用本插件。

    None（私聊/未知）→ False；空集合 → 全允许；否则成员判定。
    """
    if group_id is None:
        return False
    allowed = plugin_config.gd_allowed_groups
    if not allowed:
        return True
    return group_id in allowed
