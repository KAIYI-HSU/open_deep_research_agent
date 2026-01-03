"""CLI for PaperPDF Auto-Renamer."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from open_deep_research.paper_renamer.extractor.heuristics import (
    TITLE_SCORE_THRESHOLD,
    YEAR_SCORE_THRESHOLD,
    TitleCandidate,
    generate_title_candidates,
    generate_year_candidates,
)
from open_deep_research.paper_renamer.extractor.pymupdf_extractor import (
    TextLine,
    extract_text_blocks,
)
from open_deep_research.paper_renamer.llm.vllm_client import (
    LLMConfig,
    LLMError,
    request_structured_selection,
)
from open_deep_research.paper_renamer.renamer.rename import build_filename, rename_file
from open_deep_research.paper_renamer.watcher import watch_folder

LOGGER = logging.getLogger(__name__)

DEFAULT_FORMAT = "{year} - {title}.pdf"


class DecisionError(RuntimeError):
    """Raised when a filename cannot be decided."""


def _collect_lines(blocks: tuple[Any, ...]) -> list[TextLine]:
    lines: list[TextLine] = []
    for block in blocks:
        lines.extend(list(block.lines))
    return lines


def _select_from_heuristics(
    title_candidates: list[TitleCandidate],
    year_candidates,
    allow_title_only: bool,
) -> tuple[str, int | None, str]:
    if not title_candidates:
        raise DecisionError("No title candidates extracted")
    title_choice = title_candidates[0]
    year_choice = year_candidates[0] if year_candidates else None
    if not allow_title_only and year_choice is None:
        raise DecisionError("No year candidates extracted")
    return title_choice.text, year_choice.year if year_choice else None, "heuristic"


def _select_with_llm(
    config: LLMConfig,
    title_candidates: list[TitleCandidate],
    year_candidates,
) -> tuple[str, int | None, str]:
    candidate_texts = [candidate.text for candidate in title_candidates]
    year_payload = [
        {"year": candidate.year, "context": candidate.context} for candidate in year_candidates
    ]
    response = request_structured_selection(config, candidate_texts, year_payload)
    title = response.get("title")
    year = response.get("year")
    if not isinstance(title, str):
        raise LLMError("LLM response missing title")
    if year is not None and not isinstance(year, int):
        raise LLMError("LLM response missing year")

    if title in candidate_texts:
        return title, year, "llm"

    for index in range(len(candidate_texts) - 1):
        combined = f"{candidate_texts[index]} {candidate_texts[index + 1]}".strip()
        if title == combined:
            return title, year, "llm"

    raise LLMError("LLM returned title outside candidate list")


def _build_log_record(
    source: Path,
    target: Path | None,
    title: str | None,
    year: int | None,
    strategy: str,
    status: str,
    message: str | None = None,
) -> dict[str, Any]:
    return {
        "source": str(source),
        "target": str(target) if target else None,
        "title": title,
        "year": year,
        "strategy": strategy,
        "status": status,
        "message": message,
    }


def _write_log(log_path: Path | None, record: dict[str, Any]) -> None:
    if not log_path:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_pdf(
    pdf_path: Path,
    pages: int,
    enable_llm: bool,
    llm_config: LLMConfig | None,
    format_template: str,
    allow_title_only: bool,
    dry_run: bool,
    log_path: Path | None,
) -> None:
    LOGGER.info("Processing %s", pdf_path)
    try:
        extracted = extract_text_blocks(pdf_path, pages=pages)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to read %s: %s", pdf_path, exc)
        _write_log(
            log_path,
            _build_log_record(pdf_path, None, None, None, "heuristic", "error", str(exc)),
        )
        return

    lines = _collect_lines(extracted.blocks)
    if not lines:
        LOGGER.warning("No text extracted from %s", pdf_path)
        _write_log(
            log_path,
            _build_log_record(pdf_path, None, None, None, "heuristic", "skip", "empty"),
        )
        return

    title_candidates = generate_title_candidates(extracted.blocks, extracted.page_height)
    year_candidates = generate_year_candidates(lines, extracted.page_height)

    strategy = "heuristic"
    try:
        title, year, strategy = _select_from_heuristics(
            title_candidates, year_candidates, allow_title_only
        )
        need_llm = (
            title_candidates
            and title_candidates[0].score < TITLE_SCORE_THRESHOLD
            or not year_candidates
            or (year_candidates and year_candidates[0].score < YEAR_SCORE_THRESHOLD)
        )
        if enable_llm and llm_config and need_llm:
            title, year, strategy = _select_with_llm(llm_config, title_candidates, year_candidates)
    except (DecisionError, LLMError) as exc:
        LOGGER.warning("Decision failed for %s: %s", pdf_path, exc)
        _write_log(
            log_path,
            _build_log_record(pdf_path, None, None, None, strategy, "skip", str(exc)),
        )
        return

    target_name = build_filename(format_template, title, year, None)
    try:
        target_path = rename_file(pdf_path, target_name, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Rename failed for %s: %s", pdf_path, exc)
        _write_log(
            log_path,
            _build_log_record(pdf_path, None, title, year, strategy, "error", str(exc)),
        )
        return

    LOGGER.info("%s -> %s", pdf_path.name, target_path.name)
    _write_log(
        log_path,
        _build_log_record(pdf_path, target_path, title, year, strategy, "renamed"),
    )


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def _collect_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(input_dir.glob(pattern))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper_renamer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--dry-run", action="store_true")
        subparser.add_argument("--enable-llm", action="store_true")
        subparser.add_argument("--vllm-url", default="http://localhost:8000/v1/chat/completions")
        subparser.add_argument("--vllm-model", default="qwen2-7b-instruct")
        subparser.add_argument("--vllm-api-key", default=None)
        subparser.add_argument("--pages", type=int, default=1)
        subparser.add_argument("--format", dest="format_template", default=DEFAULT_FORMAT)
        subparser.add_argument("--allow-title-only", action="store_true")
        subparser.add_argument("--log", dest="log_path", default=None)
        subparser.add_argument("--log-level", default="INFO")

    batch = subparsers.add_parser("batch", help="Rename PDFs in a directory")
    batch.add_argument("--input", required=True, type=Path)
    batch.add_argument("--recursive", action="store_true")
    add_common(batch)

    watch = subparsers.add_parser("watch", help="Watch a directory for new PDFs")
    watch.add_argument("--input", required=True, type=Path)
    watch.add_argument("--interval", type=float, default=1.0)
    add_common(watch)

    one = subparsers.add_parser("one", help="Rename a single PDF")
    one.add_argument("--file", required=True, type=Path)
    add_common(one)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.log_level)

    log_path = Path(args.log_path) if args.log_path else None

    llm_config = None
    if args.enable_llm:
        llm_config = LLMConfig(
            url=args.vllm_url,
            model=args.vllm_model,
            api_key=args.vllm_api_key,
        )

    if args.command == "batch":
        files = _collect_pdf_files(args.input, args.recursive)
        for pdf_path in files:
            process_pdf(
                pdf_path,
                pages=args.pages,
                enable_llm=args.enable_llm,
                llm_config=llm_config,
                format_template=args.format_template,
                allow_title_only=args.allow_title_only,
                dry_run=args.dry_run,
                log_path=log_path,
            )
    elif args.command == "watch":
        def callback(path: Path) -> None:
            process_pdf(
                path,
                pages=args.pages,
                enable_llm=args.enable_llm,
                llm_config=llm_config,
                format_template=args.format_template,
                allow_title_only=args.allow_title_only,
                dry_run=args.dry_run,
                log_path=log_path,
            )

        watch_folder(args.input, callback, interval=args.interval)
    elif args.command == "one":
        process_pdf(
            args.file,
            pages=args.pages,
            enable_llm=args.enable_llm,
            llm_config=llm_config,
            format_template=args.format_template,
            allow_title_only=args.allow_title_only,
            dry_run=args.dry_run,
            log_path=log_path,
        )
