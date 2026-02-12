"""Command-line entry point for the WI advanced case scraper."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from wi_scraper import (
    DEFAULT_CLASS_CODES,
    ClassCode,
    fetch_case_summaries,
    flatten_aggregated,
)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _resolve_class_codes(selected: Sequence[str]) -> list[ClassCode]:
    lookup = {code.code: code for code in DEFAULT_CLASS_CODES}
    if not selected:
        return list(DEFAULT_CLASS_CODES)

    resolved: list[ClassCode] = []
    for code in selected:
        entry = lookup.get(code)
        if entry is None:
            entry = ClassCode(code=code, label=f"Class code {code}")
        resolved.append(entry)
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch WI advanced case search results")
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=date(2025, 1, 1),
        help="Inclusive start date (YYYY-MM-DD). Defaults to 2025-01-01.",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        default=None,
        help="Inclusive end date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--span-days",
        type=int,
        default=7,
        help="Number of days per filing-date window (default: 7).",
    )
    parser.add_argument(
        "--class-code",
        dest="class_codes",
        action="append",
        help="Limit to specific class code(s). Repeat flag to include multiple.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write JSON results. Defaults to stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    class_codes = _resolve_class_codes(args.class_codes or [])
    aggregated = fetch_case_summaries(
        start=args.start,
        end=args.end,
        class_codes=class_codes,
        span_days=args.span_days,
    )
    rows = flatten_aggregated(aggregated)

    payload = {
        "meta": {
            "start": args.start.isoformat(),
            "end": (args.end or date.today()).isoformat(),
            "span_days": args.span_days,
            "class_codes": [code.code for code in class_codes],
            "total_cases": len(rows),
        },
        "cases": rows,
    }

    if args.output:
        args.output.write_text(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
