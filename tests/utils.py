from pathlib import Path

from files_pipeline.config import Settings


def make_settings(base_dir: Path, **overrides) -> Settings:
    prompt_path = base_dir / "template.md"
    prompt_path.write_text("# 模板", encoding="utf-8")
    values = {
        "base_dir": base_dir,
        "input_dir": base_dir / "input",
        "runs_dir": base_dir / "runs",
        "data_dir": base_dir / "data",
        "mineru_base_url": "https://mineru.example/api/v4",
        "mineru_api_token": "mineru-token",
        "mineru_model_version": "vlm",
        "mineru_enable_table": True,
        "mineru_enable_formula": False,
        "mineru_language": "ch",
        "mineru_max_files_per_batch": 200,
        "mineru_submit_limit_per_minute": 50,
        "mineru_poll_interval": 0,
        "mineru_max_poll_time": 1,
        "mineru_max_query_errors": 1,
        "llm_api_key": "llm-key",
        "llm_model": "kimi-k2.5",
        "llm_base_url": "https://llm.example/v1",
        "llm_timeout": 600,
        "llm_max_retries": 2,
        "llm_retry_delay": 0,
        "llm_concurrency": 4,
        "assets_base_dir": None,
        "image_base_url": "",
        "output_format": "md",
        "section_separator": "+=+=+=",
        "sanitize_enabled": False,
        "sanitize_entities_path": None,
        "organize_template_path": prompt_path,
    }
    values.update(overrides)
    return Settings(**values)
