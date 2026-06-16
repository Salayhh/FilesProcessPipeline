"""Stage 1: parse source documents with MinerU."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from files_pipeline.clients.mineru import MinerUAPIError, MinerUClient
from files_pipeline.config import Settings
from files_pipeline.models import DocumentRecord, RunContext, StageResult


class MinerUStage:
    def __init__(self, settings: Settings, client: MinerUClient | None = None):
        self.settings = settings
        self.client = client or MinerUClient(settings)

    def run(self, context: RunContext, documents: list[DocumentRecord]) -> StageResult:
        result = StageResult(stage="mineru")
        pending_documents = [document for document in documents if document.source_path.exists()]
        if not pending_documents:
            result.failed = len(documents)
            result.errors["input"] = "没有可解析的输入文件"
            return result

        for batch in self._chunk_documents(pending_documents):
            self._process_batch(context, batch, result)
        return result

    def _chunk_documents(self, documents: list[DocumentRecord]) -> list[list[DocumentRecord]]:
        size = max(1, self.settings.mineru_max_files_per_batch)
        return [documents[index : index + size] for index in range(0, len(documents), size)]

    def _process_batch(self, context: RunContext, documents: list[DocumentRecord], stage_result: StageResult) -> None:
        try:
            file_infos = [{"name": document.source_path.name} for document in documents]
            batch_id, upload_urls = self.client.apply_upload_urls(file_infos)
        except Exception as exc:
            message = f"申请 MinerU 上传链接失败: {exc}"
            for document in documents:
                self._mark_failed(stage_result, document, message)
            return

        uploaded_documents: dict[str, DocumentRecord] = {}
        for document, upload_url in zip(documents, upload_urls):
            try:
                self.client.upload_file(document.source_path, upload_url)
                uploaded_documents[document.source_path.name] = document
            except Exception as exc:
                self._mark_failed(stage_result, document, str(exc))

        if len(upload_urls) < len(documents):
            for document in documents[len(upload_urls) :]:
                self._mark_failed(stage_result, document, "MinerU 返回的上传链接数量不足")

        if not uploaded_documents:
            return

        completed = self._poll_batch(batch_id, uploaded_documents, stage_result)
        for file_name, extract_result in completed.items():
            document = uploaded_documents[file_name]
            try:
                markdown_path = self._download_result(context, document, extract_result)
                document.mineru_markdown_path = markdown_path
                document.status = "mineru_done"
                stage_result.success += 1
                stage_result.output_files.append(markdown_path)
            except Exception as exc:
                self._mark_failed(stage_result, document, str(exc))

    def _poll_batch(
        self,
        batch_id: str,
        uploaded_documents: dict[str, DocumentRecord],
        stage_result: StageResult,
    ) -> dict[str, dict]:
        completed: dict[str, dict] = {}
        failed: set[str] = set()
        poll_start = time.monotonic()
        query_error_count = 0

        while True:
            if time.monotonic() - poll_start > self.settings.mineru_max_poll_time:
                break

            try:
                data = self.client.query_batch_results(batch_id)
                query_error_count = 0
            except MinerUAPIError as exc:
                query_error_count += 1
                if query_error_count >= self.settings.mineru_max_query_errors:
                    stage_result.errors["polling"] = str(exc)
                    break
                time.sleep(self.settings.mineru_poll_interval)
                continue

            all_done = True
            for item in data.get("extract_result", []):
                file_name = item.get("file_name", "")
                if file_name not in uploaded_documents or file_name in completed or file_name in failed:
                    continue
                state = item.get("state", "")
                if state == "done":
                    completed[file_name] = item
                elif state == "failed":
                    failed.add(file_name)
                    document = uploaded_documents[file_name]
                    self._mark_failed(stage_result, document, item.get("err_msg", "MinerU 解析失败"))
                else:
                    all_done = False

            if all_done and len(completed) + len(failed) >= len(uploaded_documents):
                break
            time.sleep(self.settings.mineru_poll_interval)

        unresolved = set(uploaded_documents) - set(completed) - failed
        for file_name in unresolved:
            self._mark_failed(stage_result, uploaded_documents[file_name], "MinerU 解析未完成或轮询超时")
        return completed

    def _download_result(self, context: RunContext, document: DocumentRecord, extract_result: dict) -> Path:
        zip_url = extract_result.get("full_zip_url")
        if not zip_url:
            raise MinerUAPIError("MinerU 结果缺少 full_zip_url")

        document_dir = context.mineru_dir / document.source_id
        document_dir.mkdir(parents=True, exist_ok=True)
        zip_path = document_dir / "result.zip"
        zip_path.write_bytes(self.client.download_zip(zip_url))
        try:
            self.extract_zip_safely(zip_path, document_dir)
        finally:
            if zip_path.exists():
                zip_path.unlink()
        return self.normalize_markdown(document_dir, document.source_id)

    def extract_zip_safely(self, zip_path: Path, extract_dir: Path) -> None:
        root = extract_dir.resolve()
        with zipfile.ZipFile(zip_path, "r") as zip_file:
            for member in zip_file.infolist():
                target_path = (extract_dir / member.filename).resolve()
                if target_path != root and root not in target_path.parents:
                    raise MinerUAPIError(f"Zip 文件包含非法路径: {member.filename}")
            zip_file.extractall(extract_dir)

    def normalize_markdown(self, document_dir: Path, source_id: str) -> Path:
        target = document_dir / f"{source_id}.md"
        full_md = document_dir / "full.md"
        if full_md.exists():
            full_md.replace(target)
            return target

        md_files = sorted(path for path in document_dir.rglob("*.md") if path != target)
        if target.exists():
            return target
        if not md_files:
            raise MinerUAPIError(f"解析结果中未找到 Markdown 文件: {document_dir}")
        md_files[0].replace(target)
        return target

    def _mark_failed(self, stage_result: StageResult, document: DocumentRecord, message: str) -> None:
        document.add_error(message)
        stage_result.failed += 1
        stage_result.failed_documents.append(document.source_id)
        stage_result.errors[document.source_id] = message
