from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    def log_request(req):
        if 'jsonPost' in req.url:
            print('REQUEST', req.method, req.url)
            print('DATA', req.post_data)
    def log_response(res):
        if 'jsonPost' in res.url:
            try:
                body = res.text()[:200]
            except Exception:
                body = '<error>'
            print('RESPONSE', res.status, res.url)
            print('BODY', body)
    page.on('request', log_request)
    page.on('response', log_response)

    page.goto('https://wcca.wicourts.gov/caseDetail.html?caseNo=2025WL000018&countyNo=5&index=0&isAdvanced=true', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(10000)
    browser.close()
