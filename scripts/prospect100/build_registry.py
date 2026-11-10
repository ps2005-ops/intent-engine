"""Build docs/engineering/prospect100/PROSPECT_REGISTRY.yaml -- deliverable A.

Joins, per prospect id:
  PROSPECT_LIST.yaml        the request, verbatim
  identity_table.py         the reviewed identity
  domain_verification.json  what the product's fetcher saw at each domain
  source_discovery*.json    which official pages were attested
  SEC submissions           the last annual report a former filer made

and states, per company, how far ENTRY is ready -- never how good an
analysis is. Analysis quality is a separate measurement and is recorded here
as NOT_MEASURED until it has been measured.

Usage:
  PYTHONPATH=src python scripts/prospect100/build_registry.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import identity_table as T  # noqa: E402

D = Path("docs/engineering/prospect100")
SEC_CACHE = D / "sec_former_filers.json"


def _last_annual(cik: str) -> dict:
    from intent_engine.company_ingestion.edgar import USER_AGENT
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT + " contact:ps2005@my.yorku.ca"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    recent = data.get("filings", {}).get("recent", {})
    last10k = last_any = ""
    for form, date in zip(recent.get("form", []), recent.get("filingDate", [])):
        last_any = max(last_any, date)
        if form in ("10-K", "10-K/A", "20-F", "40-F") and date > last10k:
            last10k = date
    return {"sec_name": data.get("name", ""), "last_annual_report": last10k,
            "last_filing_of_any_kind": last_any}


def main() -> None:
    req = {p["prospect_id"]: p for p in yaml.safe_load(
        (D / "PROSPECT_LIST.yaml").read_text())["prospects"]}
    verify = {}
    for r in json.loads((D / "domain_verification.json").read_text()):
        verify.setdefault(r["prospect_id"], []).append(r)
    found = {}
    for name in ("source_discovery.json", "source_discovery_pass2.json",
                 "source_discovery_pass3.json"):
        for r in json.loads((D / name).read_text()):
            found[(r["prospect_id"], r["host"])] = r

    sec = json.loads(SEC_CACHE.read_text()) if SEC_CACHE.exists() else {}
    for r in T.ROWS:
        cik = (r.get("former") or {}).get("cik")
        if cik and cik not in sec:
            sec[cik] = _last_annual(cik)
            time.sleep(0.3)
    SEC_CACHE.write_text(json.dumps(sec, indent=1, sort_keys=True))

    rows_by_pid = {r["pid"]: r for r in T.ROWS}
    out = []
    counts: dict = {}
    for pid in sorted(req):
        p = req[pid]
        rec = {"prospect_id": pid, "tier": p["tier"],
               "name_as_listed": p["name_as_listed"],
               "flag_as_listed": p["flag"]}
        if pid in T.EXISTING:
            register, eid = T.EXISTING[pid]
            rec.update({"register": register, "entity_id": eid,
                        "entry_readiness": "READY_EXISTING_REGISTER",
                        "analysis_quality": "NOT_MEASURED"})
            out.append(rec)
            counts["READY_EXISTING_REGISTER"] = counts.get(
                "READY_EXISTING_REGISTER", 0) + 1
            continue
        r = rows_by_pid[pid]
        st = r.get("status")
        srcs = []
        if r["host"]:
            d = found.get((pid, r["host"]))
            srcs = [{"kind": a["kind"], "url": a["url"]}
                    for a in (d or {}).get("accepted", [])]
        cik = r.get("cik", "")
        if st and st["state"] in ("ACQUIRED_ABSORBED", "CEASED_OPERATING"):
            ready = "STOP_NO_LONGER_INDEPENDENT"
        elif cik and srcs:
            ready = "READY_FILINGS_AND_SITE"
        elif cik:
            ready = "READY_FILINGS_ONLY_SITE_REFUSED"
        elif len(srcs) >= 2:
            ready = "READY_SITE"
        elif srcs:
            ready = "READY_THIN_SITE"
        else:
            ready = "IDENTITY_ONLY_SITE_REFUSED"
        counts[ready] = counts.get(ready, 0) + 1
        former = r.get("former")
        if former:
            former = {**former, **sec.get(former["cik"], {})}
            former.pop("until", None)
        rec.update({
            "register": "catalog (company_ingestion/catalog_prospects.py)",
            "entity_id": r["id"], "legal_name": r["legal"],
            "common_name": r["common"], "hq_country": r["country"] or None,
            "flag_matches_hq": (
                {"US": "United States", "CA": "Canada"}[p["flag"]]
                == r["country"]),
            "primary_domain": r["domain"], "aliases": list(r["aliases"]),
            "listing": ([f"{e}: {t}" for e, t in r.get("listings", ())]
                        or None),
            "sec_cik": cik or None,
            "former_sec_filer": former or None,
            "parent_entity_id": r.get("parent") or None,
            "disambiguation_group": r.get("group") or None,
            "corporate_status": ({**st, "evidence": list(st["evidence"])}
                                 if st else None),
            "identity_notes": r.get("note") or None,
            "domain_checks": [
                {"candidate": v["candidate_domain"],
                 "product_fetcher_ok": v.get("safe_fetch_ok"),
                 "status": v.get("safe_fetch_status"),
                 "failure": v.get("safe_fetch_failure") or None,
                 "redirected_to": (v["final_host"]
                                   if v.get("redirected_off_domain") else None),
                 "title": v.get("title") or None}
                for v in verify.get(pid, [])],
            "attested_sources": srcs,
            "retrieval_note": r.get("refused") or None,
            "entry_readiness": ready,
            "analysis_quality": "NOT_MEASURED",
            "last_verified": "2026-11-09",
        })
        out.append(rec)

    doc = {
        "version": "prospect100.registry.v1",
        "built": "2026-11-09",
        "what_this_is": (
            "Deliverable A: the canonical identity of each requested "
            "prospect. entry_readiness says how far a search-to-run journey "
            "can go on identity and retrievable sources; it is NOT a quality "
            "score. analysis_quality stays NOT_MEASURED until a pass "
            "measures it."),
        "entry_readiness_counts": dict(sorted(counts.items())),
        "prospects": out,
    }
    (D / "PROSPECT_REGISTRY.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
    print(json.dumps(doc["entry_readiness_counts"], indent=1))


if __name__ == "__main__":
    main()
