"""Asset copy helpers."""

from __future__ import annotations

import shutil
from pathlib import Path


def copy_document_images(mineru_document_dir: Path, assets_dir: Path, source_id: str) -> int:
    images_dir = mineru_document_dir / "images"
    if not images_dir.is_dir():
        return 0

    target_dir = assets_dir / source_id
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for image_file in sorted(images_dir.iterdir()):
        if image_file.is_file():
            shutil.copy2(image_file, target_dir / image_file.name)
            copied += 1
    return copied
