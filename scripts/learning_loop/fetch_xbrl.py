import json, sys, time, urllib.request, pathlib, gzip
from intent_engine.company_ingestion.third_party_filings import _sec_user_agent
from intent_engine.paper_validation import universe as U
out = pathlib.Path(sys.argv[1]); UA = _sec_user_agent()
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
        return json.loads(gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b)
tk = get("https://www.sec.gov/files/company_tickers.json")
cik = {v["ticker"].upper(): int(v["cik_str"]) for v in tk.values()}
cos, _ = U.companies(); miss = []
for c in cos:
    f = out / f"{c.symbol}.json"
    if f.exists(): continue
    k = cik.get(c.symbol.replace(".", "-")) or cik.get(c.symbol)
    if not k: miss.append(c.symbol); continue
    try:
        f.write_text(json.dumps(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{k:010d}.json")))
    except Exception as e: miss.append(f"{c.symbol}:{e}")
    time.sleep(0.15)
print("fetched", len(list(out.glob("*.json"))), "missing", miss)
