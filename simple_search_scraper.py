"""Scrape WI case details via the simple search form (case.html)."""

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
SIMPLE_SEARCH_URL = f"{BASE_URL}/case.html"


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


def _unwrap_case_detail(obj: object) -> Optional[Dict[str, object]]:
    if isinstance(obj, dict):
        if "caseDetail" in obj and isinstance(obj["caseDetail"], dict):
            return _unwrap_case_detail(obj["caseDetail"])
        if "parties" in obj or "records" in obj:
            return obj
        for key in ("result", "detail", "data"):
            if key in obj:
                detail = _unwrap_case_detail(obj[key])
                if detail:
                    return detail
    return None


def _build_party_records(case_meta: Dict[str, object], detail: Dict[str, object]) -> List[PartyRecord]:
    parties_data = detail.get("parties") or []
    caption = detail.get("caption") or case_meta.get("caption", "")
    records: List[PartyRecord] = []
    for party in parties_data:
        name = party.get("name") or party.get("partyName") or ""
        party_type = party.get("type") or party.get("partyType")
        records.append(
            PartyRecord(
                case_no=case_meta.get("case_no", ""),
                county_no=int(case_meta.get("county_no", 0) or 0),
                county_name=case_meta.get("county_name", ""),
                caption=caption,
                party_name=name,
                party_type=party_type,
                address=party.get("address"),
                dob=party.get("dob"),
                is_dob_sealed=bool(party.get("isDobSealed")),
                role_status=party.get("status"),
            )
        )
    return records


def _extract_case_detail(page, case_meta: Dict[str, object]) -> Dict[str, object]:
    storage = page.evaluate(
        "() => {const out={}; for (let i=0;i<sessionStorage.length;i++){const key=sessionStorage.key(i); out[key]=sessionStorage.getItem(key);} return out;}"
    )
    for raw in storage.values():
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        detail = _unwrap_case_detail(payload)
        if detail:
            parties = _build_party_records(case_meta, detail)
            return {"detail": detail, "parties": parties}

    return {
        "detail": {"warning": "Case detail JSON not available"},
        "parties": [],
    }


def _run_simple_search(page, case: Dict[str, object]) -> None:
    case_no = case["case_no"]
    county_name = case.get("county_name", "")
    page.goto(SIMPLE_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    # Debug: save page content and screenshot if needed
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    html_path = debug_dir / f"search_page_{case_no}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page.content())
    screenshot_path = debug_dir / f"search_page_{case_no}.png"
    page.screenshot(path=screenshot_path)
    print(f"Debug files saved: {html_path}, {screenshot_path}")

    case_input = page.locator('input[name="caseNo"], input#caseNo')
    if case_input.count() == 0:
        raise RuntimeError("Case number input not found on simple search page")
    case_input.fill(case_no)

    # Handle county dropdown - it's a React Select component
    county_dropdown = page.locator('label:has-text("County") .Select-control')
    if county_dropdown.count() == 0:
        print("Debug: County dropdown locator failed. Checking all labels:")
        labels = page.locator('label').all()
        for i, label in enumerate(labels):
            text = label.inner_text()
            if 'county' in text.lower():
                print(f"  Label {i}: '{text}'")
        raise RuntimeError("County dropdown not found on simple search page")
    county_dropdown.click()
    page.wait_for_selector('.Select-menu-outer', state='visible', timeout=5000)

    if county_name:
        # Select by county name
        option_locator = page.locator(f'.Select-option:has-text("{county_name}")')
        if option_locator.count() == 0:
            # Fallback: type county number to search
            input_selector = '.Select-input input'
            page.locator(input_selector).fill(str(case.get("county_no", "")))
            page.wait_for_timeout(500)
            option_locator = page.locator(f'.Select-option:has-text("{county_name}")')
        if option_locator.count() > 0:
            option_locator.first.click()
            page.wait_for_timeout(500)
        else:
            # List available options for debug
            options = page.locator('.Select-option').all()
            print("Available county options:")
            for opt in options:
                print(f"  - {opt.inner_text()}")
            raise RuntimeError(f"County option '{county_name}' not found")
    else:
        # Default to Statewide if no county name
        statewide_option = page.locator('.Select-option:has-text("Statewide")')
        if statewide_option.count() > 0:
            statewide_option.first.click()
        else:
            # Close dropdown if no selection
            page.keyboard.press('Escape')

    search_button = page.locator('button:has-text("Search")')
    if search_button.count() == 0:
        search_button = page.locator('input[type="submit"][value="Search"], input[type="submit"][name="search"]')
    if search_button.count() == 0:
        raise RuntimeError("Search button not found on simple search page")

    search_button.first.click()
    page.wait_for_load_state('domcontentloaded', timeout=60000)
    page.wait_for_timeout(2000)


def fetch_case_details(cases: List[Dict[str, object]], headless: bool = False) -> List[CaseDetailEnvelope]:
    envelopes: List[CaseDetailEnvelope] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 720})

        for idx, case in enumerate(cases):
            case_no = case["case_no"]
            county_no = case["county_no"]
            print(f"Fetching case detail for {case_no} (county {county_no})")

            page = context.new_page()
            try:
                _run_simple_search(page, case)
                detail_payload = _extract_case_detail(page, case)
                envelopes.append(
                    CaseDetailEnvelope(
                        case=case,
                        detail=detail_payload["detail"],
                        parties=detail_payload["parties"],
                    )
                )
            except Exception as e:
                print(f"Error fetching detail for {case_no}: {e}")
                envelopes.append(CaseDetailEnvelope(case=case, detail={}, parties=[]))
            finally:
                page.close()
                time.sleep(random.uniform(1.0, 2.0))

        context.close()
        browser.close()

    return envelopes


def load_cases_from_json(json_file: Path) -> List[Dict[str, object]]:
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        cases = data.get("cases", [])
        for idx, case in enumerate(cases):
            case.setdefault("_result_index", idx)
        return cases


def select_random_cases(cases: List[Dict[str, object]], n: int) -> List[Dict[str, object]]:
    return cases if len(cases) <= n else random.sample(cases, n)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape WI case details using the simple search form")
    parser.add_argument("--start", type=_parse_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--span-days", type=int, default=7)
    parser.add_argument("--class-code", dest="class_codes", action="append")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--random-sample", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--parties-csv", type=Path)
    parser.add_argument("--headless", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.input_json:
        cases = load_cases_from_json(args.input_json)
        if args.random_sample:
            cases = select_random_cases(cases, args.random_sample)
            print(f"Selected {len(cases)} random cases for testing")
    else:
        class_codes = _resolve_class_codes(args.class_codes or [])
        aggregated = fetch_case_summaries(
            start=args.start,
            end=args.end,
            class_codes=class_codes,
            span_days=args.span_days,
        )
        cases = flatten_aggregated(aggregated)
        for idx, case in enumerate(cases):
            case.setdefault("_result_index", idx)

    if args.offset:
        cases = cases[args.offset:]
    if args.limit is not None:
        cases = cases[: args.limit]

    if not cases:
        print("No cases matched the requested window.")
        return 0

    envelopes = fetch_case_details(cases, headless=args.headless)

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
        args.output.write_text(json.dumps(serialisable, indent=2, default=str), encoding='utf-8')
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
            with args.parties_csv.open("w", newline="", encoding='utf-8') as handle:
                fieldnames = all_parties[0].keys()
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_parties)
            print(f"Wrote {len(all_parties)} party rows to {args.parties_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
