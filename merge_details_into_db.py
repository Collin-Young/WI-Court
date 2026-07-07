"""Merge newly scraped WI case detail data into an existing SQLite database.

Usage:
    python merge_details_into_db.py --db C:\\path\\to\\cases.db \
        --details details_resume.json --parties parties_resume.csv

The script will create (or reuse) two tables:
    case_details(case_no, county_no, summary_json, detail_json)
    case_parties(case_no, county_no, party_name, party_type, address,
                 dob, is_dob_sealed, role_status)

Rows are keyed by (case_no, county_no). Existing case rows are updated in place,
and party rows are inserted with INSERT OR IGNORE to avoid duplication.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Tuple


CaseKey = Tuple[str, int]


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the destination tables if they are not already present."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_details (
            case_no TEXT NOT NULL,
            county_no INTEGER NOT NULL,
            summary_json TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            PRIMARY KEY (case_no, county_no)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_parties (
            case_no TEXT NOT NULL,
            county_no INTEGER NOT NULL,
            party_name TEXT NOT NULL,
            party_type TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            dob TEXT NOT NULL DEFAULT '',
            is_dob_sealed INTEGER NOT NULL DEFAULT 0,
            role_status TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (
                case_no,
                county_no,
                party_name,
                party_type,
                address,
                dob,
                role_status
            ),
            FOREIGN KEY (case_no, county_no)
                REFERENCES case_details(case_no, county_no)
                ON DELETE CASCADE
        )
        """
    )


def load_details(path: Path) -> Tuple[list[dict], set[CaseKey]]:
    """Load detail envelopes and return tuples for downstream processing."""
    entries = json.loads(path.read_text())
    keys: set[CaseKey] = set()
    for item in entries:
        case = item.get("case") or {}
        key = (case.get("case_no", ""), int(case.get("county_no", 0) or 0))
        keys.add(key)
    return entries, keys


def upsert_case_details(
    conn: sqlite3.Connection, entries: Iterable[dict]
) -> Tuple[int, int]:
    """Insert or update case detail rows. Returns (inserted, updated)."""
    inserted = updated = 0
    select_stmt = "SELECT 1 FROM case_details WHERE case_no=? AND county_no=?"
    upsert_stmt = """
        INSERT INTO case_details (case_no, county_no, summary_json, detail_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(case_no, county_no) DO UPDATE SET
            summary_json=excluded.summary_json,
            detail_json=excluded.detail_json
    """

    for item in entries:
        case = item.get("case") or {}
        key = (case.get("case_no", ""), int(case.get("county_no", 0) or 0))
        summary_json = json.dumps(case, ensure_ascii=False)
        detail_json = json.dumps(item.get("detail"), ensure_ascii=False)
        exists = conn.execute(select_stmt, key).fetchone()
        conn.execute(upsert_stmt, (*key, summary_json, detail_json))
        if exists:
            updated += 1
        else:
            inserted += 1
    return inserted, updated


def insert_parties(conn: sqlite3.Connection, parties_path: Path, valid_keys: set[CaseKey]) -> int:
    """Insert party rows for the provided case keys. Returns count inserted."""
    if not parties_path.exists():
        return 0

    inserted = 0
    stmt = """
        INSERT OR IGNORE INTO case_parties (
            case_no,
            county_no,
            party_name,
            party_type,
            address,
            dob,
            is_dob_sealed,
            role_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    with parties_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = (row["case_no"], int(row.get("county_no") or 0))
            if key not in valid_keys:
                continue
            params = (
                row["case_no"],
                int(row.get("county_no") or 0),
                row.get("party_name", "") or "",
                row.get("party_type") or "",
                row.get("address") or "",
                row.get("dob") or "",
                1 if str(row.get("is_dob_sealed", "")).lower() in {"1", "true", "yes"} else 0,
                row.get("role_status") or "",
            )
            cursor = conn.execute(stmt, params)
            if cursor.rowcount:
                inserted += 1
    return inserted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge WI case details into a SQLite database")
    parser.add_argument("--db", required=True, type=Path, help="Path to the target SQLite database")
    parser.add_argument(
        "--details",
        default=Path("details_resume.json"),
        type=Path,
        help="JSON file containing case/detail envelopes (default: details_resume.json)",
    )
    parser.add_argument(
        "--parties",
        default=Path("parties_resume.csv"),
        type=Path,
        help="CSV file containing party rows aligned with the detail file (default: parties_resume.csv)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.details.exists():
        raise SystemExit(f"Detail payload not found: {args.details}")

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ensure_schema(conn)

        detail_entries, case_keys = load_details(args.details)
        inserted, updated = upsert_case_details(conn, detail_entries)
        party_rows = insert_parties(conn, args.parties, case_keys)

        conn.commit()

        print(f"Cases inserted: {inserted}")
        print(f"Cases updated:  {updated}")
        print(f"Parties added: {party_rows}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
