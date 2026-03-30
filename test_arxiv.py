"""Test arXiv API directly."""
import requests
import xml.etree.ElementTree as ET

ns = {"atom": "http://www.w3.org/2005/Atom"}

for label, q in [
    ("simple", "all:nanoprobe"),
    ("AND", "all:fluorescent AND all:nanoprobe"),
    ("OR", "all:fluorescent OR all:nanoprobe"),
    ("ti+AND", 'ti:fluorescent AND ti:nanoprobe'),
]:
    print(f"\n=== {label}: {q} ===")
    try:
        r = requests.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": q, "start": 0, "max_results": 3},
            timeout=120,
        )
        print(f"Status: {r.status_code}, Len: {len(r.text)}")
        root = ET.fromstring(r.text)
        entries = root.findall("atom:entry", ns)
        print(f"Entries: {len(entries)}")
        for e in entries[:3]:
            t = e.findtext("atom:title", default="", namespaces=ns).strip()
            print(f"  - {t[:100]}")
    except Exception as ex:
        print(f"Error: {ex}")
