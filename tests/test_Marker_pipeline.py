"""Task 4: 端到端 Marker pipeline — md import → illustrator Markers → batch image list → Marker assembly.

Focused contract test that does NOT call real LLM/image providers.
Mocks: illustrator LLM response, image_gen subprocess.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

_EXECUTOR_SUBPROCESS = "app.runtime.tool_executor.subprocess.run"


# ── helpers ──────────────────────────────────────────────────────────────

MOCK_ILLUSTRATOR_RESPONSE = json.dumps({
    "anchors": [
        {"id": "cover", "kind": "cover",
         "prompt": "futuristic city skyline at dusk, wide cinematic shot",
         "anchor": "# 未来的城市"},
        {"id": "1", "kind": "illustration",
         "prompt": "holographic data streams flowing through glass buildings",
         "anchor": "数据像河流一样在城市中流动"},
        {"id": "2", "kind": "illustration",
         "prompt": "AI robot handshake with human in sunlit office",
         "anchor": "人与机器的协作"},
    ]
})

MOCK_BATCH_STDOUT = json.dumps({
    "images": [
        {"id": "cover", "path": "/fake/outputs/cover.png"},
        {"id": "1", "path": "/fake/outputs/img_1.png"},
        {"id": "2", "path": "/fake/outputs/img_2.png"},
    ]
})

SAMPLE_ARTICLE = """\
# 未来的城市

未来的城市是数据驱动的。

数据像河流一样在城市中流动，连接每一个角落。

人与机器的协作将重新定义生产力。

