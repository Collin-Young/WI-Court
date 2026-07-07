"""Merge two party CSV exports and remove duplicate rows."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable, Mapping, Tuple


Key = Tuple[str, str, str, str, str, str, str]


def build_key(row: Mapping[str, str]) -> Key:
    return (
        row.get("case_no", ""),
        row.get("county_no", ""),
        row.get("party_name", ""),
        row.get("party_type", "") or "",
        row.get("address", "") or "",
        row.get("dob", "") or "",
        row.get("role_status", "") or "",
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def merge(master: Iterable[dict[str, str]], updates: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[Key] = set()
    merged: list[dict[str, str]] = []

    def push(row: dict[str, str]) -> None:
        key = build_key(row)
        if key not in seen:
            seen.add(key)
            merged.append(row)

    for row in master:
        push(row)
    for row in updates:
        push(row)

    return merged


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise SystemExit("No rows to write; aborting.")
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge party CSV files")
    parser.add_argument("--master", default=Path("all_parties.csv"), type=Path)
    parser.add_argument("--updates", default=Path("parties_resume.csv"), type=Path)
    parser.add_argument("--output", default=Path("all_parties_merged.csv"), type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.master.exists():
        raise SystemExit(f"Master CSV not found: {args.master}")
    if not args.updates.exists():
        raise SystemExit(f"Update CSV not found: {args.updates}")

    master_rows = read_csv(args.master)
    update_rows = read_csv(args.updates)
    merged_rows = merge(master_rows, update_rows)
    write_csv(args.output, merged_rows)

    print(
        f"Merged {len(master_rows)} master rows + {len(update_rows)} updates "
        f"into {len(merged_rows)} unique rows at {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
