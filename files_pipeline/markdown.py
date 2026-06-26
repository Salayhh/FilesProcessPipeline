"""Markdown transformations for final report rendering."""

from __future__ import annotations

import re


def extract_bad_item_title(content: str) -> str | None:
    pattern_with_hash = r"^#\s*不良项目：\s*(.+)$"
    match = re.search(pattern_with_hash, content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        return f"[{title}]" if title else None

    pattern_without_hash = r"(?:^|\n\s*\n)\s*不良项目：\s*(.+?)(?=\n|$)"
    match = re.search(pattern_without_hash, content)
    if match:
        title = match.group(1).strip().split("\n")[0].strip()
        return f"[{title}]" if title else None
    return None


def process_markdown_content(content: str, bad_item_title: str, section_separator: str) -> str:
    lines = content.split("\n")
    h2_pattern = re.compile(r"^(##\s*)(第[一二三四五六七八九十]+)(部分|章|节)?(\s*[:：]?\s*)(.*)$")
    h3_pattern = re.compile(r"^(###\s+)(.*)$")

    h2_positions = [index for index, line in enumerate(lines) if h2_pattern.match(line)]
    h2_has_h3: dict[int, bool] = {}
    for index, position in enumerate(h2_positions):
        next_h2 = h2_positions[index + 1] if index + 1 < len(h2_positions) else len(lines)
        h2_has_h3[position] = any(h3_pattern.match(lines[i]) for i in range(position + 1, next_h2))

    result_lines: list[str] = []
    h2_count = 0

    for index, line in enumerate(lines):
        h2_match = h2_pattern.match(line)
        if not h2_match:
            result_lines.append(line)
            continue

        h2_count += 1
        prefix = h2_match.group(1)
        num_part = h2_match.group(2)
        suffix = h2_match.group(3) or ""
        separator = h2_match.group(4)
        rest = h2_match.group(5)
        new_heading = f"{prefix}{bad_item_title}{num_part}{suffix}{separator}{rest}"

        if h2_count == 1:
            result_lines.append(new_heading)
            continue

        if result_lines and result_lines[-1].strip():
            result_lines.append("")
        result_lines.append(section_separator)
        result_lines.append("")

        if h2_has_h3.get(index, False):
            h2_content = new_heading.lstrip("#").strip()
            rest_after_title = h2_content[len(bad_item_title) :]
            h3_prefix_text = f"{bad_item_title[:-1]}({rest_after_title})]"
            next_h2 = h2_positions[h2_count] if h2_count < len(h2_positions) else len(lines)
            for child_index in range(index + 1, next_h2):
                h3_match = h3_pattern.match(lines[child_index])
                if h3_match:
                    lines[child_index] = f"### {h3_prefix_text}{h3_match.group(2)}"
            continue

        result_lines.append(new_heading)

    return "\n".join(result_lines)


def rewrite_image_links(content: str, source_id: str, link_prefix: str) -> str:
    markdown_pattern = re.compile(r"!\[([^\]]*)\]\(\s*(?:\./)?images/([^)]+?)\s*\)")
    html_pattern = re.compile(
        r"(<\s*img\b[^>]*?\bsrc\s*=\s*)([\"'])(\s*(?:\./)?images/([^\"'>\s]+)\s*)(\2)",
        re.IGNORECASE,
    )
    normalized_prefix = link_prefix.rstrip("/")

    def replace_markdown(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        image_name = match.group(2).strip()
        return f"![{alt_text}]({normalized_prefix}/{image_name})"

    def replace_html(match: re.Match[str]) -> str:
        image_name = match.group(4).strip()
        return f"{match.group(1)}{match.group(2)}{normalized_prefix}/{image_name}{match.group(5)}"

    content = markdown_pattern.sub(replace_markdown, content)
    return html_pattern.sub(replace_html, content)
