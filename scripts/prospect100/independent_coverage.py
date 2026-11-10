"""How much independent reporting the new channel finds, per company.

Discovery and verification only (no analysis run): for every prospect the
qualification table graded as having NO independent origin, run
`independent_reporting.discover` live and record what it verifiably found.
GDELT is excluded here because this machine's IP is throttled by it (429 on
single paced requests, 2026-11-09); that is recorded, not hidden.

Usage: PYTHONPATH=src python scripts/prospect100/independent_coverage.py
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import pathlib
import time

import yaml

from intent_engine.company_ingestion import independent_reporting as IR

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/engineering/prospect100"


def main() -> int:
    reg = {r["prospect_id"]: r for r in yaml.safe_load(
        (DOCS / "PROSPECT_REGISTRY.yaml").read_text())["prospects"]}
    q = json.loads((DOCS / "qualification_100.json").read_text())
    zero = [t for t in q["companies"]
            if t["grades"].get("independence") == "FAIL"]
    fetch, fetch_json = IR.live_fetchers()

    def one(t):
        r = reg[t["prospect_id"]]
        name = r.get("common_name") or r["name_as_listed"]
        legal = r.get("legal_name") or ""
        began = time.monotonic()
        rep = IR.discover(company=name, domain=r.get("primary_domain") or "",
                          aliases=tuple(a for a in (legal,) if a and a != name),
                          fetch=fetch, fetch_json=fetch_json,
                          today="2026-11-09", use_gdelt=False)
        ind = [c for c in rep["candidates"]
               if c["source_class"] == "independent_reporting"]
        return {"prospect_id": t["prospect_id"], "company": name,
                "tier": t["tier"], "seconds": round(time.monotonic() - began, 1),
                "pointers": rep["pointers_found"],
                "fetched": rep["candidates_fetched"],
                "independent_articles": len(ind),
                "independent_origins": rep["independent_relevant_origins"],
                "publishers": sorted({c["publisher"] for c in ind}),
                "wire_releases": len(rep["candidates"]) - len(ind),
                "wikipedia": "wikipedia_references" in rep["channels_successful"],
                "rejection_reasons": rep["rejection_reasons"],
                "articles": [{"publisher": c["publisher"],
                              "published": c["published"], "title": c["title"],
                              "url": c["url"], "excerpt": c["excerpt"][:300]}
                             for c in ind]}
    with cf.ThreadPoolExecutor(2) as pool:
        rows = sorted(pool.map(one, zero), key=lambda r: r["prospect_id"])
    got = [r for r in rows if r["independent_origins"] >= 1]
    two = [r for r in rows if r["independent_origins"] >= 2]
    summary = {
        "measured": "2026-11-09, discovery + verified retrieval, no analysis",
        "companies_without_independent_evidence_before": len(rows),
        "now_with_at_least_one_independent_origin": len(got),
        "now_with_two_or_more": len(two),
        "independent_articles_total": sum(r["independent_articles"] for r in rows),
        "by_tier": {f"T{k}": sum(1 for r in got if r["tier"] == k)
                    for k in (1, 2, 3, 4)},
        "publishers": sorted({p for r in rows for p in r["publishers"]}),
        "wikipedia_identity_matched": sum(1 for r in rows if r["wikipedia"]),
        "gdelt": "excluded: 429 from this IP on single paced requests",
        "seconds_p50": sorted(r["seconds"] for r in rows)[len(rows) // 2],
    }
    (DOCS / "independent_coverage.json").write_text(json.dumps(
        {"summary": summary, "companies": rows}, indent=1))
    print(json.dumps(summary, indent=1))
    for r in rows:
        if r["independent_origins"]:
            print(f"  {r['prospect_id']:>3} {r['company'][:20]:20s} "
                  f"articles={r['independent_articles']} "
                  f"origins={r['independent_origins']} {r['publishers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
