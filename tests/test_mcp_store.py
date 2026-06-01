"""工作流仓库：active.json 读写、rev 自增、节点反序列化。"""
from __future__ import annotations
import sys
import os
from pathlib import Path

# 兼容 exec 执行和直接 import
try:
    _TEST_FILE = Path(__file__).resolve()
except NameError:
    _TEST_FILE = Path(os.getcwd()) / "tests" / "test_mcp_store.py"
sys.path.insert(0, str(_TEST_FILE.parents[1]))

from app.mcp import store as S


def test_empty_load(tmp_path):
    wf = S.load_workflow(tmp_path / "active.json")
    assert wf["rev"] == 0 and wf["nodes"] == [] and wf["edges"] == []


def test_save_bumps_rev(tmp_path):
    p = tmp_path / "active.json"
    wf = S.load_workflow(p)
    r1 = S.save_workflow(wf, p)
    r2 = S.save_workflow(S.load_workflow(p), p)
    assert r2 == r1 + 1


def test_add_connect_validates_ports(tmp_path):
    p = tmp_path / "active.json"
    a = S.add_node("douyin_profile_collect", path=p)["id"]
    b = S.add_node("douyin_video_download", path=p)["id"]
    ok = S.connect(a, b, path=p)
    assert ok["connected"] is True
    # 不兼容：采集 -> ASR（profile_links 接 video_files 失败）
    c = S.add_node("asr_extract", path=p)["id"]
    bad = S.connect(a, c, path=p)
    assert bad["connected"] is False and "契约" in bad["reason"]


def test_set_and_delete(tmp_path):
    p = tmp_path / "active.json"
    a = S.add_node("douyin_profile_collect", path=p)["id"]
    S.set_params(a, {"主页链接": "http://x"}, path=p)
    wf = S.load_workflow(p)
    assert wf["nodes"][0]["params"]["主页链接"] == "http://x"
    S.delete_node(a, path=p)
    assert S.load_workflow(p)["nodes"] == []


def test_run_all_mock_and_writes_back(tmp_path):
    p = tmp_path / "active.json"
    a = S.add_node("douyin_profile_collect", path=p)["id"]
    b = S.add_node("douyin_video_download", path=p)["id"]
    S.connect(a, b, path=p)
    res = S.run(path=p)  # run_all，默认模拟
    assert a in res["ran"] and b in res["ran"]
    wf = S.load_workflow(p)
    statuses = {n["id"]: n["status"] for n in wf["nodes"]}
    assert statuses[a] == "success" and statuses[b] == "success"


def test_run_real_high_risk_needs_confirmation(tmp_path):
    p = tmp_path / "active.json"
    a = S.add_node("mediapush_publish", params={"执行模式": "真实"}, path=p)["id"]
    res = S.run(path=p)
    assert res["needs_confirmation"] and res["needs_confirmation"][0]["id"] == a


def test_run_node_single_only(tmp_path):
    p = tmp_path / "active.json"
    a = S.add_node("douyin_profile_collect", path=p)["id"]
    b = S.add_node("douyin_video_download", path=p)["id"]
    S.connect(a, b, path=p)
    res = S.run_node(a, path=p)
    # 只有 a 跑了，b 没跑
    assert a in res["ran"] and b not in res["ran"]
    wf = S.load_workflow(p)
    statuses = {n["id"]: n["status"] for n in wf["nodes"]}
    assert statuses[a] == "success" and statuses[b] == "idle"


def test_create_skill_node_preview_then_write(tmp_path):
    # 用一个临时 SKILL.md
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: demo\ndescription: d\n---\n正文", encoding="utf-8")
    preview = S.create_skill_node(str(skill), mode="text", write=False)
    assert preview["manifest"]["type"].startswith("skill_") and preview["written"] is False


def test_connect_suggests_bridge_on_mismatch(tmp_path):
    """端口不兼容时，connect 应给出可架桥的节点建议（自修复线索）。"""
    p = tmp_path / "active.json"
    a = S.add_node("skill_baoyu_image_gen", path=p)["id"]
    b = S.add_node("skill_wechat_upload", path=p)["id"]
    r = S.connect(a, b, path=p)
    assert r["connected"] is False
    types = [s["type"] for s in r.get("suggest", [])]
    assert "wechat_article_assemble" in types


def test_complete_external_image_action_writes_image_list(tmp_path):
    p = tmp_path / "active.json"
    node_id = S.add_node("skill_baoyu_image_gen", path=p)["id"]
    img1 = tmp_path / "cover.png"
    img2 = tmp_path / "1.png"
    img1.write_bytes(b"cover")
    img2.write_bytes(b"one")

    wf = S.load_workflow(p)
    wf["nodes"][0]["status"] = "waiting_external"
    wf["nodes"][0]["last_output"] = {
        "type": "external_action_request",
        "items": [str(tmp_path / "request.json")],
        "meta": {
            "action": "codex_imagegen",
            "tasks": [
                {"id": "cover", "output_path": str(img1)},
                {"id": "1", "output_path": str(img2)},
            ],
            "output_port": "image_list",
        },
    }
    S.save_workflow(wf, p)

    result = S.complete_external_action(node_id, [
        {"id": "cover", "path": str(img1)},
        {"id": "1", "path": str(img2)},
    ], path=p)

    assert result["completed"] is True
    output = S.get_output(node_id, path=p)["last_output"]
    assert output["type"] == "image_list"
    assert output["items"] == [str(img1), str(img2)]
    assert output["meta"]["images"][0] == {"id": "cover", "path": str(img1)}


def test_complete_external_article_action_writes_article_text(tmp_path):
    p = tmp_path / "active.json"
    node_id = S.add_node("web_article_fetch", path=p)["id"]
    out_md = tmp_path / "web_x.md"

    wf = S.load_workflow(p)
    wf["nodes"][0]["status"] = "waiting_external"
    wf["nodes"][0]["last_output"] = {
        "type": "external_action_request",
        "items": [str(tmp_path / "request.json")],
        "meta": {
            "action": "fetch_webpage",
            "output_port": "article_text",
            "tasks": [{"id": "1", "url": "https://example.com/post",
                       "output_path": str(out_md)}],
        },
    }
    S.save_workflow(wf, p)

    result = S.complete_external_action(
        node_id,
        {"text": "# 标题\n\n正文 markdown", "title": "标题", "url": "https://example.com/post"},
        path=p,
    )

    assert result["completed"] is True
    output = S.get_output(node_id, path=p)["last_output"]
    assert output["type"] == "article_text"
    assert output["items"] == [str(out_md)]
    assert Path(out_md).read_text(encoding="utf-8").startswith("# 标题")
    assert output["meta"]["source_url"] == "https://example.com/post"
    assert output["meta"]["title"] == "标题"


def test_complete_external_unknown_port_rejected(tmp_path):
    p = tmp_path / "active.json"
    node_id = S.add_node("web_article_fetch", path=p)["id"]
    wf = S.load_workflow(p)
    wf["nodes"][0]["status"] = "waiting_external"
    wf["nodes"][0]["last_output"] = {
        "type": "external_action_request",
        "items": [],
        "meta": {"action": "weird", "output_port": "score_report", "tasks": []},
    }
    S.save_workflow(wf, p)
    result = S.complete_external_action(node_id, {"text": "x"}, path=p)
    assert result["completed"] is False
    assert "output_port" in result["reason"]
