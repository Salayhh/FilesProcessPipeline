"""Configuration loading for FilesProcessPipeline v2."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


SUPPORTED_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".jp2",
    ".webp",
    ".gif",
    ".bmp",
    ".html",
    ".htm",
)


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前值: {value}") from exc


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from `.env` and environment variables."""

    base_dir: Path
    input_dir: Path
    runs_dir: Path
    data_dir: Path

    mineru_base_url: str
    mineru_api_token: str | None
    mineru_model_version: str = "vlm"
    mineru_enable_table: bool = True
    mineru_enable_formula: bool = False
    mineru_language: str = "ch"
    mineru_max_files_per_batch: int = 200
    mineru_poll_interval: int = 10
    mineru_max_poll_time: int = 3600
    mineru_max_query_errors: int = 10

    kimi_api_key: str | None = None
    kimi_model: str = "kimi-k2.5"
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_timeout: int = 600
    kimi_max_retries: int = 2
    kimi_retry_delay: int = 10

    image_base_url: str = ""
    output_format: str = "md"
    section_separator: str = "+=+=+="
    supported_extensions: tuple[str, ...] = field(default_factory=lambda: SUPPORTED_EXTENSIONS)
    kimi_template_path: Path | None = None

    @classmethod
    def from_env(cls, base_dir: Path | None = None, env_file: Path | None = None) -> "Settings":
        """Load settings from `.env`, letting `.env` override shell variables."""
        root = Path(base_dir).resolve() if base_dir else Path(__file__).resolve().parents[1]
        if env_file is not None:
            dotenv_path = Path(env_file).resolve()
            if dotenv_path.exists():
                load_dotenv(dotenv_path=dotenv_path, override=True)
        else:
            dotenv_path = root / ".env"
            if dotenv_path.exists():
                load_dotenv(dotenv_path=dotenv_path, override=True)
            elif base_dir is None:
                load_dotenv(override=True)

        output_format = os.getenv("OUTPUT_FORMAT", "md").strip().lower()
        if output_format not in {"md", "txt"}:
            raise ValueError("OUTPUT_FORMAT 只允许 md 或 txt")

        template_path = root / "files_pipeline" / "prompts" / "kimi_bad_report_template.md"

        return cls(
            base_dir=root,
            input_dir=root / "input",
            runs_dir=root / "runs",
            data_dir=root / "data",
            mineru_base_url=os.getenv("MINERU_BASE_URL", "https://mineru.net/api/v4"),
            mineru_api_token=os.getenv("MINERU_API_TOKEN") or None,
            mineru_max_poll_time=_get_int_env("MINERU_MAX_POLL_TIME", 3600),
            mineru_max_query_errors=_get_int_env("MINERU_MAX_QUERY_ERRORS", 10),
            kimi_api_key=os.getenv("KIMI_API_KEY") or None,
            kimi_model=os.getenv("KIMI_MODEL", "kimi-k2.5"),
            kimi_base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
            kimi_timeout=_get_int_env("KIMI_TIMEOUT", 600),
            kimi_max_retries=_get_int_env("KIMI_MAX_RETRIES", 2),
            kimi_retry_delay=_get_int_env("KIMI_RETRY_DELAY", 10),
            image_base_url=os.getenv("IMAGE_BASE_URL", "").strip(),
            output_format=output_format,
            kimi_template_path=template_path,
        )

    def missing_required_keys(self) -> list[str]:
        missing = []
        if not self.mineru_api_token:
            missing.append("MINERU_API_TOKEN")
        if not self.kimi_api_key:
            missing.append("KIMI_API_KEY")
        return missing

    def ensure_directories(self, extra_dirs: Iterable[Path] = ()) -> None:
        dirs = [self.input_dir, self.runs_dir, self.data_dir, *extra_dirs]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)
