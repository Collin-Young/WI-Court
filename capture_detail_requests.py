from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    def log_request(request):
        if 'jsonPost' in request.url:
            print('REQUEST', request.method, request.url)
            print('DATA', request.post_data)
    def log_response(response):
        if 'jsonPost' in response.url:
            print('RESPONSE', response.status, response.url)
    page.on('request', log_request)
    page.on('response', log_response)

    page.goto('https://wcca.wicourts.gov/advanced.html', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(2000)
    control = page.locator("label:has-text('Class codes') .Select-control")
    combo_input = page.locator("label:has-text('Class codes') input[role='combobox']").first
    control.click()
    combo_input.evaluate('el => el.focus()')
    page.keyboard.insert_text('Wills filed - no probate (50111)')
    page.wait_for_timeout(1000)
    page.locator('.Select-menu-outer .Select-option', has_text='Wills filed - no probate (50111)').first.click()
    page.fill("input[name='filingDate.start']", '01-01-2025')
    page.fill("input[name='filingDate.end']", '01-07-2025')
    page.click('button:has-text("Search")')
    page.wait_for_selector('a[href^="caseDetail.html"]')
    first_case = page.locator('a[href^="caseDetail.html"]').first
    href = first_case.get_attribute('href')
    print('Case link', href)
    first_case.click()
    page.wait_for_timeout(5000)
    browser.close()
