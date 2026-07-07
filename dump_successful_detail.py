from playwright.sync_api import sync_playwright
import time

CHROME_PROFILE = r"C:\Users\Collin\AppData\Local\Google\Chrome\User Data"

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        CHROME_PROFILE,
        headless=False,
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    
    page = context.new_page()
    url = "https://wcca.wicourts.gov/caseDetail.html?caseNo=2025WL000018&countyNo=5&index=0&isAdvanced=true"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    
    click_link = page.locator('span.link:has-text("Click here")')
    if click_link.count() > 0:
        print("Clicking CAPTCHA bypass link...")
        click_link.first.click()
        page.wait_for_load_state('domcontentloaded', timeout=60000)
        page.wait_for_timeout(2000)
        if page.locator('span.link:has-text("Click here")').count() > 0 or page.locator('text=/Please complete the CAPTCHA/i').count() > 0:
            print("CAPTCHA remained after click; please solve manually, then press Enter.")
            input()
    
    page.wait_for_load_state('networkidle', timeout=30000)
    page.wait_for_timeout(5000)
    
    html = page.content()
    with open('successful_detail.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Dumped HTML to successful_detail.html")
    print(f"HTML length: {len(html)}")
    
    page.close()
    context.close()