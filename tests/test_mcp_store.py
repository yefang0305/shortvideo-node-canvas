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
