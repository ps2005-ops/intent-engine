"""§40/§41/§43: two clocks per analysis — CORE_READY and DEEP_READY.

WHY A SECOND HARNESS AND NOT A FLAG
-----------------------------------
Every previous measurement recorded ONE number: when the whole analysis
finished. That number is now the wrong one to hold the interactive SLO
against, because the product no longer makes the reader wait for the whole
analysis. Reporting it as though it were still the customer's wait would
understate a repair by exactly the size of the repair.

    CORE_READY   the first moment the analysis can be OPENED
    DEEP_READY   the moment the strategic reading has been merged in

DETECTING DEEP WITHOUT A NEW HEADER. `ResultState.DEEP_PENDING` renders a
distinctive sentence on the page — "the deeper strategic review is still
running". Its disappearance is DEEP_READY. This is read from the served page
rather than from a header the harness would have had to ask the product to
add, so the harness measures what a customer would actually see.

THE HARNESS MUST NOT BE THE LOAD. `/healthz` — sixteen characters, no work —
costs ~1.9s on this instance, and the analysis worker shares one CPU under
the GIL. Polling at 4s matches the progress page's own meta-refresh, so this
measures what a browser causes rather than what the harness causes.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://intent-engine-preview-bridge.onrender.com"
POLL_S = 4.0
PAGE_TIMEOUT = 90

#: The sentence ResultState.DEEP_PENDING renders. Its ABSENCE is DEEP_READY.
DEEP_PENDING_MARK = "deeper strategic review is still"

TIER1 = [
    ("Apple Inc.", "apple.com"), ("Microsoft", "microsoft.com"),
    ("NVIDIA", "nvidia.com"), ("Amazon", "amazon.com"),
    ("Alphabet", "abc.xyz"), ("Meta Platforms", "meta.com"),
    ("Walmart", "walmart.com"), ("JPMorgan Chase", "jpmorganchase.com"),
    ("Visa", "visa.com"), ("Caterpillar", "caterpillar.com"),
]
STRATEGIC = [
    ("Berkshire Hathaway", "berkshirehathaway.com"),
    ("Advanced Micro Devices", "amd.com"),
    ("Bank of America", "bankofamerica.com"),
    ("Deere & Company", "deere.com"),
    ("ServiceNow", "servicenow.com"), ("Starbucks", "starbucks.com"),
    ("Olo Inc", "olo.com"), ("Duolingo", "duolingo.com"),
]

#: THE 50-COMPANY QUALIFICATION COHORT, frozen before any of it was run.
#:
#: PREREGISTERED so the result cannot be improved after the fact by dropping
#: whichever companies did badly. The rule this enforces is simple and it is
#: the whole reason the list is in source control: a cohort chosen after
#: seeing results measures the chooser, not the product.
#:
#: SELECTED AGAINST THE ENGINE, NOT FOR IT. TIER1 and STRATEGIC above are
#: companies this codebase has already been developed against, so 40 of the
#: 50 below are new to it. Sector spread is deliberate: the engine reads
#: filings, and a bank, a miner and a software vendor do not write the same
#: filing. Coverage spread is deliberate too -- a few of these are thinly
#: covered on purpose, because a product that only works on mega-caps has not
#: generalised, it has memorised.
#:
#: Domains are the registrant's own primary site. Where a holding company
#: files under a different name than its consumer brand, the FILER is used,
#: because that is who the evidence is about.
QUALIFY_50 = [
    # --- semiconductors / hardware -------------------------------------
    ("NVIDIA", "nvidia.com"), ("Advanced Micro Devices", "amd.com"),
    ("Intel", "intel.com"), ("Texas Instruments", "ti.com"),
    ("Applied Materials", "appliedmaterials.com"),
    # --- software / cloud ----------------------------------------------
    ("Microsoft", "microsoft.com"), ("Oracle", "oracle.com"),
    ("Salesforce", "salesforce.com"), ("Adobe", "adobe.com"),
    ("ServiceNow", "servicenow.com"), ("Workday", "workday.com"),
    ("Datadog", "datadoghq.com"), ("Snowflake", "snowflake.com"),
    # --- platforms / consumer internet ---------------------------------
    ("Apple Inc.", "apple.com"), ("Alphabet", "abc.xyz"),
    ("Meta Platforms", "meta.com"), ("Amazon", "amazon.com"),
    ("Netflix", "netflix.com"), ("Uber Technologies", "uber.com"),
    ("Airbnb", "airbnb.com"),
    # --- payments / financials -----------------------------------------
    ("Visa", "visa.com"), ("Mastercard", "mastercard.com"),
    ("JPMorgan Chase", "jpmorganchase.com"),
    ("Bank of America", "bankofamerica.com"),
    ("Goldman Sachs", "goldmansachs.com"),
    ("American Express", "americanexpress.com"),
    ("Charles Schwab", "schwab.com"),
    # --- industrials / machinery / transport ----------------------------
    ("Caterpillar", "caterpillar.com"), ("Deere & Company", "deere.com"),
    ("Honeywell", "honeywell.com"), ("General Electric", "ge.com"),
    ("Union Pacific", "up.com"), ("FedEx", "fedex.com"),
    ("Boeing", "boeing.com"),
    # --- automotive -----------------------------------------------------
    ("Ford Motor", "ford.com"), ("General Motors", "gm.com"),
    # --- healthcare / pharma --------------------------------------------
    ("Johnson & Johnson", "jnj.com"), ("Pfizer", "pfizer.com"),
    ("UnitedHealth Group", "unitedhealthgroup.com"),
    ("Eli Lilly", "lilly.com"), ("Medtronic", "medtronic.com"),
    # --- consumer / retail ----------------------------------------------
    ("Walmart", "walmart.com"), ("Costco Wholesale", "costco.com"),
    ("Procter & Gamble", "pg.com"), ("Nike", "nike.com"),
    ("Starbucks", "starbucks.com"),
    # --- energy / materials ---------------------------------------------
    ("Exxon Mobil", "corporate.exxonmobil.com"),
    ("Chevron", "chevron.com"), ("Newmont", "newmont.com"),
    # --- thinner coverage, on purpose -----------------------------------
    ("Olo Inc", "olo.com"),
]


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler), jar


def _req(op, path, fields=None, timeout=PAGE_TIMEOUT):
    data = urllib.parse.urlencode(fields).encode() if fields else None
    headers = {"User-Agent": "progressive-matrix/1"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    began = time.monotonic()
    try:
        with op.open(req, timeout=timeout) as r:
            return (r.status, r.read().decode("utf-8", "replace"), r.geturl(),
                    time.monotonic() - began, dict(r.headers))
    except urllib.error.HTTPError as e:
        return (e.code, e.read().decode("utf-8", "replace"), BASE + path,
                time.monotonic() - began, dict(e.headers or {}))
    except Exception as e:                                   # noqa: BLE001
        return (0, f"{type(e).__name__}: {e}", BASE + path,
                time.monotonic() - began, {})


def visible(html: str) -> str:
    s = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", s).split())


def analyse(name, domain, *, budget_s, verbose=True) -> dict:
    op, _ = _opener()
    row = {"company": name, "domain": domain, "error": "",
           "core_ready_seconds": None, "deep_ready_seconds": None}

    st, entry, _u, _dt, _h = _req(op, "/demo")
    csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry)
    fields = {"consent": "on", "company_name": name,
              "website": f"https://{domain}"}
    if csrf:
        fields["csrf"] = csrf.group(1)

    began = time.monotonic()
    st, body, url, dt, _h = _req(op, "/analyze", fields)
    row["analyze_status"] = st
    if st == 429:
        row["status"] = "QUOTA_EXHAUSTED"
        row["error"] = visible(body)[:160]
        return row
    m = re.search(r"/runs/([A-Za-z0-9_-]+)", url) or \
        re.search(r"/runs/([A-Za-z0-9_-]+)", body)
    if not m:
        row["status"] = "NO_RUN"
        row["error"] = visible(body)[:240]
        return row
    run_id = row["run_id"] = m.group(1)

    # --- phase 1: wait for the analysis to become openable ----------------
    stages, last, unreachable = [], "", 0
    while time.monotonic() - began < budget_s:
        st, body, url, _d, _h = _req(op, f"/runs/{run_id}/progress",
                                     timeout=60)
        el = time.monotonic() - began
        if st == 0 or st >= 500:
            unreachable += 1
        text = visible(body)
        for lab in ("Confirming the company", "Recalling what we already",
                    "Reading current company evidence", "Reading the economic",
                    "Mapping competitors", "Stress-testing",
                    "Writing the decision"):
            i = text.lower().find(lab.lower())
            if i >= 0 and "working" in text[i:i + len(lab) + 40].lower():
                if lab != last:
                    stages.append({"stage": lab, "at_s": round(el, 1)})
                    last = lab
                break
        if "/progress" not in url and st == 200:
            row["core_ready_seconds"] = round(el, 1)
            break
        time.sleep(POLL_S)
    row["stages"] = stages
    row["progress_unreachable_polls"] = unreachable

    # --- phase 2: wait for the deep reading to be merged in ---------------
    #
    # THE ABSENCE OF A PHRASE IS ONLY EVIDENCE IF THE PHRASE CAN APPEAR.
    # `result_state_detail` renders on the brief, and only when no key
    # insight cleared the bar. If the marker never shows up at all, "marker
    # absent" means the instrument is looking in the wrong place — not that
    # the deep reading landed. That would report a false pass on the one
    # number this run exists to measure, so it is recorded as
    # MARKER_NEVER_SEEN and `deep_ready_seconds` stays None.
    row["deep_detection"] = "MARKER_NEVER_SEEN"
    if row["core_ready_seconds"] is not None:
        while time.monotonic() - began < budget_s:
            st, body, _u, _d, _h = _req(op, f"/runs/{run_id}/brief",
                                        timeout=60)
            el = time.monotonic() - began
            if st != 200 or len(body) < 2000:
                time.sleep(POLL_S)
                continue
            pending = DEEP_PENDING_MARK in visible(body).lower()
            if pending:
                row["deep_detection"] = "PENDING_SEEN"
            elif row["deep_detection"] == "PENDING_SEEN":
                # Seen, then gone: the deep reading was merged in.
                row["deep_ready_seconds"] = round(el, 1)
                row["deep_detection"] = "MERGED"
                break
            else:
                # Never pending on the first look. Either deep finished
                # before the first poll, or the marker does not render here.
                # Distinguished by whether a strategic reading is present.
                row["deep_detection"] = "NO_PENDING_ON_FIRST_POLL"
                break
            time.sleep(POLL_S)

    # --- canonical timings, read from the product ------------------------
    #
    # WHAT CHANGED AND WHY. `core_open_seconds` below is what every previous
    # number in this project was: the wall-clock moment the progress page
    # stopped redirecting, at 4s poll granularity -- 13% of a 30s budget --
    # over a network, from a harness. It is a real UX fact and it is kept as
    # one. It is not the latency the SLO is written against.
    #
    # `core_ready_seconds` now comes from `ci.lifecycle_marked`, recorded
    # inside the worker at the instant the core became openable. Same for the
    # evidence count, which is now the number of retrieved documents rather
    # than a regex for `https?://` over the rendered HTML -- a counter that
    # reported 0 for six of six companies because this product cites evidence
    # through internal routes and emits no absolute href at all.
    st, body, _u, _d, _h = _req(op, f"/runs/{run_id}/timing", timeout=60)
    canonical = {}
    if st == 200:
        try:
            canonical = json.loads(body)
        except ValueError:
            canonical = {}
    row["core_open_seconds"] = row.get("core_ready_seconds")
    if canonical.get("core_latency_s") is not None:
        row["core_ready_seconds"] = canonical["core_latency_s"]
        row["metric_source"] = canonical.get("provenance", {})
    else:
        row["metric_source"] = {"core_ready_seconds": "ui_redirect_fallback"}
    if canonical.get("deep_latency_s") is not None:
        row["deep_ready_seconds"] = canonical["deep_latency_s"]
    row["canonical_evidence_count"] = canonical.get("evidence_count")
    row["canonical_result_state"] = canonical.get("result_state")
    # A REPORT, OR NOT. `result_state` is set on every composed CORE payload,
    # so its absence means nothing was composed -- which is what a warm run
    # looked like when it skipped identity resolution and came back 48%
    # faster having produced no analysis at all. A cohort that reports only
    # latency cannot see that; this column is why it now can.
    row["has_report"] = canonical.get("result_state") is not None
    # WHERE THE ACQUISITION TIME WENT, per company, so a cohort can be ranked
    # by measured bucket instead of by impression.
    _spans = {}
    for _ph in (canonical.get("trace") or []):
        for _sp in (_ph.get("spans") or []):
            _spans[_sp["name"]] = _sp
    for _name, _key in (("discovery", "discovery_ms"),
                        ("retrieval", "retrieval_ms"),
                        ("core_composition", "composition_ms")):
        row[_key] = (_spans.get(_name) or {}).get("wall_ms")
    _obs = _spans.get("derive_observations") or {}
    row["documents"] = _obs.get("documents")
    row["text_chars"] = _obs.get("text_chars")
    row["observations"] = _obs.get("item_count")
    # WARM or COLD, read from the run rather than assumed from ordering: a
    # snapshot that failed to load silently would otherwise look like a cold
    # run that happened to be slow.
    row["snapshot_mode"] = ("WARM" if (row.get("discovery_ms") or 1e9) < 2000
                            else "COLD")

    pages, citations = {}, 0
    for suffix in ("", "/brief"):
        st, body, url, dt, h = _req(op, f"/runs/{run_id}{suffix}", timeout=120)
        text = visible(body)
        if suffix == "":
            # §4: the core must cite the evidence it rests on, so the count
            # comes from the page the reader opens. Counted on the RAW body
            # because the hrefs are attributes and `visible()` strips them.
            #
            # COUNTED ON THE LINK THIS PAGE ACTUALLY EMITS. This matched
            # `https?://` and reported 0 for all six Tier-1 companies -- not
            # because nothing was cited, but because the report cites evidence
            # through INTERNAL routes (`/runs/<id>/evidence/<claim>`) and the
            # rendered HTML contains no absolute href at all. A counter that
            # cannot return anything but zero is not a measurement, and six
            # identical zeros is what gave it away: a real per-company
            # evidence problem would scatter.
            citations = len(set(
                re.findall(r"/runs/[A-Za-z0-9_-]+/evidence/[^\s\"'<>]+", body)
            )) + len(set(re.findall(r"https?://[^\s\"'<>]+", body)))
        pages[suffix] = {"status": st, "chars": len(body),
                         "seconds": round(dt, 1),
                         "deep_pending": DEEP_PENDING_MARK in text.lower(),
                         "outcome": h.get("X-Analysis-Outcome", "")}
    row["pages"] = pages
    row["evidence_citations"] = citations

    readable = max((p["chars"] for p in pages.values()), default=0)
    if row["core_ready_seconds"] is not None:
        row["status"] = ("COMPLETE" if row["deep_ready_seconds"] is not None
                         else "CORE_READY_DEEP_PENDING")
    elif readable > 4000:
        row["status"] = "COMPLETE_LATE"
        row["core_ready_seconds"] = round(time.monotonic() - began, 1)
    else:
        row["status"] = "NO_RESULT"
    row["total_seconds"] = round(time.monotonic() - began, 1)
    if verbose:
        print(f"  {name:<22}{row['status']:<26}"
              f"core={str(row['core_ready_seconds']):>7}s  "
              f"deep={str(row['deep_ready_seconds']):>7}s  "
              f"unreachable={unreachable}")
    return row


def pct(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return round(vals[min(len(vals) - 1,
                          int(round(p / 100 * (len(vals) - 1))))], 1)


def summarise(rows) -> dict:
    counted = [r for r in rows
               if r.get("status") not in ("QUOTA_EXHAUSTED", "NO_RUN")]
    core = [r["core_ready_seconds"] for r in counted]
    deep = [r["deep_ready_seconds"] for r in counted]
    return {
        "attempted": len(rows), "counted": len(counted),
        "refused": len(rows) - len(counted),
        "core_success": sum(1 for r in counted
                            if r.get("core_ready_seconds") is not None),
        "deep_success": sum(1 for r in counted
                            if r.get("deep_ready_seconds") is not None),
        "no_result": sum(1 for r in counted if r["status"] == "NO_RESULT"),
        "core_p50": pct(core, 50), "core_p90": pct(core, 90),
        "core_max": pct(core, 100),
        "deep_p50": pct(deep, 50), "deep_p90": pct(deep, 90),
        "deep_max": pct(deep, 100),
        "core_over_60s": [r["company"] for r in counted
                          if (r.get("core_ready_seconds") or 0) > 60],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", choices=("tier1", "strategic", "qualify50"),
                    default="tier1")
    ap.add_argument("--only", default="")
    ap.add_argument("--slice", default="")
    ap.add_argument("--budget", type=float, default=420.0)
    ap.add_argument("--out", default="reports/perf/progressive_matrix.json")
    a = ap.parse_args()

    cohort = {"tier1": TIER1, "strategic": STRATEGIC,
              "qualify50": QUALIFY_50}[a.cohort]
    if a.only:
        cohort = [c for c in cohort if a.only.lower() in c[0].lower()]
    if a.slice:
        lo, hi = (int(x) if x else None for x in a.slice.split(":"))
        cohort = cohort[lo:hi]

    op, _ = _opener()
    st, ver, _u, dt, _h = _req(op, "/version", timeout=120)
    print(f"deployed: {ver.strip()[:120]}  (warm-up {dt:.1f}s)")
    print(f"cohort={a.cohort} n={len(cohort)} budget={a.budget}s\n")

    rows = []
    for name, domain in cohort:
        row = analyse(name, domain, budget_s=a.budget)
        rows.append(row)
        if row.get("status") == "QUOTA_EXHAUSTED":
            print("  ! demo quota exhausted — stopping")
            break

    report = {"base": BASE, "cohort": a.cohort, "version": ver.strip(),
              "summary": summarise(rows), "rows": rows}
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print("\n" + json.dumps(report["summary"], indent=2))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
