import httpx

headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://wcca.wicourts.gov",
    "Referer": "https://wcca.wicourts.gov/advanced.html",
}
with httpx.Client(timeout=30, headers=headers) as client:
    client.get('https://wcca.wicourts.gov/advanced.html')
    resp = client.post('https://wcca.wicourts.gov/jsonPost/', json={'caseDetail': {'caseNo': '2025WL000018', 'countyNo': 5}})
    print(resp.status_code)
    print(resp.text[:500])
