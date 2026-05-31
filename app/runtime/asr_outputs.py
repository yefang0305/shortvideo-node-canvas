from __future__ import annotations

import re
from pathlib import Path


TIMESTAMP_PREFIX = re.compile(r"^\s*\[[0-9:.]+s?\s*[–-]\s*[0-9:.]+s?\]\s*")


def collect_clean_script_files(output_dir: Path) -> list[str]:
    return sorted(str(path) for path in output_dir.glob("*.txt") if path.is_file())


def sanitize_plain_script(text: str) -> str:
    lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("**"):
            continue
        line = TIMESTAMP_PREFIX.sub("", line).strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines).strip()
