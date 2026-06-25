"""PyMuPDF-based text extraction for paper metadata heuristics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz


@dataclass(frozen=True)
class TextSpan:
    text: str
    font_size: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class TextLine:
    spans: tuple[TextSpan, ...]
    text: str
    avg_font_size: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class TextBlock:
    lines: tuple[TextLine, ...]
    text: str
    max_font_size: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ExtractedPage:
    blocks: tuple[TextBlock, ...]
    page_height: float


def _build_line(spans: Iterable[TextSpan]) -> TextLine:
    span_list = list(spans)
    text = "".join(span.text for span in span_list).strip()
    if span_list:
        avg_font_size = sum(span.font_size for span in span_list) / len(span_list)
        x0 = min(span.bbox[0] for span in span_list)
        y0 = min(span.bbox[1] for span in span_list)
        x1 = max(span.bbox[2] for span in span_list)
        y1 = max(span.bbox[3] for span in span_list)
        bbox = (x0, y0, x1, y1)
    else:
        avg_font_size = 0.0
        bbox = (0.0, 0.0, 0.0, 0.0)
    return TextLine(spans=tuple(span_list), text=text, avg_font_size=avg_font_size, bbox=bbox)


def _build_block(lines: Iterable[TextLine]) -> TextBlock:
    line_list = [line for line in lines if line.text]
    text = "\n".join(line.text for line in line_list).strip()
    if line_list:
        max_font_size = max(line.avg_font_size for line in line_list)
        x0 = min(line.bbox[0] for line in line_list)
        y0 = min(line.bbox[1] for line in line_list)
        x1 = max(line.bbox[2] for line in line_list)
        y1 = max(line.bbox[3] for line in line_list)
        bbox = (x0, y0, x1, y1)
    else:
        max_font_size = 0.0
        bbox = (0.0, 0.0, 0.0, 0.0)
    return TextBlock(lines=tuple(line_list), text=text, max_font_size=max_font_size, bbox=bbox)


def extract_text_blocks(pdf_path: str | Path, pages: int = 1) -> ExtractedPage:
    """Extract text blocks from the first N pages of a PDF."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    blocks: list[TextBlock] = []
    page_height = 0.0
    with fitz.open(path) as doc:
        page_count = min(len(doc), max(pages, 1))
        for page_index in range(page_count):
            page = doc[page_index]
            page_height = max(page_height, float(page.rect.height))
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if "lines" not in block:
                    continue
                lines: list[TextLine] = []
                for line in block.get("lines", []):
                    spans: list[TextSpan] = []
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if not text or not text.strip():
                            continue
                        spans.append(
                            TextSpan(
                                text=text,
                                font_size=float(span.get("size", 0.0)),
                                bbox=tuple(span.get("bbox", (0.0, 0.0, 0.0, 0.0))),
                            )
                        )
                    if spans:
                        lines.append(_build_line(spans))
                if lines:
                    blocks.append(_build_block(lines))

    return ExtractedPage(blocks=tuple(blocks), page_height=page_height)
