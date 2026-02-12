"""Fetch WI case details using Playwright with user's browser profile to avoid CAPTCHA."""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from playwright.sync_api import sync_playwright

from wi_scraper import (
    DEFAULT_CLASS_CODES,
    ClassCode,
    fetch_case_summaries,
    flatten_aggregated,
)

BASE_URL = "https://wcca.wicourts.gov"


@dataclass
class PartyRecord:
    case_no: str
    county_no: int
    county_name: str
    caption: str
    party_name: str
    party_type: Optional[str]
    address: Optional[str]
    dob: Optional[str]
    is_dob_sealed: bool
    role_status: Optional[str]


@dataclass
class CaseDetailEnvelope:
    case: Dict[str, object]
    detail: Dict[str, object]
    parties: List[PartyRecord]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _resolve_class_codes(selected: Sequence[str]) -> List[ClassCode]:
    lookup = {code.code: code for code in DEFAULT_CLASS_CODES}
    if not selected:
        return list(DEFAULT_CLASS_CODES)

    resolved: List[ClassCode] = []
    for code in selected:
        entry = lookup.get(code)
        if entry is None:
            entry = ClassCode(code=code, label=f"Class code {code}")
        resolved.append(entry)
    return resolved


def _get_case_detail_url(case_no: str, county_no: int) -> str:
    return f"{BASE_URL}/caseDetail.html?caseNo={case_no}&countyNo={county_no}&index=0&isAdvanced=true"


def _extract_json_from_page(page) -> Dict[str, object]:
    # Wait for the page to load and API data to be available
    page.wait_for_load_state('networkidle')
    
    # The API data is usually stored in a script tag or window object
    # Try to find the JSON data in script tags
    scripts = page.query_selector_all("script")
    for script in scripts:
        content = script.inner_text()
        if content and 'caseDetail' in content:
            # Extract JSON from script
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = content[start:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
    
    # Fallback: try to find the data in the page's data attributes or specific elements
    # This would need adjustment based on the actual DOM structure
    # For now, return empty dict
    return {}


def fetch_case_detail(page, case_no: str, county_no: int) -> Dict[str, object]:
    url = _get_case_detail_url(case_no, county_no)
    page.goto(url)
    
    # Wait for the case detail data to load
    page.wait_for_load_state('networkidle')
    
    # Extract the detail data
    detail = _extract_json_from_page(page)
    
    return detail


def flatten_parties(case_meta: Dict[str, object], detail: Dict[str, object]) -> List[PartyRecord]:
    parties = detail.get("parties") or []
    rows: List[PartyRecord] = []
    for party in parties:
        rows.append(
            PartyRecord(
                case_no=case_meta.get("case_no", ""),
                county_no=int(case_meta.get("county_no", 0) or 0),
                county_name=case_meta.get("county_name", ""),
                caption=case_meta.get("caption", ""),
                party_name=party.get("name", ""),
                party_type=party.get("type"),
                address=party.get("address"),
                dob=party.get("dob"),
                is_dob_sealed=bool(party.get("isDobSealed")),
                role_status=party.get("status"),
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape WI case details using Playwright with browser profile")
    parser.add_argument("--start", type=_parse_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--span-days", type=int, default=7)
    parser.add_argument("--class-code", dest="class_codes", action="append")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cases to process; if not provided, processes all cases")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--profile", default=".wcca_profile", help="Browser profile directory to use")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--parties-csv", type=Path)
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
    cases = flatten_aggregated(aggregated)

    if args.offset:
        cases = cases[args.offset:]
    if args.limit is not None:
        cases = cases[: args.limit]

    if not cases:
        print("No cases matched the requested window.")
        return 0

    # Use Playwright with persistent context using the browser profile
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            args.profile,
            headless=True,
            viewport={"width": 1920, "height": 1080},
        )
        
        envelopes: List[CaseDetailEnvelope] = []
        party_rows: List[PartyRecord] = []

        for idx, case in enumerate(cases):
            print(f"Fetching detail {idx + 1}/{len(cases)}: {case['case_no']} (county {case['county_no']})")
            
            page = browser.new_page()
            
            try:
                detail = fetch_case_detail(page, case['case_no'], case['county_no'])
                
                parties = flatten_parties(case, detail)
                party_rows.extend(parties)
                envelopes.append(CaseDetailEnvelope(case=case, detail=detail, parties=parties))
                
                # Small delay between pages
                time.sleep(random.uniform(0.5, 1.5))
                
            except Exception as e:
                print(f"Error fetching case {case['case_no']}: {e}")
                continue
            finally:
                page.close()

        browser.close()

    if not envelopes:
        print("No detail records captured.")
        return 1

    serialisable = [
        {
            "case": env.case,
            "detail": env.detail,
            "parties": [asdict(p) for p in env.parties],
        }
        for env in envelopes
    ]

    if args.output:
        args.output.write_text(json.dumps(serialisable, indent=2, default=str))
        print(f"Wrote {len(serialisable)} record(s) to {args.output}")
    else:
        print(json.dumps(serialisable, indent=2, default=str))

    if args.parties_csv and party_rows:
        import csv

        with args.parties_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(party_rows[0]).keys()))
            writer.writeheader()
            for row in party_rows:
                writer.writerow(asdict(row))
        print(f"Wrote {len(party_rows)} party rows to {args.parties_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
