import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime.output_summary import format_output_summary


class OutputSummaryTests(unittest.TestCase):
    def test_formats_items_and_meta(self):
        output = {
            "type": "video_files",
            "items": ["a.mp4", "b.mp4"],
            "meta": {"report_md": "report.md", "upstream_count": 1, "finished_at": "2026-05-31 12:00:00"},
        }

        text = format_output_summary(output)

        self.assertIn("类型: video_files", text)
        self.assertIn("数量: 2", text)
        self.assertIn("输出时间: 2026-05-31 12:00:00", text)
        self.assertIn("a.mp4", text)
        self.assertIn("report_md: report.md", text)
        self.assertIn("upstream_count: 1", text)


if __name__ == "__main__":
    unittest.main()
