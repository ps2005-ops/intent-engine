"""§43/§46/§52/§53: the DEPLOYED service, timed at one-second resolution.

WHY NOT `scripts/live_econ_matrix.py`
-------------------------------------
That harness answers "did the deployed product say the right thing". This one
answers "how long did the customer wait", and the difference matters: it polls
every 15 seconds, so against a 30-second target its own instrument granularity
is half the budget. Every number it produced would be a multiple of 15.

WHAT IS MEASURED, AND WHY EACH IS SEPARATE
------------------------------------------
    core_ready_seconds   first moment a usable analysis could be OPENED
    complete_seconds     the run reached a terminal state
    total_seconds        everything, including reading the surfaces

§53: a slow request and a refused one are different findings and get different
statuses. QUOTA_EXHAUSTED (429 from our own demo cap), RATE_LIMITED (a provider
or edge 429/503), COLD_START (the first request to an idle free instance, which
costs ~30s of container boot and is not analysis time), and SLOW are never
counted together. Conflating them reports an infrastructure limit as a product
defect, which sends the next session looking for the wrong thing.

THE QUOTA IS THE BUDGET: ten analyses per client IP per rolling hour. A wave
is at most ten companies, every request is logged before the next is made, and
the run stops on the first demo 429 rather than spending what is left proving
the same thing twice.

THE HARNESS MUST NOT SEND LESS THAN THE FORM DOES. `/demo` first, its CSRF
token carried. Posting straight to `/analyze` also works — the router mints an
anonymous session and skips the gate for exactly that case — but it is not
what a browser does, and a harness that dodges the gate is bypassing the
customer flow rather than testing it.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://intent-engine-preview-bridge.onrender.com"
OUT = pathlib.Path("reports/perf/live_matrix.json")

#: §41. Tier 1: well-known, high-coverage public companies — the ones an
#: executive types in first and the ones the 30s target is written for.
TIER1 = [
    ("Apple Inc.", "apple.com"),            # the named regression case
    ("Microsoft", "microsoft.com"),
    ("NVIDIA", "nvidia.com"),
    ("Amazon", "amazon.com"),
    ("Alphabet", "abc.xyz"),
    ("Meta Platforms", "meta.com"),
    ("Walmart", "walmart.com"),
    ("JPMorgan Chase", "jpmorganchase.com"),
    ("Visa", "visa.com"),
    ("Caterpillar", "caterpillar.com"),
]

#: §44. A smaller deep cohort standing in for the strategic 100 — spread
#: across business-model classes, deliberately including sparse evidence and
#: an unusual model, so the tier-2 budget is tested where it is hard.
TIER2 = [
    ("Berkshire Hathaway", "berkshirehathaway.com"),   # conglomerate
    ("Advanced Micro Devices", "amd.com"),             # semiconductor
    ("Bank of America", "bankofamerica.com"),          # financial
    ("Deere & Company", "deere.com"),                  # industrial
    ("ServiceNow", "servicenow.com"),                  # enterprise software
    ("Starbucks", "starbucks.com"),                    # consumer
    ("Olo Inc", "olo.com"),                            # sparse evidence
    ("Duolingo", "duolingo.com"),                      # unusual model
]

POLL_S = 1.0
PAGE_TIMEOUT = 90


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler), jar


def _req(op, path, fields=None, timeout=PAGE_TIMEOUT):
    data = urllib.parse.urlencode(fields).encode() if fields else None
    headers = {"User-Agent": "perf-matrix/1"}
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


def warm_up(op) -> dict:
    """§53. Pay the free instance's container boot BEFORE the clock starts.

    A free Render instance that has been idle spends ~30s waking up. Charging
    that to the first company would make it the slowest in every matrix and
    would be a measurement of Render's billing tier, not of the analysis.
    """
    st, _b, _u, dt, _h = _req(op, "/version", timeout=120)
    return {"status": st, "seconds": round(dt, 1),
            "cold_start": dt > 5.0}


def analyse(name, domain, *, budget_s, verbose=True) -> dict:
    op, _jar = _opener()
    row = {"company": name, "domain": domain, "requests": [],
           "bounded_gaps": [], "error": ""}

    st, entry, _u, dt, _h = _req(op, "/demo")
    row["requests"].append({"path": "/demo", "status": st,
                            "seconds": round(dt, 2)})
    m_csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry)
    fields = {"consent": "on", "company_name": name,
              "website": f"https://{domain}"}
    if m_csrf:
        fields["csrf"] = m_csrf.group(1)

    began = time.monotonic()
    st, body, url, dt, _h = _req(op, "/analyze", fields)
    row["requests"].append({"path": "/analyze", "status": st,
                            "seconds": round(dt, 2), "landed": url})
    if st == 429:
        row["status"] = "QUOTA_EXHAUSTED"
        row["error"] = visible(body)[:200]
        return row
    m = re.search(r"/runs/([A-Za-z0-9_-]+)", url) or \
        re.search(r"/runs/([A-Za-z0-9_-]+)", body)
    if not m:
        row["status"] = "NO_RUN"
        row["error"] = visible(body)[:300]
        return row
    run_id = row["run_id"] = m.group(1)

    # --- the poll, at one-second resolution --------------------------------
    core_ready = complete = None
    poll_timings = []
    outcome = ""
    stages_seen = []
    last_stage = ""
    polls = 0
    while time.monotonic() - began < budget_s:
        st, body, url, _dt, headers = _req(op, f"/runs/{run_id}/progress",
                                           timeout=30)
        polls += 1
        elapsed = time.monotonic() - began
        outcome = headers.get("X-Analysis-Outcome", outcome)
        # §6/§31. THE HANDLER MEASURES ITSELF, so a slow poll can be split
        # into work this handler did and time it merely waited for. On the
        # free instance the two have completely different repairs: a slow
        # segment is our code, and a large `unaccounted` is the analysis
        # worker holding the one CPU share this container gets.
        timing = headers.get("X-Request-Timing", "")
        if timing:
            poll_timings.append({"at_s": round(elapsed, 1),
                                 "client_s": round(_dt, 2),
                                 "server": timing})
        text = visible(body)
        # WHICH RUNG THE LADDER IS ON, so a stall can be attributed to a
        # stage instead of reported as a total.
        rung = ""
        for label in ("Confirming the company", "Recalling what we already",
                      "Reading current company evidence",
                      "Reading the economic", "Mapping competitors",
                      "Stress-testing", "Writing the decision"):
            if label.lower() in text.lower():
                idx = text.lower().index(label.lower())
                if "working" in text[idx:idx + len(label) + 40].lower():
                    rung = label
                    break
        if rung and rung != last_stage:
            stages_seen.append({"stage": rung, "at_s": round(elapsed, 1)})
            last_stage = rung
        # A REDIRECT OFF THE PROGRESS PAGE IS THE PRODUCT SAYING "OPEN IT".
        if "/progress" not in url and st == 200:
            core_ready = core_ready or round(elapsed, 1)
            complete = round(elapsed, 1)
            break
        if st == 429:
            row["status"] = "RATE_LIMITED"
            row["error"] = visible(body)[:200]
            return row
        if st >= 500 or st == 0:
            row["error"] = f"progress {st}: {visible(body)[:160]}"
        time.sleep(POLL_S)

    total_wait = round(time.monotonic() - began, 1)
    row["core_ready_seconds"] = core_ready
    row["complete_seconds"] = complete
    row["stages"] = stages_seen
    row["polls"] = polls
    row["poll_timings"] = poll_timings[:12]
    if poll_timings:
        client = [t["client_s"] for t in poll_timings]
        row["poll_seconds_median"] = round(statistics.median(client), 2)
        row["poll_seconds_max"] = round(max(client), 2)
    row["slowest_stage"] = max(
        ({"stage": s["stage"],
          "seconds": round((stages_seen[i + 1]["at_s"] if i + 1 < len(stages_seen)
                            else total_wait) - s["at_s"], 1)}
         for i, s in enumerate(stages_seen)),
        key=lambda d: d["seconds"], default={}) or {}

    # --- read the result surfaces ------------------------------------------
    pages = {}
    for suffix in ("", "/brief"):
        st, body, url, dt, headers = _req(op, f"/runs/{run_id}{suffix}")
        pages[suffix] = {"status": st, "chars": len(body),
                         "seconds": round(dt, 2),
                         "outcome": headers.get("X-Analysis-Outcome", "")}
        row["requests"].append({"path": f"/runs/{run_id}{suffix}",
                                "status": st, "seconds": round(dt, 2),
                                "chars": len(body)})
        text = visible(body)
        if suffix == "":
            row["evidence_count"] = len(re.findall(r"sec\.gov|https?://", body))
            row["economic_context"] = ("Economic impact" in body
                                       or "economic" in text.lower()[:6000])
            for phrase in ("could not be reached", "not requested",
                           "budget", "unavailable"):
                if phrase in text.lower():
                    row["bounded_gaps"].append(phrase)
    row["pages"] = pages
    row["outcome_header"] = outcome or pages.get("", {}).get("outcome", "")

    readable = max((p["chars"] for p in pages.values()), default=0)
    if core_ready is not None:
        row["status"] = "COMPLETE"
    elif readable > 4000:
        # §22: the poll stopped waiting but the product had an answer. That
        # is a slow page, not a failed analysis, and calling it a failure
        # reports a product defect where there was none.
        row["status"] = "COMPLETE_LATE"
        row["core_ready_seconds"] = total_wait
    else:
        row["status"] = "NO_RESULT"
    row["total_seconds"] = total_wait
    row["cache_state"] = "warm" if row.get("_warm") else "cold"
    if verbose:
        cr = row.get("core_ready_seconds")
        print(f"  {name:<22}{row['status']:<15}"
              f"core={cr if cr is not None else '-':>6}s  "
              f"total={total_wait:>6}s  "
              f"slowest={row['slowest_stage'].get('stage', '-')[:34]}")
    return row


def summarise(rows) -> dict:
    timed = [r["core_ready_seconds"] for r in rows
             if r.get("core_ready_seconds") is not None]
    timed.sort()

    def pct(p):
        if not timed:
            return None
        k = min(len(timed) - 1, int(round((p / 100) * (len(timed) - 1))))
        return round(timed[k], 1)

    counted = [r for r in rows if r["status"] not in
               ("QUOTA_EXHAUSTED", "RATE_LIMITED")]
    ok = [r for r in counted if r["status"] in ("COMPLETE", "COMPLETE_LATE")]
    return {
        "attempted": len(rows),
        # §43/§53: refusals leave the denominator because they measure our
        # quota, not the product. They are reported separately, never hidden.
        "counted": len(counted),
        "refused": len(rows) - len(counted),
        "succeeded": len(ok),
        "success_rate": (round(len(ok) / len(counted), 3) if counted else None),
        "p50": pct(50), "p90": pct(90), "p95": pct(95),
        "max": round(max(timed), 1) if timed else None,
        "over_60s": [r["company"] for r in counted
                     if (r.get("core_ready_seconds") or 0) > 60],
        "no_result": [r["company"] for r in counted
                      if r["status"] == "NO_RESULT"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", choices=("tier1", "tier2"), default="tier1")
    ap.add_argument("--budget", type=float, default=180.0,
                    help="seconds to wait before recording NO_RESULT")
    ap.add_argument("--slice", default="",
                    help="a:b — run only companies [a:b) of the cohort")
    ap.add_argument("--only", default="", help="one company name substring")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--warm", action="store_true",
                    help="label this wave as a warm-cache repeat")
    a = ap.parse_args()

    cohort = TIER1 if a.cohort == "tier1" else TIER2
    if a.only:
        cohort = [c for c in cohort if a.only.lower() in c[0].lower()]
    if a.slice:
        lo, hi = (int(x) if x else None for x in a.slice.split(":"))
        cohort = cohort[lo:hi]

    op, _ = _opener()
    boot = warm_up(op)
    print(f"instance: {boot}  cohort={a.cohort} n={len(cohort)} "
          f"budget={a.budget}s cache={'warm' if a.warm else 'cold'}")

    rows = []
    for name, domain in cohort:
        row = analyse(name, domain, budget_s=a.budget)
        row["_warm"] = a.warm
        row["cache_state"] = "warm" if a.warm else "cold"
        rows.append(row)
        if row["status"] == "QUOTA_EXHAUSTED":
            print("  ! demo quota exhausted — stopping rather than "
                  "spending the rest of the hour proving it again")
            break

    report = {"base": BASE, "cohort": a.cohort,
              "cache_state": "warm" if a.warm else "cold",
              "instance": boot, "summary": summarise(rows), "rows": rows}
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print("\n" + json.dumps(report["summary"], indent=2))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
