import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ui.param_metadata import editor_kind_for_key, options_for_key


class ParamMetadataTests(unittest.TestCase):
    def test_voice_and_segment_mode_have_dropdown_options(self):
        voice_options = options_for_key("音色")
        self.assertGreater(len(voice_options), 5)
        self.assertIn(("知梦 2.0 - 温柔女声", "zh_female_zhimeng_uranus_bigtts"), voice_options)

        self.assertEqual(
            options_for_key("分段模式"),
            [
                ("按文案分段", "按文案分段"),
                ("按时长均分", "按时长均分"),
                ("按数量均分", "按数量均分"),
            ],
        )
        self.assertEqual(options_for_key("设备"), [("CPU", "cpu"), ("GPU (CUDA)", "cuda")])

    def test_path_keys_use_file_or_directory_picker(self):
        self.assertEqual(editor_kind_for_key("素材库"), "directory")
        self.assertEqual(editor_kind_for_key("保存目录"), "directory")
        self.assertEqual(editor_kind_for_key("BGM文件"), "file")
        self.assertEqual(editor_kind_for_key("封面底图"), "file")
        self.assertEqual(editor_kind_for_key("改写SKILL文件"), "file")

    def test_subtitle_boolean_options_use_dropdowns(self):
        self.assertEqual(options_for_key("字幕描边"), [("开启", True), ("关闭", False)])
        self.assertEqual(options_for_key("字幕阴影"), [("开启", True), ("关闭", False)])
        self.assertEqual(editor_kind_for_key("字幕描边"), "select")
        self.assertEqual(editor_kind_for_key("字幕阴影"), "select")

    def test_image_generation_provider_options_are_available(self):
        providers = options_for_key("服务商")
        self.assertIn(("OpenRouter", "openrouter"), providers)
        self.assertIn(("OpenAI", "openai"), providers)
        self.assertIn(("Google Gemini", "google"), providers)
        self.assertIn(("DashScope 通义万象", "dashscope"), providers)
        self.assertEqual(editor_kind_for_key("服务商"), "select")
        self.assertEqual(options_for_key("质量"), [("2K", "2k"), ("普通", "normal")])


if __name__ == "__main__":
    unittest.main()
