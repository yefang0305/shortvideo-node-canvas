"""统一凭证文件读写、{cred:} 取值、旧 agent_settings 迁移、AgentSettings 兼容层。"""

from __future__ import annotations

import json
from pathlib import Path

from app.runtime import credentials as C


def test_default_skeleton_when_missing(tmp_path):
    data = C.load_credentials(tmp_path / "credentials.json", legacy_path=tmp_path / "none.json")
    assert "model" in data and "services" in data


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "credentials.json"
    C.save_credentials({"model": {"api_key": "k"}, "services": {"openrouter": {"api_key": "sk"}}}, p)
    data = C.load_credentials(p)
    assert data["services"]["openrouter"]["api_key"] == "sk"


def test_get_credential_value(tmp_path):
    p = tmp_path / "credentials.json"
    C.save_credentials({"model": {}, "services": {"openrouter": {"api_key": "sk-x"}}}, p)
    assert C.get_credential_value("openrouter.api_key", p) == "sk-x"
    assert C.get_credential_value("missing.api_key", p) == ""
    assert C.get_credential_value("openrouter.nope", p) == ""
    assert C.get_credential_value("noseparator", p) == ""


def test_migrates_legacy_agent_settings(tmp_path):
    legacy = tmp_path / "agent_settings.json"
    legacy.write_text(json.dumps({"api_base": "B", "api_key": "K", "model": "M"}), encoding="utf-8")
    data = C.load_credentials(tmp_path / "credentials.json", legacy_path=legacy)
    assert data["model"] == {"api_base": "B", "api_key": "K", "model": "M"}


def test_subst_token_resolves_cred(tmp_path):
    from app.runtime import tool_executor as T
    p = tmp_path / "credentials.json"
    C.save_credentials({"model": {}, "services": {"openrouter": {"api_key": "sk-9"}}}, p)
    orig = C.CREDENTIALS_PATH
    C.CREDENTIALS_PATH = p
    try:
        val, is_ph = T._subst_token("{cred:openrouter.api_key}", {}, "")
        assert (val, is_ph) == ("sk-9", True)
        env = T._resolve_env(
            {"OPENROUTER_API_KEY": "{cred:openrouter.api_key}", "X": "{cred:none.x}"}, {}
        )
        assert env == {"OPENROUTER_API_KEY": "sk-9"}
    finally:
        C.CREDENTIALS_PATH = orig


def test_load_agent_settings_reads_model_section(tmp_path):
    from app.agent import settings as S
    p = tmp_path / "credentials.json"
    C.save_credentials({"model": {"api_base": "B", "api_key": "K", "model": "M"}, "services": {}}, p)
    orig = C.CREDENTIALS_PATH
    C.CREDENTIALS_PATH = p
    try:
        s = S.load_agent_settings()
        assert (s.api_base, s.api_key, s.model) == ("B", "K", "M")
    finally:
        C.CREDENTIALS_PATH = orig
