"""阶段 4：管家造节点 + Skill 节点协议校验（不依赖网络/API Key）。"""

from __future__ import annotations

import json

from app.agent.node_builder import build_node_manifest, parse_skill_file
from app.manifest import PORT_TYPES

BAOYU_SKILL = (
    "J:/MagicTool/风格化图片生成工具/baoyu-skills-main/skills/"
    "baoyu-article-illustrator/SKILL.md"
)


def _make_skill_file(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(
        "---\nname: demo-scorer\ndescription: 给公众号文章打分\n---\n# Body\n打分规则……",
        encoding="utf-8",
    )
    return str(p)


def test_parse_frontmatter(tmp_path):
    skill = parse_skill_file(_make_skill_file(tmp_path))
    assert skill["name"] == "demo-scorer"
    assert skill["description"] == "给公众号文章打分"
    assert "打分规则" in skill["body"]


def test_rule_manifest_is_self_describing(tmp_path):
    m = build_node_manifest(_make_skill_file(tmp_path), instruction="公众号文章评分", mode="text")
    assert m["type"] == "skill_demo_scorer"
    assert m["name"] == "公众号文章评分"
    assert m["skill_binding"]["mode"] == "text"
    # 端口必须是已登记的契约
    for port in m["inputs"] + m["outputs"]:
        assert port in PORT_TYPES


def test_image_mode_requires_confirmation(tmp_path):
    m = build_node_manifest(_make_skill_file(tmp_path), instruction="配图", mode="image")
    assert m["requires_confirmation"] is True
    assert "image_list" in m["outputs"]


def test_manifest_round_trips_into_nodespec(tmp_path):
    """造出的 Manifest 经 NodeSpec 加载后，skill_binding 与说明书字段都在。"""
    from app.models import NodeSpec

    m = build_node_manifest(_make_skill_file(tmp_path), instruction="评分", mode="text")
    spec = NodeSpec(
        type=m["type"], name=m["name"], group=m["group"], icon=m["icon"],
        color=m["color"], description=m["description"], inputs=m["inputs"],
        outputs=m["outputs"], default_params=m["default_params"],
        when_to_use=m["when_to_use"], skill_binding=m["skill_binding"],
    )
    assert spec.skill_binding["skill_file"]
    assert spec.when_to_use


def test_real_baoyu_skill_if_present():
    """若 baoyu 配图 skill 在磁盘，造出的节点应是图像类、绑定该 skill。"""
    import os

    if not os.path.exists(BAOYU_SKILL):
        return
    m = build_node_manifest(BAOYU_SKILL, instruction="公众号文章配图", mode="image")
    assert m["skill_binding"]["skill_file"].endswith("SKILL.md")
    assert m["group"] == "配图"
    json.dumps(m, ensure_ascii=False)  # 必须可序列化以写入 custom_nodes.json
