"""WorkflowRunner：DAG 编排、模拟/真实分流、产物传递、失败阻断、确认闸门。"""
from __future__ import annotations
import sys
import os
from pathlib import Path

# 兼容 exec 执行和直接 import：__file__ 在 exec 中不存在
try:
    _TEST_FILE = Path(__file__).resolve()
except NameError:
    _TEST_FILE = Path(os.getcwd()) / "tests" / "test_runner.py"
sys.path.insert(0, str(_TEST_FILE.parents[1]))

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode, WorkflowEdge
from app.runtime.runner import WorkflowRunner


def _node(type_, **params):
    spec = NODE_SPEC_BY_TYPE[type_]
    p = dict(spec.default_params); p.update(params)
    n = WorkflowNode(spec=spec, x=0, y=0)
    n.params = p
    return n


def test_runs_chain_in_dependency_order():
    a = _node("douyin_profile_collect", 执行模式="模拟")
    b = _node("douyin_video_download", 执行模式="模拟")
    c = _node("asr_extract", 执行模式="模拟")
    nodes = {n.id: n for n in (a, b, c)}
    edges = [WorkflowEdge(a.id, b.id), WorkflowEdge(b.id, c.id)]
    seen = []
    r = WorkflowRunner(on_progress=lambda nid, st, _o: seen.append((nid, st)) if st == "success" else None)
    summary = r.run_sync(nodes, edges)
    order = [nid for nid, st in seen]
    assert order == [a.id, b.id, c.id], f"Expected [a, b, c] got {order}"
    assert set(summary["ran"]) == {a.id, b.id, c.id}
    assert a.last_output and b.last_output and c.last_output


def test_downstream_receives_upstream_output():
    a = _node("douyin_profile_collect", 执行模式="模拟")
    b = _node("douyin_video_download", 执行模式="模拟")
    nodes = {n.id: n for n in (a, b)}
    edges = [WorkflowEdge(a.id, b.id)]
    r = WorkflowRunner()
    r.run_sync(nodes, edges)
    # b 的输出 meta 记录了 upstream 数量（模拟实现里 upstream_count）
    assert b.last_output["meta"]["upstream_count"] == 1


def test_needs_confirmation_blocks_real_high_risk():
    a = _node("mediapush_publish", 执行模式="真实")  # requires_confirmation=True
    nodes = {a.id: a}
    r = WorkflowRunner()
    summary = r.run_sync(nodes, [])
    assert summary["needs_confirmation"] and summary["needs_confirmation"][0]["id"] == a.id
    assert a.id not in summary["ran"]
    # 带 confirm 放行后可跑（仍是模拟避免真实副作用：改回模拟验证 ran）
    a.params["执行模式"] = "模拟"
    summary2 = r.run_sync(nodes, [], confirm=True)
    assert a.id in summary2["ran"]


def test_web_fetch_mock_outputs_article_text():
    node = _node("web_article_fetch", **{"\u6267\u884C\u6A21\u5F0F": "\u6A21\u62DF", "\u7F51\u5740": "https://example.com"})
    nodes = {node.id: node}
    summary = WorkflowRunner().run_sync(nodes, [], start_ids=[node.id])
    assert node.id in summary["ran"]
    assert node.status == "success"
    assert node.last_output["type"] == "article_text"
