"""Scrape WI case details using a local Chrome profile."""

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
DEFAULT_PROFILE = ".wcca_profile"


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


def _get_case_detail_url(case_no: str, county_no: int, index: Optional[int] = None) -> str:
    if index is not None:
        return f"{BASE_URL}/caseDetail.html?caseNo={case_no}&countyNo={county_no}&index={index}&isAdvanced=true"
    return f"{BASE_URL}/caseDetail.html?caseNo={case_no}&countyNo={county_no}"


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


def _extract_case_data_from_html(page) -> Dict[str, object]:
    """Extract case detail data from the HTML page as fallback."""
    data = {
        "case": {},
        "parties": [],
    }
    
    # Always dump HTML for debugging
    html = page.content()
    with open('debug_detail.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Dumped page HTML to debug_detail.html for inspection.")
    
    # Check page title or main content to see if loaded
    title = page.title()
    print(f"Page title: {title}")
    
    # Extract case metadata
    # Try to find caption - often in h1 or .caption
    caption_elem = page.query_selector("h1, .caption, [class*='caption'], [class*='title']")
    if caption_elem:
        data["case"]["caption"] = caption_elem.inner_text().strip()
        print(f"Found caption: {data['case']['caption']}")
    
    # Case number from URL
    url = page.url
    if "caseNo=" in url:
        case_no = url.split("caseNo=")[1].split("&")[0]
        data["case"]["case_no"] = case_no
    if "countyNo=" in url:
        county_no = url.split("countyNo=")[1].split("&")[0]
        data["case"]["county_no"] = int(county_no)
    
    # Get all tables
    tables = page.query_selector_all("table")
    print(f"Found {len(tables)} tables on page.")
    
    # Extract parties from #parties section using div structure
    parties_elem = page.query_selector('#parties')
    if parties_elem:
        print("Found #parties section.")
        party_divs = parties_elem.query_selector_all('.party')
        print(f"Found {len(party_divs)} party divs.")
        for div in party_divs:
            header_elem = div.query_selector('h5.detailHeader')
            if header_elem:
                header_text = header_elem.inner_text().strip()
                print(f"Party header: {header_text}")
                # Parse type and name, e.g., "Plaintiff: NAME"
                if ':' in header_text:
                    party_type, party_name = header_text.split(':', 1)
                    party_type = party_type.strip()
                    party_name = party_name.strip()
                else:
                    party_type = ""
                    party_name = header_text
                
                detail_wrapper = div.query_selector('.partyDetail')
                address = ""
                dob = ""
                status = ""  # Status might not be directly available; could be empty or inferred
                
                if detail_wrapper:
                    # Extract DOB
                    dob_elem = detail_wrapper.query_selector('dl:has(dt:has-text("Date of birth")) dd')
                    if dob_elem:
                        dob = dob_elem.inner_text().strip()
                    
                    # Extract Address
                    addr_elem = detail_wrapper.query_selector('dl:has(dt:has-text("Address")) dd')
                    if addr_elem:
                        address = addr_elem.inner_text().strip()
                
                if party_name and len(party_name) > 1:
                    party_data = {
                        "name": party_name,
                        "type": party_type,
                        "address": address,
                        "dob": dob,
                        "status": status
                    }
                    data["parties"].append(party_data)
                    print(f"Extracted party: {party_type} - {party_name} - Address: {address} - DOB: {dob} - Status: {status}")
            else:
                print("No detailHeader found in party div.")
        if not party_divs:
            print("No .party divs found in #parties; falling back to summary table.")
    else:
        print("No #parties section found.")
    
    for i, table in enumerate(tables):
        print(f"Inspecting table {i+1}")
        header_row = table.query_selector("tr:first-child")
        if header_row:
            headers = [cell.inner_text().strip() for cell in header_row.query_selector_all("th, td")]
            print(f"Table {i+1} headers: {headers}")
            
            header_text = ' '.join(headers).lower()
            
            # Fallback parties extraction from summary table if #parties divs failed
            if "party" in header_text and "type" in header_text and "name" in header_text and "status" in header_text:
                print(f"Table {i+1} identified as parties summary table (fallback).")
                rows = table.query_selector_all("tr")[1:]  # Skip header
                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) >= 3:
                        party_type = cells[0].inner_text().strip()
                        party_name = cells[1].inner_text().strip()
                        status = cells[2].inner_text().strip()
                        
                        if party_name and len(party_name) > 1:
                            party_data = {
                                "name": party_name,
                                "type": party_type,
                                "address": "",  # Not in summary
                                "dob": "",      # Not in summary
                                "status": status
                            }
                            data["parties"].append(party_data)
                            print(f"Extracted fallback party: {party_type} - {party_name} - Status: {status}")
            
    
    print(f"Final extraction: {len(data['parties'])} parties.")
    return data


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
    
    # Fallback to HTML parsing
    print("JSON not found in sessionStorage, falling back to HTML parsing.")
    html_data = _extract_case_data_from_html(page)
    
    # Build parties from HTML data
    parties_data = html_data.get("parties", [])
    caption = html_data["case"].get("caption", case_meta.get("caption", ""))
    parties = []
    for party in parties_data:
        parties.append(
            PartyRecord(
                case_no=case_meta.get("case_no", ""),
                county_no=int(case_meta.get("county_no", 0) or 0),
                county_name=case_meta.get("county_name", ""),
                caption=caption,
                party_name=party.get("name", ""),
                party_type=party.get("type"),
                address=party.get("address"),
                dob=party.get("dob"),
                is_dob_sealed=False,  # Assume false if not specified
                role_status=party.get("status"),
            )
        )
    
    detail = {
        "caption": caption,
        "parties": [p.__dict__ for p in parties],  # Simplified for detail
        "source": "html_fallback"
    }
    
    return {"detail": detail, "parties": parties}


