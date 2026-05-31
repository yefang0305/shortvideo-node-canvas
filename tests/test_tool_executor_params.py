import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import NODE_SPEC_BY_TYPE, WorkflowNode
from app.runtime import tool_executor
from app.runtime.tool_executor import ToolExecutor, _stamp_output_finished_at, _normalize_asr_device, _resolve_bgm_path


class ToolExecutorParamTests(unittest.TestCase):
    def test_normalize_asr_device_accepts_user_friendly_gpu(self):
        self.assertEqual(_normalize_asr_device("GPU"), "cuda")
        self.assertEqual(_normalize_asr_device("cuda"), "cuda")
        self.assertEqual(_normalize_asr_device("CPU"), "cpu")
        self.assertEqual(_normalize_asr_device(""), "cpu")

    def test_resolve_bgm_path_accepts_file_or_directory(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "music.mp3"
            audio.write_text("fake", encoding="utf-8")

            self.assertEqual(_resolve_bgm_path(str(audio)), str(audio.resolve()))
            self.assertEqual(_resolve_bgm_path(str(root)), str(audio.resolve()))
            self.assertEqual(_resolve_bgm_path(""), "")

    def test_stamp_output_finished_at_adds_readable_time(self):
        output = {"type": "demo", "items": []}

        stamped = _stamp_output_finished_at(output)

        self.assertRegex(stamped["meta"]["finished_at"], r"^20\d\d-\d\d-\d\d \d\d:\d\d:\d\d$")

    def test_batch_mix_subtitle_params_are_written_to_external_config(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "抖音批量视频生成" / "config" / "settings.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text("{}", encoding="utf-8")
            old_tools_root = tool_executor.TOOLS_ROOT
            tool_executor.TOOLS_ROOT = root
            try:
                node = WorkflowNode(NODE_SPEC_BY_TYPE["batch_mix"], 0, 0)
                node.params.update(
                    {
                        "字幕字体": "Microsoft YaHei",
                        "字幕字号": 60,
                        "字幕颜色": "&H00FFFF00",
                        "字幕位置Y": 72,
                        "字幕描边": False,
                        "描边颜色": "&H00000000",
                        "描边粗细": 3,
                        "字幕阴影": True,
                        "最大字数": 12,
                        "字幕偏移秒": "0.2",
                    }
                )

                ToolExecutor._update_batch_tool_config(node)

                data = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(data["subtitle_font"], "Microsoft YaHei")
                self.assertEqual(data["subtitle_font_size"], 60)
                self.assertEqual(data["subtitle_color"], "&H00FFFF00")
                self.assertEqual(data["subtitle_position_y"], 72)
                self.assertIs(data["subtitle_outline"], False)
                self.assertEqual(data["subtitle_outline_color"], "&H00000000")
                self.assertEqual(data["subtitle_outline_size"], 3)
                self.assertIs(data["subtitle_shadow"], True)
                self.assertEqual(data["subtitle_max_chars"], 12)
                self.assertEqual(data["subtitle_offset_sec"], 0.2)
            finally:
                tool_executor.TOOLS_ROOT = old_tools_root

    def test_article_markdown_import_reads_md_as_article_text(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "article.md"
            md_path.write_text("# 标题\n\n正文内容", encoding="utf-8")
            node = WorkflowNode(NODE_SPEC_BY_TYPE["article_md_import"], 0, 0)
            node.params.update({"MD文件": str(md_path)})

            output = ToolExecutor().execute(node, [])

            self.assertEqual(output["type"], "article_text")
            self.assertEqual(output["items"], ["# 标题\n\n正文内容"])
            self.assertEqual(output["meta"]["source_file"], str(md_path.resolve()))

    def test_wechat_article_assemble_writes_cover_and_inline_images_to_markdown(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cover = root / "cover.png"
            inline = root / "inline.png"
            cover.write_text("fake cover", encoding="utf-8")
            inline.write_text("fake inline", encoding="utf-8")
            node = WorkflowNode(NODE_SPEC_BY_TYPE["wechat_article_assemble"], 0, 0)
            node.params.update({"输出目录": str(root / "out")})

            output = ToolExecutor().execute(
                node,
                [
                    {"type": "article_text", "items": ["# 标题\n\n第一段。\n\n第二段。"], "meta": {}},
                    {"type": "image_list", "items": [str(cover), str(inline)], "meta": {}},
                ],
            )

            self.assertEqual(output["type"], "article_text")
            assembled = Path(output["items"][0])
            text = assembled.read_text(encoding="utf-8")
            self.assertIn(f"![封面]({cover.resolve()})", text)
            self.assertIn(f"![插图 1]({inline.resolve()})", text)
            self.assertEqual(output["meta"]["cover_image"], str(cover.resolve()))
            self.assertEqual(output["meta"]["inline_count"], 1)


if __name__ == "__main__":
    unittest.main()
