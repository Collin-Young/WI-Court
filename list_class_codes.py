"""List available class codes from WCCA cached data."""

from __future__ import annotations

import argparse
from typing import Dict

import httpx

from wi_scraper.constants import BASE_URL


def parse_cookie_header(raw: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def build_client(cookie_header: str | None) -> httpx.Client:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/advanced.html",
        "User-Agent": "Mozilla/5.0",
    }
    client = httpx.Client(base_url=BASE_URL, timeout=30.0, headers=headers)
    if cookie_header:
        for name, value in parse_cookie_header(cookie_header).items():
            client.cookies.set(name, value, domain="wcca.wicourts.gov")
    return client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List class codes exposed by WCCA")
    parser.add_argument("--cookie", help="Cookie header containing JSessionId_9401")
    parser.add_argument("--include-inactive", action="store_true", help="Show inactive codes as well")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    client = build_client(args.cookie)
    response = client.post("/jsonPost", json={"cachedData": {"wcisClsCodes": {}}})
    response.raise_for_status()
    payload = response.json()

    codes = payload.get("cachedData", {}).get("wcisClsCodes", [])

    if not codes:
        print("No class codes returned. Provide a fresh cookie after solving the CAPTCHA.")
        return 1

    key = "classCode" if "classCode" in codes[0] else "wcisClsCode"
    description_key = "description" if "description" in codes[0] else "descr"

    filtered = [
        item for item in codes if args.include_inactive or item.get("isActive", True)
    ]

    width = max(len(str(item.get(key, ""))) for item in filtered)
    for item in sorted(filtered, key=lambda c: str(c.get(key, ""))):
        code = str(item.get(key, ""))
        desc = item.get(description_key, "")
        active_flag = "" if item.get("isActive", True) else " (inactive)"
        print(f"{code.ljust(width)}  {desc}{active_flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
