"""Scrape WI case details using Playwright with persistent browser profile to avoid CAPTCHA."""

from __future__ import annotations

import argparse
import json
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


def _extract_case_data(page) -> Dict[str, object]:
    """Extract case detail data from the HTML page."""
    data = {
        "case": {},
        "parties": [],
        "records": [],
        "activities": [],
        "documents": [],
        "warrants": [],
        "crossReferenced": [],
        "civilJdgmts": [],
    }
    
    # Extract case metadata
    case_no_elem = page.query_selector("input[name='caseNo']")
    if case_no_elem:
        data["case"]["case_no"] = case_no_elem.get_attribute("value")
    
    county_no_elem = page.query_selector("input[name='countyNo']")
    if county_no_elem:
        data["case"]["county_no"] = int(county_no_elem.get_attribute("value"))
    
    caption_elem = page.query_selector(".caption")
    if caption_elem:
        data["case"]["caption"] = caption_elem.inner_text().strip()
    
    # Extract parties
    party_elements = page.query_selector_all(".party-row")
    for elem in party_elements:
        party_data = {
            "name": elem.query_selector(".party-name").inner_text().strip() if elem.query_selector(".party-name") else None,
            "type": elem.query_selector(".party-type").inner_text().strip() if elem.query_selector(".party-type") else None,
            "address": elem.query_selector(".party-address").inner_text().strip() if elem.query_selector(".party-address") else None,
            "dob": elem.query_selector(".party-dob").inner_text().strip() if elem.query_selector(".party-dob") else None,
            "status": elem.query_selector(".party-status").inner_text().strip() if elem.query_selector(".party-status") else None,
        }
        data["parties"].append(party_data)
    
    # Extract records (events)
    record_elements = page.query_selector_all(".event-row")
    for elem in record_elements:
        record_data = {
            "date": elem.query_selector(".event-date").inner_text().strip() if elem.query_selector(".event-date") else None,
            "description": elem.query_selector(".event-description").inner_text().strip() if elem.query_selector(".event-description") else None,
            "amount": elem.query_selector(".event-amount").inner_text().strip() if elem.query_selector(".event-amount") else None,
        }
        data["records"].append(record_data)
    
    # Extract other sections if needed
    # This would need to be customized based on the actual DOM structure
    
    return data


def fetch_case_details(page, cases: List[Dict[str, object]]) -> List[CaseDetailEnvelope]:
    envelopes: List[CaseDetailEnvelope] = []
    
    for case in cases:
        case_no = case["case_no"]
        county_no = case["county_no"]
        print(f"Fetching detail for case {case_no} (county {county_no})")
        
        url = _get_case_detail_url(case_no, county_no)
        page.goto(url)
        page.wait_for_load_state('networkidle')
        
        detail = _extract_case_data(page)
        
        parties = []
        for party_data in detail.get("parties", []):
            parties.append(
                PartyRecord(
                    case_no=case_no,
                    county_no=county_no,
                    county_name=case.get("county_name", ""),
                    caption=case.get("caption", ""),
                    party_name=party_data.get("name", ""),
                    party_type=party_data.get("type"),
                    address=party_data.get("address"),
                    dob=party_data.get("dob"),
                    is_dob_sealed=False,
                    role_status=party_data.get("status"),
                )
            )
        
        envelope = CaseDetailEnvelope(
            case=case,
            detail=detail,
            parties=parties
        )
        envelopes.append(envelope)
        
        # Small delay between cases
        time.sleep(1.0)
    
    return envelopes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape WI case details using Playwright with browser profile")
    parser.add_argument("--start", type=_parse_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--span-days", type=int, default=7)
    parser.add_argument("--class-code", dest="class_codes", action="append")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cases to process")
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
            headless=False,  # Set to True for headless operation
            viewport={"width": 1920, "height": 1080},
        )
        
        page = browser.new_page()
        
        envelopes = fetch_case_details(page, cases)
        
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

    if args.parties_csv and envelopes:
        import csv

        all_parties = []
        for env in envelopes:
            for party in env.parties:
                party_dict = asdict(party)
                party_dict.update({
                    "case_no": env.case.get("case_no"),
                    "county_no": env.case.get("county_no"),
                    "county_name": env.case.get("county_name"),
                    "caption": env.case.get("caption"),
                })
                all_parties.append(party_dict)
        
        if all_parties:
            with args.parties_csv.open("w", newline="", encoding="utf-8") as handle:
                fieldnames = all_parties[0].keys()
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_parties)
            print(f"Wrote {len(all_parties)} party rows to {args.parties_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())