"""Stage 1: parse source documents with MinerU."""

from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path

from files_pipeline.clients.mineru import MinerUAPIError, MinerUClient
from files_pipeline.config import Settings
from files_pipeline.models import DocumentRecord, RunContext, StageResult
from files_pipeline.progress import format_duration


class MinerUStage:
    def __init__(self, settings: Settings, client: MinerUClient | None = None):
        self.settings = settings
        self.client = client or MinerUClient(settings)

    def run(self, context: RunContext, documents: list[DocumentRecord]) -> StageResult:
        start = time.monotonic()
        result = StageResult(stage="mineru")
        pending_documents = [document for document in documents if document.source_path.exists()]
        print(f"[MinerU] 开始解析: {len(pending_documents)}/{len(documents)} 个输入文件", flush=True)
        print(
            "[MinerU] 配置: "
            f"model_version={self.settings.mineru_model_version}, "
            f"enable_table={self.settings.mineru_enable_table}, "
            f"enable_formula={self.settings.mineru_enable_formula}, "
            f"language={self.settings.mineru_language}",
            flush=True,
        )
        if not pending_documents:
            result.failed = len(documents)
            result.errors["input"] = "没有可解析的输入文件"
            print("[MinerU] 没有可解析的输入文件", flush=True)
            return result

        batches = self._chunk_documents(pending_documents)
        for index, batch in enumerate(batches, 1):
            print(f"[MinerU] 批次 {index}/{len(batches)}: {len(batch)} 个文件", flush=True)
            self._process_batch(context, batch, result, index, len(batches))
        print(
            f"[MinerU] 完成: success={result.success}, failed={result.failed}, 用时 {format_duration(time.monotonic() - start)}",
            flush=True,
        )
        return result

    def _chunk_documents(self, documents: list[DocumentRecord]) -> list[list[DocumentRecord]]:
        size = max(1, self.settings.mineru_max_files_per_batch)
        return [documents[index : index + size] for index in range(0, len(documents), size)]

    def _process_batch(
        self,
        context: RunContext,
        documents: list[DocumentRecord],
        stage_result: StageResult,
        batch_index: int,
        batch_total: int,
    ) -> None:
        try:
            upload_names = {document.source_id: self._mineru_upload_name(document) for document in documents}
            file_infos = [
                {"name": upload_names[document.source_id], "data_id": self._mineru_data_id(document)}
                for document in documents
            ]
            print(f"[MinerU] 批次 {batch_index}/{batch_total}: 申请上传链接...", flush=True)
            batch_id, upload_urls = self.client.apply_upload_urls(file_infos)
            print(f"[MinerU] 批次 {batch_index}/{batch_total}: batch_id={batch_id}", flush=True)
        except Exception as exc:
            message = f"申请 MinerU 上传链接失败: {exc}"
            print(f"[MinerU] 批次 {batch_index}/{batch_total}: {message}", flush=True)
            for document in documents:
                self._mark_failed(stage_result, document, message)
            return

        uploaded_documents: dict[str, DocumentRecord] = {}
        upload_name_to_data_id: dict[str, str] = {}
        for document, upload_url in zip(documents, upload_urls):
            try:
                print(f"[MinerU] 上传: {document.original_name} -> {upload_names[document.source_id]}", flush=True)
                self.client.upload_file(document.source_path, upload_url)
                data_id = self._mineru_data_id(document)
                uploaded_documents[data_id] = document
                upload_name_to_data_id[upload_names[document.source_id]] = data_id
                print(f"[MinerU] 上传完成: {document.original_name}", flush=True)
            except Exception as exc:
                print(f"[MinerU] 上传失败: {document.original_name}: {exc}", flush=True)
                self._mark_failed(stage_result, document, str(exc))

        if len(upload_urls) < len(documents):
            for document in documents[len(upload_urls) :]:
                self._mark_failed(stage_result, document, "MinerU 返回的上传链接数量不足")

        if not uploaded_documents:
            return

        completed = self._poll_batch(batch_id, uploaded_documents, upload_name_to_data_id, stage_result)
        for data_id, extract_result in completed.items():
            document = uploaded_documents[data_id]
            try:
                print(f"[MinerU] 下载解析结果: {document.original_name}", flush=True)
                markdown_path = self._download_result(context, document, extract_result)
                document.mineru_markdown_path = markdown_path
                document.status = "mineru_done"
                stage_result.success += 1
                stage_result.output_files.append(markdown_path)
                print(f"[MinerU] 解析完成: {document.original_name} -> {markdown_path}", flush=True)
            except Exception as exc:
                print(f"[MinerU] 结果处理失败: {document.original_name}: {exc}", flush=True)
                self._mark_failed(stage_result, document, str(exc))

    def _poll_batch(
        self,
        batch_id: str,
        uploaded_documents: dict[str, DocumentRecord],
        upload_name_to_data_id: dict[str, str],
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
                print(f"[MinerU] 轮询失败 {query_error_count}/{self.settings.mineru_max_query_errors}: {exc}", flush=True)
                if query_error_count >= self.settings.mineru_max_query_errors:
                    stage_result.errors["polling"] = str(exc)
                    break
                time.sleep(self.settings.mineru_poll_interval)
                continue

            all_done = True
            state_counts: dict[str, int] = {}
            for item in data.get("extract_result", []):
                file_name = item.get("file_name", "")
                data_id = item.get("data_id", "")
                document_key = upload_name_to_data_id.get(file_name, data_id)
                if document_key not in uploaded_documents or document_key in completed or document_key in failed:
                    continue
                state = item.get("state", "")
                state_counts[state or "unknown"] = state_counts.get(state or "unknown", 0) + 1
                if state == "done":
                    completed[document_key] = item
                    print(f"[MinerU] 文件解析完成: {uploaded_documents[document_key].original_name}", flush=True)
                elif state == "failed":
                    failed.add(document_key)
                    document = uploaded_documents[document_key]
                    print(f"[MinerU] 文件解析失败: {document.original_name}: {item.get('err_msg', 'MinerU 解析失败')}", flush=True)
                    self._mark_failed(stage_result, document, item.get("err_msg", "MinerU 解析失败"))
                else:
                    all_done = False

            elapsed = format_duration(time.monotonic() - poll_start)
            state_text = ", ".join(f"{state}={count}" for state, count in sorted(state_counts.items())) or "无匹配结果"
            print(
                f"[MinerU] 轮询 batch={batch_id}: {state_text}, completed={len(completed)}, failed={len(failed)}, 用时 {elapsed}",
                flush=True,
            )

            if all_done and len(completed) + len(failed) >= len(uploaded_documents):
                break
            time.sleep(self.settings.mineru_poll_interval)

        unresolved = set(uploaded_documents) - set(completed) - failed
        for file_name in unresolved:
            print(f"[MinerU] 未完成: {uploaded_documents[file_name].original_name}", flush=True)
            self._mark_failed(stage_result, uploaded_documents[file_name], "MinerU 解析未完成或轮询超时")
        return completed

    def _mineru_upload_name(self, document: DocumentRecord) -> str:
        return f"{self._mineru_data_id(document)}{document.extension}"

    def _mineru_data_id(self, document: DocumentRecord) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", document.source_id)
        cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
        return (cleaned or "document")[:120]

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
