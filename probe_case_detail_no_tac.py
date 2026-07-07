import httpx

with httpx.Client(timeout=30) as client:
    client.get("https://wcca.wicourts.gov/advanced.html")
    resp = client.post("https://wcca.wicourts.gov/jsonPost/caseDetail/5/2025WL000018", json={"tac": None, "captcha": "fake"})
    print(resp.status_code)
    print(resp.text)
