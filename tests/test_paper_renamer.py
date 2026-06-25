from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from open_deep_research.paper_renamer.extractor.heuristics import (
    generate_title_candidates,
    generate_year_candidates,
)
from open_deep_research.paper_renamer.extractor.pymupdf_extractor import (
    TextBlock,
    TextLine,
    TextSpan,
)
from open_deep_research.paper_renamer.renamer.sanitize import sanitize_filename


def _make_line(text: str, font_size: float, y0: float) -> TextLine:
    span = TextSpan(text=text, font_size=font_size, bbox=(0.0, y0, 100.0, y0 + 10.0))
    return TextLine(
        spans=(span,),
        text=text,
        avg_font_size=font_size,
        bbox=span.bbox,
    )


def test_sanitize_filename_removes_invalid_chars():
    name = "  Foo:Bar/\"Baz?.pdf  "
    sanitized = sanitize_filename(name)
    assert ":" not in sanitized
    assert "/" not in sanitized
    assert "\"" not in sanitized
    assert "?" not in sanitized
    assert sanitized == "FooBarBaz.pdf"


def test_generate_year_candidates_prefers_top_context():
    top_line = _make_line("Proceedings 2024", 12.0, 100.0)
    bottom_line = _make_line("References 2019", 10.0, 800.0)
    candidates = generate_year_candidates([top_line, bottom_line], page_height=1000.0)
    assert candidates[0].year == 2024
    assert candidates[0].score > candidates[-1].score


def test_generate_title_candidates_scores_top_larger_text():
    title_line = _make_line("Deep Learning for Cats", 22.0, 80.0)
    body_line = _make_line("Introduction", 10.0, 600.0)
    block = TextBlock(
        lines=(title_line, body_line),
        text="Deep Learning for Cats\nIntroduction",
        max_font_size=22.0,
        bbox=(0.0, 80.0, 100.0, 610.0),
    )
    candidates = generate_title_candidates([block], page_height=1000.0)
    assert candidates
    assert candidates[0].text == "Deep Learning for Cats"
