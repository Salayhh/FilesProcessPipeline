"""Stage 3: render final Markdown/text and copy assets."""

from __future__ import annotations

from pathlib import Path

from files_pipeline.assets import copy_document_images
from files_pipeline.config import Settings
from files_pipeline.markdown import extract_bad_item_title, process_markdown_content, rewrite_image_links
from files_pipeline.models import DocumentRecord, RunContext, StageResult


class RenderStage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, context: RunContext, documents: list[DocumentRecord]) -> StageResult:
        result = StageResult(stage="render")
        context.final_dir.mkdir(parents=True, exist_ok=True)
        context.assets_dir.mkdir(parents=True, exist_ok=True)

        candidates = [document for document in documents if document.kimi_markdown_path]
        if not candidates:
            result.failed = len(documents)
            result.errors["input"] = "没有 Kimi Markdown 可供渲染"
            return result

        for document in candidates:
            try:
                output_path, images_copied = self._render_document(context, document)
                document.final_output_path = output_path
                document.status = "done"
                result.success += 1
                result.images_copied += images_copied
                result.output_files.append(output_path)
            except Exception as exc:
                message = str(exc)
                document.add_error(message)
                result.failed += 1
                result.failed_documents.append(document.source_id)
                result.errors[document.source_id] = message
        return result

    def _render_document(self, context: RunContext, document: DocumentRecord) -> tuple[Path, int]:
        if not document.kimi_markdown_path:
            raise ValueError("缺少 Kimi Markdown 路径")

        content = document.kimi_markdown_path.read_text(encoding="utf-8")
        bad_item_title = extract_bad_item_title(content)
        if bad_item_title:
            content = process_markdown_content(content, bad_item_title, self.settings.section_separator)

        mineru_document_dir = context.mineru_dir / document.source_id
        images_copied = copy_document_images(mineru_document_dir, context.assets_dir, document.source_id)
        if images_copied > 0:
            if self.settings.image_base_url:
                prefix = f"{self.settings.image_base_url.rstrip('/')}/{context.run_id}/{document.source_id}"
            else:
                prefix = f"../assets/{document.source_id}"
            content = rewrite_image_links(content, document.source_id, prefix)

        output_path = context.final_dir / f"{document.source_id}.{self.settings.output_format}"
        output_path.write_text(content, encoding="utf-8")
        return output_path, images_copied
