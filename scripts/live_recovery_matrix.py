"""Live matrix: did the acquisition repair recover previously-abstaining runs?

MEASURES THE TWO THINGS THE PREVIOUS CYCLE COULD NOT SETTLE.

1. SUBMISSION LATENCY, on its own clock. `POST /analyze` schedules the work
   and redirects; it must therefore be bounded and independent of analysis
   latency. One company in the last cohort returned `analyze_status: 0` -- a
   client-side read timeout at 90s -- and the run was recorded as having no
   observed terminal state. A client timeout is not proof the server hung, so
   this records the submit duration for EVERY company and never cuts it off
   early enough to have to guess.

2. WHAT THE RUN ACTUALLY HELD. `/runs/<id>/telemetry` now carries source
   health, evidence-role coverage and one classified abstention reason, so a
   bounded abstention can be attributed to a rate limit, a refusal, a spent
   budget or genuinely thin evidence instead of all four at once.
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
#: DELIBERATELY LONGER THAN THE SUBMIT COULD PLAUSIBLY TAKE. The point is to
#: MEASURE submission latency, and a client cutoff shorter than the server's
#: worst case turns a measurement into an unanswerable question.
SUBMIT_TIMEOUT = 300
PAGE_TIMEOUT = 90
DEEP_PENDING_MARK = "deeper strategic review is still"

#: The companies that took the bounded-abstention path in the 50-company
#: requalification on `142ae2c6`, plus controls that produced full reports.
PRIOR_ABSTAINED = [
    ("Goldman Sachs", "goldmansachs.com"), ("Caterpillar", "caterpillar.com"),
    ("Ford Motor", "ford.com"), ("Johnson & Johnson", "jnj.com"),
    ("Eli Lilly", "lilly.com"), ("Deere & Company", "deere.com"),
    ("Netflix", "netflix.com"), ("Chevron", "chevron.com"),
]
CONTROLS = [
    ("NVIDIA", "nvidia.com"), ("Meta Platforms", "meta.com"),
]


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler), jar


def _req(op, path, fields=None, timeout=PAGE_TIMEOUT):
    data = urllib.parse.urlencode(fields).encode() if fields else None
    headers = {"User-Agent": "recovery-matrix/1"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    began = time.monotonic()
    try:
        with op.open(req, timeout=timeout) as r:
            return (r.status, r.read().decode("utf-8", "replace"), r.geturl(),
                    time.monotonic() - began)
    except urllib.error.HTTPError as e:
        return (e.code, e.read().decode("utf-8", "replace"), BASE + path,
                time.monotonic() - began)
    except Exception as e:                                   # noqa: BLE001
        return (0, f"{type(e).__name__}: {e}", BASE + path,
                time.monotonic() - began)


def visible(html: str) -> str:
    s = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", s).split())


ABSTAIN_MARKS = (
    "rather than show a briefing that looks complete",
    "did not add enough independent evidence",
    "could not be retrieved",
    "not enough public evidence",
)


def analyse(name, domain, *, budget_s) -> dict:
    op, _ = _opener()
    row = {"company": name, "domain": domain, "error": "",
           "submit_s": None, "core_open_s": None, "outcome": "",
           "documents": None, "roles_filled": None, "abstention": ""}
    st, entry, _u, _d = _req(op, "/demo")
    csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry)
    fields = {"consent": "on", "company_name": name,
              "website": f"https://{domain}"}
    if csrf:
        fields["csrf"] = csrf.group(1)

    began = time.monotonic()
    st, body, url, submit_s = _req(op, "/analyze", fields,
                                   timeout=SUBMIT_TIMEOUT)
    row["submit_s"] = round(submit_s, 2)
    row["analyze_status"] = st
    if st == 429:
        row["outcome"] = "QUOTA_EXHAUSTED"
        row["error"] = visible(body)[:140]
        return row
    if st == 503:
        row["outcome"] = "CAPACITY_REFUSED"
        row["error"] = visible(body)[:140]
        return row
    m = re.search(r"/runs/([A-Za-z0-9_-]+)", url) or \
        re.search(r"/runs/([A-Za-z0-9_-]+)", body)
    if not m:
        row["outcome"] = "NO_RUN"
        row["error"] = visible(body)[:200]
        return row
    run_id = row["run_id"] = m.group(1)

    while time.monotonic() - began < budget_s:
        st, body, url, _d = _req(op, f"/runs/{run_id}/progress", timeout=60)
        if "/progress" not in url and st == 200:
            row["core_open_s"] = round(time.monotonic() - began, 1)
            break
        time.sleep(POLL_S)
    if row["core_open_s"] is None:
        row["outcome"] = "NO_TERMINAL_OBSERVED"
        return row

    st, brief, _u, _d = _req(op, f"/runs/{run_id}/brief", timeout=90)
    text = visible(brief).lower()
    row["brief_chars"] = len(brief)
    row["outcome"] = ("BOUNDED_ABSTENTION"
                      if any(mark in text for mark in ABSTAIN_MARKS)
                      else "USABLE_REPORT")
    st, tel, _u, _d = _req(op, f"/runs/{run_id}/telemetry", timeout=60)
    if st == 200:
        try:
            data = json.loads(tel)
            row["telemetry"] = data
            roles = (data.get("evidence_roles") or {})
            row["documents"] = roles.get("documents")
            row["roles_filled"] = roles.get("filled")
            row["roles_missing"] = roles.get("missing")
            row["abstention"] = (data.get("abstention") or {}).get("reason", "")
            row["sources"] = data.get("sources")
        except Exception:                                    # noqa: BLE001
            row["telemetry_error"] = tel[:160]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="abstained",
                    choices=("abstained", "controls", "all"))
    ap.add_argument("--budget", type=float, default=240.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pairs = {"abstained": PRIOR_ABSTAINED, "controls": CONTROLS,
             "all": PRIOR_ABSTAINED + CONTROLS}[args.set]
    if args.limit:
        pairs = pairs[:args.limit]
    rows = []
    print(f"live matrix: {len(pairs)} companies against {BASE}\n")
    print(f"{'company':<24}{'submit':>8}{'core':>8}  outcome")
    for name, domain in pairs:
        row = analyse(name, domain, budget_s=args.budget)
        rows.append(row)
        print(f"{name[:23]:<24}{str(row['submit_s']):>8}"
              f"{str(row['core_open_s']):>8}  {row['outcome']:<20}"
              f" docs={row.get('documents')} {row.get('abstention','')}"
              f" {row['error'][:60]}", flush=True)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), "utf-8")
    usable = sum(1 for r in rows if r["outcome"] == "USABLE_REPORT")
    abstain = sum(1 for r in rows if r["outcome"] == "BOUNDED_ABSTENTION")
    submits = [r["submit_s"] for r in rows if r["submit_s"] is not None]
    print(f"\n  usable {usable}/{len(rows)}   bounded abstention {abstain}")
    if submits:
        print(f"  submit latency  max {max(submits)}s  "
              f"median {sorted(submits)[len(submits)//2]}s")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
