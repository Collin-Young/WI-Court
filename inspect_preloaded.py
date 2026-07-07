from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://wcca.wicourts.gov/advanced.html', wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    control = page.locator("label:has-text('Class codes') .Select-control")
    combo = page.locator("label:has-text('Class codes') input[role='combobox']").first
    control.click()
    combo.evaluate('el => el.focus()')
    page.keyboard.insert_text('Wills filed - no probate (50111)')
    page.wait_for_timeout(800)
    page.locator('.Select-menu-outer .Select-option', has_text='Wills filed - no probate (50111)').first.click()
    page.fill("input[name='filingDate.start']", '01-01-2025')
    page.fill("input[name='filingDate.end']", '01-07-2025')
    page.click('button:has-text("Search")')
    page.wait_for_selector('a[href^="caseDetail.html"]')
    page.locator('a[href^="caseDetail.html"]').first.click()
    page.wait_for_timeout(5000)
    state = page.evaluate("() => window.__PRELOADED_STATE__ || window.__store__ || window.__STATE__")
    print('state type', type(state))
    browser.close()
