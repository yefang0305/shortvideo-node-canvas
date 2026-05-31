from __future__ import annotations

import threading
from PyQt5.QtCore import QObject, pyqtSignal

from app.models import WorkflowNode, WorkflowEdge
from app.runtime.runner import WorkflowRunner


class RuntimeEngine(QObject):
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str, dict)
    node_failed = pyqtSignal(str, str)
    log = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._running: set[str] = set()

    # ── 单节点兼容接口（供 GUI 独立运行按钮使用）──

    def run_node(self, node: WorkflowNode, upstream_outputs: list[dict] | None = None) -> None:
        """运行单个节点（兼容旧 API）。内部委托给 WorkflowRunner。"""
        if node.id in self._running:
            self.log.emit(f"{node.spec.name} 已在运行中，跳过重复启动")
            return

        self._running.add(node.id)
        node.status = "running"
        self.node_started.emit(node.id)
        self.log.emit(f"开始运行：{node.spec.name}")

        nodes = {node.id: node}
        edges: list[WorkflowEdge] = []
        # 如果调用方传了上游输出，把它们注入到一个虚拟上游节点的 last_output 上
        if upstream_outputs:
            for i, output in enumerate(upstream_outputs):
                upstream_node = WorkflowNode(spec=node.spec, x=0, y=0)
                upstream_node.id = f"_upstream_{i}_{node.id}"
                upstream_node.last_output = output
                upstream_node.status = "success"
                nodes[upstream_node.id] = upstream_node
                edges.append(WorkflowEdge(upstream_node.id, node.id))

        runner = WorkflowRunner(on_progress=self._on_progress)

        def worker() -> None:
            summary = runner.run_sync(nodes, edges, start_ids=[node.id])
            self._running.discard(node.id)
            if summary.get("needs_confirmation"):
                node.status = "idle"
                self.log.emit(f"待确认：{node.spec.name}（高风险真实节点需要显式确认）")

        threading.Thread(target=worker, daemon=True).start()

    # ── 工作流编排接口（供 GUI 跑链路使用）──

    def run_workflow(
        self,
        nodes: dict[str, WorkflowNode],
        edges: list[WorkflowEdge],
        start_ids: list[str] | None = None,
        confirm: bool | list[str] | None = None,
    ) -> None:
        """运行整条链路：WorkflowRunner 在后台线程执行，通过信号回主线程。"""
        runner = WorkflowRunner(on_progress=self._on_progress)

        def worker() -> None:
            runner.run_sync(nodes, edges, start_ids=start_ids, confirm=confirm)

        threading.Thread(target=worker, daemon=True).start()

    # ── 内部回调：把 Runner 的 on_progress 转为 Qt 信号 ──

    def _on_progress(self, node_id: str, status: str, output_or_error: dict | str | None) -> None:
        if status == "running":
            self._running.add(node_id)
            self.node_started.emit(node_id)
        elif status == "success":
            self._running.discard(node_id)
            if isinstance(output_or_error, dict):
                self.node_finished.emit(node_id, output_or_error)
            self.log.emit(f"完成：{node_id}")
        elif status == "failed":
            self._running.discard(node_id)
            error_msg = str(output_or_error) if output_or_error else "未知错误"
            self.node_failed.emit(node_id, error_msg)
            self.log.emit(f"失败：{node_id} -> {error_msg}")
