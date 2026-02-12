"""Automated detail scraper with optional hcaptcha-challenger integration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, urlparse

from hcaptcha_challenger import AgentConfig, AgentV
from playwright.async_api import async_playwright

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
    missing = [code for code in selected if code not in lookup]
    if missing:
        raise SystemExit("Unknown class code(s): {}".format(', '.join(missing)))
    return [lookup[code] for code in selected]


def resolve_gemini_key(explicit: str | None) -> str | None:
    """Return the Gemini API key if supplied explicitly or via env."""
    if explicit:
        return explicit
    return os.getenv("GEMINI_API_KEY")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch WI case details via interactive browser")
    parser.add_argument("--start", type=_parse_date, default=date(2025, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--span-days", type=int, default=7)
    parser.add_argument("--class-code", dest="class_codes", action="append")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of cases to inspect")
    parser.add_argument("--output", type=Path, help="Optional JSON file to write results")
    parser.add_argument("--no-next", action="store_true", help="Disable use of the on-page Next link")
    parser.add_argument(
        "--gemini-key",
        help="Optional Gemini API key for hcaptcha-challenger (defaults to GEMINI_API_KEY env var)",
    )
    return parser


async def _read_session_payload_async(page):
    storage = await page.evaluate(
        "() => {const out={}; for (let i=0;i<sessionStorage.length;i++){const key=sessionStorage.key(i); out[key]=sessionStorage.getItem(key);} return out;}"
    )
    for raw in storage.values():
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "caseDetail" in json.dumps(payload):
            return payload
    return None

async def _extract_case_details_from_dom(page):
    """Extract structured case details from DOM using Playwright selectors"""
    try:
        case_details = {}
        
        # Wait for the case details to be fully loaded with a shorter timeout
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # If networkidle times out, just proceed
            pass
        
        # Extract parties information from the parties table - common WCCA selectors
        parties_table = await page.query_selector("table.parties, table#partiesTable, table[aria-label*='parties']")
        if parties_table:
            # Extract table rows for parties
            parties_rows = await parties_table.query_selector_all("tbody tr")
            parties_list = []
            for row in parties_rows:
                cells = await row.query_selector_all("td")
                if len(cells) >= 2:
                    party_name = await cells[0].text_content()
                    party_type = await cells[1].text_content()
                    parties_list.append({
                        "name": party_name.strip(),
                        "type": party_type.strip()
                    })
            case_details["parties"] = parties_list
        
        # Extract events/activities from the events table
        events_table = await page.query_selector("table.activities, table.events, table#eventsTable, table[aria-label*='events']")
        if events_table:
            events_rows = await events_table.query_selector_all("tbody tr")
            events_list = []
            for row in events_rows:
                cells = await row.query_selector_all("td")
                if len(cells) >= 3:
                    event_date = await cells[0].text_content()
                    event_type = await cells[1].text_content()
                    event_description = await cells[2].text_content()
                    events_list.append({
                        "date": event_date.strip(),
                        "type": event_type.strip(),
                        "description": event_description.strip()
                    })
            case_details["events"] = events_list
        
        # Extract case information from various sections
        case_info = {}
        
        # Try to find case number and caption in common locations
        case_selectors = [
            "h1.case-number", "h2.case-number", ".case-number",
            "#caseNumber", "[data-case-number]", "caption", "title"
        ]
        for selector in case_selectors:
            element = await page.query_selector(selector)
            if element:
                case_info["case_header"] = (await element.text_content()).strip()
                break
        
        # Extract from info tables commonly found in court systems
        info_table_selectors = [
            "table.case-information", "table.case-details", "table.info",
            "table.details", "#caseInfoTable", ".case-info-table"
        ]
        for selector in info_table_selectors:
            table = await page.query_selector(selector)
            if table:
                rows = await table.query_selector_all("tr")
                for row in rows:
                    cells = await row.query_selector_all("td, th")
                    if len(cells) == 2:
                        key = (await cells[0].text_content()).strip().lower().replace(" ", "_")
                        value = (await cells[1].text_content()).strip()
                        case_info[key] = value
        
        # Also try to extract from div-based layouts
        info_divs = await page.query_selector_all("div.case-info, div.case-details, div.details")
        for div in info_divs:
            text = await div.text_content()
            if text.strip():
                case_info["div_content"] = text.strip()
        
        if case_info:
            case_details["case_info"] = case_info
        
        # If no structured data found, save the entire page content for manual review
        if not case_details:
            print("No structured data found - saving full page content for debugging")
            full_content = await page.content()
            case_details = {
                "full_html": full_content[:5000] + "..." if len(full_content) > 5000 else full_content,
                "warning": "No structured case details found in DOM"
            }
        
        return case_details
    except Exception as e:
        print(f"DOM extraction error: {e}")
        # Return the error with page content for debugging
        try:
            page_content = await page.content()
            return {
                "error": str(e),
                "page_content": page_content[:5000] + "..." if len(page_content) > 5000 else page_content
            }
        except:
            return {"error": str(e)}


def _detail_from_payload(payload):
    if not payload:
        return None
    result = payload.get("result")
    if isinstance(result, dict) and "caseDetail" in result:
        return result.get("caseDetail")
    return payload


def _current_case_identifiers_sync(page):
    parsed = urlparse(page.url)
    qs = parse_qs(parsed.query)
    case_no = qs.get("caseNo", [None])[0]
    county_raw = qs.get("countyNo", [None])[0]
    county_no = int(county_raw) if county_raw is not None else None
    return case_no, county_no

async def _current_case_identifiers_async(page):
    parsed = urlparse(page.url)
    qs = parse_qs(parsed.query)
    case_no = qs.get("caseNo", [None])[0]
    county_raw = qs.get("countyNo", [None])[0]
    county_no = int(county_raw) if county_raw is not None else None
    return case_no, county_no


def _wait_for_captcha_clear_sync(page):
    """Wait for CAPTCHA to be cleared - kept for compatibility but now handled automatically."""
    pass

async def _wait_for_captcha_clear_async(page):
    """Wait for CAPTCHA to be cleared - kept for compatibility but now handled automatically."""
    pass


async def async_scrape_case_details(
    cases,
    *,
    limit: int,
    use_next: bool,
    gemini_key: str | None,
):
    case_map = {
        (case["case_no"], case["county_no"]): case for case in cases
    }

    results = []

    tmp_dir = Path(__file__).parent.joinpath("tmp_dir")
    tmp_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()

        first = cases[0]
        await page.goto(
            "https://wcca.wicourts.gov/caseDetail.html"
            f"?caseNo={first['case_no']}&countyNo={first['county_no']}&index=0&isAdvanced=true",
            wait_until="domcontentloaded",
            timeout=60000,
        )

        # Initialize hcaptcha agent only if a key was supplied
        agent = None
        if gemini_key:
            agent_config = AgentConfig(GEMINI_API_KEY=gemini_key)
            agent = AgentV(page=page, agent_config=agent_config)

        processed = 0
        try:
            while processed < min(limit, len(cases)):
                current_case_no, current_county = await _current_case_identifiers_async(page)
                if current_case_no is None or current_county is None:
                    print("Could not read case metadata from URL; aborting loop.")
                    break
                case_meta = case_map.get((current_case_no, current_county))
                if not case_meta:
                    print(f"Warning: case {current_case_no} (county {current_county}) not in initial result set.")
                    case_meta = {"case_no": current_case_no, "county_no": current_county}

                print("\n===")
                print(f"Currently viewing case {processed + 1}: {current_case_no} (county {current_county})")
                
                # Automatically handle CAPTCHA if present
                if agent:
                    try:
                        await page.click("text=/click here/i", timeout=3000)
                    except Exception:
                        pass

                    try:
                        challenge_signal = await agent.wait_for_challenge()
                        print(f"CAPTCHA challenge handled (signal: {challenge_signal})")
                        await page.wait_for_selector("div.hcaptcha-box iframe", state="hidden", timeout=10000)
                        await page.wait_for_selector("table.parties, div.case-details, #reactContent", timeout=10000)
                    except Exception as exc:
                        print(f"CAPTCHA solving or page load error: {exc}")
                else:
                    print("Solve the CAPTCHA manually in the browser window; waiting for 15 seconds.")
                    await page.wait_for_timeout(15000)

                try:
                    # After CAPTCHA is solved, wait for the page to load case details
                    await page.wait_for_timeout(3000)
                    
                    # Try to read the session payload from sessionStorage
                    payload = await _read_session_payload_async(page)
                    detail = _detail_from_payload(payload) if payload else None
                    
                    if not detail:
                        detail = await _extract_case_details_from_dom(page)
                        if not detail:
                            detail = {"fallback_dom": await page.content(), "warning": "No case details extracted"}

                    results.append({
                        "case": case_meta,
                        "detail": detail,
                    })
                    processed += 1

                    if processed >= min(limit, len(cases)):
                        break

                    if use_next:
                        next_link = await page.query_selector("a[href*='index='] >> text=Next")
                        if not next_link:
                            print("No Next link available; stopping.")
                            break
                        await next_link.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=60000)
                    else:
                        next_case = cases[processed]
                        await page.goto(
                            "https://wcca.wicourts.gov/caseDetail.html"
                            f"?caseNo={next_case['case_no']}&countyNo={next_case['county_no']}&index={processed}&isAdvanced=true",
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                except Exception as e:
                    print(f"Error processing case detail: {e}")
                    results.append({
                        "case": case_meta,
                        "detail": {"error": str(e), "fallback_dom": await page.content()},
                    })
                    processed += 1
        except Exception as e:
            print(f"Critical error in scraping loop: {e}")
        finally:
            await browser.close()

    return results

def scrape_case_details(cases, *, limit, use_next, gemini_key):
    """Sync wrapper for async_scrape_case_details"""
    return asyncio.run(
        async_scrape_case_details(
            cases,
            limit=limit,
            use_next=use_next,
            gemini_key=gemini_key,
        )
    )


def main(argv=None):
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

    if not cases:
        print("No cases returned for the requested window.")
        return 0

    gemini_key = resolve_gemini_key(args.gemini_key)

    results = scrape_case_details(
        cases,
        limit=args.limit,
        use_next=not args.no_next,
        gemini_key=gemini_key,
    )

    if args.output:
        args.output.write_text(json.dumps(results, indent=2, default=str))
        print(f"Wrote {len(results)} record(s) to {args.output}")
    else:
        print(json.dumps(results, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
