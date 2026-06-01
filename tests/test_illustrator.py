"""Task 1 rework: illustrator 专属执行器 — 占位符锚定 + id'd prompts 两端口输出。

覆盖：
- 节点 spec 定义（builtin 优先，不被 custom_nodes.json 覆盖）
- 执行器分发
- 锚点占位符插入
- 完整原文保留
- image_prompts 嵌套在返回输出中（抗 runner last_output 覆写）
- _items_from_upstream 能从嵌套端口发现 image_prompts
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode


# ── helpers ──────────────────────────────────────────────────────────────

def _make_node(**overrides) -> WorkflowNode:
    spec = NODE_SPEC_BY_TYPE["skill_baoyu_article_illustrator"]
    params = dict(spec.default_params)
    params.update(overrides.pop("params", {}))
    return WorkflowNode(spec=spec, x=0, y=0, params=params, **overrides)


def _article_upstream(text: str) -> list[dict]:
    return [{"type": "article_text", "items": [text], "meta": {"format": "markdown"}}]


# ── mock response helpers ────────────────────────────────────────────────

MOCK_ANCHOR_RESPONSE = json.dumps({
    "anchors": [
        {"id": "cover", "kind": "cover",
         "prompt": "赛博朋克风格城市夜景横版封面",
         "anchor": "# 标题"},
        {"id": "1", "kind": "illustration",
         "prompt": "数据流动的数字插画",
         "anchor": "数据是最宝贵的资产"},
        {"id": "2", "kind": "illustration",
         "prompt": "AI 神经网络抽象艺术",
         "anchor": "人工智能正在重塑"},
    ]
})


SAMPLE_ARTICLE = """\
# 标题

这是一篇测试文章。

数据是最宝贵的资产，我们需要善加利用。

人工智能正在重塑各行各业的运作方式。

