"""Flatten case summaries and party details into single-row CSV records."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


CaseKey = Tuple[str, int]


def load_cases(path: Path) -> List[Mapping[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if isinstance(cases, list):
        return cases
    raise SystemExit(f"Unexpected structure in {path}: missing 'cases'")


def load_class_labels(path: Path) -> Dict[str, str]:
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


def load_parties(path: Path) -> Dict[CaseKey, List[Mapping[str, str]]]:
    groups: Dict[CaseKey, List[Mapping[str, str]]] = {}
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = (row.get("case_no", ""), int(row.get("county_no") or 0))
            groups.setdefault(key, []).append(row)
    return groups


def aggregate_parties(rows: Sequence[Mapping[str, str]]) -> Tuple[List[Dict[str, str]], str]:
    """Return a deduplicated, ordered list of party dicts and the case type label."""
    best: Dict[Tuple[str, str, str], Mapping[str, str]] = {}
    case_type = ""
    for row in rows:
        name = row.get("party_name", "") or ""
        ptype = row.get("party_type", "") or ""
        status = row.get("role_status") or ""
        key = (ptype, name, status)
        stored = best.get(key)
        address = row.get("address") or ""
        if stored is None:
            best[key] = row
        else:
            stored_address = stored.get("address") or ""
            if not stored_address and address:
                best[key] = row
        if not case_type:
            case_type = row.get("case_type", "") or ""

    ordered = sorted(best.items(), key=lambda item: item[0])
    result: List[Dict[str, str]] = []
    for (_, name, status), row in ordered:
        result.append(
            {
                "name": name,
                "type": row.get("party_type", "") or "",
                "address": row.get("address") or "",
                "status": status or "",
            }
        )
    return result, case_type


def build_rows(
    cases: Iterable[Mapping[str, object]],
    party_lookup: Mapping[CaseKey, Sequence[Mapping[str, str]]],
    class_labels: Mapping[str, str],
) -> List[Tuple[Dict[str, object], List[Dict[str, str]], str]]:
    rows: List[Tuple[Dict[str, object], List[Dict[str, str]], str]] = []
    for entry in cases:
        key = (entry.get("case_no", ""), int(entry.get("county_no") or 0))
        case_row = dict(entry)
        # Normalise complex fields for CSV output
        labels: List[str] = []
        codes = entry.get("class_codes") or []
        if isinstance(codes, Iterable) and not isinstance(codes, (str, bytes)):
            for code in codes:
                labels.append(class_labels.get(code, f"Class {code}"))
        case_row["class_codes"] = "; ".join(filter(None, labels))
        if isinstance(case_row.get("raw"), (dict, list)):
            case_row["raw"] = json.dumps(case_row["raw"], ensure_ascii=False)
        party_rows, case_type = aggregate_parties(party_lookup.get(key, []))
        if not case_type:
            case_type = "; ".join(filter(None, labels))
        rows.append((case_row, party_rows, case_type))
    return rows


def write_csv(
    path: Path,
    rows: List[Tuple[Dict[str, object], List[Dict[str, str]], str]],
    party_cap: int = 10,
) -> None:
    if not rows:
        raise SystemExit("No rows generated; aborting.")
    base_columns = list(rows[0][0].keys())
    if "case_type" not in base_columns:
        base_columns.append("case_type")
    max_parties = min(
        party_cap,
        max(len(parties) for _, parties, _ in rows),
    )
    dynamic_columns: List[str] = []
    for idx in range(1, max_parties + 1):
        dynamic_columns.extend(
            [
                f"party_{idx}_name",
                f"party_{idx}_type",
                f"party_{idx}_address",
                f"party_{idx}_status",
            ]
        )
    fieldnames = base_columns + dynamic_columns
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for base_row, parties, case_type in rows:
            row = dict(base_row)
            row["case_type"] = case_type
            for idx in range(1, max_parties + 1):
                suffix = f"party_{idx}_"
                if idx <= len(parties):
                    party = parties[idx - 1]
                    row[suffix + "name"] = party["name"]
                    row[suffix + "type"] = party["type"]
                    row[suffix + "address"] = party["address"]
                    row[suffix + "status"] = party["status"]
                else:
                    row[suffix + "name"] = ""
                    row[suffix + "type"] = ""
                    row[suffix + "address"] = ""
                    row[suffix + "status"] = ""
            writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create case-level CSV rows that include aggregated party details."
    )
    parser.add_argument(
        "--cases",
        default=Path("results_all_updated.json"),
        type=Path,
        help="JSON file containing cases with class_codes.",
    )
    parser.add_argument(
        "--parties",
        default=Path("all_parties_with_case_type.csv"),
        type=Path,
        help="CSV file containing party rows to aggregate.",
    )
    parser.add_argument(
        "--class-codes",
        default=Path("class_codes.txt"),
        type=Path,
        help="Optional mapping of class code to label.",
    )
    parser.add_argument(
        "--output",
        default=Path("cases_with_party_details.csv"),
        type=Path,
        help="Destination CSV path.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.cases.exists():
        raise SystemExit(f"Cases JSON not found: {args.cases}")
    if not args.parties.exists():
        raise SystemExit(f"Parties CSV not found: {args.parties}")

    cases = load_cases(args.cases)
    party_lookup = load_parties(args.parties)
    class_labels = load_class_labels(args.class_codes)
    rows = build_rows(cases, party_lookup, class_labels)
    write_csv(args.output, rows)
    print(f"Wrote {len(rows)} case rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
