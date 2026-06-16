import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from files_pipeline.models import DocumentRecord, RunContext
from files_pipeline.stages.render import RenderStage

from tests.utils import make_settings


class RenderStageTest(unittest.TestCase):
    def test_render_rewrites_headings_and_copies_images_with_relative_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            kimi_md = context.kimi_dir / "0001_doc.md"
            kimi_md.write_text(
                "\n".join(
                    [
                        "# 不良项目：A",
                        "",
                        "## 第一部分：发生状况",
                        "![现象](images/a.png)",
                        "",
                        "## 第二部分：事实把握",
                        "### 不良品确认结果",
                        "内容",
                    ]
                ),
                encoding="utf-8",
            )
            images_dir = context.mineru_dir / "0001_doc" / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "a.png").write_bytes(b"image")
            document = make_document(temp_path, context, kimi_md)

            result = RenderStage(settings).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(result.images_copied, 1)
            self.assertTrue((context.assets_dir / "0001_doc" / "a.png").exists())
            self.assertTrue((images_dir / "a.png").exists())
            output = document.final_output_path.read_text(encoding="utf-8")
            self.assertIn("## [A]第一部分：发生状况", output)
            self.assertIn("+=+=+=", output)
            self.assertIn("### [A(第二部分：事实把握)]不良品确认结果", output)
            self.assertIn("![现象](../assets/0001_doc/a.png)", output)

    def test_render_keeps_content_when_bad_item_title_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            kimi_md = context.kimi_dir / "0001_doc.md"
            kimi_md.write_text("## 第一部分：发生状况\n内容", encoding="utf-8")
            document = make_document(temp_path, context, kimi_md)

            result = RenderStage(settings).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(document.final_output_path.read_text(encoding="utf-8"), "## 第一部分：发生状况\n内容")

    def test_render_uses_absolute_image_url_when_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = replace(make_settings(temp_path), image_base_url="https://cdn.example/assets")
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            kimi_md = context.kimi_dir / "0001_doc.md"
            kimi_md.write_text("# 不良项目：A\n\n![x](images/a.png)", encoding="utf-8")
            images_dir = context.mineru_dir / "0001_doc" / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "a.png").write_bytes(b"image")
            document = make_document(temp_path, context, kimi_md)

            RenderStage(settings).run(context, [document])

            output = document.final_output_path.read_text(encoding="utf-8")
            self.assertIn("![x](https://cdn.example/assets/run-1/0001_doc/a.png)", output)


def make_document(temp_path, context, kimi_md):
    return DocumentRecord(
        source_id="0001_doc",
        original_path=temp_path / "doc.pdf",
        source_path=context.source_dir / "0001_doc.pdf",
        original_name="doc.pdf",
        original_stem="doc",
        extension=".pdf",
        kimi_markdown_path=kimi_md,
    )


if __name__ == "__main__":
    unittest.main()
