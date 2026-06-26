"""Stage 1.5: sanitize MinerU Markdown before sending it to the LLM."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from files_pipeline.config import Settings
from files_pipeline.models import DocumentRecord, RunContext, StageResult
from files_pipeline.progress import format_duration
from files_pipeline.stages.organize import read_text_with_fallback


Replacement = tuple[str, str]

LINK_DESTINATION_PATTERN = re.compile(r"(!?\[[^\]\n]*\]\()([^)]+)(\))")
INLINE_CODE_PATTERN = re.compile(r"(`+[^`]*`+)")


class SanitizeStage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, context: RunContext, documents: list[DocumentRecord]) -> StageResult:
        start = time.monotonic()
        result = StageResult(stage="sanitize")
        context.sanitized_dir.mkdir(parents=True, exist_ok=True)

        candidates = [document for document in documents if document.mineru_markdown_path]
        print(f"[Sanitize] 开始脱敏: {len(candidates)}/{len(documents)} 个 MinerU Markdown", flush=True)
        if not candidates:
            result.failed = len(documents)
            result.errors["input"] = "没有 MinerU Markdown 可供脱敏"
            print("[Sanitize] 没有 MinerU Markdown 可供处理", flush=True)
            return result

        try:
            replacements = load_replacements(self.settings.sanitize_entities_path)
        except Exception as exc:
            message = str(exc)
            result.failed = len(candidates)
            result.errors["config"] = message
            for document in candidates:
                document.add_error(message)
                result.failed_documents.append(document.source_id)
                result.errors[document.source_id] = message
            print(f"[Sanitize] 配置错误: {message}", flush=True)
            return result

        for index, document in enumerate(candidates, 1):
            try:
                print(f"[Sanitize] 文件 {index}/{len(candidates)}: {document.original_name}", flush=True)
                output_path, replacements_count = self._process_document(context, document, replacements)
                document.sanitized_markdown_path = output_path
                document.status = "sanitized_done"
                result.success += 1
                result.output_files.append(output_path)
                print(
                    f"[Sanitize] 文件完成: {document.original_name}, replacements={replacements_count}, output={output_path}",
                    flush=True,
                )
            except Exception as exc:
                message = str(exc)
                document.add_error(message)
                result.failed += 1
                result.failed_documents.append(document.source_id)
                result.errors[document.source_id] = message
                print(f"[Sanitize] 脱敏失败: {document.original_name}: {message}", flush=True)

        print(
            f"[Sanitize] 完成: success={result.success}, failed={result.failed}, "
            f"用时 {format_duration(time.monotonic() - start)}",
            flush=True,
        )
        return result

    def _process_document(
        self,
        context: RunContext,
        document: DocumentRecord,
        replacements: list[Replacement],
    ) -> tuple[Path, int]:
        if not document.mineru_markdown_path:
            raise ValueError("缺少 MinerU Markdown 路径")

        content = read_text_with_fallback(document.mineru_markdown_path)
        sanitized, replacements_count = sanitize_markdown(content, replacements)
        output_path = context.sanitized_dir / f"{document.source_id}.md"
        output_path.write_text(sanitized, encoding="utf-8")
        return output_path, replacements_count


def load_replacements(path: Path | None) -> list[Replacement]:
    if path is None:
        raise ValueError("未配置 SANITIZE_ENTITIES_PATH")
    if not path.exists():
        raise FileNotFoundError(f"脱敏词表不存在: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    entries = _extract_entries(data)
    replacements: list[Replacement] = []
    for source, replacement in entries:
        source_text = str(source).strip()
        replacement_text = str(replacement).strip()
        if not source_text or not replacement_text:
            raise ValueError("脱敏词表中的原文和替换值都不能为空")
        replacements.append((source_text, replacement_text))

    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    return replacements


def _extract_entries(data: Any) -> list[tuple[Any, Any]]:
    if isinstance(data, dict) and isinstance(data.get("entities"), dict):
        return list(data["entities"].items())
    if isinstance(data, dict) and isinstance(data.get("entities"), list):
        return [(item.get("source"), item.get("replacement")) for item in data["entities"]]
    if isinstance(data, dict):
        return list(data.items())
    if isinstance(data, list):
        return [(item.get("source"), item.get("replacement")) for item in data]
    raise ValueError("脱敏词表必须是 JSON 对象或列表")


def sanitize_markdown(content: str, replacements: list[Replacement]) -> tuple[str, int]:
    if not replacements:
        return content, 0

    pattern = re.compile("|".join(re.escape(source) for source, _ in replacements))
    replacement_map = dict(replacements)
    count = 0
    in_fence = False
    result_lines: list[str] = []

    def replace_match(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return replacement_map[match.group(0)]

    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            result_lines.append(line)
            in_fence = not in_fence
            continue
        if in_fence:
            result_lines.append(line)
            continue
        result_lines.append(_sanitize_line(line, pattern, replace_match))

    return "".join(result_lines), count


def _sanitize_line(line: str, pattern: re.Pattern[str], replace_match) -> str:
    protected: list[str] = []

    def protect_destination(match: re.Match[str]) -> str:
        protected.append(match.group(2))
        return f"{match.group(1)}\x00SANITIZE_LINK_{len(protected) - 1}\x00{match.group(3)}"

    line = LINK_DESTINATION_PATTERN.sub(protect_destination, line)
    parts = INLINE_CODE_PATTERN.split(line)
    for index in range(0, len(parts), 2):
        parts[index] = pattern.sub(replace_match, parts[index])
    line = "".join(parts)

    for index, destination in enumerate(protected):
        line = line.replace(f"\x00SANITIZE_LINK_{index}\x00", destination)
    return line
