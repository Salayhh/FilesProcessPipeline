"""Stage 2: organize MinerU Markdown with an OpenAI-compatible LLM."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path

from files_pipeline.clients.llm import OpenAICompatibleClient
from files_pipeline.config import Settings
from files_pipeline.models import DocumentRecord, RunContext, StageResult, TokenUsage
from files_pipeline.progress import format_duration


class OrganizeStage:
    def __init__(self, settings: Settings, client: OpenAICompatibleClient | None = None):
        self.settings = settings
        self.client = client or OpenAICompatibleClient(settings)

    def run(self, context: RunContext, documents: list[DocumentRecord]) -> StageResult:
        start = time.monotonic()
        result = StageResult(stage="organize")
        context.organized_dir.mkdir(parents=True, exist_ok=True)

        candidates = [document for document in documents if self._input_markdown_path(document)]
        input_label = "脱敏 Markdown" if self.settings.sanitize_enabled else "Markdown"
        print(f"[Organize] 开始整理: {len(candidates)}/{len(documents)} 个 {input_label}", flush=True)
        print(
            "[Organize] 配置: "
            f"model={self.settings.llm_model}, "
            f"base_url={self.settings.llm_base_url}, "
            f"concurrency={self.settings.llm_concurrency}",
            flush=True,
        )
        if not candidates:
            result.errors["input"] = f"没有 {input_label} 可供整理"
            result.failed = len(documents)
            print(f"[Organize] 没有 {input_label} 可供处理", flush=True)
            return result

        max_workers = min(self.settings.llm_concurrency, len(candidates))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_document = {
                executor.submit(self._process_document, context, document, index, len(candidates)): document
                for index, document in enumerate(candidates, 1)
            }
            for future in as_completed(future_to_document):
                document = future_to_document[future]
                try:
                    output_path, token_usage = future.result()
                    document.organized_markdown_path = output_path
                    document.status = "organized_done"
                    result.success += 1
                    result.output_files.append(output_path)
                    result.token_usage.add(token_usage)
                except Exception as exc:
                    message = str(exc)
                    document.add_error(message)
                    result.failed += 1
                    result.failed_documents.append(document.source_id)
                    result.errors[document.source_id] = message
                    print(f"[Organize] 整理失败: {document.original_name}: {message}", flush=True)
        usage = result.token_usage
        print(
            "[Organize] 完成: "
            f"success={result.success}, failed={result.failed}, "
            f"tokens prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}, "
            f"用时 {format_duration(time.monotonic() - start)}",
            flush=True,
        )
        return result

    def _process_document(
        self,
        context: RunContext,
        document: DocumentRecord,
        index: int,
        total: int,
    ) -> tuple[Path, TokenUsage]:
        start = time.monotonic()
        print(f"[Organize] 文件 {index}/{total}: {document.original_name}", flush=True)
        input_path = self._input_markdown_path(document)
        if not input_path:
            raise ValueError("缺少可供整理的 Markdown 路径")
        source_content = read_text_with_fallback(input_path)
        if not source_content.strip():
            raise ValueError("文件内容为空")

        attempts = max(1, self.settings.llm_max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                print(f"[Organize] 调用 LLM API: {document.original_name}, attempt={attempt}/{attempts}", flush=True)
                completion = self.client.complete(source_content, document.original_name)
                output_path = context.organized_dir / f"{document.source_id}.md"
                output_path.write_text(completion.content, encoding="utf-8")
                usage = completion.token_usage
                print(
                    "[Organize] 文件完成: "
                    f"{document.original_name}, "
                    f"tokens prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}, "
                    f"用时 {format_duration(time.monotonic() - start)}",
                    flush=True,
                )
                return output_path, completion.token_usage
            except Exception as exc:
                last_error = exc
                print(f"[Organize] 调用失败: {document.original_name}, attempt={attempt}/{attempts}: {exc}", flush=True)
                if attempt < attempts and self.settings.llm_retry_delay > 0:
                    print(f"[Organize] {self.settings.llm_retry_delay}s 后重试: {document.original_name}", flush=True)
                    time.sleep(self.settings.llm_retry_delay)

        raise RuntimeError(f"LLM API 调用失败: {last_error}")

    def _input_markdown_path(self, document: DocumentRecord) -> Path | None:
        if document.sanitized_markdown_path:
            return document.sanitized_markdown_path
        if self.settings.sanitize_enabled:
            return None
        return document.mineru_markdown_path


def read_text_with_fallback(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return file_path.read_text(encoding="gbk")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="utf-8", errors="ignore")
