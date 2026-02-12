# Wisconsin Circuit Court (WCCA) Scraper

Python tooling for the public Wisconsin Circuit Court Access (WCCA) site. The project mirrors the UI's JSON traffic so you can script:

- Bulk advanced searches across filing-date windows and class codes.
- Detail scraping with Playwright, including optional integration with hcaptcha-challenger for automated CAPTCHA solving.
- API-detail pulls using a pre-authenticated browser session so you can skip repeated CAPTCHAs.
- Cookie capture helpers and utility scripts (e.g., enumerating class codes).

Large JSON/CSV exports are intentionally ignored via `.gitignore`; only the reusable code and documentation live in git so the repo stays lightweight for your teammates.

## Requirements

- Python 3.10+ (the checked-in `.python-version` pins 3.10.5).
- Google Chrome/Chromium for Playwright.
- Installed Playwright browsers: `python -m playwright install chromium`.
- Optional: a Gemini API key if you want automatic CAPTCHA solving. Copy `.env.example` to `.env`, place the key under `GEMINI_API_KEY`, and the scripts will read it automatically.

Install dependencies inside a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Repository layout

```
wi_scraper/           # Reusable library (client, models, helpers).
main.py               # CLI for summary sweeps via advancedCaseSearch.
detail_scraper.py     # Playwright+hcaptcha flow for interactive details.
api_detail_scraper.py # Uses a persistent browser profile/cookies to pull details.
cookie_helper.py      # Captures a cookie header after you manually pass hCaptcha.
list_class_codes.py   # Enumerates class codes (requires valid cookie).
test_captcha_*.py     # Optional sanity checks for hcaptcha-challenger.
.gitignore            # Keeps massive JSON/CSV/DB exports out of git.
```

Any JSON/CSV/DB outputs you generate stay local—drop them anywhere in the repo root and git will ignore them. If you want to check sample payloads into source control, create `examples/` and remove/override the relevant ignore rule.

## Usage

### 1. Fetch summary case data

```powershell
python main.py --start 2025-01-01 --end 2025-01-07 \
  --class-code 50111 --class-code 50101 \
  --output results.json
```

Key arguments:

- `--start` / `--end`: inclusive filing-date window (`YYYY-MM-DD`, `--end` defaults to today).
- `--span-days`: bucket size while iterating the calendar (default `7`).
- `--class-code`: repeat to restrict which class codes are queried (defaults to the foreclosure/estate set in `wi_scraper.constants.DEFAULT_CLASS_CODES`).
- `--output`: optional JSON file to write (otherwise prints to stdout).

The resulting JSON has a `meta` block plus `cases[]` entries with normalized fields (`case_no`, `county_no`, `filing_date`, `status`, etc.) and a `raw` blob that mirrors the API payload for your own enrichment.

### 2. Capture cookies once

```
python cookie_helper.py --output session_cookie.txt
```

- Opens Chromium with a persistent profile stored in `.wcca_profile` (ignored by git).
- Solve hCaptcha manually, navigate to any case, then return to the terminal and press Enter.
- A ready-to-use `Cookie` header containing `JSessionId_XXXX` will be printed and (optionally) saved.

Reuse that cookie string in `list_class_codes.py` and `api_detail_scraper.py` to avoid solving CAPTCHAs on every run.

### 3. Enumerate class codes

```
python list_class_codes.py --cookie "$(Get-Content session_cookie.txt)"
```

Returns the list exposed by the UI. Pass `--include-inactive` to show inactive codes as well.

### 4. Scrape case details interactively

```
python detail_scraper.py --start 2025-01-01 --end 2025-01-07 --limit 5 --output details.json
```

- Launches Chromium (non-headless) and iterates cases returned by `main.py`.
- If `GEMINI_API_KEY` or `--gemini-key` is supplied, hcaptcha-challenger will attempt to auto-solve CAPTCHAs; otherwise you'll be prompted to solve them manually.
- Detail payloads are pulled from `sessionStorage`. When the JSON blob is missing, the script extracts the DOM as a fallback so you can still inspect the data.

### 5. Pull details via API once you have cookies

```
python api_detail_scraper.py --start 2025-09-01 --end 2025-09-07 \
  --profile .wcca_profile --limit 100 \
  --output api_details.json --parties-csv parties.csv
```

- Reuses the existing advanced search sweep, then loads each case detail inside a persistent Chromium profile.
- Populate the profile once with `cookie_helper.py` (solve hCaptcha manually) and subsequent runs will automatically reuse those cookies.
- Emits a JSON array of case/detail envelopes and (optionally) a flattened CSV of parties.

## Library usage

```python
from datetime import date
from wi_scraper import fetch_case_summaries, flatten_aggregated

aggregated = fetch_case_summaries(start=date(2025, 1, 1))
for row in flatten_aggregated(aggregated):
    process(row)
```

`WICourtClient` is exported for direct access to the `/jsonPost/advancedCaseSearch` endpoint if you want to embed the client in another service.

## Security & privacy checklist

- Never commit downloaded case data. `.gitignore` already excludes JSON/CSV/DB files, but double-check before pushing.
- Provide your own `GEMINI_API_KEY`; the repo ships with no secrets.
- `.wcca_profile/` keeps a Chromium profile with any local cookies. It's ignored and should stay local.

## Developing & publishing

1. Run `git status` to make sure only code/doc changes are staged.
2. Optionally run the browser-based smoke tests:
   - `python test_captcha_integration.py`
   - `python test_captcha_solving.py`
3. Commit and push to GitHub (commands shown in the task tracker/issue or run `git remote add origin ... && git push -u origin main`).

Feel free to add a LICENSE file before pushing to a public repository if you plan to open-source the tool.
