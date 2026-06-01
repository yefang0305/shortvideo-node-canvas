"""Task 2: 文生图 batch 多图 — 检测结构化 image_prompts → 构造 batch.json → 批量出图。

TDD: mock subprocess.run 返回固定 JSON，验证 batch.json 结构 + meta.images id→path 映射。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode

# _run_image_gen_batch uses subprocess.run from its own module namespace
_EXECUTOR_SUBPROCESS = "app.runtime.tool_executor.subprocess.run"


# ── helpers ──────────────────────────────────────────────────────────────

def _make_image_gen_node(**overrides) -> WorkflowNode:
    spec = NODE_SPEC_BY_TYPE["skill_baoyu_image_gen"]
    params = dict(spec.default_params)
    params.update(overrides.pop("params", {}))
    params.setdefault("执行模式", "真实")
    return WorkflowNode(spec=spec, x=0, y=0, params=params, **overrides)


def _structured_upstream(prompts_items: list[dict], work_dir: Path) -> list[dict]:
    """模拟 illustrator 输出的 image_prompts 端口（嵌套在 article_text 输出中）。"""
    prompts_data = {"items": prompts_items, "meta": {"count": len(prompts_items), "source": "illustrator"}}
    prompts_path = work_dir / "prompts_test.json"
    prompts_path.write_text(json.dumps(prompts_data, ensure_ascii=False), encoding="utf-8")
    return [{
        "type": "article_text",
        "items": ["dummy.md"],
        "meta": {},
        "image_prompts": {
            "type": "image_prompts",
            "items": [str(prompts_path)],
            "meta": prompts_data["meta"],
        },
    }]


def _legacy_upstream(prompt_text: str, work_dir: Path) -> list[dict]:
    """模拟旧单 prompt .md 文件输入。"""
    prompt_path = work_dir / "single_prompt.md"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    return [{"type": "image_prompts", "items": [str(prompt_path)], "meta": {}}]


# ── mock batch stdout ────────────────────────────────────────────────────

MOCK_BATCH_STDOUT = json.dumps({
    "images": [
        {"id": "cover", "path": "outputs/skill_nodes/skill_baoyu_image_gen/cover.png"},
        {"id": "1", "path": "outputs/skill_nodes/skill_baoyu_image_gen/img_1.png"},
        {"id": "2", "path": "outputs/skill_nodes/skill_baoyu_image_gen/img_2.png"},
    ]
})


# ── tests ────────────────────────────────────────────────────────────────

def test_image_gen_batch_detects_structured_prompts():
    """检测到结构化 image_prompts 时应走 batch 路径，构造 batch.json。"""
    from app.runtime.tool_executor import ToolExecutor

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        node = _make_image_gen_node(params={"输出目录": str(work_dir), "服务商": "jimeng", "模型": "jimeng_t2i_v40"})

        prompts = [
            {"id": "cover", "kind": "cover", "prompt": "cyberpunk city night"},
            {"id": "1", "kind": "illustration", "prompt": "data flow digital art"},
            {"id": "2", "kind": "illustration", "prompt": "AI neural network abstract"},
        ]
        upstream = _structured_upstream(prompts, work_dir)
        executor = ToolExecutor()

        with patch(_EXECUTOR_SUBPROCESS) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = MOCK_BATCH_STDOUT
            mock_run.return_value.stderr = ""

            result = executor.execute(node, upstream)

        assert mock_run.call_count >= 1
        cmd_args = mock_run.call_args[0][0] if mock_run.call_args else []
        assert "--batchfile" in cmd_args, f"--batchfile not found in args: {cmd_args}"
        batchfile_idx = cmd_args.index("--batchfile")
        batchfile_path = Path(cmd_args[batchfile_idx + 1])
        assert batchfile_path.exists(), f"batch.json not written: {batchfile_path}"

        # 验证 batch.json 结构
        batch = json.loads(batchfile_path.read_text(encoding="utf-8"))
        assert len(batch["tasks"]) == 3, f"expected 3 tasks, got {len(batch['tasks'])}"

        for i, task in enumerate(batch["tasks"]):
            expected = prompts[i]
            assert task["id"] == expected["id"], f"task {i} id mismatch"
            assert len(task["promptFiles"]) == 1
            prompt_file = Path(task["promptFiles"][0])
            assert prompt_file.exists()
            assert prompt_file.read_text(encoding="utf-8").strip() == expected["prompt"]
            assert task["provider"] == "jimeng"
            assert task["model"] == "jimeng_t2i_v40"
            # image 字段：每个 task 必须有稳定的输出路径
            assert "image" in task, f"task {i} missing image field"
            assert task["image"].endswith(f"{expected['id']}.png"), f"task {i} image path should end with {expected['id']}.png, got {task['image']}"

        # 验证输出 image_list 结构
        assert result["type"] == "image_list"
        assert len(result["items"]) == 3
        assert "images" in result["meta"]
        id_map = {img["id"]: img["path"] for img in result["meta"]["images"]}
        assert id_map["cover"].endswith("cover.png")
        assert id_map["1"].endswith("img_1.png")
        assert id_map["2"].endswith("img_2.png")
        assert result["meta"]["count"] == 3


def test_image_gen_batch_legacy_fallback():
    """非结构化 prompts（旧单 .md）应回退到 legacy 路径，走 _run_skill_node。"""
    from app.runtime.tool_executor import ToolExecutor

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        node = _make_image_gen_node(params={"输出目录": str(work_dir), "服务商": "openrouter"})
        upstream = _legacy_upstream("A single prompt for one image", work_dir)
        executor = ToolExecutor()

        with patch(_EXECUTOR_SUBPROCESS) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({"items": ["out.png"], "count": 1})
            mock_run.return_value.stderr = ""

            result = executor.execute(node, upstream)

        cmd_args = mock_run.call_args[0][0] if mock_run.call_args else []
        assert "--promptfiles" in cmd_args, f"legacy should use --promptfiles, got: {cmd_args}"
        assert "--batchfile" not in cmd_args
        assert result["type"] == "image_list"


def test_image_gen_batch_meta_images_mapping():
    """meta.images 的 id→path 映射必须与输入的 prompt id 一一对应。"""
    from app.runtime.tool_executor import ToolExecutor

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        node = _make_image_gen_node(params={"输出目录": str(work_dir), "服务商": "jimeng", "模型": "jimeng_t2i_v40"})

        prompts = [
            {"id": "cover", "kind": "cover", "prompt": "cover image"},
            {"id": "1", "kind": "illustration", "prompt": "illustration 1"},
        ]
        upstream = _structured_upstream(prompts, work_dir)
        executor = ToolExecutor()

        stdout = json.dumps({
            "images": [
                {"id": "cover", "path": "outputs/cover.png"},
                {"id": "1", "path": "outputs/img1.png"},
            ]
        })

        with patch(_EXECUTOR_SUBPROCESS) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = stdout
            mock_run.return_value.stderr = ""
            result = executor.execute(node, upstream)

        assert result["meta"]["count"] == 2
        images = result["meta"]["images"]
        assert len(images) == 2
        for img in images:
            assert img["path"] in result["items"], f"{img['path']} not in items"


def test_image_gen_batch_respects_node_params():
    """batch.json 的 provider/model/ar 应从节点参数读取。"""
    from app.runtime.tool_executor import ToolExecutor

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        node = _make_image_gen_node(params={
            "输出目录": str(work_dir),
            "服务商": "dashscope",
            "模型": "flux-dev",
            "比例": "1:1",
        })

        prompts = [{"id": "1", "kind": "illustration", "prompt": "test"}]
        upstream = _structured_upstream(prompts, work_dir)
        executor = ToolExecutor()

        stdout = json.dumps({"images": [{"id": "1", "path": "out.png"}]})

        with patch(_EXECUTOR_SUBPROCESS) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = stdout
            mock_run.return_value.stderr = ""
            executor.execute(node, upstream)

        cmd_args = mock_run.call_args[0][0]
        batchfile_idx = cmd_args.index("--batchfile")
        batchfile_path = Path(cmd_args[batchfile_idx + 1])
        batch = json.loads(batchfile_path.read_text(encoding="utf-8"))
        task = batch["tasks"][0]
        assert task["provider"] == "dashscope"
        assert task["model"] == "flux-dev"
        assert task["ar"] == "1:1"
