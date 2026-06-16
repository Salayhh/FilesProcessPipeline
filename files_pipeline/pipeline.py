"""Core orchestration API for FilesProcessPipeline v2."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from files_pipeline.config import Settings
from files_pipeline.models import DocumentRecord, RunContext, RunManifest, StageResult
from files_pipeline.stages.kimi import KimiStage
from files_pipeline.stages.mineru import MinerUStage
from files_pipeline.stages.render import RenderStage


class PipelineError(Exception):
    """Pipeline execution failed."""


def run_pipeline(
    input_dir: Path | str | None = None,
    run_id: str | None = None,
    settings: Settings | None = None,
    mineru_stage: MinerUStage | None = None,
    kimi_stage: KimiStage | None = None,
    render_stage: RenderStage | None = None,
) -> RunManifest:
    settings = settings or Settings.from_env()
    missing = settings.missing_required_keys()
    if missing:
        raise PipelineError(f"缺少必要配置: {', '.join(missing)}")

    context = create_run_context(settings, run_id)
    context.ensure_directories()
    settings.ensure_directories()

    documents = prepare_documents(Path(input_dir) if input_dir else settings.input_dir, context, settings)
    if not documents:
        raise PipelineError(f"输入目录中没有支持的文件: {input_dir or settings.input_dir}")

    manifest = RunManifest.create(context.run_id, documents)
    manifest.save(context.manifest_path)

    try:
        mineru_result = (mineru_stage or MinerUStage(settings)).run(context, documents)
        _record_or_abort(manifest, context, mineru_result, "MinerU 阶段没有成功文件")

        kimi_result = (kimi_stage or KimiStage(settings)).run(context, documents)
        _record_or_abort(manifest, context, kimi_result, "Kimi 阶段没有成功文件")

        render_result = (render_stage or RenderStage(settings)).run(context, documents)
        _record_or_abort(manifest, context, render_result, "Render 阶段没有成功文件")

        manifest.status = "success"
        manifest.save(context.manifest_path)
        return manifest
    except Exception as exc:
        manifest.add_error(str(exc))
        manifest.save(context.manifest_path)
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(str(exc)) from exc


def run_parse(input_dir: Path | str | None = None, run_id: str | None = None, settings: Settings | None = None) -> RunManifest:
    settings = settings or Settings.from_env()
    missing = ["MINERU_API_TOKEN"] if not settings.mineru_api_token else []
    if missing:
        raise PipelineError(f"缺少必要配置: {', '.join(missing)}")

    context = create_run_context(settings, run_id)
    context.ensure_directories()
    documents = prepare_documents(Path(input_dir) if input_dir else settings.input_dir, context, settings)
    if not documents:
        raise PipelineError(f"输入目录中没有支持的文件: {input_dir or settings.input_dir}")
    manifest = RunManifest.create(context.run_id, documents)
    result = MinerUStage(settings).run(context, documents)
    _record_or_abort(manifest, context, result, "MinerU 阶段没有成功文件")
    manifest.status = "parsed"
    manifest.save(context.manifest_path)
    return manifest


def run_organize(run_id: str, settings: Settings | None = None) -> RunManifest:
    settings = settings or Settings.from_env()
    if not settings.kimi_api_key:
        raise PipelineError("缺少必要配置: KIMI_API_KEY")
    context = create_run_context(settings, run_id)
    manifest = RunManifest.load(context.manifest_path)
    result = KimiStage(settings).run(context, manifest.documents)
    _record_or_abort(manifest, context, result, "Kimi 阶段没有成功文件")
    manifest.status = "organized"
    manifest.save(context.manifest_path)
    return manifest


def run_render(run_id: str, settings: Settings | None = None) -> RunManifest:
    settings = settings or Settings.from_env()
    context = create_run_context(settings, run_id)
    manifest = RunManifest.load(context.manifest_path)
    result = RenderStage(settings).run(context, manifest.documents)
    _record_or_abort(manifest, context, result, "Render 阶段没有成功文件")
    manifest.status = "rendered"
    manifest.save(context.manifest_path)
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
    return RunContext.create(settings.runs_dir, actual_run_id)


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


def _record_or_abort(manifest: RunManifest, context: RunContext, result: StageResult, message: str) -> None:
    manifest.record_stage(result, context.run_dir)
    manifest.save(context.manifest_path)
    if result.success == 0:
        raise PipelineError(message)
