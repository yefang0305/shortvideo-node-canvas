from __future__ import annotations

import re
from typing import Any


def fallback_rewrite(text: str) -> dict[str, str]:
    cleaned = _clean_text(text)
    first = re.split(r"[。！？!?；;\n]", cleaned, maxsplit=1)[0].strip()
    title = re.sub(r"\s+", "", first)[:16] or "短视频文案"
    return {
        "title": title,
        "cover_text": title[:4],
        "rewritten": cleaned,
    }


def build_batch_tasks(
    rewrites: list[dict[str, str]],
    *,
    material_folder: str,
    bgm_path: str,
    output_dir: str,
    output_count: int,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tasks = []
    extra_params = extra_params or {}
    for index, item in enumerate(rewrites, start=1):
        title = item.get("title") or f"task_{index}"
        task = {
            "name": title,
            "script_text": item.get("rewritten", ""),
            "title": title,
            "cover_text": item.get("cover_text", title[:4]),
            "material_folder": material_folder,
            "bgm_path": bgm_path,
            "output_dir": output_dir,
            "output_count": output_count,
            "use_timestamps": True,
        }
        task.update(extra_params)
        tasks.append(task)
    return {"tasks": tasks}


def _clean_text(text: str) -> str:
    text = re.sub(r"^#.*$", "", text, flags=re.M)
    text = re.sub(r"\[[0-9:.\-> ]+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
