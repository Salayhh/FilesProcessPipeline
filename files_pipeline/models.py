"""Typed runtime models for FilesProcessPipeline v2."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def utc_now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _path_to_text(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMCompletion:
    content: str
    token_usage: TokenUsage = field(default_factory=TokenUsage)


KimiCompletion = LLMCompletion


@dataclass
class DocumentRecord:
    source_id: str
    original_path: Path
    source_path: Path
    original_name: str
    original_stem: str
    extension: str
    mineru_markdown_path: Path | None = None
    sanitized_markdown_path: Path | None = None
    organized_markdown_path: Path | None = None
    final_output_path: Path | None = None
    status: str = "pending"
    errors: list[str] = field(default_factory=list)

    @property
    def kimi_markdown_path(self) -> Path | None:
        return self.organized_markdown_path

    @kimi_markdown_path.setter
    def kimi_markdown_path(self, value: Path | None) -> None:
        self.organized_markdown_path = value

    def add_error(self, message: str) -> None:
        self.status = "failed"
        self.errors.append(message)

    def to_dict(self, run_dir: Path) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "original_path": str(self.original_path),
            "source_path": _path_to_text(self.source_path, run_dir),
            "original_name": self.original_name,
            "original_stem": self.original_stem,
            "extension": self.extension,
            "mineru_markdown_path": _path_to_text(self.mineru_markdown_path, run_dir),
            "sanitized_markdown_path": _path_to_text(self.sanitized_markdown_path, run_dir),
            "organized_markdown_path": _path_to_text(self.organized_markdown_path, run_dir),
            "final_output_path": _path_to_text(self.final_output_path, run_dir),
            "status": self.status,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], run_dir: Path) -> "DocumentRecord":
        def resolve(value: str | None) -> Path | None:
            if value is None:
                return None
            path = Path(value)
            return path if path.is_absolute() else run_dir / path

        return cls(
            source_id=data["source_id"],
            original_path=Path(data["original_path"]),
            source_path=resolve(data["source_path"]) or run_dir / "source" / data["original_name"],
            original_name=data["original_name"],
            original_stem=data["original_stem"],
            extension=data["extension"],
            mineru_markdown_path=resolve(data.get("mineru_markdown_path")),
            sanitized_markdown_path=resolve(data.get("sanitized_markdown_path")),
            organized_markdown_path=resolve(data.get("organized_markdown_path") or data.get("kimi_markdown_path")),
            final_output_path=resolve(data.get("final_output_path")),
            status=data.get("status", "pending"),
            errors=list(data.get("errors", [])),
        )


@dataclass
class StageResult:
    stage: str
    success: int = 0
    failed: int = 0
    output_files: list[Path] = field(default_factory=list)
    failed_documents: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    images_copied: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    def to_dict(self, run_dir: Path) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "success": self.success,
            "failed": self.failed,
            "output_files": [_path_to_text(path, run_dir) for path in self.output_files],
            "failed_documents": self.failed_documents,
            "errors": self.errors,
            "images_copied": self.images_copied,
            "token_usage": self.token_usage.to_dict(),
        }


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    source_dir: Path
    mineru_dir: Path
    sanitized_dir: Path
    organized_dir: Path
    assets_dir: Path
    final_dir: Path
    manifest_path: Path

    @property
    def kimi_dir(self) -> Path:
        return self.organized_dir

    @classmethod
    def create(cls, runs_dir: Path, run_id: str, assets_base_dir: Path | None = None) -> "RunContext":
        run_dir = runs_dir / run_id
        assets_dir = assets_base_dir / run_id if assets_base_dir else run_dir / "assets"
        return cls(
            run_id=run_id,
            run_dir=run_dir,
            source_dir=run_dir / "source",
            mineru_dir=run_dir / "mineru",
            sanitized_dir=run_dir / "sanitized",
            organized_dir=run_dir / "organized",
            assets_dir=assets_dir,
            final_dir=run_dir / "final",
            manifest_path=run_dir / "manifest.json",
        )

    def ensure_directories(self) -> None:
        for directory in [
            self.run_dir,
            self.source_dir,
            self.mineru_dir,
            self.sanitized_dir,
            self.organized_dir,
            self.assets_dir,
            self.final_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class RunManifest:
    run_id: str
    status: str
    created_at: str
    updated_at: str
    documents: list[DocumentRecord] = field(default_factory=list)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, run_id: str, documents: list[DocumentRecord]) -> "RunManifest":
        now = utc_now_text()
        return cls(run_id=run_id, status="running", created_at=now, updated_at=now, documents=documents)

    @classmethod
    def load(cls, path: Path) -> "RunManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        run_dir = path.parent
        return cls(
            run_id=data["run_id"],
            status=data.get("status", "unknown"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            documents=[DocumentRecord.from_dict(item, run_dir) for item in data.get("documents", [])],
            stages=dict(data.get("stages", {})),
            errors=list(data.get("errors", [])),
        )

    def record_stage(self, result: StageResult, run_dir: Path) -> None:
        self.stages[result.stage] = result.to_dict(run_dir)
        self.updated_at = utc_now_text()

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.status = "failed"
        self.updated_at = utc_now_text()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(path.parent), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self, run_dir: Path) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "documents": [document.to_dict(run_dir) for document in self.documents],
            "stages": self.stages,
            "errors": self.errors,
        }
