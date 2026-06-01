"""无 Qt 的工作流执行核：GUI 与 MCP 共用。

把原先散在 GUI（main_window._run_chain/_start_ready_nodes）与 engine 的编排逻辑
收敛到这里。模拟模式产出 mock 输出；真实模式调 ToolExecutor。
"""
from __future__ import annotations
from datetime import datetime
from typing import Callable

from app.models import WorkflowNode, WorkflowEdge
from app.runtime.tool_executor import ToolExecutionError, ToolExecutor

ProgressCb = Callable[[str, str, dict | str | None], None]

_MOCK = {
    "douyin_profile_collect": ["https://douyin.com/video/demo-001", "https://douyin.com/video/demo-002"],
    "douyin_video_download": ["outputs/downloads/demo-001.mp4"],
    "asr_extract": ["outputs/scripts/demo-001.txt"],
    "script_rewrite": ["outputs/scripts/batch_tasks.json"],
    "batch_mix": ["outputs/videos/final-001.mp4"],
    "mediapush_publish": ["publish_records/demo-run.json"],
    "article_md_import": ["# 示例文章\n\n正文。"],
    "wechat_article_assemble": ["outputs/articles/assembled-demo.md"],
}


def _mock_items(node: WorkflowNode) -> list[str]:
    return _MOCK.get(node.spec.type, ["outputs/result.json"])


class WorkflowRunner:
    def __init__(self, executor: ToolExecutor | None = None, on_progress: ProgressCb | None = None) -> None:
        self._executor = executor or ToolExecutor()
        self._on_progress = on_progress or (lambda *a: None)

    def run_sync(
        self,
        nodes: dict[str, WorkflowNode],
        edges: list[WorkflowEdge],
        start_ids: list[str] | None = None,
        confirm: bool | list[str] | None = None,
    ) -> dict:
        scope = self._scope(nodes, edges, start_ids)
        for nid in scope:
            nodes[nid].status = "idle"
        summary = {"ran": [], "failed": [], "needs_confirmation": [], "needs_external_action": [], "skipped": []}
        completed: set[str] = set()

        def upstream_ready(nid: str) -> bool:
            return all(e.source_id in completed for e in edges if e.target_id == nid and e.source_id in scope)

        remaining = [nid for nid in scope]
        progressed = True
        while remaining and progressed:
            progressed = False
            for nid in list(remaining):
                if not upstream_ready(nid):
                    continue
                node = nodes[nid]
                # 上游若有失败/待确认导致未完成，则该节点阻断
                blocked = any(
                    e.source_id in scope and e.source_id not in completed
                    for e in edges if e.target_id == nid
                )
                if blocked:
                    continue
                remaining.remove(nid)
                progressed = True
                if self._needs_confirm(node, confirm):
                    node.status = "idle"
                    summary["needs_confirmation"].append(
                        {"id": nid, "name": node.spec.name, "risk": node.spec.risk_level}
                    )
                    continue
                self._run_one(node, nodes, edges, summary)
                if node.status == "success":
                    completed.add(nid)
        summary["skipped"] = [nid for nid in remaining]
        return summary

    def _run_one(self, node, nodes, edges, summary) -> None:
        node.status = "running"
        self._on_progress(node.id, "running", None)
        upstream = [nodes[e.source_id].last_output for e in edges
                    if e.target_id == node.id and nodes[e.source_id].last_output]
        try:
            if str(node.params.get("执行模式", "模拟")).strip() == "真实":
                output = self._executor.execute(node, upstream)
            else:
                output = {
                    "type": node.spec.outputs[0] if node.spec.outputs else "generic",
                    "items": _mock_items(node),
                    "meta": {"node_type": node.spec.type, "upstream_count": len(upstream),
                             "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                }
        except ToolExecutionError as exc:
            node.status = "failed"; node.error = str(exc)
            summary["failed"].append({"id": node.id, "error": str(exc)})
            self._on_progress(node.id, "failed", str(exc)); return
        except Exception as exc:  # noqa: BLE001
            node.status = "failed"; node.error = f"未预期错误: {exc}"
            summary["failed"].append({"id": node.id, "error": node.error})
            self._on_progress(node.id, "failed", node.error); return
        output.setdefault("meta", {})["source_node_id"] = node.id
        if output.get("type") == "external_action_request":
            node.last_output = output
            node.status = "waiting_external"
            node.error = ""
            summary["needs_external_action"].append({
                "id": node.id,
                "name": node.spec.name,
                "action": output.get("meta", {}).get("action", ""),
                "request_file": output.get("meta", {}).get("request_file", ""),
                "count": output.get("meta", {}).get("count", 0),
            })
            self._on_progress(node.id, "waiting_external", output)
            return
        node.last_output = output; node.status = "success"; node.error = ""
        summary["ran"].append(node.id)
        self._on_progress(node.id, "success", output)

    @staticmethod
    def _needs_confirm(node: WorkflowNode, confirm) -> bool:
        real = str(node.params.get("执行模式", "模拟")).strip() == "真实"
        if not (real and node.spec.requires_confirmation):
            return False
        if confirm is True:
            return False
        if isinstance(confirm, list) and node.id in confirm:
            return False
        return True

    @staticmethod
    def _scope(nodes, edges, start_ids) -> list[str]:
        if not start_ids:
            return list(nodes.keys())
        scope: set[str] = set()
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e.source_id, []).append(e.target_id)
        stack = list(start_ids)
        while stack:
            nid = stack.pop()
            if nid in scope or nid not in nodes:
                continue
            scope.add(nid)
            stack.extend(adj.get(nid, []))
        return [nid for nid in nodes if nid in scope]
