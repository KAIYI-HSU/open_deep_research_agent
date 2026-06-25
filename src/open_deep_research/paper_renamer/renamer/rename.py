"""Renaming logic for PDF files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from open_deep_research.paper_renamer.renamer.sanitize import sanitize_filename


def build_filename(template: str, title: str, year: int | None, first_author: str | None) -> str:
    mapping = {
        "title": title,
        "year": str(year) if year else "",
        "first_author": first_author or "",
    }
    return template.format(**mapping).strip()


def unique_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path
    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent

    for index in range(1, 100):
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    digest = hashlib.sha1(str(target_path).encode("utf-8")).hexdigest()[:8]
    return parent / f"{stem}-{digest}{suffix}"


def rename_file(
    source_path: Path,
    target_name: str,
    dry_run: bool,
) -> Path:
    sanitized = sanitize_filename(target_name)
    target_path = source_path.with_name(sanitized)
    target_path = unique_path(target_path)
    if dry_run:
        return target_path
    return source_path.rename(target_path)
