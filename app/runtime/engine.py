from __future__ import annotations

import threading
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from app.models import WorkflowNode
from app.runtime.tool_executor import ToolExecutionError, ToolExecutor


class RuntimeEngine(QObject):
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str, dict)
    node_failed = pyqtSignal(str, str)
    log = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._running: set[str] = set()
        self._executor = ToolExecutor()

    def run_node(self, node: WorkflowNode, upstream_outputs: list[dict] | None = None) -> None:
        if node.id in self._running:
            self.log.emit(f"{node.spec.name} 已在运行中，跳过重复启动")
            return

        self._running.add(node.id)
        node.status = "running"
        self.node_started.emit(node.id)
        self.log.emit(f"开始运行：{node.spec.name}")

        if str(node.params.get("执行模式", "模拟")).strip() == "真实":
            self._run_real_node(node, upstream_outputs or [])
            return

        def finish() -> None:
            self._running.discard(node.id)
            node.status = "success"
            node.error = ""
            node.last_output = {
                "type": node.spec.outputs[0] if node.spec.outputs else "generic",
                "items": self._mock_items(node),
                "meta": {
                    "source_node_id": node.id,
                    "node_type": node.spec.type,
                    "upstream_count": len(upstream_outputs or []),
                    "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            }
            self.node_finished.emit(node.id, node.last_output)
            self.log.emit(f"完成：{node.spec.name} -> {node.last_output['type']}")

        QTimer.singleShot(900 + len(self._running) * 180, finish)

    def _run_real_node(self, node: WorkflowNode, upstream_outputs: list[dict]) -> None:
        def worker() -> None:
            try:
                output = self._executor.execute(node, upstream_outputs)
            except ToolExecutionError as exc:
                self._running.discard(node.id)
                node.status = "failed"
                node.error = str(exc)
                self.node_failed.emit(node.id, str(exc))
                self.log.emit(f"失败：{node.spec.name} -> {exc}")
                return
            except Exception as exc:
                self._running.discard(node.id)
                node.status = "failed"
                node.error = f"未预期错误: {exc}"
                self.node_failed.emit(node.id, node.error)
                self.log.emit(f"失败：{node.spec.name} -> {node.error}")
                return

            self._running.discard(node.id)
            node.status = "success"
            node.error = ""
            output.setdefault("meta", {})
            output["meta"]["source_node_id"] = node.id
            output["meta"]["node_type"] = node.spec.type
            node.last_output = output
            self.node_finished.emit(node.id, output)
            self.log.emit(f"完成：{node.spec.name} -> {output.get('type', 'result')}")

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _mock_items(node: WorkflowNode) -> list[str]:
        sample = {
            "douyin_profile_collect": ["https://douyin.com/video/demo-001", "https://douyin.com/video/demo-002"],
            "douyin_video_download": ["outputs/downloads/demo-001.mp4", "outputs/downloads/demo-002.mp4"],
            "asr_extract": ["outputs/scripts/demo-001.txt", "outputs/scripts/demo-002.txt"],
            "script_rewrite": ["outputs/scripts/batch_tasks.json"],
            "batch_mix": ["outputs/videos/final-001.mp4", "outputs/videos/final-002.mp4"],
            "mediapush_publish": ["publish_records/demo-run.json"],
            "article_md_import": ["# 示例文章\n\n这是一篇用于内容链路的 Markdown。"],
            "wechat_article_assemble": ["outputs/articles/assembled-demo.md"],
        }
        return sample.get(node.spec.type, ["outputs/result.json"])
