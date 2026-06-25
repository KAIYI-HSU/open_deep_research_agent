"""Utilities for generating safe filenames."""

from __future__ import annotations

import re
import unicodedata

INVALID_CHARS = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")
MULTI_SPACE = re.compile(r"\s+")


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """Sanitize filename to be filesystem-safe across platforms."""
    normalized = unicodedata.normalize("NFKC", name)
    normalized = INVALID_CHARS.sub("", normalized)
    normalized = MULTI_SPACE.sub(" ", normalized).strip(" .")
    if len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip(" .")
    return normalized
