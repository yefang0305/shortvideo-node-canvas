"""Task 3: 装配占位符插入 — Marker 替换 + cover 提取 + 旧策略兼容。

TDD: 验证 [[IMG:id]]→![](path) 替换、[[COVER]] 移除与封面选择、未匹配删除、无 Marker 回退。
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from app.runtime.tool_executor import (
    _assemble_markdown_with_images,
    _read_article_item,
    _normalize_media_ref,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _make_upstream(article_text: str, image_list_items: list[str], meta_images: list[dict] | None = None) -> list[dict]:
    """构造装配节点的上游输入。"""
    upstream: list[dict] = [
        {"type": "article_text", "items": [article_text], "meta": {"format": "markdown"}},
    ]
    if image_list_items:
        img_meta: dict = {"count": len(image_list_items)}
        if meta_images is not None:
            img_meta["images"] = meta_images
        upstream.append({"type": "image_list", "items": image_list_items, "meta": img_meta})
    return upstream


# ── tests ────────────────────────────────────────────────────────────────

def test_marker_replacement_img_by_id():
    """RED: [[IMG:id]] 应替换为对应 id 的 Markdown 图片语法。"""
    # This test targets the new marker-aware assembly path
    from app.runtime.tool_executor import ToolExecutor, ToolExecutionError

    article = "# Title\n\nIntro paragraph.\n\n[[IMG:1]]\n\nBody text.\n\n[[IMG:2]]\n\nConclusion."
    image_items = ["/images/img1.png", "/images/img2.png"]
    meta_images = [
        {"id": "1", "path": "/images/img1.png"},
        {"id": "2", "path": "/images/img2.png"},
    ]
    upstream = _make_upstream(article, image_items, meta_images)

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

        spec = NODE_SPEC_BY_TYPE["wechat_article_assemble"]
        node = WorkflowNode(spec=spec, x=0, y=0, params={
            "执行模式": "真实",
            "输出目录": str(work_dir),
            "插图策略": "按段落均匀插入",
        })
        executor = ToolExecutor()
        result = executor.execute(node, upstream)

        items = result["items"]
        assert items, "应输出文件"
        assembled = Path(items[0]).read_text(encoding="utf-8")

        # [[IMG:1]] 应被替换
        assert "[[IMG:1]]" not in assembled, f"[[IMG:1]] should be replaced: {assembled[:300]}"
        assert "![插图]({})".format("/images/img1.png") in assembled or f"![]({ '/images/img1.png' })" in assembled or f"](/images/img1.png)" in assembled, f"img1 should be in output: {assembled[:500]}"

        # [[IMG:2]] 应被替换
        assert "[[IMG:2]]" not in assembled, f"[[IMG:2]] should be replaced: {assembled[:300]}"

        # 原始内容保留
        assert "Intro paragraph" in assembled
        assert "Body text" in assembled
        assert "Conclusion" in assembled


def test_marker_cover_removal_and_selection():
    """RED: [[COVER]] 应从正文移除，cover id 对应的图作为封面。"""
    from app.runtime.tool_executor import ToolExecutor

    article = "# Title\n\n[[COVER]]\n\nIntro.\n\n[[IMG:1]]\n\nBody."
    image_items = ["/images/cover.png", "/images/img1.png"]
    meta_images = [
        {"id": "cover", "path": "/images/cover.png"},
        {"id": "1", "path": "/images/img1.png"},
    ]
    upstream = _make_upstream(article, image_items, meta_images)

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

        spec = NODE_SPEC_BY_TYPE["wechat_article_assemble"]
        node = WorkflowNode(spec=spec, x=0, y=0, params={
            "执行模式": "真实",
            "输出目录": str(work_dir),
            "插图策略": "按段落均匀插入",
        })
        executor = ToolExecutor()
        result = executor.execute(node, upstream)

        items = result["items"]
        assembled = Path(items[0]).read_text(encoding="utf-8")

        # [[COVER]] 应从正文消失
        assert "[[COVER]]" not in assembled, f"[[COVER]] should be removed: {assembled[:300]}"

        # 封面图应在 meta 中
        assert result["meta"].get("cover_image"), f"cover_image not in meta: {result['meta']}"
        assert "cover.png" in result["meta"]["cover_image"], f"cover should be cover.png: {result['meta']['cover_image']}"


def test_marker_unmatched_deletion():
    """RED: 未匹配的 [[IMG:99]] 和 [[COVER]] 应被静默删除。"""
    from app.runtime.tool_executor import ToolExecutor

    article = "# Title\n\n[[COVER]]\n\nText.\n\n[[IMG:99]]\n\nMore text."
    image_items: list[str] = []  # no images at all
    upstream = _make_upstream(article, image_items, None)

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

        spec = NODE_SPEC_BY_TYPE["wechat_article_assemble"]
        node = WorkflowNode(spec=spec, x=0, y=0, params={
            "执行模式": "真实",
            "输出目录": str(work_dir),
            "插图策略": "按段落均匀插入",
        })
        executor = ToolExecutor()
        result = executor.execute(node, upstream)

        items = result["items"]
        assembled = Path(items[0]).read_text(encoding="utf-8")

        # 所有 marker 应消失
        assert "[[COVER]]" not in assembled
        assert "[[IMG:99]]" not in assembled
        assert "[[IMG:" not in assembled, f"no markers should remain: {assembled[:300]}"
        # 原始文本保留
        assert "Text" in assembled
        assert "More text" in assembled


def test_marker_legacy_no_marker_fallback():
    """RED: 无 marker 的文章应回退到旧均匀/段落策略，不回归。"""
    from app.runtime.tool_executor import ToolExecutor

    article = "# Title\n\nParagraph one.\n\nParagraph two.\n\nParagraph three."
    image_items = ["/images/a.png", "/images/b.png"]
    upstream = _make_upstream(article, image_items, None)

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

        spec = NODE_SPEC_BY_TYPE["wechat_article_assemble"]
        node = WorkflowNode(spec=spec, x=0, y=0, params={
            "执行模式": "真实",
            "输出目录": str(work_dir),
            "插图策略": "按段落均匀插入",
        })
        executor = ToolExecutor()
        result = executor.execute(node, upstream)

        items = result["items"]
        assembled = Path(items[0]).read_text(encoding="utf-8")

        # 旧策略：图片均匀插入段落间
        assert "a.png" in assembled or "/images/a.png" in assembled, f"image a should be present: {assembled[:300]}"
        assert "b.png" in assembled or "/images/b.png" in assembled, f"image b should be present: {assembled[:300]}"
        # 原始文本保留
        assert "Paragraph one" in assembled
        assert "Paragraph three" in assembled


def test_marker_mixed_with_legacy_images():
    """RED: 混合场景 — 有 marker 时优先用 marker 替换，忽略旧插图策略。"""
    from app.runtime.tool_executor import ToolExecutor

    article = "# Title\n\n[[COVER]]\n\nIntro.\n\n[[IMG:1]]\n\nBody.\n\n[[IMG:2]]\n\nEnd."
    image_items = ["/images/cover.png", "/images/img1.png", "/images/img2.png"]
    meta_images = [
        {"id": "cover", "path": "/images/cover.png"},
        {"id": "1", "path": "/images/img1.png"},
        {"id": "2", "path": "/images/img2.png"},
    ]
    upstream = _make_upstream(article, image_items, meta_images)

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

        spec = NODE_SPEC_BY_TYPE["wechat_article_assemble"]
        node = WorkflowNode(spec=spec, x=0, y=0, params={
            "执行模式": "真实",
            "输出目录": str(work_dir),
            "插图策略": "按段落均匀插入",
        })
        executor = ToolExecutor()
        result = executor.execute(node, upstream)

        items = result["items"]
        assembled = Path(items[0]).read_text(encoding="utf-8")

        # 所有 marker 应被替换或删除
        assert "[[COVER]]" not in assembled
        assert "[[IMG:1]]" not in assembled
        assert "[[IMG:2]]" not in assembled

        # img1 和 img2 应在正确位置（不是均匀散布）
        assert "img1.png" in assembled
        assert "img2.png" in assembled

        # cover 应在 meta
        assert "cover.png" in result["meta"].get("cover_image", "")

        # inline_count 应只含插图（不含封面）
        assert result["meta"]["inline_count"] == 2
