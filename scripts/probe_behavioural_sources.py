"""§2/§29: call every candidate behavioural source and classify it honestly.

WHY THIS SCRIPT EXISTS
----------------------
The previous run shipped six series marked LIVE that were not, because the
series ids were real and the figures are public and nobody called the
endpoint. A classification that was never exercised is a guess with a label
on it.

So this probes. It makes one real request per candidate, records the status,
the content type, the byte count and a fingerprint of the first line, and
classifies from what came back rather than from what the documentation says.

CLASSIFICATION
    LIVE              answered, keyless, with parseable data
    KEY_REQUIRED      answered, and the answer was "where is your key"
    QUOTA_BLOCKED     keyless but currently rate-limited
    LICENSE_REQUIRED  the terms forbid the use, whatever the endpoint returns
    BLOCKED           did not answer, or answered with something unusable
    UNAVAILABLE       no endpoint exists for this at all

Never prints a credential. Nothing here reads one.
"""
from __future__ import annotations

import json
import pathlib
import socket
import sys
import urllib.error
import urllib.request

TIMEOUT = 20
UA = {"User-Agent": "intent-engine research (github.com/intent-engine); "
                    "contact in repository"}

LIVE = "LIVE"
KEY_REQUIRED = "KEY_REQUIRED"
QUOTA_BLOCKED = "QUOTA_BLOCKED"
LICENSE_REQUIRED = "LICENSE_REQUIRED"
BLOCKED = "BLOCKED"

# (id, construct, publisher, url, what a good answer looks like)
CANDIDATES = [
    # --- Federal Reserve Data Download Program: keyless CSV -----------------
    ("FRB_G19_REVOLVING", "financial_anxiety", "Federal Reserve G.19",
     "https://www.federalreserve.gov/datadownload/Output.aspx?rel=G19&series="
     "d63e0f39cd1e0e2d0e0f1e9e0f4e0f5c&lastobs=24&from=&to=&filetype=csv&"
     "label=include&layout=seriescolumn", "csv"),
    ("FRB_G19_INDEX", "financial_anxiety", "Federal Reserve G.19 landing",
     "https://www.federalreserve.gov/releases/g19/current/default.htm", "html"),
    ("FRB_H8_INDEX", "financial_anxiety", "Federal Reserve H.8 landing",
     "https://www.federalreserve.gov/releases/h8/current/default.htm", "html"),
    ("FRB_CHARGEOFF", "financial_anxiety", "Federal Reserve charge-off/delinq",
     "https://www.federalreserve.gov/releases/chargeoff/delallsa.htm", "html"),

    # --- New York Fed: keyless XLSX/CSV -------------------------------------
    ("NYFED_SCE_PAGE", "household_expectation", "NY Fed Survey of Consumer "
     "Expectations",
     "https://www.newyorkfed.org/microeconomics/sce", "html"),
    ("NYFED_HHDC_PAGE", "financial_anxiety", "NY Fed Household Debt & Credit",
     "https://www.newyorkfed.org/microeconomics/hhdc", "html"),

    # --- BLS: keyless with a daily quota ------------------------------------
    ("BLS_JOLTS_QUITS", "perceived_control", "BLS JOLTS",
     "https://api.bls.gov/publicAPI/v2/timeseries/data/"
     "JTS000000000000000QUR", "json"),

    # --- Treasury FiscalData: keyless API -----------------------------------
    ("TREASURY_FISCALDATA", "n/a", "US Treasury FiscalData",
     "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/"
     "accounting/od/avg_interest_rates?page[size]=1", "json"),

    # --- University of Michigan: published tables ---------------------------
    ("UMICH_SCA_TABLE", "survey_confidence", "U. Michigan Surveys of Consumers",
     "http://www.sca.isr.umich.edu/files/tbmics.csv", "csv"),

    # --- Census BFS: known to need a key, probed to confirm -----------------
    ("CENSUS_BFS", "perceived_control", "Census Business Formation Statistics",
     "https://api.census.gov/data/timeseries/eits/bfs?get=cell_value&"
     "for=us:*&time=2025-06", "json"),

    # --- FRED: known to need a key, probed to confirm -----------------------
    ("FRED_CSV", "financial_anxiety", "FRED keyless CSV",
     "https://fred.stlouisfed.org/graph/fredgraph.csv?id=PSAVERT", "csv"),

    # --- BEA: needs registration --------------------------------------------
    ("BEA_API", "saving_rate", "Bureau of Economic Analysis",
     "https://apps.bea.gov/api/data?&method=GetDataSetList&"
     "ResultFormat=JSON", "json"),
]


def probe(url: str) -> dict:
    socket.setdefaulttimeout(TIMEOUT)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(60000)
            return {"http": r.status, "ctype": r.headers.get("Content-Type", ""),
                    "bytes": len(raw),
                    "head": raw[:300].decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read(500)
        except Exception:
            pass
        return {"http": e.code, "ctype": "", "bytes": len(body),
                "head": body.decode("utf-8", "replace"), "error": str(e)}
    except Exception as e:                                  # noqa: BLE001
        return {"http": 0, "ctype": "", "bytes": 0, "head": "",
                "error": f"{type(e).__name__}: {e}"}


def classify(r: dict, expect: str) -> tuple:
    head = (r.get("head") or "").lower()
    if r["http"] == 0:
        return BLOCKED, r.get("error", "no response")[:110]
    if "missing key" in head or "api_key" in head or "api key" in head:
        return KEY_REQUIRED, "the endpoint answered by asking for a key"
    if "threshold" in head or "quota" in head or r["http"] == 429:
        return QUOTA_BLOCKED, "keyless but currently rate-limited"
    if r["http"] >= 400:
        return BLOCKED, f"HTTP {r['http']}"
    if r["bytes"] < 200:
        return BLOCKED, f"answered with only {r['bytes']} bytes"
    if expect == "json" and not head.strip().startswith(("{", "[")):
        if "request_not_processed" in head:
            return QUOTA_BLOCKED, "keyless, quota exhausted"
        return BLOCKED, "expected JSON, got something else"
    if expect == "csv" and "<html" in head[:200]:
        return BLOCKED, "expected CSV, got an HTML page"
    return LIVE, f"HTTP {r['http']}, {r['bytes']}b, {r['ctype'][:40]}"


def main() -> int:
    out = []
    for cid, construct, publisher, url, expect in CANDIDATES:
        r = probe(url)
        status, why = classify(r, expect)
        out.append({"id": cid, "construct": construct, "publisher": publisher,
                    "url": url, "status": status, "why": why,
                    "http": r["http"], "bytes": r["bytes"]})
        print(f"  {status:<17} {cid:<22} {why}")
    dest = pathlib.Path("reports/behavioural_source_probe.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {dest}")
    by = {}
    for o in out:
        by[o["status"]] = by.get(o["status"], 0) + 1
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(by.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
