#!/usr/bin/env python3
"""§6: are all forty findable, correctly, before a single analysis is spent?

COSTS NO QUOTA. It reads `/api/companies` only, which is session-free and does
not admit an analysis, so this can be run against the live preview as often as
needed. That is the entire point: identity is the cheapest gate to measure and
the most expensive to get wrong, and the previous wave learned that by spending
four analyses on a harness bug.

IT MATCHES ON `entity_id`, NOT ON A SUBSTRING. A first version of this check
accepted any row whose name or domain contained the typed word, and it passed
"Clari" because "clari" is a substring of "Clarivate" -- reporting a
wrong-company match as a success. The registry id is the only answer that
cannot be satisfied by a coincidence.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BASE = "https://intent-engine-preview-bridge.onrender.com"

# (n, typed, entity_id, [variants a person might type])
FORTY = [
 (1, "Rubrik", "rubrik", ["Rub", "rubrik", "RUBRIK", "Rubrik Inc"]),
 (2, "Cohesity", "cohesity", ["Coh", "cohesity", "COHESITY"]),
 (3, "project44", "project44", ["proj", "Project44", "Project 44", "p44"]),
 (4, "Kinaxis", "kinaxis", ["Kin", "kinaxis", "KINAXIS"]),
 (5, "Alation", "alation", ["Ala", "alation"]),
 (6, "Workato", "workato", ["Work", "workato"]),
 (7, "Dataminr", "dataminr", ["Datamin", "dataminr"]),
 (8, "Adastra", "adastra", ["Adas", "adastra", "Adastra Corporation"]),
 (9, "HYCU", "hycu", ["HYC", "hycu", "Hycu"]),
 (10, "Nasuni", "nasuni", ["Nas", "nasuni"]),
 (11, "Dataiku", "dataiku", ["Dataik", "dataiku"]),
 (12, "Commvault", "commvault", ["Comm", "commvault", "Commvault Systems"]),
 (13, "Boomi", "boomi", ["Boo", "boomi"]),
 (14, "SnapLogic", "snaplogic", ["Snap", "snaplogic", "Snaplogic",
                                 "snap logic"]),
 (15, "West Monroe", "west_monroe", ["West", "west monroe",
                                     "West Monroe Partners"]),
 (16, "Guidehouse", "guidehouse", ["Guide", "guidehouse"]),
 (17, "Collibra", "collibra", ["Coll", "collibra"]),
 (18, "Airbyte", "airbyte", ["Airb", "airbyte"]),
 (19, "OneTrust", "onetrust", ["OneT", "onetrust", "Onetrust", "one trust"]),
 (20, "Samsara", "samsara", ["Sams", "samsara"]),
 (21, "FourKites", "fourkites", ["Four", "fourkites", "Fourkites",
                                 "four kites"]),
 (22, "Descartes Systems", "descartes", ["Desc", "descartes",
                                         "Descartes Systems Group"]),
 (23, "o9 Solutions", "o9_solutions", ["o9", "o9 solutions", "O9"]),
 (24, "ThoughtSpot", "thoughtspot", ["Thought", "thoughtspot", "Thoughtspot",
                                     "thought spot"]),
 (25, "Starburst", "starburst", ["Starb", "starburst", "Starburst Data"]),
 (26, "Dremio", "dremio", ["Drem", "dremio"]),
 (27, "Denodo", "denodo", ["Deno", "denodo", "Denodo Technologies"]),
 (28, "Geotab", "geotab", ["Geo", "geotab"]),
 (29, "Clari", "clari", ["Clar", "clari", "Clari Inc"]),
 (30, "6sense", "6sense", ["6se", "6sense", "6 sense", "6Sense"]),
 (31, "Gong", "gong", ["Gon", "gong", "Gong.io"]),
 (32, "AlphaSense", "alphasense", ["Alpha", "alphasense", "Alpha Sense",
                                   "alpha-sense"]),
 (33, "FiscalNote", "fiscalnote", ["Fiscal", "fiscalnote", "Fiscal Note"]),
 (34, "Recorded Future", "recorded_future", ["Recorded", "recorded future",
                                             "recordedfuture"]),
 (35, "Prewave", "prewave", ["Prew", "prewave"]),
 (36, "Protiviti", "protiviti", ["Prot", "protiviti"]),
 (37, "Credera", "credera", ["Cred", "credera"]),
 (38, "Long View Systems", "long_view", ["Long View", "long view systems",
                                         "longview"]),
 (39, "Celigo", "celigo", ["Cel", "celigo"]),
 (40, "Fivetran", "fivetran", ["Five", "fivetran", "dbt Labs", "dbt"]),
]

#: Typed words that MUST still offer the other real company second. Removing a
#: genuine registrant from the list would trade one wrong answer for another.
COLLISIONS = {"Clari": "clarivate", "Sigma": "sigma lithium",
              "Point B": "turning point brands"}


def suggest(base, typed, timeout=30):
    url = f"{base}/api/companies?q=" + urllib.parse.quote(typed)
    began = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "next40/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode())
    return body.get("companies") or [], (time.time() - began) * 1000.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--out", default="reports/next40_preflight.json")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/version", timeout=30) as r:
            sha = json.loads(r.read().decode()).get("commit", "")
    except Exception:                                        # noqa: BLE001
        sha = ""
    print(f"base {base}\nlive {sha[:12]}\n")

    rows, lat = [], []
    for n, typed, eid, variants in FORTY:
        rec = {"n": n, "typed": typed, "entity_id": eid}
        try:
            got, ms = suggest(base, typed)
        except Exception as exc:                             # noqa: BLE001
            rec.update(error=f"{type(exc).__name__}: {exc}",
                       discoverable=False, canonical_identity=False,
                       manual_url_required=True)
            rows.append(rec)
            print(f"{n:02d} ERR  {typed:20s} {exc}")
            continue
        lat.append(ms)
        top = got[0] if got else None
        rec["latency_ms"] = round(ms, 1)
        rec["rows"] = len(got)
        rec["first"] = (top or {}).get("legal_name", "")
        rec["first_entity_id"] = (top or {}).get("entity_id", "")
        rec["discoverable"] = bool(top) and top.get("entity_id") == eid
        rec["domain"] = (top or {}).get("domain", "")
        rec["cik"] = (top or {}).get("cik", "")
        rec["ticker"] = (top or {}).get("ticker", "")
        rec["listing"] = (top or {}).get("listing", "")
        rec["canonical_identity"] = bool(
            rec["discoverable"] and (rec["domain"] or rec["cik"]))
        rec["manual_url_required"] = not rec["canonical_identity"]
        misses = []
        for v in variants:
            try:
                vr, _ms = suggest(base, v)
            except Exception as exc:                         # noqa: BLE001
                misses.append(f"{v}:{type(exc).__name__}")
                continue
            if not vr or vr[0].get("entity_id") != eid:
                misses.append(
                    f"{v}->{(vr[0].get('legal_name') if vr else 'NONE')}")
        rec["variant_misses"] = misses
        rows.append(rec)
        flag = "OK " if rec["canonical_identity"] and not misses else "FAIL"
        print(f"{n:02d} {flag} {typed:20s} {rec['first'][:30]:30s} "
              f"dom={rec['domain'] or '-':20s} cik={rec['cik'] or '-':12s} "
              f"{rec['ticker'] or '-':6s} {rec['listing'] or '-':8s} "
              f"{ms:4.0f}ms" + (f"  MISS={misses}" if misses else ""))

    collide = {}
    for typed, other in COLLISIONS.items():
        try:
            got, _ms = suggest(base, typed)
        except Exception:                                    # noqa: BLE001
            continue
        names = " | ".join((r.get("legal_name") or "") for r in got)
        collide[typed] = {"first": (got[0].get("legal_name") if got else ""),
                          "still_offers_other": other in names.lower(),
                          "all": names}

    disc = sum(1 for r in rows if r["discoverable"])
    canon = sum(1 for r in rows if r["canonical_identity"])
    manual = sum(1 for r in rows if r["manual_url_required"])
    vmiss = {r["typed"]: r["variant_misses"] for r in rows
             if r.get("variant_misses")}
    print(f"\nSEARCH_DISCOVERABLE   {disc}/40")
    print(f"CANONICAL_IDENTITY    {canon}/40")
    print(f"MANUAL_URL_REQUIRED   {manual}/40")
    if lat:
        print(f"autocomplete p50 {statistics.median(lat):.0f}ms  "
              f"p90 {sorted(lat)[max(0, int(len(lat) * 0.9) - 1)]:.0f}ms  "
              f"max {max(lat):.0f}ms")
    print(f"VARIANT_MISSES        {json.dumps(vmiss) if vmiss else '{}'}")
    for typed, c in collide.items():
        print(f"collision {typed!r}: first={c['first']!r} "
              f"still offers the other: {c['still_offers_other']}")
    wrong = [r for r in rows
             if r["rows"] and not r["discoverable"]]
    for r in wrong:
        print(f"WRONG COMPANY FIRST for {r['typed']!r}: {r['first']!r} "
              f"(entity_id={r['first_entity_id']!r})")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"base": base, "live_sha": sha, "rows": rows,
         "collisions": collide,
         "totals": {"discoverable": disc, "canonical_identity": canon,
                    "manual_url_required": manual,
                    "variant_misses": vmiss}}, indent=1))
    print(f"\nwrote {out}")
    return 0 if (disc == 40 and canon == 40 and manual == 0 and not vmiss) else 1


if __name__ == "__main__":
    raise SystemExit(main())
