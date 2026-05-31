"""统一凭证配置：模型 API + 各服务商密钥集中一处，节点按名引用。

设计见 docs/superpowers/specs/2026-05-31-移除内置总控与统一凭证-design.md。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
LEGACY_AGENT_SETTINGS = CONFIG_DIR / "agent_settings.json"


def _default() -> dict[str, Any]:
    return {"model": {"api_base": "", "api_key": "", "model": ""}, "services": {}}


def load_credentials(path: Path | None = None, legacy_path: Path | None = None) -> dict[str, Any]:
    """读取凭证文件；不存在时返回默认骨架，并尝试迁移旧 agent_settings.json。

    path 默认在调用时解析为模块全局 CREDENTIALS_PATH（便于测试/运行时改写路径）。
    """
    path = path or CREDENTIALS_PATH
    legacy_path = legacy_path if legacy_path is not None else LEGACY_AGENT_SETTINGS
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = _default()
        if legacy_path and legacy_path.exists():
            try:
                legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
                data["model"] = {
                    "api_base": legacy.get("api_base", ""),
                    "api_key": legacy.get("api_key", ""),
                    "model": legacy.get("model", ""),
                }
            except (json.JSONDecodeError, OSError):
                pass
    data.setdefault("model", {})
    data.setdefault("services", {})
    return data


def save_credentials(data: dict[str, Any], path: Path = CREDENTIALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_service(name: str, path: Path | None = None) -> dict[str, Any]:
    return dict(load_credentials(path).get("services", {}).get(name, {}))


def get_credential_value(ref: str, path: Path | None = None) -> str:
    """ref 形如 'openrouter.api_key'。服务/字段缺失返回空串。"""
    if "." not in ref:
        return ""
    name, field = ref.split(".", 1)
    return str(get_service(name, path).get(field, "") or "")
