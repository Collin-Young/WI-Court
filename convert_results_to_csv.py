"""Utility to convert WI scraper JSON results into CSV format."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Mapping


def serialise_case(case: Mapping[str, object]) -> Mapping[str, object]:
    """Prepare a single case row for CSV output."""
    class_codes = case.get("class_codes") or []
    raw_payload = case.get("raw") or {}

    row = dict(case)
    row["class_codes"] = ";".join(class_codes)
    row["raw"] = json.dumps(raw_payload, ensure_ascii=False)
    return row


def convert(input_path: Path, output_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    cases: Iterable[Mapping[str, object]] = payload.get("cases", [])
    if not cases:
        output_path.write_text("", encoding="utf-8")
        return 0

    fieldnames = list(cases[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            writer.writerow(serialise_case(case))

    return len(payload["cases"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert WI scraper JSON into CSV format")
    parser.add_argument(
        "--input",
        default=Path("results_new_from_20250915.json"),
        type=Path,
        help="Path to the JSON file produced by the scraper.",
    )
    parser.add_argument(
        "--output",
        default=Path("results_new_from_20250915.csv"),
        type=Path,
        help="Destination CSV path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    total = convert(args.input, args.output)
    print(f"Wrote {total} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
