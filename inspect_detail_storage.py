from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://wcca.wicourts.gov/caseDetail.html?caseNo=2025WL000018&countyNo=5&index=0&isAdvanced=true', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)
    keys = page.evaluate("() => Object.keys(sessionStorage)")
    print('keys', keys)
    data = page.evaluate("() => sessionStorage.getItem('/caseDetail.html')")
    print('length', len(data) if data else None)
    browser.close()