def fetch_case_details(
    cases: List[Dict[str, object]],
    *,
    headless: bool = False,
    profile: Path,
) -> List[CaseDetailEnvelope]:
    envelopes: List[CaseDetailEnvelope] = []

    user_data_dir = Path(profile)
    if not user_data_dir.exists():
        raise RuntimeError(
            f"Profile missing at {user_data_dir}. Run cookie_helper.py first to create/seed it."
        )
    print(f"Using Chromium profile: {user_data_dir}")
    print("Note: Close all Chrome instances before running to avoid lock errors.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        for idx, case in enumerate(cases):
            case_no = case["case_no"]
            county_no = case["county_no"]
            result_index = case.get("_result_index", idx)
            print(f"Fetching case detail for {case_no} (county {county_no}, index {result_index})")

            url = _get_case_detail_url(case_no, county_no, result_index)

            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)  # Increased wait for dynamic content

                # Detect and handle CAPTCHA
                captcha_detected = False
                try:
                    page.wait_for_selector('text=/Please complete the CAPTCHA/i', timeout=10000)
                    captcha_detected = True
                    print("CAPTCHA page detected.")
                except:
                    pass

                if captcha_detected:
                    click_link = page.locator('span.link:has-text("Click here")')
                    try:
                        page.wait_for_selector('span.link:has-text("Click here")', timeout=10000)
                        print("Found 'Click here' CAPTCHA bypass link. Clicking it...")
                        click_link.first.click()
                        # Wait for case details to load instead of networkidle
                        page.wait_for_selector('#parties, h4:has-text("Case summary")', state='visible', timeout=60000)
                        page.wait_for_timeout(3000)
                        print("Case details loaded after CAPTCHA bypass.")
                    except Exception as e:
                        print(f"Error waiting for case details after CAPTCHA click: {e}")
                        # Fallback: wait a bit and check
                        page.wait_for_timeout(10000)
                        if page.locator('text=/Please complete the CAPTCHA/i').count() > 0:
                            print("CAPTCHA still present; manual intervention needed.")
                            input("Solve CAPTCHA manually in browser, then press Enter to continue...")

                # Additional wait for case details to load
                page.wait_for_timeout(3000)
                
                # Removed duplicate CAPTCHA check as it's handled above
                
                # Final wait for case details to load
                page.wait_for_timeout(5000)

                # Verify if still on CAPTCHA page
                if page.locator('text=/Please complete the CAPTCHA/i').count() > 0:
                    print("Still on CAPTCHA page after attempts. Skipping case.")
                    page.close()
                    continue
                
                # Dump HTML for debugging
                html = page.content()
                with open('debug_detail_final.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print("Dumped final page HTML to debug_detail_final.html")
                
                # Verify content loaded
                body_text = page.locator("body").inner_text().lower()
                if any(word in body_text for word in ["case", "party", "court", "docket"]):
                    print("Case content detected in page.")
                else:
                    print("No case content detected; page may not have loaded properly.")
                    input("Check the browser window. If the case details are visible, press Enter. Otherwise, resolve any issues and press Enter.")

                detail_payload = _extract_case_detail(page, case)
                envelopes.append(
                    CaseDetailEnvelope(
                        case=case,
                        detail=detail_payload["detail"],
                        parties=detail_payload["parties"],
                    )
                )

                page.close()
                time.sleep(random.uniform(1.5, 3.0))

            except Exception as e:
                print(f"Error fetching detail for {case_no}: {e}")
                envelopes.append(CaseDetailEnvelope(case=case, detail={}, parties=[]))
                if 'page' in locals():
                    try:
                        page.close()
                    except Exception:
                        pass
                continue

        try:
            context.close()
        except Exception as close_err:
            print(f"Error closing context: {close_err}")
    return envelopes


def load_cases_from_json(json_file: Path) -> List[Dict[str, object]]:
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, list):
            raw_cases = data
        else:
            raw_cases = data.get("cases", [])
        
        cases = []
        for raw_case in raw_cases:
            if isinstance(raw_case, dict) and "case" in raw_case:
                case = raw_case["case"].copy()
                case.setdefault("_result_index", len(cases))
                cases.append(case)
            else:
                # Fallback for flat cases
                case = raw_case.copy()
                case.setdefault("_result_index", len(cases))
                cases.append(case)
        
        return cases


def select_random_cases(cases: List[Dict[str, object]], n: int) -> List[Dict[str, object]]:
    return cases if len(cases) <= n else random.sample(cases, n)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape WI case details using browser to avoid CAPTCHA")
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
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(DEFAULT_PROFILE),
        help="Playwright user-data dir to reuse (default: .wcca_profile created via cookie_helper.py)",
    )
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

    envelopes = fetch_case_details(cases, headless=args.headless, profile=args.profile)

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
            with args.parties_csv.open("w", newline="", encoding="utf-8") as handle:
                fieldnames = all_parties[0].keys()
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_parties)
            print(f"Wrote {len(all_parties)} party rows to {args.parties_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
