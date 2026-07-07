from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    def log_request(request):
        if 'jsonPost' in request.url:
            print('URL', request.url)
            print('HEADERS', request.headers)
            print('DATA', request.post_data)
    page.on('request', log_request)

    page.goto('https://wcca.wicourts.gov/advanced.html', wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    browser.close()
