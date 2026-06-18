import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import requests

from files_pipeline.clients.mineru import MinerUAPIError
from files_pipeline.clients.mineru import MinerUClient
from files_pipeline.models import DocumentRecord, RunContext
from files_pipeline.pipeline import collect_input_files
from files_pipeline.stages.mineru import MinerUStage

from tests.utils import make_settings


class FakeMinerUClient:
    def __init__(self, zip_bytes: bytes):
        self.zip_bytes = zip_bytes
        self.uploaded = []
        self.files = []

    def apply_upload_urls(self, files):
        self.files = files
        return "batch-1", [f"https://upload/{item['name']}" for item in files]

    def upload_file(self, file_path, upload_url):
        self.uploaded.append((Path(file_path).name, upload_url))

    def query_batch_results(self, batch_id):
        return {
            "extract_result": [
                {
                    "file_name": self.files[0]["name"],
                    "data_id": self.files[0].get("data_id", ""),
                    "state": "done",
                    "full_zip_url": "https://download/result.zip",
                }
            ]
        }

    def download_zip(self, zip_url):
        return self.zip_bytes


class ShortUploadUrlClient(FakeMinerUClient):
    def apply_upload_urls(self, files):
        self.files = files
        return "batch-1", ["https://upload/only-one"]


class DataIdResultClient(FakeMinerUClient):
    def query_batch_results(self, batch_id):
        return {
            "extract_result": [
                {
                    "file_name": "unexpected-name.pptx",
                    "data_id": self.files[0]["data_id"],
                    "state": "done",
                    "full_zip_url": "https://download/result.zip",
                }
            ]
        }


class MinerUStageTest(unittest.TestCase):
    def test_client_retries_upload_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(
                temp_path,
                mineru_upload_max_retries=1,
                mineru_upload_retry_delay=0,
                mineru_upload_timeout=1,
            )
            source_path = temp_path / "doc.pdf"
            source_path.write_bytes(b"pdf")
            response = requests.Response()
            response.status_code = 200
            calls = []

            def put(url, data, timeout):
                calls.append((url, timeout))
                if len(calls) == 1:
                    raise requests.exceptions.ReadTimeout("timeout")
                return response

            with patch("files_pipeline.clients.mineru.requests.put", side_effect=put):
                MinerUClient(settings).upload_file(source_path, "https://upload/doc.pdf")

            self.assertEqual(calls, [("https://upload/doc.pdf", 1), ("https://upload/doc.pdf", 1)])

    def test_extract_zip_safely_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            stage = MinerUStage(settings, client=FakeMinerUClient(b""))
            zip_path = temp_path / "bad.zip"
            extract_dir = temp_path / "extract"
            extract_dir.mkdir()

            with zipfile.ZipFile(zip_path, "w") as zip_file:
                zip_file.writestr("../evil.md", "bad")

            with self.assertRaises(MinerUAPIError):
                stage.extract_zip_safely(zip_path, extract_dir)

    def test_normalize_markdown_renames_full_md_to_source_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            stage = MinerUStage(settings, client=FakeMinerUClient(b""))
            document_dir = temp_path / "mineru" / "doc"
            document_dir.mkdir(parents=True)
            (document_dir / "full.md").write_text("content", encoding="utf-8")

            output = stage.normalize_markdown(document_dir, "0001_doc")

            self.assertEqual(output, document_dir / "0001_doc.md")
            self.assertEqual(output.read_text(encoding="utf-8"), "content")
            self.assertFalse((document_dir / "full.md").exists())

    def test_collect_input_files_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "A.PDF").write_text("a", encoding="utf-8")
            (temp_path / "B.pptx").write_text("b", encoding="utf-8")
            (temp_path / "ignore.txt").write_text("x", encoding="utf-8")

            files = collect_input_files(temp_path, (".pdf", ".pptx"))

            self.assertEqual([path.name for path in files], ["A.PDF", "B.pptx"])

    def test_run_processes_successful_mocked_mineru_flow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, mineru_poll_interval=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            source_path = context.source_dir / "0001_doc.pdf"
            source_path.write_bytes(b"pdf")
            document = DocumentRecord(
                source_id="0001_doc",
                original_path=temp_path / "doc.pdf",
                source_path=source_path,
                original_name="doc.pdf",
                original_stem="doc",
                extension=".pdf",
            )
            zip_path = temp_path / "result.zip"
            with zipfile.ZipFile(zip_path, "w") as zip_file:
                zip_file.writestr("full.md", "# title")
            stage = MinerUStage(settings, client=FakeMinerUClient(zip_path.read_bytes()))

            result = stage.run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(document.mineru_markdown_path, context.mineru_dir / "0001_doc" / "0001_doc.md")
            self.assertEqual(document.mineru_markdown_path.read_text(encoding="utf-8"), "# title")

    def test_run_matches_result_by_data_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, mineru_poll_interval=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            source_path = context.source_dir / "0001_资料.pptx"
            source_path.write_bytes(b"pptx")
            document = DocumentRecord(
                source_id="0001_资料",
                original_path=temp_path / "资料.pptx",
                source_path=source_path,
                original_name="资料.pptx",
                original_stem="资料",
                extension=".pptx",
            )
            zip_path = temp_path / "result.zip"
            with zipfile.ZipFile(zip_path, "w") as zip_file:
                zip_file.writestr("full.md", "# title")
            client = DataIdResultClient(zip_path.read_bytes())
            stage = MinerUStage(settings, client=client)

            result = stage.run(context, [document])

            self.assertEqual(result.success, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(client.files[0]["name"], "0001.pptx")
            self.assertEqual(client.files[0]["data_id"], "0001")

    def test_run_marks_documents_without_upload_urls_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, mineru_poll_interval=0)
            context = RunContext.create(settings.runs_dir, "run-1")
            context.ensure_directories()
            docs = []
            for source_id in ["0001_a", "0002_b"]:
                source_path = context.source_dir / f"{source_id}.pdf"
                source_path.write_bytes(b"pdf")
                docs.append(
                    DocumentRecord(
                        source_id=source_id,
                        original_path=temp_path / f"{source_id}.pdf",
                        source_path=source_path,
                        original_name=f"{source_id}.pdf",
                        original_stem=source_id,
                        extension=".pdf",
                    )
                )
            zip_path = temp_path / "result.zip"
            with zipfile.ZipFile(zip_path, "w") as zip_file:
                zip_file.writestr("full.md", "# title")
            stage = MinerUStage(settings, client=ShortUploadUrlClient(zip_path.read_bytes()))

            result = stage.run(context, docs)

            self.assertEqual(result.success, 1)
            self.assertEqual(result.failed, 1)
            self.assertIn("0002_b", result.failed_documents)
            self.assertIn("上传链接数量不足", result.errors["0002_b"])


if __name__ == "__main__":
    unittest.main()
