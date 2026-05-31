"""阶段 4 script 模式：脚本型 Skill 节点的参数/运行时/输入收敛逻辑（不实际跑脚本）。"""

from __future__ import annotations

from pathlib import Path

from app.runtime.tool_executor import (
    _materialize_input,
    _resolve_env,
    _resolve_runtime,
    _resolve_script_args,
    _subst_token,
    _try_parse_json,
)


def test_subst_input_and_param():
    assert _subst_token("{input}", {}, "a.md") == ("a.md", True)
    assert _subst_token("{param:作者}", {"作者": "天乙"}, "") == ("天乙", True)
    assert _subst_token("--file", {}, "") == ("--file", False)


def test_empty_optional_arg_drops_its_flag():
    templates = ["--file", "{input}", "--cover", "{param:封面}", "--author", "{param:作者}"]
    argv = _resolve_script_args(templates, {"封面": "", "作者": "天乙"}, "a.md")
    assert argv == ["--file", "a.md", "--author", "天乙"]


def test_filled_optional_arg_is_kept():
    templates = ["--cover", "{param:封面}"]
    argv = _resolve_script_args(templates, {"封面": "c.jpg"}, "a.md")
    assert argv == ["--cover", "c.jpg"]


def test_runtime_explicit_wins():
    assert _resolve_runtime(["py", "-3.13"], Path("x.py")) == ["py", "-3.13"]
    assert _resolve_runtime("node", Path("x.js")) == ["node"]


def test_runtime_infers_python_for_py():
    rt = _resolve_runtime(None, Path("scripts/x.py"))
    assert rt and ("python" in rt[0].lower() or rt[0] == "py")


def test_materialize_existing_file_is_reused(tmp_path):
    f = tmp_path / "real.md"
    f.write_text("hi", encoding="utf-8")
    assert _materialize_input([str(f)], tmp_path) == str(f)


def test_materialize_text_writes_tempfile(tmp_path):
    out = _materialize_input(["纯文本内容"], tmp_path)
    p = Path(out)
    assert p.exists() and p.read_text(encoding="utf-8") == "纯文本内容"


def test_try_parse_json_from_last_line():
    assert _try_parse_json('日志行\n{"items": ["x"], "ok": true}') == {"items": ["x"], "ok": True}
    assert _try_parse_json("不是 json") is None


def test_output_placeholder_resolves():
    assert _subst_token("{output}", {}, "in.md", "out.png") == ("out.png", True)
    argv = _resolve_script_args(["--image", "{output}"], {}, "in.md", "out.png")
    assert argv == ["--image", "out.png"]


def test_env_resolves_only_nonempty():
    env_map = {"OPENROUTER_API_KEY": "{param:OR_KEY}", "OPENAI_API_KEY": "{param:OA_KEY}"}
    env = _resolve_env(env_map, {"OR_KEY": "sk-xxx", "OA_KEY": ""})
    assert env == {"OPENROUTER_API_KEY": "sk-xxx"}


def test_image_gen_node_is_registered():
    """文生图节点应已入库，绑定 image-gen 脚本、带 {output} 与 env 映射。"""
    from app.models import load_node_specs

    node = {s.type: s for s in load_node_specs()}.get("skill_baoyu_image_gen")
    assert node is not None
    b = node.skill_binding
    assert b["mode"] == "script" and b["script"].endswith("main.ts")
    assert any("{output}" in a for a in b["args"])
    assert "--model" in b["args"]
    assert "--size" in b["args"]
    assert "--imageSize" in b["args"]
    # 密钥改为按名引用统一凭证文件，不再裸放在节点参数里
    assert b["env"]["OPENROUTER_API_KEY"] == "{cred:openrouter.api_key}"
    assert b["env"]["GOOGLE_API_KEY"] == "{cred:google.api_key}"
    assert b["env"]["JIMENG_ACCESS_KEY_ID"] == "{cred:jimeng.access_key_id}"
    assert b["env"]["ARK_API_KEY"] == "{cred:ark.api_key}"
    for key in node.default_params:
        assert not (key.endswith("_API_KEY") or key.endswith("_TOKEN") or key.endswith("_BASE_URL")), key


def test_wechat_upload_node_is_registered():
    """顺手造的公众号上传节点应已在节点库且绑定脚本。"""
    from app.models import load_node_specs

    specs = {s.type: s for s in load_node_specs()}
    node = specs.get("skill_wechat_upload")
    assert node is not None, "公众号草稿上传节点未注册"
    assert node.skill_binding["mode"] == "script"
    assert node.skill_binding["script"].endswith("publish_article.py")
    assert node.requires_confirmation is True
