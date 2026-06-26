"""Core orchestration API for FilesProcessPipeline v2."""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from files_pipeline.config import Settings
from files_pipeline.models import DocumentRecord, RunContext, RunManifest, StageResult
from files_pipeline.progress import format_duration
from files_pipeline.stages.mineru import MinerUStage
from files_pipeline.stages.organize import OrganizeStage
from files_pipeline.stages.render import RenderStage
from files_pipeline.stages.sanitize import SanitizeStage


class PipelineError(Exception):
    """Pipeline execution failed."""


def run_pipeline(
    input_dir: Path | str | None = None,
    run_id: str | None = None,
    settings: Settings | None = None,
    mineru_stage: MinerUStage | None = None,
    sanitize_stage: SanitizeStage | None = None,
    organize_stage: OrganizeStage | None = None,
    kimi_stage: OrganizeStage | None = None,
    render_stage: RenderStage | None = None,
) -> RunManifest:
    start = time.monotonic()
    settings = settings or Settings.from_env()
    missing = settings.missing_required_keys()
    if missing:
        raise PipelineError(f"缺少必要配置: {', '.join(missing)}")

    context = create_run_context(settings, run_id)
    print(f"[Pipeline] 开始完整流程: run_id={context.run_id}", flush=True)
    context.ensure_directories()
    settings.ensure_directories()

    documents = prepare_documents(Path(input_dir) if input_dir else settings.input_dir, context, settings)
    if not documents:
        raise PipelineError(f"输入目录中没有支持的文件: {input_dir or settings.input_dir}")
    print(f"[Pipeline] 输入文件: {len(documents)} 个, manifest={context.manifest_path}", flush=True)

    manifest = RunManifest.create(context.run_id, documents)
    manifest.save(context.manifest_path)

    try:
        mineru_result = (mineru_stage or MinerUStage(settings)).run(context, documents)
        _record_or_abort(manifest, context, mineru_result, "MinerU 阶段没有成功文件")

        if settings.sanitize_enabled:
            sanitize_result = (sanitize_stage or SanitizeStage(settings)).run(context, documents)
            _record_or_abort(manifest, context, sanitize_result, "Sanitize 阶段没有成功文件")

        organize_result = (organize_stage or kimi_stage or OrganizeStage(settings)).run(context, documents)
        _record_or_abort(manifest, context, organize_result, "Organize 阶段没有成功文件")

        render_result = (render_stage or RenderStage(settings)).run(context, documents)
        _record_or_abort(manifest, context, render_result, "Render 阶段没有成功文件")

        manifest.status = completion_status(documents)
        manifest.save(context.manifest_path)
        print(f"[Pipeline] 完整流程完成: runs/{context.run_id}, 用时 {format_duration(time.monotonic() - start)}", flush=True)
        return manifest
    except Exception as exc:
        manifest.add_error(str(exc))
        manifest.save(context.manifest_path)
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(str(exc)) from exc


def run_parse(input_dir: Path | str | None = None, run_id: str | None = None, settings: Settings | None = None) -> RunManifest:
    start = time.monotonic()
    settings = settings or Settings.from_env()
    missing = ["MINERU_API_TOKEN"] if not settings.mineru_api_token else []
    if missing:
        raise PipelineError(f"缺少必要配置: {', '.join(missing)}")

    context = create_run_context(settings, run_id)
    print(f"[Pipeline] 开始 MinerU parse: run_id={context.run_id}", flush=True)
    context.ensure_directories()
    documents = prepare_documents(Path(input_dir) if input_dir else settings.input_dir, context, settings)
    if not documents:
        raise PipelineError(f"输入目录中没有支持的文件: {input_dir or settings.input_dir}")
    print(f"[Pipeline] 输入文件: {len(documents)} 个, manifest={context.manifest_path}", flush=True)
    manifest = RunManifest.create(context.run_id, documents)
    result = MinerUStage(settings).run(context, documents)
    _record_or_abort(manifest, context, result, "MinerU 阶段没有成功文件")
    manifest.status = stage_completion_status(documents, result, "parsed")
    manifest.save(context.manifest_path)
    print(f"[Pipeline] MinerU parse 完成: runs/{context.run_id}, 用时 {format_duration(time.monotonic() - start)}", flush=True)
    return manifest


def run_sanitize(run_id: str, settings: Settings | None = None) -> RunManifest:
    start = time.monotonic()
    settings = settings or Settings.from_env()
    context = create_run_context(settings, run_id)
    print(f"[Pipeline] 开始 sanitize: run_id={context.run_id}", flush=True)
    manifest = RunManifest.load(context.manifest_path)
    result = SanitizeStage(settings).run(context, manifest.documents)
    _record_or_abort(manifest, context, result, "Sanitize 阶段没有成功文件")
    manifest.status = stage_completion_status(manifest.documents, result, "sanitized")
    manifest.save(context.manifest_path)
    print(f"[Pipeline] sanitize 完成: runs/{context.run_id}, 用时 {format_duration(time.monotonic() - start)}", flush=True)
    return manifest