结论：技术改变未来。"""


# ── tests ────────────────────────────────────────────────────────────────

def test_illustrator_spec_has_no_skill_binding():
    """builtin 优先：即使 custom_nodes.json 有旧条目，NODE_SPEC_BY_TYPE 也用 builtin。"""
    spec = NODE_SPEC_BY_TYPE["skill_baoyu_article_illustrator"]
    assert spec.skill_binding is None, f"expected no skill_binding, got {spec.skill_binding}"
    assert spec.outputs == ["article_text", "image_prompts"], f"expected [article_text, image_prompts], got {spec.outputs}"
    assert "执行模式" in spec.default_params
    assert "配图数量" in spec.default_params
    assert "补充指令" in spec.default_params
    assert "输出目录" in spec.default_params


def test_illustrator_dispatches():
    """ToolExecutor.execute 应把 illustrator 节点派发给 _run_article_illustrator。"""
    from app.runtime.tool_executor import ToolExecutor

    node = _make_node()
    upstream = _article_upstream(SAMPLE_ARTICLE)
    executor = ToolExecutor()

    with patch.object(executor, "_chat_completion_content", return_value=MOCK_ANCHOR_RESPONSE):
        result = executor.execute(node, upstream)

    assert result["type"] == "article_text", f"expected article_text type, got {result.get('type')}"
    assert "finished_at" in result["meta"]


def test_illustrator_marker_insertion_by_anchor():
    """锚点定位：[[COVER]] 插在 anchor 段落后，[[IMG:n]] 插在对应 anchor 段落后。"""
    from app.runtime.tool_executor import ToolExecutor

    node = _make_node()
    upstream = _article_upstream(SAMPLE_ARTICLE)
    executor = ToolExecutor()

    with patch.object(executor, "_chat_completion_content", return_value=MOCK_ANCHOR_RESPONSE):
        result = executor.execute(node, upstream)

    items = result.get("items", [])
    assert items, "article_text 端口应有输出文件"
    article_path = Path(items[0])
    assert article_path.exists(), f"输出文章文件不存在: {article_path}"
    marked = article_path.read_text(encoding="utf-8")

    assert "[[COVER]]" in marked, f"missing [[COVER]] in: {marked[:500]}"
    assert "[[IMG:1]]" in marked, f"missing [[IMG:1]] in: {marked[:500]}"
    assert "[[IMG:2]]" in marked, f"missing [[IMG:2]] in: {marked[:500]}"

    cover_pos = marked.index("[[COVER]]")
    title_pos = marked.index("# 标题")
    assert cover_pos > title_pos, "[[COVER]] should be after title"

    img1_pos = marked.index("[[IMG:1]]")
    anchor1_pos = marked.index("数据是最宝贵的资产")
    assert img1_pos > anchor1_pos, "[[IMG:1]] should be after its anchor paragraph"

    img2_pos = marked.index("[[IMG:2]]")
    anchor2_pos = marked.index("人工智能正在重塑")
    assert img2_pos > anchor2_pos, "[[IMG:2]] should be after its anchor paragraph"


def test_illustrator_preserves_complete_article():
    """完整原文保留：占位符插入后，原文所有内容不丢。"""
    from app.runtime.tool_executor import ToolExecutor

    node = _make_node()
    upstream = _article_upstream(SAMPLE_ARTICLE)
    executor = ToolExecutor()

    with patch.object(executor, "_chat_completion_content", return_value=MOCK_ANCHOR_RESPONSE):
        result = executor.execute(node, upstream)

    items = result.get("items", [])
    article_path = Path(items[0])
    marked = article_path.read_text(encoding="utf-8")

    cleaned = marked.replace("[[COVER]]", "").replace("[[IMG:1]]", "").replace("[[IMG:2]]", "")
    import re
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    original = SAMPLE_ARTICLE.strip()
    assert cleaned == original, f"article content mismatch:\n--- cleaned ---\n{cleaned}\n--- original ---\n{original}"


def test_illustrator_image_prompts_in_returned_output():
    """image_prompts 嵌套在返回输出中：含结构化 id/kind/prompt 和 meta.count。"""
    from app.runtime.tool_executor import ToolExecutor

    node = _make_node()
    upstream = _article_upstream(SAMPLE_ARTICLE)
    executor = ToolExecutor()

    with patch.object(executor, "_chat_completion_content", return_value=MOCK_ANCHOR_RESPONSE):
        result = executor.execute(node, upstream)

    # 验证嵌套的 image_prompts 在返回输出中
    nested = result.get("image_prompts")
    assert nested is not None, f"image_prompts not in returned output: keys={list(result.keys())}"
    assert nested["type"] == "image_prompts"
    assert len(nested["items"]) == 1

    # 读取 prompts JSON 文件验证内容
    prompts_path = Path(nested["items"][0])
    assert prompts_path.exists(), f"prompts file missing: {prompts_path}"
    img_prompts = json.loads(prompts_path.read_text(encoding="utf-8"))

    assert "meta" in img_prompts
    assert img_prompts["meta"]["count"] == 3
    items = img_prompts["items"]
    assert len(items) == 3

    cover = [i for i in items if i["id"] == "cover"][0]
    assert cover["kind"] == "cover"
    assert "prompt" in cover

    img1 = [i for i in items if i["id"] == "1"][0]
    assert img1["kind"] == "illustration"
    assert "prompt" in img1


def test_illustrator_runner_overwrite_and_upstream_discovery():
    """模拟 WorkflowRunner 覆写 node.last_output 后，
    _items_from_upstream 仍能通过嵌套端口发现 image_prompts。"""
    from app.runtime.tool_executor import ToolExecutor, _items_from_upstream

    node = _make_node()
    upstream = _article_upstream(SAMPLE_ARTICLE)
    executor = ToolExecutor()

    with patch.object(executor, "_chat_completion_content", return_value=MOCK_ANCHOR_RESPONSE):
        output = executor.execute(node, upstream)

    # 模拟 runner: node.last_output = output（覆写 executor 内部设置的 last_output）
    node.last_output = output

    # 验证 article_text 端口：正常匹配 type
    article_items = _items_from_upstream([node.last_output], "article_text")
    assert len(article_items) == 1
    assert article_items[0].endswith(".md")

    # 验证 image_prompts 端口：通过嵌套键发现
    prompt_items = _items_from_upstream([node.last_output], "image_prompts")
    assert len(prompt_items) == 1, f"expected 1 image_prompts item, got {prompt_items}"
    assert prompt_items[0].endswith(".json")

    # 确认 JSON 内容有效
    prompts_data = json.loads(Path(prompt_items[0]).read_text(encoding="utf-8"))
    assert prompts_data["meta"]["count"] == 3
    assert len(prompts_data["items"]) == 3
