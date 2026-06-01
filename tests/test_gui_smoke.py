"""GUI 冒烟：构造 MainWindow，跑模拟链路，断言节点状态更新；active.json 同步。"""
from __future__ import annotations
import json
import sys
import os
import time
from pathlib import Path

# 兼容 exec 执行和直接 import
try:
    _TEST_FILE = Path(__file__).resolve()
except NameError:
    _TEST_FILE = Path(os.getcwd()) / "tests" / "test_gui_smoke.py"
sys.path.insert(0, str(_TEST_FILE.parents[1]))

# 必须在导入 PyQt 前设置 offscreen
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtCore import QPointF, QTimer
from PyQt5.QtWidgets import QApplication

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode
from app.runtime.engine import RuntimeEngine
from app.ui.canvas import node_status_text
from app.ui.main_window import MainWindow


def test_mainwindow_constructs_and_runs_chain(tmp_path):
    app = QApplication.instance() or QApplication(sys.argv)
    # 用空临时 active.json，避免读到真实 workflows/active.json
    w = MainWindow(active_path=tmp_path / "active.json")
    # 种子 demo 已有 3 节点链路，检查初始状态
    assert len(w.scene.nodes) == 3, f"Expected 3 seed nodes, got {len(w.scene.nodes)}"

    # 跑整条链路
    w._run_all()

    # 等待后台线程完成（模拟模式很快）
    deadline = time.time() + 10
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.1)
        statuses = {n.status for n in w.scene.nodes.values()}
        if statuses == {"success"}:
            break

    # 断言三节点都成功
    for node in w.scene.nodes.values():
        assert node.status == "success", f"Node {node.spec.name} status is {node.status}, expected success"
        assert node.last_output is not None, f"Node {node.spec.name} has no last_output"

    print("test_gui_smoke ok")


def test_runtime_engine_run_node_preserves_upstream_outputs():
    app = QApplication.instance() or QApplication(sys.argv)
    node = WorkflowNode(NODE_SPEC_BY_TYPE["douyin_video_download"], 0, 0)
    engine = RuntimeEngine()
    engine.run_node(node, [{"type": "profile_links", "items": ["https://douyin.com/video/demo"]}])

    deadline = time.time() + 5
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.05)
        if node.status == "success":
            break

    assert node.status == "success"
    assert node.last_output["meta"]["upstream_count"] == 1


def test_runtime_engine_waiting_external_refreshes_node():
    app = QApplication.instance() or QApplication(sys.argv)
    engine = RuntimeEngine()
    finished = []
    engine.node_finished.connect(lambda node_id, output: finished.append((node_id, output)))

    engine._running.add("image-node")
    output = {"type": "external_action_request", "meta": {"action": "codex_imagegen"}}
    engine._on_progress("image-node", "waiting_external", output)

    assert "image-node" not in engine._running
    assert finished == [("image-node", output)]


def test_canvas_status_text_supports_waiting_external():
    assert node_status_text("waiting_external") == "等待 Codex"


def test_autosave_writes_active_json_and_bumps_rev(tmp_path):
    """GUI 改动后 autosave 写入 active.json，rev 自增。"""
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    active_path = tmp_path / "active.json"
    w._active_path = active_path

    # 初始写入
    w._autosave()
    assert active_path.exists()
    data = json.loads(active_path.read_text(encoding="utf-8"))
    rev1 = data["rev"]
    assert rev1 > 0

    # 加一个节点后再 autosave，rev 应该增加
    w.scene.add_node("douyin_profile_collect", QPointF(200, 200))
    w._autosave()
    data2 = json.loads(active_path.read_text(encoding="utf-8"))
    assert data2["rev"] > rev1
    # 不应触发重载（rev 匹配）
    assert w._last_rev == data2["rev"]

    print("test_autosave ok")


def test_external_store_change_reloads_canvas(tmp_path):
    """外部 store 修改 active.json（rev 更高）后，GUI 重载画布。"""
    app = QApplication.instance() or QApplication(sys.argv)
    active_path = tmp_path / "active.json"
    w = MainWindow(active_path=active_path)
    w._autosave()

    # 初始画布应有 3 个种子节点
    assert len(w.scene.nodes) == 3

    # 模拟 MCP/store 从外部添加节点（rev 更高）
    from app.mcp import store as S
    S.add_node("douyin_profile_collect", path=active_path)
    S.add_node("douyin_video_download", path=active_path)

    # 手动触发重载（模拟 QFileSystemWatcher 回调）
    w._reload_from_disk()

    # 画布现在应该有 5 个节点（3 种子 + 2 新加）
    assert len(w.scene.nodes) == 5

    print("test_external_reload ok")


def test_gui_autosave_does_not_loop_reload(tmp_path):
    """GUI 自己的 autosave 不会触发重载（rev 比对阻止回环）。"""
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    active_path = tmp_path / "active.json"
    w._active_path = active_path
    w._autosave()

    node_count_before = len(w.scene.nodes)

    # GUI 自己加节点 → autosave
    w.scene.add_node("asr_extract", QPointF(300, 300))
    w._autosave()

    # rev 应匹配，不应触发重载
    data = json.loads(active_path.read_text(encoding="utf-8"))
    assert w._last_rev == data["rev"]
    # 画布节点数应等于之前 + 1（新增的），没有被重载覆盖
    assert len(w.scene.nodes) == node_count_before + 1

    print("test_no_reload_loop ok")
