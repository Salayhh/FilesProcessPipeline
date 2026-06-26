import tempfile
import threading
import unittest
from pathlib import Path

from files_pipeline.models import DocumentRecord, LLMCompletion, RunContext, TokenUsage
from files_pipeline.stages.organize import OrganizeStage

from tests.utils import make_settings


class FakeLLMClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, source_content, file_name):
        self.calls.append((source_content, file_name))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ConcurrentLLMClient:
    def __init__(self, expected_calls):
        self.expected_calls = expected_calls
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.all_started = threading.Event()

    def complete(self, source_content, file_name):
        with self.lock:
            self.calls.append((source_content, file_name))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if len(self.calls) >= self.expected_calls:
                self.all_started.set()

        self.all_started.wait(timeout=1)

        with self.lock:
            self.active -= 1

        return LLMCompletion(f"ok {file_name}", TokenUsage(1, 2, 3))


class OrganizeStageTest(unittest.TestCase):
    def test_run_writes_organized_markdown_and_accumulates_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, llm_retry_delay=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("原始内容\n![](images/a.png)\n", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            completion = LLMCompletion("# 不良项目：A", TokenUsage(10, 20, 30))
            client = FakeLLMClient([completion])

            result = OrganizeStage(settings, client=client).run(context, [document])

            self.assertEqual(result.stage, "organize")
            self.assertEqual(result.success, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.token_usage.total_tokens, 30)
            self.assertEqual(client.calls, [("原始内容\n![](images/a.png)\n", "doc.pdf")])
            self.assertEqual(document.organized_markdown_path, context.organized_dir / "0001_doc.md")
            self.assertEqual(document.organized_markdown_path.read_text(encoding="utf-8"), "# 不良项目：A")

    def test_run_processes_documents_concurrently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, llm_concurrency=2, llm_retry_delay=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            documents = []
            for source_id, file_name in [("0001_doc_a", "doc-a.pdf"), ("0002_doc_b", "doc-b.pdf")]:
                mineru_md = context.mineru_dir / source_id / f"{source_id}.md"
                mineru_md.parent.mkdir(parents=True)
                mineru_md.write_text(f"原始内容 {file_name}", encoding="utf-8")
                documents.append(make_document(temp_path, context, mineru_md, source_id, file_name))
            client = ConcurrentLLMClient(expected_calls=2)

            result = OrganizeStage(settings, client=client).run(context, documents)

            self.assertEqual(result.success, 2)
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.token_usage.total_tokens, 6)
            self.assertEqual(client.max_active, 2)

    def test_run_retries_api_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, llm_max_retries=1, llm_retry_delay=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("原始内容", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            client = FakeLLMClient([RuntimeError("busy"), LLMCompletion("ok", TokenUsage(1, 2, 3))])

            result = OrganizeStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(result.token_usage.total_tokens, 3)

    def test_run_uses_sanitized_markdown_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, sanitize_enabled=True)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("原始公司名", encoding="utf-8")
            sanitized_md = context.sanitized_dir / "0001_doc.md"
            sanitized_md.parent.mkdir(parents=True, exist_ok=True)
            sanitized_md.write_text("公司_001", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            document.sanitized_markdown_path = sanitized_md
            client = FakeLLMClient([LLMCompletion("ok", TokenUsage(1, 2, 3))])

            result = OrganizeStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(client.calls, [("公司_001", "doc.pdf")])

    def test_run_requires_sanitized_markdown_when_sanitize_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, sanitize_enabled=True)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("原始公司名", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            client = FakeLLMClient([])

            result = OrganizeStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 0)
            self.assertEqual(result.failed, 1)
            self.assertEqual(client.calls, [])

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
            client = FakeLLMClient([])

            result = OrganizeStage(settings, client=client).run(context, [document])

            self.assertEqual(result.success, 0)
            self.assertEqual(result.failed, 1)
            self.assertIn("文件内容为空", result.errors["0001_doc"])


def make_document(temp_path, context, mineru_md, source_id="0001_doc", file_name="doc.pdf"):
    return DocumentRecord(
        source_id=source_id,
        original_path=temp_path / file_name,
        source_path=context.source_dir / file_name,
        original_name=file_name,
        original_stem=Path(file_name).stem,
        extension=".pdf",
        mineru_markdown_path=mineru_md,
    )


if __name__ == "__main__":
    unittest.main()