def run_organize(run_id: str, settings: Settings | None = None) -> RunManifest:
    start = time.monotonic()
    settings = settings or Settings.from_env()
    if not settings.llm_api_key:
        raise PipelineError("缺少必要配置: LLM_API_KEY")
    context = create_run_context(settings, run_id)
    print(f"[Pipeline] 开始 organize: run_id={context.run_id}", flush=True)
    manifest = RunManifest.load(context.manifest_path)
    if settings.sanitize_enabled:
        sanitize_result = SanitizeStage(settings).run(context, manifest.documents)
        _record_or_abort(manifest, context, sanitize_result, "Sanitize 阶段没有成功文件")
    result = OrganizeStage(settings).run(context, manifest.documents)
    _record_or_abort(manifest, context, result, "Organize 阶段没有成功文件")
    manifest.status = stage_completion_status(manifest.documents, result, "organized")
    manifest.save(context.manifest_path)
    print(f"[Pipeline] organize 完成: runs/{context.run_id}, 用时 {format_duration(time.monotonic() - start)}", flush=True)
    return manifest


def run_render(run_id: str, settings: Settings | None = None) -> RunManifest:
    start = time.monotonic()
    settings = settings or Settings.from_env()
    context = create_run_context(settings, run_id)
    print(f"[Pipeline] 开始 render: run_id={context.run_id}", flush=True)
    manifest = RunManifest.load(context.manifest_path)
    result = RenderStage(settings).run(context, manifest.documents)
    _record_or_abort(manifest, context, result, "Render 阶段没有成功文件")
    manifest.status = stage_completion_status(manifest.documents, result, "rendered")
    manifest.save(context.manifest_path)
    print(f"[Pipeline] render 完成: runs/{context.run_id}, 用时 {format_duration(time.monotonic() - start)}", flush=True)
    return manifest


def list_failed_documents(run_id: str, settings: Settings | None = None) -> list[DocumentRecord]:
    settings = settings or Settings.from_env()
    context = create_run_context(settings, run_id)
    manifest = RunManifest.load(context.manifest_path)
    return retryable_documents(manifest.documents)


def run_retry_failed(
    run_id: str,
    settings: Settings | None = None,
    mineru_stage: MinerUStage | None = None,
    sanitize_stage: SanitizeStage | None = None,
    organize_stage: OrganizeStage | None = None,
    kimi_stage: OrganizeStage | None = None,
    render_stage: RenderStage | None = None,
) -> RunManifest:
    start = time.monotonic()
    settings = settings or Settings.from_env()
    context = create_run_context(settings, run_id)
    manifest = RunManifest.load(context.manifest_path)
    documents = retryable_documents(manifest.documents)
    if not documents:
        manifest.status = completion_status(manifest.documents)
        manifest.save(context.manifest_path)
        print(f"[Pipeline] 没有需要补跑的文件: runs/{run_id}", flush=True)
        return manifest

    needs_mineru = any(not path_exists(document.mineru_markdown_path) for document in documents)
    needs_organize = any(not path_exists(document.organized_markdown_path) for document in documents)
    if needs_mineru and not settings.mineru_api_token:
        raise PipelineError("缺少必要配置: MINERU_API_TOKEN")
    if needs_organize and not settings.llm_api_key:
        raise PipelineError("缺少必要配置: LLM_API_KEY")

    print(f"[Pipeline] 开始补跑失败文件: run_id={run_id}, files={len(documents)}", flush=True)
    for document in documents:
        reset_document_for_retry(document)
        print(f"[Pipeline] 补跑候选: {document.original_name}, status={document.status}", flush=True)
    manifest.save(context.manifest_path)

    mineru_documents = [document for document in documents if not path_exists(document.mineru_markdown_path)]
    if mineru_documents:
        result = (mineru_stage or MinerUStage(settings)).run(context, mineru_documents)
        _record_retry_stage(manifest, context, result)

    sanitize_documents = [
        document
        for document in documents
        if settings.sanitize_enabled
        and path_exists(document.mineru_markdown_path)
        and not path_exists(document.sanitized_markdown_path)
        and not path_exists(document.organized_markdown_path)
    ]
    if sanitize_documents:
        result = (sanitize_stage or SanitizeStage(settings)).run(context, sanitize_documents)
        _record_retry_stage(manifest, context, result)

    organize_documents = [
        document
        for document in documents
        if path_exists(organize_input_markdown_path(document, settings))
        and not path_exists(document.organized_markdown_path)
    ]
    if organize_documents:
        result = (organize_stage or kimi_stage or OrganizeStage(settings)).run(context, organize_documents)
        _record_retry_stage(manifest, context, result)

    render_documents = [
        document
        for document in documents
        if path_exists(document.organized_markdown_path) and not path_exists(document.final_output_path)
    ]
    if render_documents:
        result = (render_stage or RenderStage(settings)).run(context, render_documents)
        _record_retry_stage(manifest, context, result)

    manifest.status = completion_status(manifest.documents)
    manifest.save(context.manifest_path)
    remaining = retryable_documents(manifest.documents)
    print(
        f"[Pipeline] 补跑完成: remaining={len(remaining)}, status={manifest.status}, "
        f"用时 {format_duration(time.monotonic() - start)}",
        flush=True,
    )
    return manifest


