import httpx

headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": "https://wcca.wicourts.gov/advanced.html",
}
with httpx.Client(timeout=30, headers=headers) as client:
    client.get('https://wcca.wicourts.gov/advanced.html')
    resp = client.post('https://wcca.wicourts.gov/jsonPost/caseDetail/5/2025WL000018.json', json={'tac': None, 'captcha': None})
    print(resp.status_code)
    print(resp.text[:200])
