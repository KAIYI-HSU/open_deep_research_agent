"""Heuristics to extract title and year candidates."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from open_deep_research.paper_renamer.extractor.pymupdf_extractor import TextBlock, TextLine

TITLE_SCORE_THRESHOLD = 0.7
YEAR_SCORE_THRESHOLD = 0.6

NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\barxiv\b",
        r"\bproceedings\b",
        r"\bdoi\b",
        r"\bieee\b",
        r"\bacm\b",
        r"\bcopyright\b",
        r"\bpage\s+\d+\b",
    ]
]


@dataclass(frozen=True)
class TitleCandidate:
    text: str
    score: float
    features: dict[str, float | str]
    source_lines: tuple[TextLine, ...]


@dataclass(frozen=True)
class YearCandidate:
    year: int
    score: float
    context: str
    source_line: TextLine | None


def _is_noise(text: str) -> bool:
    return any(pattern.search(text) for pattern in NOISE_PATTERNS)


def _line_char_ratio(text: str) -> float:
    letters = sum(1 for char in text if char.isalpha())
    total = sum(1 for char in text if not char.isspace())
    return letters / total if total else 0.0


def _title_score(
    text: str,
    font_size: float,
    max_font_size: float,
    y0: float,
    page_height: float,
) -> float:
    if max_font_size <= 0:
        font_score = 0.0
    else:
        font_score = min(font_size / max_font_size, 1.0)
    position_score = 1.0 - min(y0 / max(page_height, 1.0), 1.0)
    ratio_score = _line_char_ratio(text)
    length_penalty = 1.0
    if len(text) < 6:
        length_penalty = 0.0
    elif len(text) > 200:
        length_penalty = 0.4
    noise_penalty = 0.2 if _is_noise(text) else 1.0
    return (0.55 * font_score + 0.35 * position_score + 0.1 * ratio_score) * length_penalty * noise_penalty


def _merge_lines(line: TextLine, next_line: TextLine) -> tuple[str, tuple[float, float, float, float]]:
    merged_text = f"{line.text} {next_line.text}".strip()
    x0 = min(line.bbox[0], next_line.bbox[0])
    y0 = min(line.bbox[1], next_line.bbox[1])
    x1 = max(line.bbox[2], next_line.bbox[2])
    y1 = max(line.bbox[3], next_line.bbox[3])
    return merged_text, (x0, y0, x1, y1)


def generate_title_candidates(
    blocks: Iterable[TextBlock],
    page_height: float,
    top_ratio: float = 0.55,
) -> list[TitleCandidate]:
    lines: list[TextLine] = []
    max_font = 0.0
    for block in blocks:
        max_font = max(max_font, block.max_font_size)
        for line in block.lines:
            if line.text:
                lines.append(line)

    top_limit = page_height * top_ratio
    candidates: list[TitleCandidate] = []

    for idx, line in enumerate(lines):
        if line.bbox[1] > top_limit:
            continue
        text = line.text.strip()
        if not text or _is_noise(text):
            continue
        score = _title_score(text, line.avg_font_size, max_font, line.bbox[1], page_height)
        if score <= 0:
            continue
        candidates.append(
            TitleCandidate(
                text=text,
                score=score,
                features={
                    "font_score": min(line.avg_font_size / max(max_font, 1.0), 1.0),
                    "position_score": 1.0 - min(line.bbox[1] / max(page_height, 1.0), 1.0),
                    "length": len(text),
                },
                source_lines=(line,),
            )
        )
        if idx + 1 < len(lines):
            next_line = lines[idx + 1]
            if next_line.bbox[1] > top_limit:
                continue
            merged_text, merged_bbox = _merge_lines(line, next_line)
            if len(merged_text) > 200 or _is_noise(merged_text):
                continue
            merged_font = max(line.avg_font_size, next_line.avg_font_size)
            merged_score = _title_score(
                merged_text, merged_font, max_font, merged_bbox[1], page_height
            )
            if merged_score > score:
                candidates.append(
                    TitleCandidate(
                        text=merged_text,
                        score=merged_score,
                        features={
                            "font_score": min(merged_font / max(max_font, 1.0), 1.0),
                            "position_score": 1.0 - min(merged_bbox[1] / max(page_height, 1.0), 1.0),
                            "length": len(merged_text),
                        },
                        source_lines=(line, next_line),
                    )
                )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[:15]


def _is_reference_zone(line: TextLine, page_height: float) -> bool:
    return line.bbox[1] > page_height * 0.6


def generate_year_candidates(
    lines: Iterable[TextLine],
    page_height: float,
) -> list[YearCandidate]:
    year_regex = re.compile(r"\b(19\d{2}|20\d{2})\b")
    candidates: list[YearCandidate] = []

    for line in lines:
        if not line.text:
            continue
        for match in year_regex.finditer(line.text):
            year = int(match.group(1))
            if not 1990 <= year <= 2035:
                continue
            base_score = 0.5
            if line.bbox[1] < page_height * 0.35:
                base_score += 0.25
            if _is_reference_zone(line, page_height):
                base_score -= 0.2
            if re.search(r"©|copyright|proceedings|ieee|acm", line.text, re.IGNORECASE):
                base_score += 0.2
            candidates.append(
                YearCandidate(
                    year=year,
                    score=max(min(base_score, 1.0), 0.0),
                    context=line.text.strip(),
                    source_line=line,
                )
            )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates
