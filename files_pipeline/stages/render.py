"""Stage 3: render final Markdown/text and copy assets."""

from __future__ import annotations

import os
import time
from pathlib import Path

from files_pipeline.assets import copy_document_images
from files_pipeline.config import Settings
from files_pipeline.markdown import extract_bad_item_title, process_markdown_content, rewrite_image_links
from files_pipeline.models import DocumentRecord, RunContext, StageResult
from files_pipeline.progress import format_duration


class RenderStage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, context: RunContext, documents: list[DocumentRecord]) -> StageResult:
        start = time.monotonic()
        result = StageResult(stage="render")
        context.final_dir.mkdir(parents=True, exist_ok=True)
        context.assets_dir.mkdir(parents=True, exist_ok=True)

        candidates = [document for document in documents if document.organized_markdown_path]
        print(f"[Render] 开始渲染: {len(candidates)}/{len(documents)} 个整理后 Markdown", flush=True)
        if not candidates:
            result.failed = len(documents)
            result.errors["input"] = "没有整理后 Markdown 可供渲染"
            print("[Render] 没有整理后 Markdown 可供渲染", flush=True)
            return result

        for index, document in enumerate(candidates, 1):
            try:
                print(f"[Render] 文件 {index}/{len(candidates)}: {document.original_name}", flush=True)
                output_path, images_copied = self._render_document(context, document)
                document.final_output_path = output_path
                document.status = "done"
                result.success += 1
                result.images_copied += images_copied
                result.output_files.append(output_path)
                print(f"[Render] 文件完成: {document.original_name}, images={images_copied}, output={output_path}", flush=True)
            except Exception as exc:
                message = str(exc)
                document.add_error(message)
                result.failed += 1
                result.failed_documents.append(document.source_id)
                result.errors[document.source_id] = message
                print(f"[Render] 渲染失败: {document.original_name}: {message}", flush=True)
        print(
            f"[Render] 完成: success={result.success}, failed={result.failed}, images={result.images_copied}, "
            f"用时 {format_duration(time.monotonic() - start)}",
            flush=True,
        )
        return result

    def _render_document(self, context: RunContext, document: DocumentRecord) -> tuple[Path, int]:
        if not document.organized_markdown_path:
            raise ValueError("缺少整理后 Markdown 路径")

        content = document.organized_markdown_path.read_text(encoding="utf-8")
        bad_item_title = extract_bad_item_title(content)
        if bad_item_title:
            content = process_markdown_content(content, bad_item_title, self.settings.section_separator)

        mineru_document_dir = context.mineru_dir / document.source_id
        images_copied = copy_document_images(mineru_document_dir, context.assets_dir, document.source_id)
        if images_copied > 0:
            if self.settings.image_base_url:
                prefix = f"{self.settings.image_base_url.rstrip('/')}/{context.run_id}/{document.source_id}"
            else:
                prefix = relative_link_prefix(context.final_dir, context.assets_dir / document.source_id)
            content = rewrite_image_links(content, document.source_id, prefix)

        output_path = context.final_dir / f"{document.source_id}.{self.settings.output_format}"
        output_path.write_text(content, encoding="utf-8")
        return output_path, images_copied


def relative_link_prefix(from_dir: Path, target_dir: Path) -> str:
    try:
        return Path(os.path.relpath(target_dir, start=from_dir)).as_posix()
    except ValueError:
        return target_dir.as_posix()
