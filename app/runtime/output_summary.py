from __future__ import annotations

from typing import Any


def format_output_summary(output: dict[str, Any] | None, max_items: int = 8) -> str:
    if not output:
        return "暂无输出。"

    lines = [
        f"类型: {output.get('type', 'unknown')}",
        f"数量: {len(output.get('items', []))}",
    ]
    meta = output.get("meta") or {}
    if meta.get("finished_at"):
        lines.append(f"输出时间: {meta['finished_at']}")

    items = [str(item) for item in output.get("items", [])]
    if items:
        lines.append("")
        lines.append("产物:")
        for item in items[:max_items]:
            lines.append(f"- {item}")
        if len(items) > max_items:
            lines.append(f"- ... 其余 {len(items) - max_items} 项")

    if meta:
        lines.append("")
        lines.append("元数据:")
        for key, value in meta.items():
            if key == "finished_at":
                continue
            lines.append(f"- {key}: {value}")

    return "\n".join(lines)
