"""Annotate party CSV rows with case type labels derived from class codes."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


CaseKey = Tuple[str, int]


def load_class_labels(path: Path) -> Dict[str, str]:
    """Parse `class_codes.txt` into a mapping of code -> label."""
    mapping: Dict[str, str] = {}
    if not path.exists():
        return mapping
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-16")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 1:
            code, label = parts[0], ""
        else:
            code, label = parts
        mapping[code] = label.strip()
    return mapping


def build_case_type_lookup(
    cases: Sequence[Mapping[str, object]], class_labels: Mapping[str, str]
) -> Dict[CaseKey, str]:
    """Create a lookup from (case_no, county_no) -> case type label."""
    lookup: Dict[CaseKey, str] = {}
    for entry in cases:
        case_no = entry.get("case_no")
        county_no = entry.get("county_no")
        if not case_no or county_no is None:
            continue
        codes = entry.get("class_codes") or []
        if not isinstance(codes, Iterable):
            codes = []
        labels: List[str] = []
        for code in codes:
            labels.append(class_labels.get(code, f"Class {code}"))
        case_type = "; ".join(labels)
        lookup[(case_no, int(county_no))] = case_type
    return lookup


def load_cases(path: Path) -> List[Mapping[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if isinstance(cases, list):
        return cases
    raise SystemExit(f"Unexpected JSON payload in {path}: missing 'cases'")


def annotate_parties(
    parties_path: Path, output_path: Path, lookup: Mapping[CaseKey, str]
) -> int:
    with parties_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if not rows:
        output_path.write_text("", encoding="utf-8")
        return 0

    fieldnames = list(rows[0].keys())
    if "case_type" not in fieldnames:
        fieldnames.append("case_type")

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            key = (row.get("case_no", ""), int(row.get("county_no") or 0))
            row["case_type"] = lookup.get(key, "")
            writer.writerow(row)

    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append case type labels to party CSV rows.")
    parser.add_argument(
        "--cases",
        default=Path("results_all_updated.json"),
        type=Path,
        help="JSON file containing case summaries with class_codes.",
    )
    parser.add_argument(
        "--parties",
        default=Path("all_parties_merged.csv"),
        type=Path,
        help="CSV file containing party rows.",
    )
    parser.add_argument(
        "--output",
        default=Path("all_parties_with_case_type.csv"),
        type=Path,
        help="Destination CSV with case_type column.",
    )
    parser.add_argument(
        "--class-codes",
        default=Path("class_codes.txt"),
        type=Path,
        help="Optional file mapping class code to human-readable label.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.cases.exists():
        raise SystemExit(f"Cases JSON not found: {args.cases}")
    if not args.parties.exists():
        raise SystemExit(f"Parties CSV not found: {args.parties}")

    class_labels = load_class_labels(args.class_codes)
    cases = load_cases(args.cases)
    lookup = build_case_type_lookup(cases, class_labels)

    total = annotate_parties(args.parties, args.output, lookup)
    print(f"Wrote {total} rows with case_type to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
