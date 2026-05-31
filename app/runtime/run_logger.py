from __future__ import annotations

from datetime import datetime
from pathlib import Path


class RunLogger:
    def __init__(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = log_dir / f"run_{stamp}.log"

    def write(self, message: str) -> None:
        time_text = datetime.now().strftime("%H:%M:%S")
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(f"[{time_text}] {message}\n")

