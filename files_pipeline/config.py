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


def _get_env_value(name: str, fallback_names: tuple[str, ...] = ()) -> tuple[str, str | None]:
    for candidate in (name, *fallback_names):
        value = os.getenv(candidate)
        if value is not None and value != "":
            return candidate, value
    return name, None


def _get_env(name: str, default: str = "", fallback_names: tuple[str, ...] = ()) -> str:
    _, value = _get_env_value(name, fallback_names)
    return default if value is None else value


def _get_int_env(name: str, default: int, fallback_names: tuple[str, ...] = ()) -> int:
    actual_name, value = _get_env_value(name, fallback_names)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{actual_name} 必须是整数，当前值: {value}") from exc


def _get_positive_int_env(name: str, default: int, fallback_names: tuple[str, ...] = ()) -> int:
    value = _get_int_env(name, default, fallback_names)
    if value < 1:
        raise ValueError(f"{name} 必须是大于等于 1 的整数，当前值: {value}")
    return value


def _get_nonnegative_int_env(name: str, default: int, fallback_names: tuple[str, ...] = ()) -> int:
    value = _get_int_env(name, default, fallback_names)
    if value < 0:
        raise ValueError(f"{name} 必须是大于等于 0 的整数，当前值: {value}")
    return value


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} 必须是布尔值，当前值: {value}")


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from `.env` and environment variables."""

    base_dir: Path
    input_dir: Path
    runs_dir: Path
    data_dir: Path

    mineru_base_url: str
    mineru_api_token: str | None
    mineru_model_version: str = "pipeline"
    mineru_enable_table: bool = True
    mineru_enable_formula: bool = False
    mineru_language: str = "ch"
    mineru_max_files_per_batch: int = 50
    mineru_submit_limit_per_minute: int = 50
    mineru_poll_interval: int = 10
    mineru_max_poll_time: int = 3600
    mineru_max_query_errors: int = 10
    mineru_upload_timeout: int = 60
    mineru_upload_max_retries: int = 2
    mineru_upload_retry_delay: int = 10

    llm_api_key: str | None = None
    llm_model: str = "kimi-k2.5"
    llm_base_url: str = "https://api.moonshot.cn/v1"
    llm_timeout: int = 600
    llm_max_retries: int = 2
    llm_retry_delay: int = 10
    llm_concurrency: int = 4

    assets_base_dir: Path | None = None
    image_base_url: str = ""
    output_format: str = "md"
    section_separator: str = "+=+=+="
    sanitize_enabled: bool = False
    sanitize_entities_path: Path | None = None
    supported_extensions: tuple[str, ...] = field(default_factory=lambda: SUPPORTED_EXTENSIONS)
    organize_template_path: Path | None = None

    @property
    def kimi_api_key(self) -> str | None:
        return self.llm_api_key

    @property
    def kimi_model(self) -> str:
        return self.llm_model

    @property
    def kimi_base_url(self) -> str:
        return self.llm_base_url

    @property
    def kimi_timeout(self) -> int:
        return self.llm_timeout

    @property
    def kimi_max_retries(self) -> int:
        return self.llm_max_retries

    @property
    def kimi_retry_delay(self) -> int:
        return self.llm_retry_delay

    @property
    def kimi_concurrency(self) -> int:
        return self.llm_concurrency

    @property
    def kimi_template_path(self) -> Path | None:
        return self.organize_template_path

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

        template_path = root / "files_pipeline" / "prompts" / "bad_report_template.md"
        if not template_path.exists():
            template_path = root / "files_pipeline" / "prompts" / "kimi_bad_report_template.md"

        return cls(
            base_dir=root,
            input_dir=root / "input",
            runs_dir=root / "runs",
            data_dir=root / "data",
            mineru_base_url=os.getenv("MINERU_BASE_URL", "https://mineru.net/api/v4"),
            mineru_api_token=os.getenv("MINERU_API_TOKEN") or None,
            mineru_model_version=os.getenv("MINERU_MODEL_VERSION", "pipeline"),
            mineru_enable_table=_get_bool_env("MINERU_ENABLE_TABLE", True),
            mineru_enable_formula=_get_bool_env("MINERU_ENABLE_FORMULA", False),
            mineru_language=os.getenv("MINERU_LANGUAGE", "ch"),
            mineru_max_files_per_batch=_get_positive_int_env("MINERU_MAX_FILES_PER_BATCH", 50),
            mineru_submit_limit_per_minute=_get_positive_int_env("MINERU_SUBMIT_LIMIT_PER_MINUTE", 50),
            mineru_max_poll_time=_get_int_env("MINERU_MAX_POLL_TIME", 3600),
            mineru_max_query_errors=_get_int_env("MINERU_MAX_QUERY_ERRORS", 10),
            mineru_upload_timeout=_get_positive_int_env("MINERU_UPLOAD_TIMEOUT", 60),
            mineru_upload_max_retries=_get_nonnegative_int_env("MINERU_UPLOAD_MAX_RETRIES", 2),
            mineru_upload_retry_delay=_get_nonnegative_int_env("MINERU_UPLOAD_RETRY_DELAY", 10),
            llm_api_key=_get_env("LLM_API_KEY", fallback_names=("KIMI_API_KEY",)) or None,
            llm_model=_get_env("LLM_MODEL", "kimi-k2.5", fallback_names=("KIMI_MODEL",)),
            llm_base_url=_get_env("LLM_BASE_URL", "https://api.moonshot.cn/v1", fallback_names=("KIMI_BASE_URL",)),
            llm_timeout=_get_int_env("LLM_TIMEOUT", 600, fallback_names=("KIMI_TIMEOUT",)),
            llm_max_retries=_get_int_env("LLM_MAX_RETRIES", 2, fallback_names=("KIMI_MAX_RETRIES",)),
            llm_retry_delay=_get_int_env("LLM_RETRY_DELAY", 10, fallback_names=("KIMI_RETRY_DELAY",)),
            llm_concurrency=_get_positive_int_env("LLM_CONCURRENCY", 4, fallback_names=("KIMI_CONCURRENCY",)),
            assets_base_dir=_get_optional_path_env("ASSETS_DIR", root),
            image_base_url=os.getenv("IMAGE_BASE_URL", "").strip(),
            output_format=output_format,
            organize_template_path=template_path,
            sanitize_enabled=_get_bool_env("SANITIZE_ENABLED", False),
            sanitize_entities_path=_get_optional_path_env("SANITIZE_ENTITIES_PATH", root),
        )

    def missing_required_keys(self) -> list[str]:
        missing = []
        if not self.mineru_api_token:
            missing.append("MINERU_API_TOKEN")
        if not self.llm_api_key:
            missing.append("LLM_API_KEY")
        return missing

    def ensure_directories(self, extra_dirs: Iterable[Path] = ()) -> None:
        dirs = [self.input_dir, self.runs_dir, self.data_dir, *extra_dirs]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)


def _get_optional_path_env(name: str, root: Path) -> Path | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    return path if path.is_absolute() else root / path
