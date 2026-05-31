import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime.script_tasks import build_batch_tasks, fallback_rewrite


class ScriptTaskTests(unittest.TestCase):
    def test_fallback_rewrite_builds_title_and_script(self):
        item = fallback_rewrite("这是第一句话。这里是第二句话，继续测试。")
        self.assertTrue(item["title"])
        self.assertIn("rewritten", item)
        self.assertLessEqual(len(item["title"]), 16)

    def test_build_batch_tasks_adds_material_and_output(self):
        rewrites = [{"title": "测试标题", "rewritten": "测试文案"}]
        tasks = build_batch_tasks(
            rewrites,
            material_folder="materials",
            bgm_path="bgm/music.mp3",
            output_dir="outputs/videos",
            output_count=2,
        )

        self.assertEqual(tasks["tasks"][0]["name"], "测试标题")
        self.assertEqual(tasks["tasks"][0]["material_folder"], "materials")
        self.assertEqual(tasks["tasks"][0]["output_count"], 2)

    def test_build_batch_tasks_carries_mix_parameters(self):
        tasks = build_batch_tasks(
            [{"title": "测试标题", "rewritten": "测试文案", "cover_text": "重点"}],
            material_folder="D:/materials",
            bgm_path="D:/bgm.mp3",
            output_dir="D:/out",
            output_count=3,
            extra_params={
                "tts_voice": "voice_a",
                "tts_speed": 1.15,
                "tts_volume": 120,
                "segment_mode": "text",
                "min_segment_duration": 2.0,
                "resolution": "1080x1920",
                "fps": 30,
                "bgm_volume": 25,
                "cover_bg_path": "D:/cover.png",
            },
        )

        task = tasks["tasks"][0]
        self.assertEqual(task["tts_voice"], "voice_a")
        self.assertEqual(task["tts_speed"], 1.15)
        self.assertEqual(task["tts_volume"], 120)
        self.assertEqual(task["segment_mode"], "text")
        self.assertEqual(task["min_segment_duration"], 2.0)
        self.assertEqual(task["resolution"], "1080x1920")
        self.assertEqual(task["fps"], 30)
        self.assertEqual(task["bgm_volume"], 25)
        self.assertEqual(task["cover_bg_path"], "D:/cover.png")


if __name__ == "__main__":
    unittest.main()
