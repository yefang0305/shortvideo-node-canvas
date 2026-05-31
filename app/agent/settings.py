from __future__ import annotations

from dataclasses import dataclass

from app.runtime.credentials import load_credentials, save_credentials


@dataclass
class AgentSettings:
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"


def load_agent_settings() -> AgentSettings:
    """模型 API 配置现统一存于 config/credentials.json 的 model 段。"""
    model = load_credentials().get("model", {})
    return AgentSettings(
        api_base=(model.get("api_base") or AgentSettings.api_base),
        api_key=(model.get("api_key") or ""),
        model=(model.get("model") or AgentSettings.model),
    )


def save_agent_settings(settings: AgentSettings) -> None:
    data = load_credentials()
    data["model"] = {
        "api_base": settings.api_base,
        "api_key": settings.api_key,
        "model": settings.model,
    }
    save_credentials(data)
