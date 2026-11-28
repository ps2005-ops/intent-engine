"""Offline A/B: independent discovery with and without GDELT, DEVELOPMENT only.
Same discover(), same verify(); only use_gdelt differs. Measures distinct
independent origins, and what the verifier refused (wire copies, namesakes)."""
from __future__ import annotations
import datetime, json, sys
from intent_engine.company_ingestion import independent_reporting as IR

COS = [("ClickHouse", "clickhouse.com"), ("Pinecone", "pinecone.io"), ("Glean", "glean.com"),
       ("Labelbox", "labelbox.com"), ("GEP", "gep.com"), ("Fairmarkit", "fairmarkit.com"),
       ("NAVEX", "navex.com"), ("Riskonnect", "riskonnect.com"), ("Prophix", "prophix.com"),
       ("Kantata", "kantata.com"), ("Nintex", "nintex.com"), ("Claroty", "claroty.com"),
       ("Corelight", "corelight.com"), ("Censys", "censys.com"), ("SoftServe", "softserveinc.com"),
       ("Bounteous", "bounteous.com")]
fetch, fetch_json = IR.live_fetchers()
today = datetime.date.today().isoformat()
out = []
for name, dom in COS:
    row = {"company": name}
    for g in (False, True):
        r = IR.discover(company=name, domain=dom, aliases=(), fetch=fetch, fetch_json=fetch_json,
                        today=today, use_gdelt=g)
        ind = [c for c in r["candidates"] if c["source_class"] == "independent_reporting"]
        row["gdelt" if g else "base"] = {
            "origins": r["independent_relevant_origins"], "pointers": r["pointers_found"],
            "channels_ok": r["channels_successful"],
            "hosts": sorted({IR._registrable(IR._host(c["url"])) for c in ind}),
            "classes": sorted({c["source_class"] for c in r["candidates"]}),
            "rejections": r["rejection_reasons"]}
    out.append(row)
    print(name, row["base"]["origins"], "->", row["gdelt"]["origins"], row["gdelt"]["hosts"], flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
