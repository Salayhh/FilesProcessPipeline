import tempfile
import unittest
from pathlib import Path

from files_pipeline.models import DocumentRecord, KimiCompletion, RunContext, TokenUsage
from files_pipeline.stages.kimi import KimiStage

from tests.utils import make_settings


class FakeKimiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, source_content, file_name):
        self.calls.append((source_content, file_name))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class KimiStageTest(unittest.TestCase):
    def test_run_writes_kimi_markdown_and_accumulates_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, kimi_retry_delay=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("原始内容\n![](images/a.png)\n", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            completion = KimiCompletion("# 不良项目：A", TokenUsage(10, 20, 30))
            client = FakeKimiClient([completion])

            result = KimiStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.token_usage.total_tokens, 30)
            self.assertEqual(client.calls, [("原始内容\n![](images/a.png)\n", "doc.pdf")])
            self.assertEqual(document.kimi_markdown_path, context.kimi_dir / "0001_doc.md")
            self.assertEqual(document.kimi_markdown_path.read_text(encoding="utf-8"), "# 不良项目：A")

    def test_run_retries_api_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, kimi_max_retries=1, kimi_retry_delay=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("原始内容", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            client = FakeKimiClient([RuntimeError("busy"), KimiCompletion("ok", TokenUsage(1, 2, 3))])

            result = KimiStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(result.token_usage.total_tokens, 3)

    def test_empty_markdown_is_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("  ", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            client = FakeKimiClient([])

            result = KimiStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 0)
            self.assertEqual(result.failed, 1)
            self.assertIn("文件内容为空", result.errors["0001_doc"])


def make_document(temp_path, context, mineru_md):
    return DocumentRecord(
        source_id="0001_doc",
        original_path=temp_path / "doc.pdf",
        source_path=context.source_dir / "0001_doc.pdf",
        original_name="doc.pdf",
        original_stem="doc",
        extension=".pdf",
        mineru_markdown_path=mineru_md,
    )


if __name__ == "__main__":
    unittest.main()
