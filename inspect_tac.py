from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://wcca.wicourts.gov/tac.html', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(5000)
    html = page.inner_html('body')
    print(html[:2000])
    browser.close()
