"""管家造节点（阶段 4）：把一个 skill 文件变成一条节点 Manifest。

设计要点（见 PRD v2 §9）：
- 只生成"声明"，不生成执行器代码——执行交给通用 skill_node 执行器。
- 无 API Key 时用规则兜底（解析 SKILL.md frontmatter）；有 Key 时调模型增强。
- 生成结果先返回给 UI 预览，确认后才由 write_custom_node 写入 custom_nodes.json。
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from app.agent.settings import AgentSettings

NODES_DIR = Path(__file__).resolve().parents[1] / "nodes"
CUSTOM_NODES_PATH = NODES_DIR / "custom_nodes.json"

# mode -> (默认输入端口, 默认输出端口, 默认分组)
_MODE_DEFAULTS = {
    "text": ("article_text", "article_text", "创作"),
    "image": ("article_text", "image_list", "配图"),
    "script": ("article_text", "generic", "工具"),
}


def parse_skill_file(skill_file: str) -> dict[str, str]:
    """读取 SKILL.md，拆出 frontmatter 的 name/description 与正文。"""
    path = Path(skill_file)
    if not path.exists():
        raise FileNotFoundError(f"找不到 skill 文件：{skill_file}")
    raw = path.read_text(encoding="utf-8")
    name, description, body = "", "", raw
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, flags=re.S)
    if match:
        front, body = match.group(1), match.group(2)
        name = _front_value(front, "name")
        description = _front_value(front, "description")
    if not name:
        name = path.parent.name or path.stem
    return {"name": name, "description": description, "body": body.strip()}


def _front_value(front: str, key: str) -> str:
    m = re.search(rf"^{key}\s*:\s*(.+)$", front, flags=re.M)
    return m.group(1).strip().strip("'\"") if m else ""


def _slug(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    return slug or "skill"


def build_node_manifest(
    skill_file: str,
    instruction: str = "",
    mode: str = "text",
    settings: AgentSettings | None = None,
) -> dict[str, Any]:
    """生成候选节点 Manifest（不写盘）。先规则兜底，有 API Key 再尝试模型增强。"""
    skill = parse_skill_file(skill_file)
    manifest = _rule_manifest(skill, skill_file, instruction, mode)
    if settings and settings.api_key.strip():
        try:
            manifest = _llm_enhance(manifest, skill, instruction, settings)
        except Exception:
            pass  # 模型不可用时保留规则兜底结果
    return manifest


def _rule_manifest(skill: dict[str, str], skill_file: str, instruction: str, mode: str) -> dict[str, Any]:
    in_port, out_port, group = _MODE_DEFAULTS.get(mode, _MODE_DEFAULTS["text"])
    node_name = instruction.strip() or skill["name"]
    binding: dict[str, Any] = {
        "skill_file": str(Path(skill_file)),
        "mode": mode,
        "input_port": in_port,
        "output_port": out_port,
        "instruction": instruction,
    }
    if mode == "script":
        # baoyu 系 skill 约定 scripts/main.ts；其它脚本需人工/模型调整 script 与 runtime
        binding["script"] = "scripts/main.ts"
        binding["runtime"] = ["npx", "-y", "bun"]
        binding["args"] = []
    return {
        "type": f"skill_{_slug(skill['name'])}",
        "name": node_name,
        "group": group,
        "icon": "技",
        "color": "#6650b8",
        "description": skill["description"] or f"由 skill「{skill['name']}」生成的节点",
        "inputs": [in_port],
        "outputs": [out_port],
        "default_params": {"执行模式": "模拟", "补充指令": instruction},
        "risk_level": "medium" if mode in {"image", "script"} else "low",
        "requires_confirmation": mode in {"image", "script"},
        "when_to_use": instruction or skill["description"],
        "capability": f"skill::{skill['name']}",
        "output_example": None,
        "skill_binding": binding,
    }


def _llm_enhance(manifest: dict[str, Any], skill: dict[str, str], instruction: str, settings: AgentSettings) -> dict[str, Any]:
    """让模型完善端口/参数/适用场景；失败由调用方回退规则结果。"""
    from app.manifest import PORT_TYPES

    system = (
        "你在为一个节点画布把一个 skill 封装成节点。"
        "只返回 JSON 对象，补全 name/group/description/inputs/outputs/when_to_use 字段。"
        f"inputs/outputs 只能从这些端口名里选：{list(PORT_TYPES.keys())}。"
        "不要返回 skill_binding（由系统填充）。不要解释。"
    )
    user = (
        f"skill 名称：{skill['name']}\nskill 描述：{skill['description']}\n"
        f"用户目标：{instruction}\n当前候选：{json.dumps(manifest, ensure_ascii=False)}"
    )
    content = _chat(settings, system, user)
    data = _loads_json_object(content)
    # 只接受白名单字段，skill_binding 与 type 由系统保留
    for key in ("name", "group", "description", "when_to_use"):
        if data.get(key):
            manifest[key] = str(data[key])
    for key in ("inputs", "outputs"):
        ports = [p for p in data.get(key, []) if p in PORT_TYPES]
        if ports:
            manifest[key] = ports
    # 端口变了，同步 binding 的读写端口
    manifest["skill_binding"]["input_port"] = manifest["inputs"][0] if manifest["inputs"] else "generic"
    manifest["skill_binding"]["output_port"] = manifest["outputs"][0] if manifest["outputs"] else "generic"
    return manifest


def _chat(settings: AgentSettings, system: str, user: str) -> str:
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        settings.api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _loads_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        raise ValueError("模型没有返回 JSON 对象")
    return json.loads(match.group(0))


def write_custom_node(manifest: dict[str, Any]) -> Path:
    """把确认后的 Manifest 追加进 custom_nodes.json（按 type 去重覆盖）。"""
    NODES_DIR.mkdir(parents=True, exist_ok=True)
    if CUSTOM_NODES_PATH.exists():
        data = json.loads(CUSTOM_NODES_PATH.read_text(encoding="utf-8"))
    else:
        data = {"nodes": []}
    nodes = [n for n in data.get("nodes", []) if n.get("type") != manifest["type"]]
    nodes.append(manifest)
    data["nodes"] = nodes
    CUSTOM_NODES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return CUSTOM_NODES_PATH
