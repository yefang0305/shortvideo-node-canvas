"""工作流仓库：以 workflows/active.json 为单一真相源（带 rev）。

供 MCP server 调用；纯函数、无 Qt，可单测。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.manifest import best_connection, describe_port
from app.models import NODE_SPECS, NODE_SPEC_BY_TYPE, WorkflowNode, WorkflowEdge
from app.runtime.runner import WorkflowRunner

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_PATH = PROJECT_ROOT / "workflows" / "active.json"


def _empty() -> dict[str, Any]:
    return {"version": "0.1.0", "rev": 0, "nodes": [], "edges": []}


def load_workflow(path: Path | None = None) -> dict[str, Any]:
    path = path or ACTIVE_PATH
    if not path.exists():
        return _empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("rev", 0); data.setdefault("nodes", []); data.setdefault("edges", [])
    return data


def save_workflow(data: dict[str, Any], path: Path | None = None) -> int:
    path = path or ACTIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data["rev"] = int(data.get("rev", 0)) + 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data["rev"]


def add_node(
    type: str,
    params: dict[str, Any] | None = None,
    x: int | None = None,
    y: int | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """向当前工作流添加一个节点；校验 type 后生成 id 并落盘。

    不传坐标时按现有节点数自动错位排布（每行 4 个的网格），避免新节点堆叠。
    """
    if type not in NODE_SPEC_BY_TYPE:
        return {"error": f"未知节点类型：{type}"}
    spec = NODE_SPEC_BY_TYPE[type]
    node_id = f"node_{uuid4().hex[:8]}"
    merged_params = dict(spec.default_params)
    if params:
        merged_params.update(params)
    wf = load_workflow(path)
    n = len(wf["nodes"])
    if x is None:
        x = 120 + (n % 4) * 280
    if y is None:
        y = 160 + (n // 4) * 200
    wf["nodes"].append({
        "id": node_id, "type": type, "x": x, "y": y,
        "params": merged_params, "status": "idle", "last_output": None, "error": "",
    })
    save_workflow(wf, path)
    return {"id": node_id}


def _bridge_candidates(src_spec, tgt_spec) -> list[dict[str, str]]:
    """端口不兼容时，找能架桥的节点：src.outputs → B.inputs 且 B.outputs → tgt.inputs。"""
    out = []
    for b in NODE_SPECS:
        if b.type in (src_spec.type, tgt_spec.type):
            continue
        if best_connection(src_spec.outputs, b.inputs) and best_connection(b.outputs, tgt_spec.inputs):
            extra = [p for p in b.inputs if not best_connection(src_spec.outputs, [p])]
            note = f"接 {src_spec.name} 的输出，吐出可喂 {tgt_spec.name} 的产物"
            if extra:
                note += f"；它还需另接上游补 [{', '.join(describe_port(p) for p in extra)}]"
            out.append({"type": b.type, "name": b.name, "note": note})
    return out


def connect(
    source_id: str,
    target_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    """在两个节点之间建立连线；用 best_connection 校验端口兼容性。"""
    wf = load_workflow(path)
    node_by_id = {n["id"]: n for n in wf["nodes"]}
    src = node_by_id.get(source_id)
    tgt = node_by_id.get(target_id)
    if not src:
        return {"connected": False, "reason": f"源节点不存在：{source_id}"}
    if not tgt:
        return {"connected": False, "reason": f"目标节点不存在：{target_id}"}
    src_spec = NODE_SPEC_BY_TYPE.get(src["type"])
    tgt_spec = NODE_SPEC_BY_TYPE.get(tgt["type"])
    if not src_spec or not tgt_spec:
        return {"connected": False, "reason": "未知节点类型"}
    pair = best_connection(src_spec.outputs, tgt_spec.inputs)
    if pair is None:
        src_ports = ", ".join(describe_port(p) for p in src_spec.outputs)
        tgt_ports = ", ".join(describe_port(p) for p in tgt_spec.inputs)
        return {
            "connected": False,
            "reason": f"数据契约不匹配：上游输出 [{src_ports}] 无法接入下游输入 [{tgt_ports}]",
            "suggest": _bridge_candidates(src_spec, tgt_spec),
        }
    edge_id = f"edge_{uuid4().hex[:8]}"
    wf["edges"].append({"id": edge_id, "source_id": source_id, "target_id": target_id})
    save_workflow(wf, path)
    return {"connected": True, "id": edge_id}


def set_params(
    node_id: str,
    params: dict[str, Any],
    path: Path | None = None,
) -> dict[str, Any]:
    """更新指定节点的参数（dict.update），落盘后返回确认信息。"""
    wf = load_workflow(path)
    for node in wf["nodes"]:
        if node["id"] == node_id:
            node["params"].update(params)
            save_workflow(wf, path)
            return {"updated": True, "id": node_id}
    return {"updated": False, "reason": f"节点不存在：{node_id}"}


def delete_node(
    node_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    """移除节点及其关联的所有连线。"""
    wf = load_workflow(path)
    wf["nodes"] = [n for n in wf["nodes"] if n["id"] != node_id]
    wf["edges"] = [e for e in wf["edges"] if e["source_id"] != node_id and e["target_id"] != node_id]
    save_workflow(wf, path)
    return {"deleted": True, "id": node_id}


def _deserialize_workflow(wf: dict[str, Any]) -> tuple[dict[str, WorkflowNode], list[WorkflowEdge]]:
    """把 active.json 的 dict 列表反序列化为 WorkflowNode / WorkflowEdge 对象。"""
    nodes: dict[str, WorkflowNode] = {}
    for nd in wf["nodes"]:
        spec = NODE_SPEC_BY_TYPE[nd["type"]]
        node = WorkflowNode(spec=spec, x=nd.get("x", 0), y=nd.get("y", 0))
        node.id = nd["id"]
        node.status = nd.get("status", "idle")
        node.params = dict(nd.get("params", spec.default_params))
        node.last_output = nd.get("last_output")
        node.error = nd.get("error", "")
        nodes[node.id] = node
    edges = [WorkflowEdge(e["source_id"], e["target_id"], id=e.get("id", f"edge_{uuid4().hex[:8]}")) for e in wf["edges"]]
    return nodes, edges


def _write_back(wf: dict[str, Any], nodes: dict[str, WorkflowNode]) -> None:
    """把 WorkflowNode 的 status / last_output / error 写回 wf dict。"""
    for nd in wf["nodes"]:
        node = nodes.get(nd["id"])
        if node:
            nd["status"] = node.status
            nd["last_output"] = node.last_output
            nd["error"] = node.error


def run(
    path: Path | None = None,
    start_ids: list[str] | None = None,
    cascade: bool = True,
    confirm: bool | list[str] | None = None,
) -> dict[str, Any]:
    """运行工作流：反序列化 → WorkflowRunner → 写回 status/output/error。"""
    wf = load_workflow(path)
    nodes, edges = _deserialize_workflow(wf)
    runner = WorkflowRunner()
    # cascade=False 时只跑 start_ids 指定的节点，不传播到下游
    if not cascade and start_ids:
        # 仅保留目标节点和它们之间的边
        target_set = set(start_ids)
        nodes = {nid: node for nid, node in nodes.items() if nid in target_set}
        edges = [e for e in edges if e.source_id in target_set and e.target_id in target_set]
        start_ids = None  # runner 自己会算 scope
    summary = runner.run_sync(nodes, edges, start_ids=start_ids, confirm=confirm)
    _write_back(wf, nodes)
    save_workflow(wf, path)
    return summary


def run_node(
    node_id: str,
    confirm: bool = False,
    path: Path | None = None,
) -> dict[str, Any]:
    """运行单个节点，不级联下游。"""
    return run(path=path, start_ids=[node_id], cascade=False, confirm=confirm)


def create_skill_node(
    skill_file: str,
    mode: str = "text",
    instruction: str = "",
    write: bool = False,
) -> dict[str, Any]:
    """从 SKILL.md 生成自定义节点。write=False 仅预览，write=True 落盘并热加载。"""
    from app.agent.node_builder import build_node_manifest, write_custom_node
    manifest = build_node_manifest(skill_file, instruction=instruction, mode=mode)
    if write:
        write_custom_node(manifest)
        from app.models import reload_node_specs
        reload_node_specs()
        return {"manifest": manifest, "written": True}
    return {"manifest": manifest, "written": False}


def list_nodes() -> str:
    """列出全部可用节点类型及其能力/端口/参数（厚 Manifest JSON）。"""
    from app.agent.planner import node_protocol_prompt
    return node_protocol_prompt()


def get_output(
    node_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    """返回指定节点的产物/状态/错误信息。"""
    wf = load_workflow(path)
    for nd in wf["nodes"]:
        if nd["id"] == node_id:
            return {
                "id": node_id,
                "type": nd.get("type"),
                "status": nd.get("status"),
                "last_output": nd.get("last_output"),
                "error": nd.get("error"),
            }
    return {"id": node_id, "found": False}


def get_external_actions(path: Path | None = None) -> list[dict[str, Any]]:
    """列出等待外部 Codex 接手的动作请求。"""
    wf = load_workflow(path)
    actions: list[dict[str, Any]] = []
    for nd in wf["nodes"]:
        output = nd.get("last_output") or {}
        if nd.get("status") == "waiting_external" and output.get("type") == "external_action_request":
            meta = output.get("meta", {})
            actions.append({
                "id": nd["id"],
                "type": nd.get("type"),
                "action": meta.get("action", ""),
                "request_file": meta.get("request_file", ""),
                "tasks": meta.get("tasks", []),
                "count": meta.get("count", 0),
            })
    return actions


def complete_external_action(
    node_id: str,
    result: list[dict[str, str]] | list[str] | dict[str, str] | str,
    path: Path | None = None,
) -> dict[str, Any]:
    """外部大脑完成动作后回写产物，按请求的 output_port 分流形态。

    - image_list：result 为 [{id,path}] 或 [path]，校验文件存在。
    - article_text：result 为 {text,title?,url?} 或纯文本，写文件后产出 article_text。
    """
    wf = load_workflow(path)
    for nd in wf["nodes"]:
        if nd["id"] != node_id:
            continue
        last = nd.get("last_output") or {}
        if last.get("type") != "external_action_request":
            return {"completed": False, "reason": f"节点不是外部动作等待态：{node_id}"}
        meta = last.get("meta", {})
        output_port = meta.get("output_port", "image_list")

        if output_port == "image_list":
            built = _build_image_list_output(result, meta)
        elif output_port == "article_text":
            built = _build_article_text_output(result, meta)
        else:
            return {"completed": False, "reason": f"不支持的 output_port：{output_port}"}
        if not built.get("ok"):
            return {"completed": False, "reason": built["reason"]}

        nd["status"] = "success"
        nd["error"] = ""
        nd["last_output"] = built["output"]
        save_workflow(wf, path)
        return {"completed": True, "id": node_id, **built.get("extra", {})}
    return {"completed": False, "reason": f"节点不存在：{node_id}"}


def _build_image_list_output(result: Any, meta: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, list):
        return {"ok": False, "reason": "image_list 动作需要图片列表 [{id,path}]"}
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(result):
        if isinstance(item, dict):
            img_id = str(item.get("id") or index)
            img_path = str(item.get("path") or item.get("output_path") or "")
        else:
            img_id = str(index)
            img_path = str(item)
        if not img_path:
            return {"ok": False, "reason": f"第 {index + 1} 张图片缺少 path"}
        if not Path(img_path).exists():
            return {"ok": False, "reason": f"图片不存在：{img_path}"}
        normalized.append({"id": img_id, "path": img_path})
    return {
        "ok": True,
        "extra": {"count": len(normalized)},
        "output": {
            "type": "image_list",
            "items": [img["path"] for img in normalized],
            "meta": {
                "images": normalized,
                "count": len(normalized),
                "completed_from": "external_action_request",
                "action": meta.get("action", ""),
            },
        },
    }


def _build_article_text_output(result: Any, meta: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        text = str(result.get("text") or result.get("markdown") or "")
        title = str(result.get("title") or "")
        url = str(result.get("url") or "")
    else:
        text = str(result or "")
        title = ""
        url = ""
    if not text.strip():
        return {"ok": False, "reason": "article_text 动作需要非空正文 text"}

    tasks = meta.get("tasks") or []
    if tasks and tasks[0].get("output_path"):
        out_path = Path(tasks[0]["output_path"])
    else:
        out_dir = PROJECT_ROOT / "outputs" / "web_fetch"
        out_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        out_path = out_dir / f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text.strip() + "\n", encoding="utf-8")
    if not url and tasks:
        url = str(tasks[0].get("url", ""))
    return {
        "ok": True,
        "output": {
            "type": "article_text",
            "items": [str(out_path)],
            "meta": {
                "source_url": url,
                "title": title,
                "format": "markdown",
                "completed_from": "external_action_request",
                "action": meta.get("action", ""),
            },
        },
    }


def get_logs(
    limit: int = 50,
    path: Path | None = None,
) -> str:
    """返回最近运行日志的尾部（最多 limit 行）。无日志时返回空字符串。"""
    runs_dir = PROJECT_ROOT / "runs"
    if not runs_dir.exists():
        return ""
    log_files = sorted(runs_dir.glob("**/*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        return ""
    lines = log_files[0].read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-limit:])
