#!/usr/bin/env python3
"""The cohort checkpoint (§26) and the per-company matrix, from state alone.

Costs nothing and needs no analysis: everything it prints was measured during
the one paid run per company and persisted. Run it as often as you like.

IT REPORTS DISTRIBUTIONS, IT DOES NOT MANIPULATE THEM. Decision-grade,
defensible abstention and retrieval limitation are counted as they fell out;
a run that abstained is not reclassified to improve a ratio, because the
abstention rate is the evidence that the system is selective rather than
silent.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
COHORTS = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41)}

#: The gates §25/§27 name, and where each is read from a state row.
GATE_KEYS = (
    ("SEARCH", lambda r: r["gates"].get("AUTOCOMPLETE")),
    ("IDENTITY", lambda r: r["gates"].get("CANONICAL_IDENTITY")),
    ("NO_MANUAL_URL", lambda r: r["gates"].get("NO_MANUAL_URL")),
    ("PUBLIC_JOURNEY", lambda r: r.get("result") == "PASS"),
    ("CORE_WITHIN_120", lambda r: r["gates"].get("CORE_WITHIN_120S")),
    ("SURFACES", lambda r: r["gates"].get("SURFACES_RENDER")),
    ("HISTORY", lambda r: r["gates"].get("HISTORY_REWIND")),
    ("EVIDENCE_NO_DUP", lambda r: r["gates"].get("EVIDENCE_NO_DUPLICATES")),
    ("EVIDENCE_NO_BROKEN", lambda r: r["gates"].get(
        "EVIDENCE_NO_BROKEN_SPANS")),
    ("PROFILE_CONSISTENT", lambda r: r["gates"].get("PROFILE_CONSISTENCY")),
    ("QA_VALID", lambda r: r["gates"].get("QA_VALID")),
    ("FOLLOWUP", lambda r: r["gates"].get("FOLLOWUP_CONTEXT")),
    ("ROLES", lambda r: r["gates"].get("ROLE_VIEWS")),
    ("XRAY", lambda r: r["gates"].get("XRAY_RENDERS")),
    ("NO_SPINNER", lambda r: r["gates"].get("NO_ENDLESS_SPINNER")),
)


def _rows(state, cohort):
    keep = COHORTS[cohort] if cohort in COHORTS else range(1, 41)
    return [r for k, r in sorted(state.get("rows", {}).items(),
                                 key=lambda kv: int(kv[0]))
            if r.get("n") in keep]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="A")
    ap.add_argument("--state", default="reports/next40_state.json")
    args = ap.parse_args()
    path = ROOT / args.state
    if not path.exists():
        print("no state yet")
        return 0
    state = json.loads(path.read_text())
    rows = _rows(state, args.cohort)
    if not rows:
        print(f"cohort {args.cohort}: no rows yet")
        return 0
    n = len(rows)
    sha = state.get("live_sha", "")[:12]
    print(f"COHORT:    {args.cohort}")
    print(f"COMPANIES: {n}")
    print(f"SHA:       {sha}\n")

    # --- the matrix --------------------------------------------------------
    print(f"{'#':>2} {'company':20s} {'class':34s} {'CORE':>6s} {'hst':>3s} "
          f"{'doc':>3s} {'search':24s} {'ind':>3s} {'QA':>4s} {'dup':>3s}")
    for r in rows:
        d = r.get("discovery") or {}
        h = r.get("history") or {}
        qa = r.get("qa") or {}
        ev = r.get("evidence") or {}
        print(f"{r.get('n',0):2d} {r.get('company','')[:20]:20s} "
              f"{(r.get('final_class') or '')[:34]:34s} "
              f"{(str(r.get('core_s')) + 's') if r.get('core_s') else '-':>6s} "
              f"{(r.get('history_level') or '?'):>3s} "
              f"{str(h.get('dated_documents') or '-'):>3s} "
              f"{(d.get('search_state') or '-')[:24]:24s} "
              f"{str(d.get('independent_origins') if d.get('independent_origins') is not None else '-'):>3s} "
              f"{str(qa.get('answered', '-')) + '/6':>4s} "
              f"{str(ev.get('duplicates', '-')):>3s}")

    # --- gates -------------------------------------------------------------
    print("\nGATES")
    for label, get in GATE_KEYS:
        vals = [bool(get(r)) for r in rows if r.get("gates")]
        if not vals:
            continue
        print(f"  {label:20s} {sum(vals)}/{len(vals)}"
              + ("" if all(vals) else
                 "   FAIL: " + ", ".join(
                     r.get("company", "") for r in rows
                     if r.get("gates") and not get(r))))

    # --- §8 outcome distribution, reported not steered ---------------------
    dist = collections.Counter(r.get("final_class") for r in rows)
    print("\nOUTCOME DISTRIBUTION (reported, never steered)")
    for k, v in dist.most_common():
        print(f"  {k or 'UNKNOWN':40s} {v}")

    # --- history, per company (§12) ---------------------------------------
    print("\nHISTORY (§12)")
    print(f"  {'company':20s} {'lvl':3s} {'docs':>4s} {'earliest':10s} "
          f"{'latest':10s} {'series':6s} {'econ':>4s} wall")
    for r in rows:
        h = r.get("history") or {}
        print(f"  {r.get('company','')[:20]:20s} "
              f"{(r.get('history_level') or '?'):3s} "
              f"{str(h.get('dated_documents') or '-'):>4s} "
              f"{str(h.get('earliest') or '-'):10s} "
              f"{str(h.get('latest') or '-'):10s} "
              f"{str(h.get('financial_series')):6s} "
              f"{str(h.get('economic_links') or 0):>4s} "
              f"{h.get('hindsight_wall') or '-'}")
    levels = collections.Counter(r.get("history_level") for r in rows)
    print(f"  levels: {dict(levels)}")

    # --- discovery (§14) ---------------------------------------------------
    print("\nDISCOVERY (§14)")
    for r in rows:
        d = r.get("discovery") or {}
        print(f"  {r.get('company','')[:20]:20s} "
              f"{(d.get('search_state') or '-'):28s} "
              f"hits={str(d.get('hits') or '-'):>4s} "
              f"read={str(d.get('read_in_full') or '-'):>3s} "
              f"independent={str(d.get('independent_origins') if d.get('independent_origins') is not None else '-'):>3s} "
              f"reused={bool(d.get('reused'))}")
    states = collections.Counter((r.get("discovery") or {}).get("search_state")
                                 for r in rows)
    print(f"  states: {dict(states)}")
    said_none = [r.get("company") for r in rows
                 if (r.get("discovery") or {}).get("says_no_search")]
    print(f"  still says 'no search was run': {said_none or 'none'}")

    # --- performance -------------------------------------------------------
    cores = [r["core_s"] for r in rows if r.get("core_s")]
    acks = [r["submit_ack_s"] for r in rows if r.get("submit_ack_s") is not None]
    vis = [r["visible_progress_s"] for r in rows
           if r.get("visible_progress_s") is not None]
    if cores:
        print(f"\nPERFORMANCE  CORE p50 {statistics.median(cores):.1f}s  "
              f"p90 {sorted(cores)[max(0, int(len(cores)*0.9)-1)]:.1f}s  "
              f"max {max(cores):.1f}s")
    if acks:
        print(f"             SUBMIT_ACK max {max(acks):.2f}s (<=2s)")
    if vis:
        print(f"             VISIBLE_PROGRESS max {max(vis):.2f}s (<=3s)")

    # --- Q&A ---------------------------------------------------------------
    ans = sum((r.get("qa") or {}).get("answered", 0) for r in rows)
    asked = sum((r.get("qa") or {}).get("of", 0) for r in rows)
    fol = sum(1 for r in rows if (r.get("qa") or {}).get("followup"))
    print(f"\nQ&A          {ans}/{asked}   FOLLOWUPS {fol}/{n}")

    # --- §7/§8 STRATEGIC GENERALIZATION -----------------------------------
    #
    # THE QUESTION THIS ANSWERS. Seven of nine cohort-A companies received the
    # identical central question, and nothing in the pass/fail matrix showed
    # it: every one of them passed. A decision reached purely by the business
    # model's menu ordering is not wrong for an evidence-poor company -- it is
    # the honest fallback -- but a heterogeneous cohort collapsing onto one is
    # the signature of a class prior standing in for an answer.
    #
    # Concentration is MEASURED, never compared against an invented target
    # distribution: the question is whether the evidence explains it.
    gen = [r for r in rows if r.get("generalization")]
    if gen:
        print("\nSTRATEGIC GENERALIZATION (§7)")
        print(f"  {'company':20s} {'archetype':22s} {'won by':14s} "
              f"{'prior':>5s} {'evid':>4s} {'econ':>4s} {'post':>4s}")
        for r in gen:
            g = r["generalization"]
            c = g.get("contributions") or {}
            won = ("CLASS_PRIOR" if c.get("class_prior_only") else
                   "EVIDENCE" if c.get("evidence") else
                   "ECON" if c.get("econ") else
                   "POSTURE" if c.get("posture") else "OTHER")
            print(f"  {r.get('company','')[:20]:20s} "
                  f"{(g.get('archetype') or '-')[:22]:22s} {won:14s} "
                  f"{c.get('class_prior', 0):5d} {c.get('evidence', 0):4d} "
                  f"{c.get('econ', 0):4d} {c.get('posture', 0):4d}")
        only = [r for r in gen
                if ((r["generalization"].get("contributions") or {})
                    .get("class_prior_only"))]
        changed_ev = [r for r in gen
                      if ((r["generalization"].get("contributions") or {})
                          .get("evidence"))]
        changed_ec = [r for r in gen
                      if ((r["generalization"].get("contributions") or {})
                          .get("econ"))]
        changed_po = [r for r in gen
                      if ((r["generalization"].get("contributions") or {})
                          .get("posture"))]
        qcount = collections.Counter(
            (r["generalization"].get("decision_question") or "")[:90]
            for r in gen)
        print(f"\n  CLASS_PRIOR_ONLY_DECISIONS  {len(only)}/{len(gen)}"
              + (f"   {[r['company'] for r in only]}" if only else ""))
        print(f"  EVIDENCE_CHANGED_DECISION   {len(changed_ev)}/{len(gen)}")
        print(f"  ECON_CHANGED_DECISION       {len(changed_ec)}/{len(gen)}")
        print(f"  POSTURE_CHANGED_DECISION    {len(changed_po)}/{len(gen)}")
        print(f"  DISTINCT decision questions {len(qcount)}/{len(gen)}")
        for q, n in qcount.most_common(3):
            print(f"     x{n}  {q[:78]}")
        # The flag is a WARNING to inspect, not a verdict: one evidence-poor
        # company on the class prior is correct behaviour.
        share = len(only) / float(len(gen))
        top_share = (qcount.most_common(1)[0][1] / float(len(gen))
                     if qcount else 0)
        if len(gen) >= 4 and (share >= 0.5 or top_share >= 0.5):
            print(f"  ** CLASS_PRIOR_DOMINANCE: {share:.0%} of a "
                  f"heterogeneous cohort decided by the class menu alone, and "
                  f"{top_share:.0%} share one question. Inspect whether the "
                  f"evidence explains it.")
        else:
            print("  CLASS_PRIOR_DOMINANCE: not flagged")

    # --- defects, classified ----------------------------------------------
    kinds = collections.Counter(
        d["kind"] for r in rows for d in (r.get("defects") or ()))
    print(f"\nDEFECTS BY KIND: {dict(kinds) or 'none'}")
    for r in rows:
        for d in (r.get("defects") or ())[:4]:
            print(f"  {r.get('company','')[:18]:18s} {d['kind']}: "
                  f"{d['detail'][:120]}")
    inst = [(r.get("company"), e) for r in rows
            for e in (r.get("instrument_errors") or ())]
    if inst:
        print(f"\nINSTRUMENT ERRORS (mine, not the product's): {inst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
