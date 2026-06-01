from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.agent.settings import load_agent_settings
from app.models import WorkflowNode
from app.runtime.asr_outputs import collect_clean_script_files, sanitize_plain_script
from app.runtime.script_tasks import build_batch_tasks, fallback_rewrite


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT.parent


class ToolExecutionError(RuntimeError):
    pass


class ToolExecutor:
    def execute(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if node.spec.skill_binding:
            # 文生图节点：检测上游是否有结构化 image_prompts（来自 illustrator），走 batch 路径
            if node.spec.type == "skill_baoyu_image_gen" and _has_structured_prompts(upstream_outputs):
                return _stamp_output_finished_at(self._run_image_gen_batch(node, upstream_outputs))
            return _stamp_output_finished_at(self._run_skill_node(node, upstream_outputs))
        if node.spec.type == "skill_baoyu_article_illustrator":
            return _stamp_output_finished_at(self._run_article_illustrator(node, upstream_outputs))
        if node.spec.type == "article_md_import":
            return _stamp_output_finished_at(self._run_article_md_import(node))
        if node.spec.type == "wechat_article_assemble":
            return _stamp_output_finished_at(self._run_wechat_article_assemble(node, upstream_outputs))
        if node.spec.type == "douyin_profile_collect":
            return _stamp_output_finished_at(self._run_profile_collect(node))
        if node.spec.type == "douyin_video_download":
            return _stamp_output_finished_at(self._run_video_download(node, upstream_outputs))
        if node.spec.type == "asr_extract":
            return _stamp_output_finished_at(self._run_asr(node, upstream_outputs))
        if node.spec.type == "script_rewrite":
            return _stamp_output_finished_at(self._run_script_rewrite(node, upstream_outputs))
        if node.spec.type == "batch_mix":
            return _stamp_output_finished_at(self._run_batch_mix(node, upstream_outputs))
        if node.spec.type == "mediapush_publish":
            return _stamp_output_finished_at(self._run_mediapush_dispatch(node, upstream_outputs))
        raise ToolExecutionError(f"{node.spec.name} 还没有真实执行器，请先使用模拟模式")

    def _run_article_md_import(self, node: WorkflowNode) -> dict[str, Any]:
        md_file = _absolute_path(node.params.get("MD文件", ""))
        if not md_file.exists() or not md_file.is_file():
            raise ToolExecutionError(f"Markdown 文件不存在：{md_file}")
        if md_file.suffix.lower() not in {".md", ".markdown"}:
            raise ToolExecutionError("文章 MD 导入节点只接受 .md 或 .markdown 文件")
        text = md_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            raise ToolExecutionError(f"Markdown 文件内容为空：{md_file}")
        return {
            "type": "article_text",
            "items": [text],
            "meta": {"source_file": str(md_file), "format": "markdown", "chars": len(text)},
        }

    def _run_article_illustrator(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """专属执行器：调 LLM 生成配图方案 -> 锚点插入占位符 -> 两端口输出。

        article_text 端口：带 [[COVER]]/[[IMG:n]] 占位符的完整 Markdown。
        image_prompts 端口：结构化 id/kind/prompt 列表（写入 JSON 文件）。
        """
        article_items = _items_from_upstream(upstream_outputs, "article_text")
        if not article_items:
            raise ToolExecutionError("没有文章正文：请连接文章 MD 导入节点并先运行上游")
        article_text, _source_file = _read_article_item(article_items[0])
        if not article_text.strip():
            raise ToolExecutionError("文章正文为空，无法生成配图方案")

        settings = load_agent_settings()
        if not settings.api_key.strip():
            raise ToolExecutionError("配图方案节点真实运行需要先在总控配置 API Key")

        image_count = max(_as_int(node.params.get("配图数量"), 3), 1)
        extra_instruction = str(node.params.get("补充指令", "")).strip()

        system_prompt = (
            "你是专业的文章配图规划助手。分析文章结构，为合适位置规划配图方案。\n"
            "严格返回 JSON，不要包含任何其他文字。格式：\n"
            '{"anchors":[{"id":"cover","kind":"cover","prompt":"封面图片英文提示词","anchor":"定位锚点文本"},'
            '{"id":"1","kind":"illustration","prompt":"插图英文提示词","anchor":"定位锚点文本"}]}\n'
            "- id: cover 固定为封面，其余从 1 开始编号\n"
            "- kind: cover 或 illustration\n"
            "- prompt: 英文图片生成提示词，描述具体画面\n"
            "- anchor: 文章中的定位文本（章节标题或段落首句），用于确定占位符插入位置\n"
            f"- 插图数量不超过 {image_count} 张\n"
            "- [[COVER]] 应插入在文章标题/开头附近\n"
            "- [[IMG:n]] 应插入在对应 anchor 段落之前或之后"
        )
        instruction_line = f"补充要求：{extra_instruction}" if extra_instruction else ""
        user_prompt = f"{instruction_line}\n\n【文章内容】\n{article_text[:12000]}".strip()

        payload = {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
            "response_format": {"type": "json_object"},
        }
        try:
            content = self._chat_completion_content(settings.api_base, settings.api_key, payload, timeout=120)
        except (Exception, urllib.error.URLError) as exc:
            raise ToolExecutionError(f"调用配图模型失败：{exc}") from exc

        parsed = _extract_json(content)
        anchors = parsed.get("anchors") or parsed.get("images") or []
        if not anchors:
            raise ToolExecutionError("模型未返回有效的配图方案（缺少 anchors/images 数组）")

        marked_article = _insert_markers_by_anchors(article_text, anchors)

        image_prompts_items: list[dict[str, Any]] = []
        for a in anchors:
            entry = {
                "id": str(a.get("id", "")),
                "kind": str(a.get("kind", "illustration")),
                "prompt": str(a.get("prompt", "")),
            }
            if a.get("ar"):
                entry["ar"] = str(a["ar"])
            image_prompts_items.append(entry)

        output_dir = _absolute_path(node.params.get("输出目录", "outputs/illustrator"))
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        article_path = output_dir / f"marked_{stamp}.md"
        article_path.write_text(marked_article.strip() + "\n", encoding="utf-8")

        prompts_data = {
            "items": image_prompts_items,
            "meta": {"count": len(image_prompts_items), "source": "illustrator"},
        }
        prompts_path = output_dir / f"prompts_{stamp}.json"
        prompts_path.write_text(json.dumps(prompts_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # 多端口输出：article_text 为主端口，image_prompts 嵌套在返回对象中供
        # _items_from_upstream 发现。runner 会把这个 dict 赋给 node.last_output，
        # 下游节点通过 _items_from_upstream(upstream, "image_prompts") 读取。
        return {
            "type": "article_text",
            "items": [str(article_path)],
            "meta": {
                "marked_file": str(article_path),
                "image_prompts_file": str(prompts_path),
                "image_count": len(image_prompts_items),
                "marker_count": len(anchors),
            },
            "image_prompts": {
                "type": "image_prompts",
                "items": [str(prompts_path)],
                "meta": prompts_data["meta"],
            },
        }

    def _run_image_gen_batch(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """批量文生图：检测结构化 image_prompts → 构造 batch.json → bun 批量出图。

        上游来自 illustrator 的 image_prompts 端口（嵌套在 article_text 输出中）。
        每条 prompt 写为独立 .md，构造 baoyu batch.json，一次运行批量生成。
        兼容旧单 prompt .md 路径：非结构化输入回退到 _run_skill_node。
        """
        binding = node.spec.skill_binding or {}
        skill_path = Path(str(binding.get("skill_file", "")))
        if not skill_path.exists():
            raise ToolExecutionError(f"skill 文件不存在：{skill_path}")
        skill_dir = skill_path.parent
        script_rel = str(binding.get("script", "scripts/main.ts")).strip()
        script_path = (skill_dir / script_rel) if not Path(script_rel).is_absolute() else Path(script_rel)
        if not script_path.exists():
            raise ToolExecutionError(f"脚本不存在：{script_path}")

        runtime = _resolve_runtime(binding.get("runtime"), script_path)
        if runtime is None:
            raise ToolExecutionError(f"找不到运行该脚本的运行时（{binding.get('runtime')}），请在环境面板检查")

        # 收集结构化 prompts
        prompt_files = _items_from_upstream(upstream_outputs, "image_prompts")
        if not prompt_files:
            raise ToolExecutionError("没有配图提示词：请连接文章配图方案节点并先运行上游")

        # 读取 prompts JSON（来自 illustrator 的 prompts_{stamp}.json）
        prompts_json_path = Path(prompt_files[0])
        if not prompts_json_path.exists():
            raise ToolExecutionError(f"配图提示词文件不存在：{prompts_json_path}")
        prompts_data = json.loads(prompts_json_path.read_text(encoding="utf-8"))
        entries = prompts_data.get("items", [])
        if not entries:
            raise ToolExecutionError("配图提示词清单为空")

        # 节点参数
        provider = str(node.params.get("服务商", "jimeng")).strip() or "jimeng"
        model = str(node.params.get("模型", "")).strip()
        ar = str(node.params.get("比例", "16:9")).strip() or "16:9"

        # 工作目录
        work_dir = _absolute_path(f"outputs/skill_nodes/{node.spec.type}")
        work_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_run_dir = work_dir / f"batch_{stamp}"
        batch_run_dir.mkdir(parents=True, exist_ok=True)

        # 为每条 prompt 写独立 .md 文件，构造 batch tasks
        tasks: list[dict[str, Any]] = []
        for entry in entries:
            prompt_id = str(entry.get("id", ""))
            prompt_text = str(entry.get("prompt", ""))
            if not prompt_text.strip():
                continue
            prompt_md = batch_run_dir / f"prompt_{prompt_id}.md"
            prompt_md.write_text(prompt_text.strip(), encoding="utf-8")

            # 稳定的输出路径：batch run 目录下以 id 命名，如 cover.png, 1.png
            image_path = str((batch_run_dir / f"{prompt_id}.png").resolve())

            task: dict[str, Any] = {
                "id": prompt_id,
                "promptFiles": [str(prompt_md.resolve())],
                "image": image_path,
                "provider": provider,
                "ar": ar,
            }
            if model:
                task["model"] = model
            if entry.get("ar"):
                task["ar"] = str(entry["ar"])
            tasks.append(task)

        if not tasks:
            raise ToolExecutionError("没有有效的配图提示词（所有 prompt 为空）")

        # 构造 batch.json
        batch_json_path = batch_run_dir / "batch.json"
        batch_payload = {"jobs": 4, "tasks": tasks}
        batch_json_path.write_text(json.dumps(batch_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # 运行 bun scripts/main.ts --batchfile batch.json --json
        argv = list(runtime) + [str(script_path), "--batchfile", str(batch_json_path), "--json"]
        env = os.environ.copy()
        env.update(_resolve_env(binding.get("env", {}), node.params))

        try:
            proc = subprocess.run(
                argv, cwd=str(skill_dir), capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=900, env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToolExecutionError(f"启动批量出图脚本失败：{exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise ToolExecutionError(f"批量出图脚本退出码 {proc.returncode}：{tail}")

        stdout = (proc.stdout or "").strip()
        batch_result = _try_parse_json(stdout)
        if not isinstance(batch_result, dict):
            raise ToolExecutionError(f"批量出图脚本未返回有效 JSON：{stdout[:500]}")

        # 解析 stdout → meta.images=[{id,path}], items=[paths]
        images_list = batch_result.get("images") or []
        if not images_list:
            # fallback: look for items array
            images_list = batch_result.get("items") or []

        image_paths: list[str] = []
        meta_images: list[dict[str, str]] = []
        for img in images_list:
            if isinstance(img, dict):
                path = str(img.get("path", ""))
                img_id = str(img.get("id", ""))
            else:
                path = str(img)
                img_id = ""
            if path:
                image_paths.append(path)
            if img_id and path:
                meta_images.append({"id": img_id, "path": path})

        # 回退：stdout 未提供 id→path 映射时，用 task 的计划 image 路径补全
        if not meta_images:
            for task in tasks:
                task_id = task["id"]
                planned_path = task["image"]
                if planned_path not in image_paths:
                    image_paths.append(planned_path)
                meta_images.append({"id": task_id, "path": planned_path})

        return {
            "type": "image_list",
            "items": image_paths,
            "meta": {
                "images": meta_images,
                "count": len(image_paths),
                "batch_file": str(batch_json_path),
                "stdout": stdout[-2000:],
            },
        }

    def _run_wechat_article_assemble(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        article_items = _items_from_upstream(upstream_outputs, "article_text")
        if not article_items:
            raise ToolExecutionError("没有文章正文：请连接文章 MD 导入节点并先运行上游")

        article_text, source_file = _read_article_item(article_items[0])
        if not article_text.strip():
            raise ToolExecutionError("文章正文为空，无法装配")

        image_items = _items_from_upstream(upstream_outputs, "image_list")
        manual_cover = str(node.params.get("封面图", "")).strip()

        if _has_markers(article_text):
            # ──  Marker-aware path: use image_list.meta.images id→path mapping ──
            image_meta = _get_upstream_image_meta(upstream_outputs)
            assembled, cover_image, inline_images = _assemble_markdown_with_markers(
                article_text, image_meta,
            )
            # Fallback: no cover from markers → try manual_cover or first image item
            if not cover_image:
                if manual_cover:
                    cover_image = _normalize_media_ref(manual_cover)
                elif image_items:
                    normalized = [_normalize_media_ref(item) for item in image_items if str(item).strip()]
                    if normalized:
                        cover_image = normalized[0]
        else:
            # ── Legacy path: no markers → old strategy ──
            cover_image = _normalize_media_ref(manual_cover) if manual_cover else ""
            normalized_images = [_normalize_media_ref(item) for item in image_items if str(item).strip()]
            if not cover_image and normalized_images:
                cover_image = normalized_images[0]
            inline_images = [item for item in normalized_images if item != cover_image]
            strategy = str(node.params.get("插图策略", "按段落均匀插入")).strip()
            assembled = _assemble_markdown_with_images(article_text, cover_image, inline_images, strategy)

        output_dir = _absolute_path(node.params.get("输出目录", "outputs/articles"))
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"assembled_{stamp}.md"
        output_path.write_text(assembled.strip() + "\n", encoding="utf-8")

        return {
            "type": "article_text",
            "items": [str(output_path)],
            "meta": {
                "source_file": source_file,
                "assembled_file": str(output_path),
                "cover_image": cover_image,
                "inline_images": inline_images,
                "inline_count": len(inline_images),
            },
        }

    def _run_profile_collect(self, node: WorkflowNode) -> dict[str, Any]:
        profile_url = str(node.params.get("主页链接", "")).strip()
        if not profile_url:
            raise ToolExecutionError("请先填写抖音主页链接")
        cookie_file = str(node.params.get("Cookie文件", "")).strip()

        tool_dir = TOOLS_ROOT / "抖音主页链接采集"
        output_dir = _absolute_path(node.params.get("导出文件", "outputs/links.md")).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        max_count = _as_int(node.params.get("最大采集数量"), 50)
        page_size = min(max(max_count, 1), 50)
        max_pages = max((max_count + page_size - 1) // page_size, 1)

        code = r"""
import json
import sys
from pathlib import Path
from core.markdown_exporter import export_links_to_markdown
from core.profile_extractor import extract_profile_links

profile_url, output_dir, page_size, max_pages, cookie_file = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
result = extract_profile_links(profile_url=profile_url, page_size=page_size, max_pages=max_pages, cookie_file=cookie_file)
links = result["links"]
md_path = export_links_to_markdown(profile_url=profile_url, sec_uid=result["sec_uid"], links=links, output_dir=output_dir)
print(json.dumps({"links": links, "md_file": str(md_path), "total": len(links), "sec_uid": result["sec_uid"]}, ensure_ascii=False))
"""
        data = self._run_json_python(tool_dir, code, [profile_url, str(output_dir), str(page_size), str(max_pages), cookie_file])
        return {
            "type": "profile_links",
            "items": data.get("links", []),
            "meta": {"md_file": data.get("md_file"), "total": data.get("total"), "sec_uid": data.get("sec_uid")},
        }

    def _run_video_download(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        links = _items_from_upstream(upstream_outputs, "profile_links")
        if not links:
            raise ToolExecutionError("没有可下载链接：请连接主页采集节点，或先运行上游节点")

        tool_dir = TOOLS_ROOT / "抖音视频下载"
        output_dir = _absolute_path(node.params.get("保存目录", "outputs/downloads"))
        report_dir = PROJECT_ROOT / "runs" / "download_reports"
        cr_dir = tool_dir / "crtubeget_runtime"
        payload = {
            "links": links,
            "output_dir": str(output_dir),
            "report_dir": str(report_dir),
            "crtubeget_dir": str(cr_dir),
        }

        code = r"""
import json
import sys
from pathlib import Path
from downloader import YtDlpDownloader
from report import RunReport
from url_utils import validate_urls

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
valid, rejected = validate_urls("\n".join(payload["links"]))
report = RunReport()
for url in rejected:
    report.record(url, "skipped", "无效或不支持的链接")

downloader = YtDlpDownloader(crtubeget_dir=payload["crtubeget_dir"], prefer_crtubeget=True)
files = []
for url in valid:
    try:
        path = downloader.download(url, payload["output_dir"])
        files.append(str(path))
        report.record(url, "ok", str(path), str(path))
    except Exception as exc:
        report.record(url, "fail", str(exc))
report.finish()
md_path, json_path = report.save(payload["report_dir"])
print(json.dumps({"files": files, "summary": report.summary, "report_md": str(md_path), "report_json": str(json_path)}, ensure_ascii=False))
"""
        data = self._run_json_payload(tool_dir, code, payload)
        return {
            "type": "video_files",
            "items": data.get("files", []),
            "meta": {"summary": data.get("summary"), "report_md": data.get("report_md"), "report_json": data.get("report_json")},
        }

    def _run_asr(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        video_files = _items_from_upstream(upstream_outputs, "video_files")
        if not video_files:
            raise ToolExecutionError("没有可识别视频：请连接下载节点，或先运行上游节点")

        tool_dir = TOOLS_ROOT / "抖音文案提取"
        output_dir = _absolute_path(node.params.get("输出目录", "outputs/scripts"))
        output_dir.mkdir(parents=True, exist_ok=True)
        model = str(node.params.get("模型", "small")).strip() or "small"
        device = _normalize_asr_device(node.params.get("设备", "cpu"))

        input_path = Path(video_files[0])
        if len(video_files) > 1:
            list_path = PROJECT_ROOT / "runs" / "asr_input_hint.txt"
            list_path.parent.mkdir(parents=True, exist_ok=True)
            list_path.write_text("\n".join(video_files), encoding="utf-8")
            input_path = Path(video_files[0]).parent

        cmd = [
            sys.executable,
            "cli.py",
            str(input_path),
            "--model",
            model,
            "--device",
            device,
            "--compute-type",
            "int8",
            "--output-dir",
            str(output_dir),
        ]
        if not _as_bool(node.params.get("启用过滤器"), True):
            cmd.append("--no-clean")
        result = self._run_command(tool_dir, cmd, timeout=60 * 60)
        outputs = collect_clean_script_files(output_dir)
        if not outputs:
            raise ToolExecutionError("ASR 未生成纯文本 TXT 输出")
        for output in outputs:
            path = Path(output)
            text = sanitize_plain_script(path.read_text(encoding="utf-8", errors="ignore"))
            if _as_bool(node.params.get("LLM优化错别字断句"), True):
                text = self._optimize_asr_text_with_llm(text) or text
            path.write_text(text.strip() + "\n", encoding="utf-8")
        debug_files = sorted(str(path) for path in output_dir.glob("*.md")) + sorted(str(path) for path in output_dir.glob("*.json"))
        return {
            "type": "clean_scripts",
            "items": outputs,
            "meta": {"stdout": result.stdout[-2000:], "output_dir": str(output_dir), "input_count": len(video_files), "debug_files": debug_files},
        }

    def _run_script_rewrite(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        script_files = _items_from_upstream(upstream_outputs, "clean_scripts")
        if not script_files:
            raise ToolExecutionError("没有可改写文案：请连接 ASR 文案提取节点并先运行上游")

        output_dir = _absolute_path(node.params.get("输出目录", "outputs/batch_tasks"))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_count = max(_as_int(node.params.get("每条输出"), 1), 1)

        rewrites = []
        for script_file in script_files:
            text = sanitize_plain_script(Path(script_file).read_text(encoding="utf-8", errors="ignore"))
            base = self._rewrite_script_with_llm(text, node) or fallback_rewrite(text)
            for copy_index in range(output_count):
                item = dict(base)
                if copy_index:
                    item["title"] = f"{item['title']}{copy_index + 1}"[:16]
                rewrites.append(item)

        tasks = build_batch_tasks(
            rewrites,
            material_folder="",
            bgm_path="",
            output_dir="",
            output_count=1,
        )
        tasks_path = output_dir / "batch_tasks.json"
        tasks_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        rewrites_path = output_dir / "rewrites.json"
        rewrites_path.write_text(json.dumps({"items": rewrites}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "type": "batch_scripts",
            "items": [str(tasks_path)],
            "meta": {"task_count": len(tasks["tasks"]), "source_count": len(script_files), "rewrites_file": str(rewrites_path), "rewrites": rewrites},
        }

    def _run_skill_node(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """通用 Skill 节点执行器（阶段 4）：text/image 调模型，script 跑 skill 自带脚本。"""
        binding = node.spec.skill_binding or {}
        mode = str(binding.get("mode", "text"))
        in_port = str(binding.get("input_port") or (node.spec.inputs[0] if node.spec.inputs else "generic"))
        out_port = str(binding.get("output_port") or (node.spec.outputs[0] if node.spec.outputs else "generic"))

        skill_path = Path(str(binding.get("skill_file", "")))
        if not skill_path.exists():
            raise ToolExecutionError(f"skill 文件不存在：{skill_path}")

        # 脚本型 skill：跑它自带的脚本，不需要 API Key（脚本自带逻辑）
        if mode == "script":
            return self._run_script_skill(node, binding, skill_path, upstream_outputs, in_port, out_port)

        skill_prompt = skill_path.read_text(encoding="utf-8", errors="ignore").strip()
        settings = load_agent_settings()
        if not settings.api_key.strip():
            raise ToolExecutionError("Skill 节点真实运行需要先在总控配置 API Key")

        upstream_text = "\n\n".join(_items_from_upstream(upstream_outputs, in_port)) or "（无上游输入）"
        instruction = "\n".join(
            part for part in (
                str(binding.get("instruction", "")).strip(),
                str(node.params.get("补充指令", "")).strip(),
            ) if part
        )
        payload = {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": skill_prompt[:8000]},
                {"role": "user", "content": f"{instruction}\n\n【输入内容】\n{upstream_text[:8000]}".strip()},
            ],
            "temperature": 0.5,
        }
        try:
            content = self._chat_completion_content(settings.api_base, settings.api_key, payload, timeout=90)
        except (Exception, urllib.error.URLError) as exc:
            raise ToolExecutionError(f"调用 skill 模型失败：{exc}") from exc

        out_dir = _absolute_path(f"outputs/skill_nodes/{node.spec.type}")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        text_path = out_dir / f"{stamp}.md"
        text_path.write_text(content.strip(), encoding="utf-8")

        if mode == "image":
            images = self._generate_images(settings, content, out_dir, str(node.params.get("图像模型", "")).strip())
            if images:
                return {"type": "image_list", "items": images, "meta": {"prompt_file": str(text_path), "count": len(images)}}
            # 未配置/失败 → 优雅降级为提示词产物
            return {"type": out_port, "items": [str(text_path)], "meta": {"degraded": True, "note": "未接图像后端，仅产出配图提示词"}}

        return {"type": out_port, "items": [str(text_path)], "meta": {"skill": skill_path.parent.name, "chars": len(content)}}

    def _generate_images(self, settings, prompt_text: str, out_dir: Path, model: str) -> list[str]:
        """调用 OpenAI-compatible /images/generations 出图；失败返回 [] 让调用方降级。"""
        import base64

        payload = {"model": model or "gpt-image-1", "prompt": prompt_text[:3500], "n": 1}
        request = urllib.request.Request(
            settings.api_base.rstrip("/") + "/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
            saved: list[str] = []
            for i, item in enumerate(data.get("data", [])):
                img_path = out_dir / f"img_{datetime.now().strftime('%H%M%S')}_{i}.png"
                if item.get("b64_json"):
                    img_path.write_bytes(base64.b64decode(item["b64_json"]))
                elif item.get("url"):
                    with urllib.request.urlopen(item["url"], timeout=120) as r:
                        img_path.write_bytes(r.read())
                else:
                    continue
                saved.append(str(img_path))
            return saved
        except (Exception, urllib.error.URLError):
            return []

    def _run_script_skill(
        self,
        node: WorkflowNode,
        binding: dict[str, Any],
        skill_path: Path,
        upstream_outputs: list[dict[str, Any]],
        in_port: str,
        out_port: str,
    ) -> dict[str, Any]:
        """script 模式：运行 skill 自带脚本（脚本由 skill 作者提供，我们只负责调用）。"""
        skill_dir = skill_path.parent
        script_rel = str(binding.get("script", "")).strip()
        if not script_rel:
            raise ToolExecutionError("skill_binding 缺少 script（要运行的脚本路径）")
        script_path = (skill_dir / script_rel) if not Path(script_rel).is_absolute() else Path(script_rel)
        if not script_path.exists():
            raise ToolExecutionError(f"脚本不存在：{script_path}")

        runtime = _resolve_runtime(binding.get("runtime"), script_path)
        if runtime is None:
            raise ToolExecutionError(f"找不到运行该脚本的运行时（{binding.get('runtime')}），请在环境面板检查")

        work_dir = _absolute_path(f"outputs/skill_nodes/{node.spec.type}")
        work_dir.mkdir(parents=True, exist_ok=True)
        input_items = _items_from_upstream(upstream_outputs, in_port)
        input_path = _materialize_input(input_items, work_dir)

        # {output} 占位：脚本产物是文件（如出图）时，预生成输出路径供脚本写入
        args = list(binding.get("args", []))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_ext = str(binding.get("output_ext", "png")).lstrip(".")
        output_path = str(work_dir / f"out_{stamp}.{out_ext}") if any("{output}" in str(a) for a in args) else ""

        argv = list(runtime) + [str(script_path)] + _resolve_script_args(
            args, node.params, input_path, output_path
        )
        env = os.environ.copy()
        env.update(_resolve_env(binding.get("env", {}), node.params))
        try:
            proc = subprocess.run(
                argv, cwd=str(skill_dir), capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=600, env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToolExecutionError(f"启动脚本失败：{exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise ToolExecutionError(f"脚本退出码 {proc.returncode}：{tail}")

        stdout = (proc.stdout or "").strip()
        meta: dict[str, Any] = {"skill": skill_dir.name, "returncode": 0}
        # 产物优先取脚本写出的文件；否则回退 stdout 的 JSON/文本
        if output_path and Path(output_path).exists():
            items = [output_path]
        else:
            parsed = _try_parse_json(stdout)
            items = parsed.get("items") if isinstance(parsed, dict) and "items" in parsed else [stdout or str(input_path)]
            if isinstance(parsed, dict):
                meta.update({k: v for k, v in parsed.items() if k != "items"})
        return {"type": out_port, "items": items, "meta": meta}

    def _optimize_asr_text_with_llm(self, text: str) -> str | None:
        settings = load_agent_settings()
        if not text.strip() or not settings.api_key.strip():
            return None
        payload = {
            "model": settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是专业的 ASR 文案校对助手。只补全标点、合理断句、纠正明显错别字；"
                        "不改写、不扩写、不添加标题或解释。只输出口播文案本身。"
                    ),
                },
                {"role": "user", "content": f"【原始文案】\n{text[:6000]}"},
            ],
            "temperature": 0.3,
        }
        try:
            content = self._chat_completion_content(settings.api_base, settings.api_key, payload, timeout=60)
        except (Exception, urllib.error.URLError):
            return None
        return sanitize_plain_script(content) if content else None

    def _rewrite_script_with_llm(self, text: str, node: WorkflowNode) -> dict[str, str] | None:
        settings = load_agent_settings()
        if not settings.api_key.strip():
            return None
        skill_path = str(node.params.get("改写SKILL文件", "")).strip()
        skill_prompt = ""
        if skill_path:
            path = _absolute_path(skill_path)
            if not path.exists():
                raise ToolExecutionError(f"改写 SKILL 文件不存在: {path}")
            skill_prompt = path.read_text(encoding="utf-8", errors="ignore").strip()
        prompt = (
            "请把下面的口播文案改写成适合短视频混剪生产的文案，并生成标题。"
            f"改写风格：{node.params.get('改写风格', '爆款短视频')}。"
            f"标题规则：{node.params.get('标题规则', '≤16字')}。"
            "只返回 JSON，格式为："
            '{"rewritten":"改写后的文案","title":"标题","cover_text":"封面词"}。'
            f"\n\n原文：\n{text[:6000]}"
        )
        payload = {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": (skill_prompt + "\n\n" if skill_prompt else "") + "你是短视频文案改写助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        }
        try:
            content = self._chat_completion_content(settings.api_base, settings.api_key, payload, timeout=60)
            start = content.find("{")
            end = content.rfind("}") + 1
            parsed = json.loads(content[start:end])
        except (Exception, urllib.error.URLError):
            return None
        rewritten = str(parsed.get("rewritten") or "").strip()
        if not rewritten:
            return None
        title = str(parsed.get("title") or "").strip()[:16] or fallback_rewrite(rewritten)["title"]
        cover_text = str(parsed.get("cover_text") or "").strip()[:4] or title[:4]
        return {"rewritten": rewritten, "title": title, "cover_text": cover_text}

    @staticmethod
    def _chat_completion_content(api_base: str, api_key: str, payload: dict[str, Any], timeout: int) -> str:
        request = urllib.request.Request(
            api_base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"])

    def _run_batch_mix(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        task_files = _items_from_upstream(upstream_outputs, "batch_scripts")
        if not task_files:
            raise ToolExecutionError("没有批量任务 JSON：请连接文案改写/标题节点并先运行上游")

        batch_tool = TOOLS_ROOT / "抖音批量视频生成"
        _ensure_batch_tool_ffmpeg(batch_tool)
        source_tasks = json.loads(Path(task_files[0]).read_text(encoding="utf-8"))
        tasks = source_tasks.get("tasks", [])
        if not tasks:
            raise ToolExecutionError("批量任务 JSON 为空")

        self._update_batch_tool_config(node)
        material_folder = str(_absolute_path(node.params.get("素材库", "materials")))
        bgm_file = _resolve_bgm_path(node.params.get("BGM文件", ""))
        output_dir = str(_absolute_path(node.params.get("输出目录", "outputs/videos")))
        output_count = max(_as_int(node.params.get("生成数量"), 1), 1)
        per_task_count = max(output_count // max(len(tasks), 1), 1)

        for task in tasks:
            task["material_folder"] = material_folder
            task["bgm_path"] = bgm_file
            task["output_dir"] = output_dir
            task["output_count"] = per_task_count
            task["tts_voice"] = str(node.params.get("音色", "")).strip() or None
            task["tts_speed"] = _as_float(node.params.get("语速"), 1.0)
            task["tts_volume"] = _as_int(node.params.get("音量"), 100)
            task["segment_mode"] = str(node.params.get("分段模式", "按文案分段")).strip()
            task["min_segment_duration"] = _as_float(node.params.get("最短分段秒数"), 1.8)
            task["split_duration"] = _as_float(node.params.get("均分时长秒数"), 3.0)
            task["split_count"] = _as_int(node.params.get("均分段数"), 6)
            task["resolution"] = str(node.params.get("输出分辨率", "1080x1920")).strip()
            task["fps"] = _as_int(node.params.get("输出帧率"), 30)
            task["bgm_volume"] = _as_int(node.params.get("BGM音量"), 30)
            task["cover_bg_path"] = str(node.params.get("封面底图", "")).strip()

        run_dir = PROJECT_ROOT / "runs" / "batch_mix"
        run_dir.mkdir(parents=True, exist_ok=True)
        tasks_path = run_dir / f"tasks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        tasks_path.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
        result = self._run_command(batch_tool, [sys.executable, "main.py", "batch", "--tasks", str(tasks_path)], timeout=60 * 60 * 4)
        videos = sorted(str(path) for path in Path(output_dir).glob("*.mp4"))
        if not videos:
            raise ToolExecutionError("批量混剪没有生成任何视频。\n" + result.stdout[-3000:])
        if "视频生成失败" in result.stdout:
            raise ToolExecutionError("批量混剪有任务生成失败。\n" + result.stdout[-3000:])
        return {
            "type": "rendered_videos",
            "items": videos,
            "meta": {"tasks_file": str(tasks_path), "stdout": result.stdout[-2000:], "output_dir": output_dir},
        }

    @staticmethod
    def _update_batch_tool_config(node: WorkflowNode) -> None:
        text_mapping = {
            "TTS App ID": "volcengine_app_id",
            "TTS Token": "volcengine_token",
            "TTS Resource ID": "volcengine_resource_id",
            "字幕字体": "subtitle_font",
            "字幕颜色": "subtitle_color",
            "描边颜色": "subtitle_outline_color",
        }
        int_mapping = {
            "字幕字号": ("subtitle_font_size", 52),
            "字幕位置Y": ("subtitle_position_y", 80),
            "描边粗细": ("subtitle_outline_size", 2),
            "最大字数": ("subtitle_max_chars", 0),
        }
        bool_mapping = {
            "字幕描边": ("subtitle_outline", True),
            "字幕阴影": ("subtitle_shadow", True),
        }
        float_mapping = {
            "字幕偏移秒": ("subtitle_offset_sec", 0.15),
        }
        updates: dict[str, Any] = {}
        for source, target in text_mapping.items():
            value = str(node.params.get(source, "")).strip()
            if value:
                updates[target] = value
        for source, (target, default) in int_mapping.items():
            if source in node.params:
                updates[target] = _as_int(node.params.get(source), default)
        for source, (target, default) in bool_mapping.items():
            if source in node.params:
                updates[target] = _as_bool(node.params.get(source), default)
        for source, (target, default) in float_mapping.items():
            if source in node.params:
                updates[target] = _as_float(node.params.get(source), default)
        if not updates:
            return
        config_path = TOOLS_ROOT / "抖音批量视频生成" / "config" / "settings.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        data.update(updates)
        config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _run_mediapush_dispatch(self, node: WorkflowNode, upstream_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        video_files = _items_from_upstream(upstream_outputs, "rendered_videos")
        if not video_files:
            raise ToolExecutionError("没有可发布视频：请连接批量混剪生成节点并先运行上游")

        inbox_dir = _absolute_path(node.params.get("Inbox目录", r"J:\MagicTool\emdia\MediaPush\inbox"))
        slot_name = str(node.params.get("时段名", "manual")).strip() or "manual"
        scheduled_text = str(node.params.get("发布时间", "")).strip()
        scheduled_time = datetime.fromisoformat(scheduled_text) if scheduled_text else datetime.now() + timedelta(hours=2)
        copy_files = bool(node.params.get("复制文件", True))

        batch_tool = TOOLS_ROOT / "抖音批量视频生成"
        code = r"""
import json
import sys
from datetime import datetime
from core.mediapush_dispatcher import write_batch

payload = json.loads(sys.argv[1])
batch_dir = write_batch(
    payload["inbox_dir"],
    payload["video_files"],
    datetime.fromisoformat(payload["scheduled_time"]),
    payload["slot_name"],
    move=not payload["copy_files"],
)
print(json.dumps({"batch_dir": str(batch_dir)}, ensure_ascii=False))
"""
        payload = {
            "inbox_dir": str(inbox_dir),
            "video_files": video_files,
            "scheduled_time": scheduled_time.isoformat(timespec="seconds"),
            "slot_name": slot_name,
            "copy_files": copy_files,
        }
        data = self._run_json_python(batch_tool, code, [json.dumps(payload, ensure_ascii=False)])
        return {
            "type": "publish_records",
            "items": [data["batch_dir"]],
            "meta": {"scheduled_time": payload["scheduled_time"], "video_count": len(video_files)},
        }

    def _run_json_payload(self, cwd: Path, code: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)
            payload_path = Path(fp.name)
        try:
            return self._run_json_python(cwd, code, [str(payload_path)])
        finally:
            payload_path.unlink(missing_ok=True)

    def _run_json_python(self, cwd: Path, code: str, args: list[str]) -> dict[str, Any]:
        result = self._run_command(cwd, [sys.executable, "-c", code, *args], timeout=60 * 30)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise ToolExecutionError("工具没有返回 JSON 输出")
        try:
            return json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(f"工具输出不是有效 JSON: {lines[-1]}") from exc

    @staticmethod
    def _run_command(cwd: Path, cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        if not cwd.exists():
            raise ToolExecutionError(f"工具目录不存在: {cwd}")
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            startupinfo=startupinfo,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            raise ToolExecutionError(message[-2000:] or f"工具执行失败，退出码 {result.returncode}")
        return result


def _absolute_path(value: Any) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "开启", "是"}


def _normalize_asr_device(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"gpu", "cuda", "显卡"}:
        return "cuda"
    return "cpu"


def _stamp_output_finished_at(output: dict[str, Any]) -> dict[str, Any]:
    output.setdefault("meta", {})
    output["meta"]["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return output


# —— 脚本型 Skill 节点辅助（阶段 4 script 模式）——

def _find_bun() -> str | None:
    """找 bun：先 PATH，再官方安装器默认位置（PATH 未刷新时兜底）。"""
    found = shutil.which("bun")
    if found:
        return found
    default = Path.home() / ".bun" / "bin" / ("bun.exe" if sys.platform == "win32" else "bun")
    return str(default) if default.exists() else None


def _resolve_runtime(runtime: Any, script_path: Path) -> list[str] | None:
    """把 skill_binding.runtime 解析成 argv 前缀；未指定时按脚本扩展名推断。None=找不到。"""
    if runtime:
        argv = list(runtime) if isinstance(runtime, list) else str(runtime).split()
        # 显式指定 bun 但 PATH 没有时，替换成可用的绝对路径
        if argv and argv[0] == "bun":
            bun = _find_bun()
            if bun:
                argv[0] = bun
        return argv
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return ["py", "-3.13"] if shutil.which("py") else [sys.executable]
    if suffix in {".ts", ".js", ".mjs"}:
        bun = _find_bun()
        if bun:
            return [bun]
        if shutil.which("npx"):
            return ["npx", "-y", "bun"]
    return None


def _subst_token(tok: str, params: dict[str, Any], input_path: str, output_path: str = "") -> tuple[str, bool]:
    """返回 (取值, 是否占位符)。支持 {input}、{output} 与 {param:参数名}。"""
    if tok == "{input}":
        return input_path, True
    if tok == "{output}":
        return output_path, True
    if tok.startswith("{param:") and tok.endswith("}"):
        return str(params.get(tok[len("{param:"):-1], "")).strip(), True
    if tok.startswith("{cred:") and tok.endswith("}"):
        from app.runtime.credentials import get_credential_value
        return get_credential_value(tok[len("{cred:"):-1]), True
    return tok, False


def _resolve_script_args(templates: list[Any], params: dict[str, Any], input_path: str, output_path: str = "") -> list[str]:
    """按模板生成 argv 参数。占位符解析为空时，丢弃该值及其前置 flag（处理可选参数）。"""
    out: list[str] = []
    for tok in templates:
        value, is_ph = _subst_token(str(tok), params, input_path, output_path)
        if is_ph and value == "":
            if out:
                out.pop()
            continue
        out.append(value)
    return out


def _resolve_env(env_map: dict[str, Any], params: dict[str, Any]) -> dict[str, str]:
    """把 skill_binding.env 的模板解析成环境变量（仅注入非空值）。"""
    resolved: dict[str, str] = {}
    for key, tmpl in (env_map or {}).items():
        value, _ = _subst_token(str(tmpl), params, "")
        if value:
            resolved[str(key)] = value
    return resolved


def _materialize_input(input_items: list[str], work_dir: Path) -> str:
    """把上游输入收敛成一个文件路径供脚本消费：已是文件则直用，否则文本写临时 .md。"""
    if not input_items:
        return ""
    first = Path(str(input_items[0]))
    if first.exists() and first.is_file():
        return str(first)
    out = work_dir / f"input_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text("\n\n".join(str(x) for x in input_items), encoding="utf-8")
    return str(out)


def _read_article_item(item: str) -> tuple[str, str]:
    """article_text 端口既可能传正文文本，也可能传已落盘的 Markdown 文件路径。"""
    path = Path(str(item))
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8", errors="ignore"), str(path.resolve())
    return str(item), ""


def _normalize_media_ref(value: str) -> str:
    text = str(value or "").strip()
    if not text or text.startswith(("http://", "https://")):
        return text
    path = _absolute_path(text)
    return str(path)


def _assemble_markdown_with_images(article_text: str, cover_image: str, inline_images: list[str], strategy: str) -> str:
    lines: list[str] = []
    if cover_image:
        lines.extend([f"![封面]({cover_image})", ""])

    article_body = article_text.strip()
    if not inline_images:
        lines.append(article_body)
        return "\n".join(lines)

    blocks = [block.strip() for block in re.split(r"\n\s*\n", article_body) if block.strip()]
    if not blocks:
        blocks = [article_body]

    if strategy == "追加到文末":
        lines.append("\n\n".join(blocks))
        for index, image in enumerate(inline_images, start=1):
            lines.extend(["", f"![插图 {index}]({image})"])
        return "\n".join(lines)

    insert_after: dict[int, list[tuple[int, str]]] = {}
    block_count = len(blocks)
    for index, image in enumerate(inline_images, start=1):
        position = min(block_count - 1, max(0, round(index * block_count / (len(inline_images) + 1)) - 1))
        insert_after.setdefault(position, []).append((index, image))

    for block_index, block in enumerate(blocks):
        lines.append(block)
        for image_index, image in insert_after.get(block_index, []):
            lines.extend(["", f"![插图 {image_index}]({image})"])
        if block_index != block_count - 1:
            lines.append("")
    return "\n".join(lines)


def _has_markers(article_text: str) -> bool:
    """检测文章是否包含 [[IMG:...]] 或 [[COVER]] 占位符。"""
    return bool(re.search(r"\[\[(IMG:\w+|COVER)\]\]", article_text))


def _get_upstream_image_meta(upstream_outputs: list[dict[str, Any]]) -> dict[str, str]:
    """从上游 image_list 的 meta.images 提取 id→path 映射。"""
    for output in upstream_outputs:
        if output.get("type") == "image_list":
            meta = output.get("meta", {})
            images = meta.get("images", [])
            if images:
                return {str(img["id"]): str(img["path"]) for img in images if "id" in img and "path" in img}
    return {}


def _assemble_markdown_with_markers(
    article_text: str,
    image_map: dict[str, str],
) -> tuple[str, str, list[str]]:
    """替换 [[IMG:id]] 为 Markdown 图片语法，移除 [[COVER]]，返回 (assembled, cover_image, inline_images)。

    - [[IMG:id]]: 替换为 ![](path)，未匹配则静默删除。
    - [[COVER]]: 从正文删除；cover_image 取自 id='cover' 的映射。
    - 封面图不作为内联图片插入正文。
    - 无标记时回退到旧策略（由调用方处理）。
    """
    cover_image = image_map.get("cover", "")

    # Remove [[COVER]] from body
    body = re.sub(r"\[\[COVER\]\]\s*\n?", "", article_text)

    # Collect inline image paths
    inline_images: list[str] = []

    def _replace_img(match: re.Match) -> str:
        img_id = match.group(1)
        path = image_map.get(img_id)
        if path:
            inline_images.append(path)
            return f"![]({path})"
        # Unmatched: silently remove
        return ""

    body = re.sub(r"\[\[IMG:(\w+)\]\]", _replace_img, body)

    # Clean up double blank lines from removals
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return body, cover_image, inline_images


def _try_parse_json(text: str) -> Any:
    """尝试把脚本 stdout 解析为 JSON（整体或最后一行）；失败返回 None。"""
    text = (text or "").strip()
    candidates = [text]
    if "\n" in text:
        candidates.append(text.splitlines()[-1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _resolve_bgm_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = _absolute_path(text)
    if path.is_file():
        return str(path)
    if path.is_dir():
        for suffix in (".mp3", ".wav", ".aac", ".flac", ".m4a"):
            matches = sorted(item for item in path.rglob(f"*{suffix}") if item.is_file())
            if matches:
                return str(matches[0].resolve())
    return text


def _ensure_batch_tool_ffmpeg(batch_tool: Path) -> None:
    target_dir = batch_tool / "ffmpeg"
    target_ffmpeg = target_dir / "ffmpeg.exe"
    target_ffprobe = target_dir / "ffprobe.exe"

    source_dir = Path(r"J:\MagicTool\Standalone\VideoCut\video_tool\ffmpeg")
    source_ffmpeg = source_dir / "ffmpeg.exe"
    source_ffprobe = source_dir / "ffprobe.exe"
    if not source_ffmpeg.exists() or not source_ffprobe.exists():
        raise ToolExecutionError(f"批量混剪需要 FFmpeg，但未找到源文件: {source_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    for source_file in source_dir.iterdir():
        if source_file.is_file():
            target_file = target_dir / source_file.name
            if not target_file.exists() or target_file.stat().st_size != source_file.stat().st_size:
                shutil.copy2(source_file, target_file)
    if not target_ffmpeg.exists() or not target_ffprobe.exists():
        raise ToolExecutionError(f"批量混剪 FFmpeg 补齐失败: {target_dir}")


def _items_from_upstream(upstream_outputs: list[dict[str, Any]], output_type: str) -> list[str]:
    items: list[str] = []
    for output in upstream_outputs:
        if output.get("type") == output_type:
            items.extend(str(item) for item in output.get("items", []))
        elif output_type in output and isinstance(output[output_type], dict):
            # 多端口节点：如 illustrator 返回 {"type":"article_text", "image_prompts":{...}}
            nested = output[output_type]
            items.extend(str(item) for item in nested.get("items", []))
    return items


def _has_structured_prompts(upstream_outputs: list[dict[str, Any]]) -> bool:
    """检测上游 image_prompts 是否来自 illustrator（结构化 JSON 而非旧单 .md）。"""
    prompt_items = _items_from_upstream(upstream_outputs, "image_prompts")
    if not prompt_items:
        return False
    first = prompt_items[0]
    if not first.endswith(".json"):
        return False
    try:
        data = json.loads(Path(first).read_text(encoding="utf-8"))
        items = data.get("items", [])
        return bool(items) and all(isinstance(i, dict) and "id" in i for i in items)
    except (json.JSONDecodeError, OSError):
        return False


def _extract_json(text: str) -> dict[str, Any]:
    """从模型返回文本中提取 JSON 对象；优先整体解析，否则取首尾花括号。"""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return {}


def _insert_markers_by_anchors(article_text: str, anchors: list[dict[str, Any]]) -> str:
    """按锚点文本在完整原文中插入 [[COVER]] 和 [[IMG:n]] 占位符。

    策略：
    - [[COVER]]：插在第一个标题后（或文首）。
    - [[IMG:n]]：在匹配到 anchor 文本的段落行之后插入。
    - 未匹配到的锚点追加到文末。
    - 完整原文内容不丢失。
    """
    lines = article_text.splitlines(keepends=True)
    result_lines: list[str] = []

    cover_anchors = [a for a in anchors if str(a.get("kind", "")).lower() == "cover"]
    ill_anchors = [a for a in anchors if str(a.get("kind", "")).lower() != "cover"]

    anchor_map: dict[str, str] = {}
    for a in ill_anchors:
        anchor_text = str(a.get("anchor", "")).strip()
        if anchor_text:
            anchor_map[anchor_text] = str(a.get("id", "?"))

    inserted_cover = False
    inserted_ids: set[str] = set()

    for line in lines:
        result_lines.append(line)

        if not inserted_cover and line.strip().startswith("#"):
            result_lines.append("[[COVER]]\n")
            inserted_cover = True

        line_stripped = line.strip()
        for anchor_text, img_id in list(anchor_map.items()):
            if img_id not in inserted_ids and anchor_text in line_stripped:
                result_lines.append(f"[[IMG:{img_id}]]\n")
                inserted_ids.add(img_id)

    if not inserted_cover:
        result_lines.insert(0, "[[COVER]]\n")

    for anchor_text, img_id in anchor_map.items():
        if img_id not in inserted_ids:
            result_lines.append(f"\n[[IMG:{img_id}]]\n")

    return "".join(result_lines)
