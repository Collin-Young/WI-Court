"""Interactive helper to capture WCCA cookies after manual CAPTCHA solve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent

from playwright.sync_api import sync_playwright

START_URL = "https://wcca.wicourts.gov/advanced.html"
DEFAULT_PROFILE = ".wcca_profile"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Obtain WCCA cookies after manually solving CAPTCHA")
    parser.add_argument("--url", default=START_URL, help="Page to open (default: advanced search)")
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Directory to store persistent browser data (default: .wcca_profile)",
    )
    parser.add_argument("--output", type=Path, help="Optional file to write the cookie header")
    return parser


def format_cookie_header(cookies: list[dict]) -> str:
    parts = []
    for cookie in cookies:
        if not cookie.get("value"):
            continue
        domain = cookie.get("domain", "") or ""
        if "wicourts.gov" not in domain:
            continue
        parts.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(parts)


def main() -> int:
    args = build_parser().parse_args()

    intro = dedent(
        f"""
        A Chromium window will open to {args.url}.
        1. Sign in/solve hCaptcha as usual until case details load normally.
        2. Navigate to any case detail page if needed.
        3. Return to this terminal and press Enter when ready.
        Cookies captured from the same browser session will then be printed.
        """
    )
    print(intro)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            args.profile,
            headless=False,
        )
        page = browser.new_page()
        page.goto(args.url, wait_until="domcontentloaded")

        input("\nPress Enter once the CAPTCHA is solved and case details are accessible...")

        cookies = browser.cookies()
        header = format_cookie_header(cookies)
        if not header:
            print("No cookies found for wicourts.gov; did you solve the CAPTCHA in this window?")
            browser.close()
            return 1

        print("\nCookie header (copy this into --cookie):")
        print(header)

        if args.output:
            args.output.write_text(header, encoding="utf-8")
            print(f"\nSaved to {args.output}")

        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
