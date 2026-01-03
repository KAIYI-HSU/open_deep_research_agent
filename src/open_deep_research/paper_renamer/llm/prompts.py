"""Prompt templates for vLLM structured extraction."""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = (
    "You are a strict extraction engine. "
    "You must only select from provided candidates or concatenate two adjacent title candidates. "
    "Do not invent text. Output must be valid JSON."
)


def build_user_prompt(
    title_candidates: list[str],
    year_candidates: list[dict[str, Any]],
) -> str:
    payload = {
        "title_candidates": [
            {"index": index, "text": text} for index, text in enumerate(title_candidates)
        ],
        "year_candidates": year_candidates,
        "rules": {
            "title": "must match candidate text or concat of two adjacent candidates",
            "year": "must match one of the candidates",
        },
        "output_schema": {
            "title": "string",
            "year": "number",
            "title_source_index": "number",
            "year_source": "regex|context",
            "confidence": "number",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
