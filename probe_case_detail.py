import httpx

case_no = "2025WL000039"
county_no = 23

with httpx.Client(timeout=30) as client:
    client.get('https://wcca.wicourts.gov/advanced.html')
    resp = client.post('https://wcca.wicourts.gov/jsonPost/caseDetail', json={
        "caseNo": case_no,
        "countyNo": county_no
    })
    print(resp.status_code)
    print(resp.text[:500])
