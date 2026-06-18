import tempfile
import unittest
from pathlib import Path

from files_pipeline.models import StageResult
from files_pipeline.pipeline import (
    PipelineError,
    archive_run,
    create_run_context,
    list_failed_documents,
    run_pipeline,
    run_retry_failed,
    run_sanitize,
)

from tests.utils import make_settings


class FakeStage:
    def __init__(self, name, calls, writer):
        self.name = name
        self.calls = calls
        self.writer = writer

    def run(self, context, documents):
        self.calls.append(self.name)
        return self.writer(context, documents)


class PipelineTest(unittest.TestCase):
    def test_create_run_context_uses_custom_assets_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, assets_base_dir=temp_path / "custom-assets")

            context = create_run_context(settings, "run-1")

            self.assertEqual(context.assets_dir, temp_path / "custom-assets" / "run-1")

    def test_run_pipeline_orchestrates_stages_and_does_not_archive_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            input_dir = settings.input_dir
            input_dir.mkdir()
            source_file = input_dir / "Report.PDF"
            source_file.write_bytes(b"source")
            calls = []

            def mineru_writer(context, documents):
                output = context.mineru_dir / documents[0].source_id / f"{documents[0].source_id}.md"
                output.parent.mkdir(parents=True)
                output.write_text("mineru", encoding="utf-8")
                documents[0].mineru_markdown_path = output
                return StageResult(stage="mineru", success=1, output_files=[output])

            def kimi_writer(context, documents):
                output = context.kimi_dir / f"{documents[0].source_id}.md"
                output.write_text("kimi", encoding="utf-8")
                documents[0].kimi_markdown_path = output
                return StageResult(stage="kimi", success=1, output_files=[output])

            def render_writer(context, documents):
                output = context.final_dir / f"{documents[0].source_id}.md"
                output.write_text("final", encoding="utf-8")
                documents[0].final_output_path = output
                documents[0].status = "done"
                return StageResult(stage="render", success=1, output_files=[output])

            manifest = run_pipeline(
                input_dir=input_dir,
                run_id="run-1",
                settings=settings,
                mineru_stage=FakeStage("mineru", calls, mineru_writer),
                kimi_stage=FakeStage("kimi", calls, kimi_writer),
                render_stage=FakeStage("render", calls, render_writer),
            )

            self.assertEqual(calls, ["mineru", "kimi", "render"])
            self.assertEqual(manifest.status, "success")
            self.assertTrue(source_file.exists())
            self.assertTrue((settings.runs_dir / "run-1" / "source" / "0001_Report.pdf").exists())
            self.assertFalse((settings.data_dir / "run-1").exists())
            self.assertIn("render", manifest.stages)

    def test_run_pipeline_runs_sanitize_before_kimi_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path, sanitize_enabled=True, sanitize_entities_path=temp_path / "entities.json")
            input_dir = settings.input_dir
            input_dir.mkdir()
            (input_dir / "Report.PDF").write_bytes(b"source")
            calls = []

            def mineru_writer(context, documents):
                output = context.mineru_dir / documents[0].source_id / f"{documents[0].source_id}.md"
                output.parent.mkdir(parents=True)
                output.write_text("mineru", encoding="utf-8")
                documents[0].mineru_markdown_path = output
                return StageResult(stage="mineru", success=1, output_files=[output])

            def sanitize_writer(context, documents):
                output = context.sanitized_dir / f"{documents[0].source_id}.md"
                output.write_text("sanitized", encoding="utf-8")
                documents[0].sanitized_markdown_path = output
                return StageResult(stage="sanitize", success=1, output_files=[output])

            def kimi_writer(context, documents):
                self.assertEqual(documents[0].sanitized_markdown_path.read_text(encoding="utf-8"), "sanitized")
                output = context.kimi_dir / f"{documents[0].source_id}.md"
                output.write_text("kimi", encoding="utf-8")
                documents[0].kimi_markdown_path = output
                return StageResult(stage="kimi", success=1, output_files=[output])

            def render_writer(context, documents):
                output = context.final_dir / f"{documents[0].source_id}.md"
                output.write_text("final", encoding="utf-8")
                documents[0].final_output_path = output
                documents[0].status = "done"
                return StageResult(stage="render", success=1, output_files=[output])

            manifest = run_pipeline(
                input_dir=input_dir,
                run_id="run-1",
                settings=settings,
                mineru_stage=FakeStage("mineru", calls, mineru_writer),
                sanitize_stage=FakeStage("sanitize", calls, sanitize_writer),
                kimi_stage=FakeStage("kimi", calls, kimi_writer),
                render_stage=FakeStage("render", calls, render_writer),
            )

            self.assertEqual(calls, ["mineru", "sanitize", "kimi", "render"])
            self.assertEqual(manifest.status, "success")
            self.assertIn("sanitize", manifest.stages)

    def test_run_sanitize_records_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entities_path = temp_path / "entities.json"
            entities_path.write_text('{"深圳某某科技有限公司": "公司_001"}', encoding="utf-8")
            settings = make_settings(temp_path, sanitize_enabled=True, sanitize_entities_path=entities_path)
            context = create_run_context(settings, "run-1")
            context.ensure_directories()
            mineru_md = context.mineru_dir / "0001_doc" / "0001_doc.md"
            mineru_md.parent.mkdir(parents=True)
            mineru_md.write_text("深圳某某科技有限公司", encoding="utf-8")
            document = make_document(temp_path, context, mineru_md)
            from files_pipeline.models import RunManifest

            manifest = RunManifest.create("run-1", [document])
            manifest.save(context.manifest_path)

            sanitized = run_sanitize("run-1", settings=settings)

            self.assertEqual(sanitized.status, "sanitized")
            self.assertEqual(
                sanitized.documents[0].sanitized_markdown_path.read_text(encoding="utf-8"),
                "公司_001",
            )

    def test_run_pipeline_records_manifest_when_stage_aborts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            settings.input_dir.mkdir()
            (settings.input_dir / "doc.pdf").write_bytes(b"source")

            def failed_mineru(context, documents):
                return StageResult(stage="mineru", success=0, failed=1, errors={"doc": "fail"})

            with self.assertRaises(PipelineError):
                run_pipeline(
                    input_dir=settings.input_dir,
                    run_id="run-1",
                    settings=settings,
                    mineru_stage=FakeStage("mineru", [], failed_mineru),
                )

            manifest_path = settings.runs_dir / "run-1" / "manifest.json"
            self.assertTrue(manifest_path.exists())
            content = manifest_path.read_text(encoding="utf-8")
            self.assertIn('"status": "failed"', content)
            self.assertIn("MinerU 阶段没有成功文件", content)

    def test_run_pipeline_marks_partial_success_and_retry_failed_completes_remaining_document(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            input_dir = settings.input_dir
            input_dir.mkdir()
            (input_dir / "a.pdf").write_bytes(b"a")
            (input_dir / "b.pdf").write_bytes(b"b")
            calls = []

            def initial_mineru(context, documents):
                output = context.mineru_dir / documents[0].source_id / f"{documents[0].source_id}.md"
                output.parent.mkdir(parents=True)
                output.write_text("mineru", encoding="utf-8")
                documents[0].mineru_markdown_path = output
                documents[0].status = "mineru_done"
                documents[1].add_error("upload timeout")
                return StageResult(
                    stage="mineru",
                    success=1,
                    failed=1,
                    output_files=[output],
                    failed_documents=[documents[1].source_id],
                    errors={documents[1].source_id: "upload timeout"},
                )

            def initial_kimi(context, documents):
                document = documents[0]
                output = context.kimi_dir / f"{document.source_id}.md"
                output.write_text("kimi", encoding="utf-8")
                document.kimi_markdown_path = output
                document.status = "kimi_done"
                return StageResult(stage="kimi", success=1, output_files=[output])

            def initial_render(context, documents):
                document = documents[0]
                output = context.final_dir / f"{document.source_id}.md"
                output.write_text("final", encoding="utf-8")
                document.final_output_path = output
                document.status = "done"
                return StageResult(stage="render", success=1, output_files=[output])

            manifest = run_pipeline(
                input_dir=input_dir,
                run_id="run-1",
                settings=settings,
                mineru_stage=FakeStage("mineru", calls, initial_mineru),
                kimi_stage=FakeStage("kimi", calls, initial_kimi),
                render_stage=FakeStage("render", calls, initial_render),
            )

            self.assertEqual(manifest.status, "partial_success")
            failed_documents = list_failed_documents("run-1", settings=settings)
            self.assertEqual([document.original_name for document in failed_documents], ["b.pdf"])

            def retry_mineru(context, documents):
                document = documents[0]
                output = context.mineru_dir / document.source_id / f"{document.source_id}.md"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("mineru retry", encoding="utf-8")
                document.mineru_markdown_path = output
                document.status = "mineru_done"
                return StageResult(stage="mineru", success=1, output_files=[output])

            def retry_kimi(context, documents):
                document = documents[0]
                output = context.kimi_dir / f"{document.source_id}.md"
                output.write_text("kimi retry", encoding="utf-8")
                document.kimi_markdown_path = output
                document.status = "kimi_done"
                return StageResult(stage="kimi", success=1, output_files=[output])

            def retry_render(context, documents):
                document = documents[0]
                output = context.final_dir / f"{document.source_id}.md"
                output.write_text("final retry", encoding="utf-8")
                document.final_output_path = output
                document.status = "done"
                return StageResult(stage="render", success=1, output_files=[output])

            retried = run_retry_failed(
                "run-1",
                settings=settings,
                mineru_stage=FakeStage("retry_mineru", calls, retry_mineru),
                kimi_stage=FakeStage("retry_kimi", calls, retry_kimi),
                render_stage=FakeStage("retry_render", calls, retry_render),
            )

            self.assertEqual(retried.status, "success")
            self.assertEqual(list_failed_documents("run-1", settings=settings), [])
            self.assertIn("retry_mineru", retried.stages)
            self.assertIn("retry_kimi", retried.stages)
            self.assertIn("retry_render", retried.stages)

    def test_archive_run_moves_only_requested_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = make_settings(temp_path)
            run_dir = settings.runs_dir / "run-1"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text("{}", encoding="utf-8")

            target = archive_run("run-1", settings=settings)

            self.assertEqual(target, settings.data_dir / "run-1")
            self.assertFalse(run_dir.exists())
            self.assertTrue((target / "manifest.json").exists())


def make_document(temp_path, context, mineru_md):
    from files_pipeline.models import DocumentRecord

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