技术让生活更美好。"""


# ── test: full e2e pipeline (mocked) ─────────────────────────────────────

def test_full_marker_pipeline_e2e():
    """端到端：md import → illustrator(占位符) → image_gen(batch) → assemble(Marker替换)。

    全程 mock LLM 和 subprocess，不调真实提供商。
    """
    from app.runtime.tool_executor import ToolExecutor, _items_from_upstream

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        executor = ToolExecutor()

        # ── Step 1: md import ──
        md_path = work_dir / "article.md"
        md_path.write_text(SAMPLE_ARTICLE, encoding="utf-8")

        import_spec = NODE_SPEC_BY_TYPE["article_md_import"]
        import_node = WorkflowNode(spec=import_spec, x=0, y=0, params={
            "执行模式": "真实",
            "MD文件": str(md_path),
        })
        import_result = executor.execute(import_node, [])
        assert import_result["type"] == "article_text"
        assert len(import_result["items"]) == 1

        # ── Step 2: illustrator (mocked LLM) ──
        ill_spec = NODE_SPEC_BY_TYPE["skill_baoyu_article_illustrator"]
        ill_node = WorkflowNode(spec=ill_spec, x=0, y=0, params={
            "执行模式": "真实",
            "配图数量": 3,
            "输出目录": str(work_dir / "illustrator"),
        })

        with patch.object(executor, "_chat_completion_content", return_value=MOCK_ILLUSTRATOR_RESPONSE):
            ill_result = executor.execute(ill_node, [import_result])

        assert ill_result["type"] == "article_text"
        assert "image_prompts" in ill_result, f"image_prompts not in illustrator output: {list(ill_result.keys())}"

        # Read marked article
        marked_path = Path(ill_result["items"][0])
        assert marked_path.exists()
        marked = marked_path.read_text(encoding="utf-8")
        assert "[[COVER]]" in marked, f"missing [[COVER]] in: {marked[:300]}"
        assert "[[IMG:1]]" in marked, f"missing [[IMG:1]]"
        assert "[[IMG:2]]" in marked, f"missing [[IMG:2]]"

        # Verify prompts JSON
        prompt_items = _items_from_upstream([ill_result], "image_prompts")
        assert len(prompt_items) == 1
        prompts_path = Path(prompt_items[0])
        assert prompts_path.exists()
        prompts_data = json.loads(prompts_path.read_text(encoding="utf-8"))
        assert prompts_data["meta"]["count"] == 3
        assert len(prompts_data["items"]) == 3

        # ── Step 3: image_gen generates an external Codex request ──
        gen_spec = NODE_SPEC_BY_TYPE["skill_baoyu_image_gen"]
        gen_node = WorkflowNode(spec=gen_spec, x=0, y=0, params={
            "执行模式": "真实",
            "服务商": "codex_builtin",
            "比例": "16:9",
        })

        with patch(_EXECUTOR_SUBPROCESS) as mock_run:
            gen_result = executor.execute(gen_node, [ill_result])

        assert mock_run.call_count == 0
        assert gen_result["type"] == "external_action_request"
        assert gen_result["meta"]["action"] == "codex_imagegen"
        assert gen_result["meta"]["count"] == 3

        # Simulate Codex completing the external action and writing image_list.
        gen_result = {
            "type": "image_list",
            "items": ["/fake/outputs/cover.png", "/fake/outputs/img_1.png", "/fake/outputs/img_2.png"],
            "meta": {
                "count": 3,
                "images": [
                    {"id": "cover", "path": "/fake/outputs/cover.png"},
                    {"id": "1", "path": "/fake/outputs/img_1.png"},
                    {"id": "2", "path": "/fake/outputs/img_2.png"},
                ],
            },
        }

        assert gen_result["type"] == "image_list"
        assert gen_result["meta"]["count"] == 3
        images_meta = gen_result["meta"]["images"]
        assert len(images_meta) == 3
        id_map = {img["id"]: img["path"] for img in images_meta}
        assert "cover" in id_map
        assert "1" in id_map
        assert "2" in id_map

        # ── Step 4: assemble (Marker replacement) ──
        # Use the marked article as input to assemble
        # Simulate runner: set last_output on ill_node so assemble picks up markers
        ill_node.last_output = ill_result

        assemble_spec = NODE_SPEC_BY_TYPE["wechat_article_assemble"]
        assemble_node = WorkflowNode(spec=assemble_spec, x=0, y=0, params={
            "执行模式": "真实",
            "输出目录": str(work_dir / "assembled"),
            "插图策略": "按段落均匀插入",
        })

        # Upstream for assemble: marked article + image_list
        assemble_upstream = [ill_result, gen_result]
        assemble_result = executor.execute(assemble_node, assemble_upstream)

        assert assemble_result["type"] == "article_text"
        assembled_path = Path(assemble_result["items"][0])
        assert assembled_path.exists()
        assembled = assembled_path.read_text(encoding="utf-8")

        # All markers should be gone
        assert "[[COVER]]" not in assembled, f"[[COVER]] should be replaced/removed: {assembled[:300]}"
        assert "[[IMG:1]]" not in assembled, f"[[IMG:1]] should be replaced"
        assert "[[IMG:2]]" not in assembled, f"[[IMG:2]] should be replaced"
        assert "[[IMG:" not in assembled, f"no raw markers should remain: {assembled[:300]}"

        # Images should be in the assembled output
        assert "/fake/outputs/img_1.png" in assembled, f"img_1 not in assembled: {assembled[:500]}"
        assert "/fake/outputs/img_2.png" in assembled, f"img_2 not in assembled: {assembled[:500]}"

        # Cover should be in meta
        assert assemble_result["meta"].get("cover_image"), "cover_image not in meta"
        assert "cover.png" in assemble_result["meta"]["cover_image"]

        # Original content preserved
        assert "未来的城市" in assembled
        assert "数据像河流一样" in assembled
        assert "人与机器的协作" in assembled
        assert "技术让生活更美好" in assembled

        # inline_count should be 2 (img1 + img2, not cover)
        assert assemble_result["meta"]["inline_count"] == 2, (
            f"inline_count should be 2, got {assemble_result['meta']['inline_count']}"
        )


def test_custom_nodes_json_no_stale_illustrator():
    """custom_nodes.json 不应再有旧的 skill_baoyu_article_illustrator 定义。

    builtin (models.py) 拥有该节点，custom_nodes.json 中的旧条目应被移除或已更新为与 builtin 一致。
    如果条目仍存在且与 builtin 冲突，builtin 会优先（load_node_specs 跳过 builtin types），
    但残留的旧定义会造成维护混淆。
    """
    custom_path = Path(__file__).resolve().parent.parent / "app" / "nodes" / "custom_nodes.json"
    data = json.loads(custom_path.read_text(encoding="utf-8"))
    for item in data.get("nodes", []):
        if item["type"] == "skill_baoyu_article_illustrator":
            # If it exists, it must match the builtin contract (no skill_binding, two outputs, 配图数量 param)
            assert item.get("skill_binding") is None, (
                f"custom_nodes.json illustrator must not have skill_binding: {item.get('skill_binding')}"
            )
            assert "article_text" in item.get("outputs", []), (
                f"custom_nodes.json illustrator must output article_text: {item.get('outputs')}"
            )
            assert "image_prompts" in item.get("outputs", []), (
                f"custom_nodes.json illustrator must output image_prompts: {item.get('outputs')}"
            )
            assert "配图数量" in item.get("default_params", {}), (
                f"custom_nodes.json illustrator must have 配图数量 param: {item.get('default_params')}"
            )


def test_illustrator_node_loaded_from_builtin_not_custom():
    """确认运行时 NODE_SPEC_BY_TYPE 的 illustrator 来自 builtin（无 skill_binding）。"""
    from app.models import NODE_SPEC_BY_TYPE

    spec = NODE_SPEC_BY_TYPE["skill_baoyu_article_illustrator"]
    assert spec.skill_binding is None, (
        f"illustrator must have no skill_binding (builtin owns it): {spec.skill_binding}"
    )
    assert spec.outputs == ["article_text", "image_prompts"], (
        f"illustrator must output [article_text, image_prompts]: {spec.outputs}"
    )
    assert "配图数量" in spec.default_params, (
        f"illustrator must have 配图数量 in default_params: {spec.default_params}"
    )
    assert spec.capability == "generate_article_illustration_plan"
    assert spec.group == "公众号"
