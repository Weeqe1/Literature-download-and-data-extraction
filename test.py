import requests, os, time
def test_semantic_scholar(q, api_key=None):
    base = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": q, "limit": 5, "fields": "title,abstract,year,doi"}
    headers = {"User-Agent":"pdf-harvester/1.0"}
    if api_key:
        headers["x-api-key"] = api_key
    t0 = time.time()
    r = requests.get(base, params=params, headers=headers, timeout=20)
    print("HTTP", r.status_code, "time:", time.time()-t0)
    try:
        js = r.json()
        print("top keys:", list(js.keys()))
        data = js.get("data") or js.get("results") or js
        print("sample count:", len(data) if isinstance(data, list) else "non-list")
        if isinstance(data, list) and data:
            print("first title:", data[0].get("title"))
    except Exception as e:
        print("failed json parse:", e)
    print("raw snippet:", repr(r.text[:800]))

# Example usage:
test_semantic_scholar("nano fluorescent probe", api_key=None)
