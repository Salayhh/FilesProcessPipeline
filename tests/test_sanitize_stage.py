import tempfile
import unittest
from pathlib import Path

from files_pipeline.models import DocumentRecord, RunContext
from files_pipeline.stages.sanitize import SanitizeStage, load_replacements, sanitize_markdown

from tests.utils import make_settings


class SanitizeStageTest(unittest.TestCase):
    def test_sanitize_markdown_replaces_text_and_preserves_code_and_link_destinations(self):
        content = "\n".join(
            [
                "深圳某某科技有限公司 和 上海测试设备有限公司",
                "![深圳某某科技有限公司](images/深圳某某科技有限公司.png)",
                "`深圳某某科技有限公司`",
                "```",
                "上海测试设备有限公司",
                "```",
            ]
        )

        sanitized, count = sanitize_markdown(
            content,
            [
                ("深圳某某科技有限公司", "公司_001"),
                ("上海测试设备有限公司", "供应商_001"),
            ],
        )

        self.assertEqual(count, 3)
        self.assertIn("公司_001 和 供应商_001", sanitized)
        self.assertIn("![公司_001](images/深圳某某科技有限公司.png)", sanitized)
        self.assertIn("`深圳某某科技有限公司`", sanitized)
        self.assertIn("上海测试设备有限公司\n```", sanitized)

    def test_run_writes_sanitized_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entities_path = temp_path / "entities.json"
            entities_path.write_text('{"深圳某某科技有限公司": "公司_001"}', encoding="utf-8")
            settings = make_settings(temp_path, sanitize_enabled=True, sanitize_entities_path=entities_path)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("深圳某某科技有限公司", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)

            result = SanitizeStage(settings).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(document.sanitized_markdown_path, context.sanitized_dir / "0001_doc.md")
            self.assertEqual(document.sanitized_markdown_path.read_text(encoding="utf-8"), "公司_001")

    def test_load_replacements_accepts_entities_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "entities.json"
            path.write_text('{"entities": {"短名": "B", "较长公司名": "A"}}', encoding="utf-8")

            replacements = load_replacements(path)

            self.assertEqual(replacements, [("较长公司名", "A"), ("短名", "B")])


def make_document(temp_path, context, mineru_md):
    return DocumentRecord(
        source_id="0001_doc",
        original_path=temp_path / "doc.pdf",
        source_path=context.source_dir / "doc.pdf",
        original_name="doc.pdf",
        original_stem="doc",
        extension=".pdf",
        mineru_markdown_path=mineru_md,
    )


if __name__ == "__main__":
    unittest.main()
