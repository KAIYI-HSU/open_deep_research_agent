"""vLLM client wrapper for structured extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from open_deep_research.paper_renamer.llm.prompts import SYSTEM_PROMPT, build_user_prompt


@dataclass(frozen=True)
class LLMConfig:
    url: str
    model: str
    api_key: str | None = None
    timeout_s: float = 8.0
    max_tokens: int = 256


class LLMError(RuntimeError):
    """Raised when the LLM response is invalid or cannot be parsed."""


def request_structured_selection(
    config: LLMConfig,
    title_candidates: list[str],
    year_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "model": config.model,
        "temperature": 0,
        "max_tokens": config.max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(title_candidates, year_candidates)},
        ],
    }

    with httpx.Client(timeout=config.timeout_s) as client:
        response = client.post(config.url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError("Invalid response format from vLLM") from exc

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError("vLLM response is not valid JSON") from exc

    return parsed