def archive_run(run_id: str, settings: Settings | None = None) -> Path:
    settings = settings or Settings.from_env()
    source = settings.runs_dir / run_id
    if not source.exists():
        raise PipelineError(f"Run 不存在: {source}")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    target = settings.data_dir / run_id
    if target.exists():
        raise PipelineError(f"归档目标已存在: {target}")
    shutil.move(str(source), str(target))
    return target


def create_run_context(settings: Settings, run_id: str | None = None) -> RunContext:
    actual_run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return RunContext.create(settings.runs_dir, actual_run_id, settings.assets_base_dir)


def prepare_documents(input_dir: Path, context: RunContext, settings: Settings) -> list[DocumentRecord]:
    files = collect_input_files(input_dir, settings.supported_extensions)
    documents: list[DocumentRecord] = []
    for index, source_path in enumerate(files, 1):
        source_id = f"{index:04d}_{safe_filename(source_path.stem)}"
        snapshot_path = context.source_dir / f"{source_id}{source_path.suffix.lower()}"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, snapshot_path)
        documents.append(
            DocumentRecord(
                source_id=source_id,
                original_path=source_path,
                source_path=snapshot_path,
                original_name=source_path.name,
                original_stem=source_path.stem,
                extension=source_path.suffix.lower(),
            )
        )
    return documents


def collect_input_files(input_dir: Path, supported_extensions: tuple[str, ...]) -> list[Path]:
    supported = {extension.lower() for extension in supported_extensions}
    if not input_dir.exists():
        return []
    return sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in supported)


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned or "document"


def path_exists(path: Path | None) -> bool:
    return path is not None and path.exists()


def organize_input_markdown_path(document: DocumentRecord, settings: Settings) -> Path | None:
    if document.sanitized_markdown_path:
        return document.sanitized_markdown_path
    if settings.sanitize_enabled:
        return None
    return document.mineru_markdown_path


kimi_input_markdown_path = organize_input_markdown_path


def document_is_complete(document: DocumentRecord) -> bool:
    return document.status == "done" and path_exists(document.final_output_path)


def retryable_documents(documents: list[DocumentRecord]) -> list[DocumentRecord]:
    return [document for document in documents if not document_is_complete(document)]


def completion_status(documents: list[DocumentRecord]) -> str:
    if documents and all(document_is_complete(document) for document in documents):
        return "success"
    if any(document_is_complete(document) for document in documents):
        return "partial_success"
    return "failed"


def stage_completion_status(documents: list[DocumentRecord], result: StageResult, completed_status: str) -> str:
    if documents and result.success == len(documents) and result.failed == 0:
        return completed_status
    return f"partial_{completed_status}"


def reset_document_for_retry(document: DocumentRecord) -> None:
    document.errors.clear()
    if path_exists(document.final_output_path):
        document.status = "done"
        return
    document.final_output_path = None

    if path_exists(document.organized_markdown_path):
        document.status = "organized_done"
        return
    document.organized_markdown_path = None

    if path_exists(document.sanitized_markdown_path):
        document.status = "sanitized_done"
        return
    document.sanitized_markdown_path = None

    if path_exists(document.mineru_markdown_path):
        document.status = "mineru_done"
        return
    document.mineru_markdown_path = None
    document.status = "pending"


def _record_or_abort(manifest: RunManifest, context: RunContext, result: StageResult, message: str) -> None:
    manifest.record_stage(result, context.run_dir)
    manifest.save(context.manifest_path)
    _print_stage_summary(result)
    if result.success == 0:
        raise PipelineError(message)


def _record_retry_stage(manifest: RunManifest, context: RunContext, result: StageResult) -> None:
    retry_result = replace(result, stage=f"retry_{result.stage}")
    manifest.record_stage(retry_result, context.run_dir)
    manifest.save(context.manifest_path)
    _print_stage_summary(retry_result)


def _print_stage_summary(result: StageResult) -> None:
    usage = result.token_usage
    token_text = ""
    if usage.total_tokens:
        token_text = f", tokens prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}"
    print(
        f"[Pipeline] 阶段记录: {result.stage}, success={result.success}, failed={result.failed}{token_text}",
        flush=True,
    )
