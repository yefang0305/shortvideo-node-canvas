import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime.environment import check_environment


class EnvironmentCheckTests(unittest.TestCase):
    def test_reports_core_items(self):
        results = check_environment()
        names = {item.name for item in results}

        self.assertIn("Python", names)
        self.assertIn("FFmpeg", names)
        self.assertIn("批量混剪 FFmpeg", names)
        self.assertIn("CR TubeGet Runtime", names)
        self.assertIn("抖音主页链接采集", names)
        self.assertIn("抖音视频下载", names)
        self.assertIn("抖音文案提取", names)
        self.assertIn("MediaPush", names)

        python = next(item for item in results if item.name == "Python")
        self.assertTrue(python.ok)
        self.assertTrue(python.detail)

        ffmpeg = next(item for item in results if item.name == "FFmpeg")
        self.assertTrue(ffmpeg.ok)
        self.assertNotIn("未在 PATH", ffmpeg.detail)


if __name__ == "__main__":
    unittest.main()
