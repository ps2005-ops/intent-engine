#!/usr/bin/env python3
"""PRE-100 live qualification against the DEPLOYED service.

ONE SESSION PER COMPANY, HELD OPEN. `perf_progressive_matrix.analyse` builds
its opener and drops it, which is correct for latency and useless for Q&A:
`/runs/<id>/conversation` checks run ownership, so a second anonymous session
cannot ask anything about the run the first one created. Everything here --
submit, poll, timing, report surfaces, Q&A -- runs on one cookie jar.

WHAT IS RECORDED, beyond latency (§26):

    blocking / deferred / final documents   the minimum-evidence CORE claim
    ci.analysis_updated                     deferred evidence moved the answer
    live Q&A through the canonical route    with follow-ups
    provenance + identity on the report     read from the rendered page
    unaccounted wall as a share of CORE     §3 accounting

THRESHOLDS ARE FROZEN (§7) and are read, never written, by this file.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from perf_progressive_matrix import (                       # noqa: E402
    POLL_S, QUALIFY_50, TIER1, _opener, _req, visible,
)

TIER_A = (45.0, 60.0)
TIER_B = (60.0, 90.0)
TIER_C = (75.0, 100.0)
TERMINAL_CONTRACT_S = 120.0

QUESTIONS = (
    "Why does this matter for this company?",
    "What evidence most supports this recommendation?",
    "What would have to be true for this recommendation to be wrong?",
    "What should management monitor next?",
    "What is the biggest uncertainty?",
)
FOLLOW_UP = "Which of those would you watch first, and why that one?"

DEEP_PENDING_MARK = "the strategic reading is still being written"


def _pct(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 1)


def _csrf(html):
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html or "")
    return m.group(1) if m else ""


def _own_time(trace):
    """Top-level spans only: children are a breakdown OF a parent."""
    out = {}
    for phase in (trace or []):
        for span in (phase.get("spans") or []):
            if int(span.get("depth", 0) or 0) == 0:
                out[span.get("name", "?")] = span
    return out


def qualify(name, domain, *, budget_s=300.0, with_qa=False) -> dict:
    op, _jar = _opener()
    row = {"company": name, "domain": domain, "status": "", "error": "",
           "core_ready_seconds": None, "usable_seconds": None,
           "qa": [], "questions_ok": 0}

    st, entry, _u, _d, _h = _req(op, "/demo")
    csrf = _csrf(entry)
    began = time.monotonic()
    st, body, url, _d, _h = _req(
        op, "/analyze", {"consent": "on", "company_name": name,
                         "website": f"https://{domain}", "csrf": csrf})
    row["analyze_status"] = st
    if st == 429:
        row["status"] = "QUOTA_EXHAUSTED"
        text = visible(body)
        row["error"] = text[:160]
        # THE SERVICE STATES ITS OWN WINDOW. Guessing a retry interval that is
        # slightly too short spends an attempt AND keeps the window full:
        # measured, a 7-minute retry against a stated 9-minute window waited
        # sixteen times without landing once.
        m = re.search(r"try again in about (\d+) minute", text)
        row["retry_after_s"] = (int(m.group(1)) + 1) * 60.0 if m else None
        return row
    m = (re.search(r"/runs/([A-Za-z0-9_-]+)", url)
         or re.search(r"/runs/([A-Za-z0-9_-]+)", body))
    if not m:
        row["status"] = "NO_RUN"
        row["error"] = visible(body)[:240]
        return row
    run_id = row["run_id"] = m.group(1)

    # --- wait for a TERMINAL outcome, which is not only a redirect --------
    #
    # A REDIRECT IS ONE OF TWO TERMINAL OUTCOMES, and treating it as the only
    # one reports correct product behaviour as a failure. MEASURED: Netflix
    # retrieved zero sources, reached `run_state: FAILED`, and rendered a
    # 7,507-character bounded-abstention page -- and this harness recorded
    # NO_RESULT because the progress page answered in place instead of
    # redirecting away. A defensible refusal is a product outcome; only an
    # endless spinner is a failure.
    terminal_states = ("COMPLETE", "PARTIAL", "FAILED", "REJECTED",
                       "INTERRUPTED")
    polls = 0
    while time.monotonic() - began < budget_s:
        st, page, url, _d, _h = _req(op, f"/runs/{run_id}/progress",
                                     timeout=90)
        elapsed = time.monotonic() - began
        polls += 1
        if "/progress" not in url and st == 200:
            row["usable_seconds"] = round(elapsed, 1)
            row["outcome"] = "USABLE_REPORT"
            break
        # Every few polls, ask the run itself whether it is still working.
        if polls % 3 == 0:
            st2, tb, _u, _d, _h = _req(op, f"/runs/{run_id}/timing",
                                       timeout=60)
            if st2 == 200:
                try:
                    snap = json.loads(tb)
                except ValueError:
                    snap = {}
                if snap.get("run_state") in terminal_states \
                        and snap.get("result_state") is None \
                        and not snap.get("evidence_count"):
                    row["usable_seconds"] = round(elapsed, 1)
                    row["outcome"] = "BOUNDED_ABSTENTION"
                    row["abstention_reason"] = snap.get("run_state")
                    break
        time.sleep(POLL_S)
    row.setdefault("outcome", "NO_RESULT")
    row["terminal_within_contract"] = bool(
        row["usable_seconds"] is not None
        and row["usable_seconds"] <= TERMINAL_CONTRACT_S)

    # --- canonical timing, retried until the trace lands ------------------
    # PATIENCE, BECAUSE THE MISSING ROWS ARE THE SLOW ONES. The lifecycle
    # marker and the trace are written by the worker AFTER the page opens, so
    # a short poll drops exactly the runs whose latency is worth reading --
    # and the resulting percentiles describe only the fast half. Measured: 3
    # of 10 and then 3 of 5 rows came back with `core_latency_s: None`, every
    # one of them a slower run.
    #
    # The loop now waits for the MARKER, not only for spans, and gives the
    # worker a real chance to finish its continuation and deep pass before
    # giving up. A row that still has no marker is reported as missing rather
    # than silently excluded.
    canonical = {}
    for attempt in range(40):
        st, tbody, _u, _d, _h = _req(op, f"/runs/{run_id}/timing", timeout=90)
        if st == 200:
            try:
                canonical = json.loads(tbody)
            except ValueError:
                canonical = {}
        has_marker = canonical.get("core_latency_s") is not None
        has_spans = any((ph.get("spans") or [])
                        for ph in (canonical.get("trace") or []))
        if has_marker and has_spans:
            break
        if has_marker and attempt > 12:
            break                       # marker is what the gate is read from
        time.sleep(4.0)
    row["timing_polls"] = attempt + 1
    row["core_ready_seconds"] = canonical.get("core_latency_s")
    row["deep_ready_seconds"] = canonical.get("deep_latency_s")
    row["result_state"] = canonical.get("result_state")
    row["run_state"] = canonical.get("run_state")
    row["final_documents"] = canonical.get("evidence_count")
    row["deep_status"] = canonical.get("deep_status")
    row["has_report"] = canonical.get("result_state") is not None

    spans = _own_time(canonical.get("trace"))
    for label in ("discovery", "retrieval", "core_composition",
                  "source_selection", "deferred_acquisition"):
        span = spans.get(label) or {}
        row[f"{label}_ms"] = span.get("wall_ms")
        row[f"{label}_cpu_ms"] = span.get("cpu_ms")
    retrieval = spans.get("retrieval") or {}
    row["blocking_documents"] = retrieval.get("item_count")
    row["deferred_documents"] = retrieval.get("deferred")
    row["stopped_on"] = retrieval.get("stopped_on")
    for phase in (canonical.get("trace") or []):
        if phase.get("unaccounted_ms") is not None:
            row["unaccounted_ms"] = phase.get("unaccounted_ms")
            row["total_wall_ms"] = phase.get("total_wall_ms")

    # --- the rendered report: identity, provenance, Q&A mount -------------
    st, brief, _u, _d, _h = _req(op, f"/runs/{run_id}/brief", timeout=90)
    text = visible(brief)
    row["brief_status"] = st
    row["brief_chars"] = len(text)
    row["identity_named"] = bool(
        name.split()[0].lower() in text.lower()
        or domain.split(".")[0].lower() in text.lower())
    row["qa_mounted"] = "/conversation" in brief
    row["provenance_present"] = bool(
        re.search(r"sec\.gov|source|evidence", text, re.I))
    row["analysis_updated"] = bool(
        re.search(r"analysis (was )?updated|updated after", text, re.I))
    # No internal identifiers on a reader-facing page.
    row["enum_leak"] = sorted(set(
        re.findall(r"\b(?:READY_FOR_[A-Z_]+|EVIDENCE_[A-Z_]+|DEEP_[A-Z]+|"
                   r"OFFICIAL_WEB_[A-Z]+|CACHE_[A-Z]+)\b", text)))[:6]

    # --- live Q&A on the same session -------------------------------------
    if with_qa and row["has_report"]:
        st, page, _u, _d, _h = _req(op, f"/runs/{run_id}/brief", timeout=90)
        token = _csrf(page)
        for question in QUESTIONS:
            began_q = time.monotonic()
            st, ans, _u, _d, _h = _req(
                op, f"/runs/{run_id}/conversation",
                {"csrf": token, "question": question}, timeout=240)
            body_text = visible(ans)
            row["qa"].append({
                "question": question, "status": st,
                "seconds": round(time.monotonic() - began_q, 1),
                "chars": len(body_text),
                "answer": body_text[-1800:],
            })
            if st == 200 and len(body_text) > 400:
                row["questions_ok"] += 1
            token = _csrf(ans) or token
        began_q = time.monotonic()
        st, ans, _u, _d, _h = _req(
            op, f"/runs/{run_id}/conversation",
            {"csrf": token, "question": FOLLOW_UP}, timeout=240)
        row["qa"].append({"question": FOLLOW_UP, "status": st,
                          "seconds": round(time.monotonic() - began_q, 1),
                          "chars": len(visible(ans)),
                          "answer": visible(ans)[-1800:], "follow_up": True})

    row["status"] = ("COMPLETE" if row["has_report"]
                     else ("ABSTAINED"
                           if row.get("outcome") == "BOUNDED_ABSTENTION"
                           else ("NO_RESULT" if row["usable_seconds"] is None
                                 else "USABLE_NO_REPORT")))
    return row


def summarise(rows) -> dict:
    counted = [r for r in rows if r.get("status") != "QUOTA_EXHAUSTED"]
    core = [r["core_ready_seconds"] for r in counted
            if r.get("core_ready_seconds") is not None]
    usable = [r["usable_seconds"] for r in counted
              if r.get("usable_seconds") is not None]
    within = [r for r in counted if r.get("terminal_within_contract")]
    out = {
        "attempted": len(rows), "counted": len(counted),
        "quota_exhausted": len(rows) - len(counted),
        "usable_reports": sum(1 for r in counted if r.get("has_report")),
        "bounded_abstentions": sum(1 for r in counted
                                   if r.get("outcome") == "BOUNDED_ABSTENTION"),
        "no_result": sum(1 for r in counted
                         if r.get("outcome") == "NO_RESULT"),
        "terminal": len(within),
        "core_p50": _pct(core, 50), "core_p90": _pct(core, 90),
        "core_p95": _pct(core, 95), "core_max": max(core) if core else None,
        "usable_p50": _pct(usable, 50), "usable_p90": _pct(usable, 90),
        "within_60": sum(1 for v in core if v <= 60),
        "within_90": sum(1 for v in core if v <= 90),
        "within_120": sum(1 for v in usable if v <= 120),
        "deep_success": sum(1 for r in counted
                            if r.get("deep_ready_seconds") is not None),
        "enum_leaks": sum(1 for r in counted if r.get("enum_leak")),
        "qa_mounted": sum(1 for r in counted if r.get("qa_mounted")),
        "analysis_updated": sum(1 for r in counted
                                if r.get("analysis_updated")),
    }
    p50, p90 = out["core_p50"], out["core_p90"]
    if p50 is None:
        out["performance_tier"] = "NO_DATA"
    elif p50 <= TIER_A[0] and p90 <= TIER_A[1]:
        out["performance_tier"] = "A_EXCELLENT"
    elif p50 <= TIER_B[0] and p90 <= TIER_B[1]:
        out["performance_tier"] = "B_ACCEPTABLE"
    elif p50 <= TIER_C[0] and p90 <= TIER_C[1]:
        out["performance_tier"] = "C_CONDITIONAL"
    else:
        out["performance_tier"] = "FAIL"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", default="",
                    help='"Name|domain,Name|domain" — overrides --cohort')
    ap.add_argument("--cohort", choices=("tier1", "qualify50"), default="tier1")
    ap.add_argument("--slice", default="")
    ap.add_argument("--qa", action="store_true")
    ap.add_argument("--budget", type=float, default=300.0)
    ap.add_argument("--out", default="reports/perf/pre100_live.json")
    a = ap.parse_args()

    if a.companies:
        cohort = [tuple(c.split("|")) for c in a.companies.split(",")]
    else:
        cohort = {"tier1": TIER1, "qualify50": QUALIFY_50}[a.cohort]
    if a.slice:
        lo, hi = (int(x) if x else None for x in a.slice.split(":"))
        cohort = cohort[lo:hi]

    op, _ = _opener()
    st, ver, _u, dt, _h = _req(op, "/version", timeout=120)
    print(f"deployed: {ver.strip()[:110]}   (warm-up {dt:.1f}s)")
    print(f"n={len(cohort)} qa={a.qa}\n")

    rows = []
    for name, domain in cohort:
        row = qualify(name, domain, budget_s=a.budget, with_qa=a.qa)
        rows.append(row)
        print(f"  {row.get('status','?'):16s} {name:22s} "
              f"core={row.get('core_ready_seconds')} "
              f"usable={row.get('usable_seconds')} "
              f"docs={row.get('blocking_documents')}/"
              f"{row.get('deferred_documents')}/{row.get('final_documents')} "
              f"deep={'y' if row.get('deep_ready_seconds') else 'n'} "
              f"qa={row.get('questions_ok')}"
              f"{'  ENUM_LEAK ' + ','.join(row['enum_leak']) if row.get('enum_leak') else ''}")
        if row.get("status") == "QUOTA_EXHAUSTED":
            print("  ! demo quota exhausted — stopping cleanly")
            break

    summary = summarise(rows)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"version": ver.strip(), "summary": summary,
                               "rows": rows}, indent=1))
    print("\n" + json.dumps(summary, indent=1))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
