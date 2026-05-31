"""节点协议（厚 Manifest）。

内置总控/计划器已移除（外部 agent 经 MCP/直接操作担任总控）。此处仅保留
`node_protocol_prompt()`——把全部节点的自描述序列化，供阶段 6 MCP 工具发现与
外部总管理解节点之用。
"""

from __future__ import annotations

import json
from typing import Any

from app.models import NODE_SPECS


def _port_manifest(spec, port_name: str) -> dict[str, Any]:
    port = spec.port_type(port_name)
    return {
        "port": port.name,
        "label": port.label,
        "kind": port.kind,
        "item": port.item,
        "example": port.example,
    }


def node_protocol_prompt() -> str:
    """输出厚 Manifest：让外部总控/MCP 像管家一样理解每个节点（含端口契约与参数说明）。"""
    payload = []
    for spec in NODE_SPECS:
        payload.append(
            {
                "type": spec.type,
                "name": spec.name,
                "capability": spec.capability,
                "description": spec.description,
                "when_to_use": spec.when_to_use,
                "inputs": [_port_manifest(spec, name) for name in spec.inputs],
                "outputs": [_port_manifest(spec, name) for name in spec.outputs],
                "typical_upstream": spec.typical_upstream,
                "typical_downstream": spec.typical_downstream,
                "keywords": spec.keywords,
                "skill_mode": (spec.skill_binding or {}).get("mode") if spec.skill_binding else None,
                "params": [
                    {
                        "key": ps.key,
                        "label": ps.label,
                        "meaning": ps.meaning,
                        "how_to_fill": ps.how_to_fill,
                        "consequence": ps.consequence,
                        "widget": ps.widget,
                        **({"options": ps.options} if ps.options else {}),
                    }
                    for ps in spec.param_specs.values()
                ],
                "default_params": spec.default_params,
                "output_example": spec.output_example,
                "risk_level": spec.risk_level,
                "requires_confirmation": spec.requires_confirmation,
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)
