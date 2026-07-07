import httpx

resp = httpx.get('https://wcca.wicourts.gov/caseDetail.html?caseNo=2025WL000018&countyNo=5&index=0&isAdvanced=true')
print(resp.status_code)
print(resp.text[:2000])
