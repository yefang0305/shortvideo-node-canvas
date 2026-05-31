import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime.asr_outputs import collect_clean_script_files, sanitize_plain_script


class ASROutputTests(unittest.TestCase):
    def test_collect_clean_script_files_only_returns_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("口播文案", encoding="utf-8")
            (root / "a.md").write_text("# 标题\n\n口播文案", encoding="utf-8")
            (root / "a.json").write_text("{}", encoding="utf-8")

            files = collect_clean_script_files(root)

        self.assertEqual([Path(path).suffix for path in files], [".txt"])

    def test_sanitize_plain_script_removes_markdown_and_timestamp_lines(self):
        text = "# 视频标题\n\n**语言**: zh\n\n[0.0s - 1.2s] 你好世界\n\n真正的口播。"

        cleaned = sanitize_plain_script(text)

        self.assertEqual(cleaned, "你好世界\n\n真正的口播。")


if __name__ == "__main__":
    unittest.main()
