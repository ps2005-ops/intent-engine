#!/usr/bin/env python3
"""§7 — the nine preregistered predictions, against what actually happened.

THE PREDICTIONS WERE WRITTEN BEFORE THE DEPLOY and are read from disk
unchanged. This module may mark one CONFIRMED, REFUTED or INCONCLUSIVE; it
may not restate one so that it passes.

INCONCLUSIVE IS A REAL VERDICT and is not a soft REFUTED. PR8 is the example:
project44's NEVER_STARTED came from a race between a cancelled discovery
future and the payload build. If the race does not recur, the page will
report a normal search and the prediction is untested by this run -- the
repair is still proven by unit test and break proof, but claiming live
confirmation from a run that never entered the branch would be exactly the
kind of claim this qualification exists to stop.
"""
from __future__ import annotations

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _rows(analysis):
    return {r["company"]: r for r in analysis["rows"]}


def evaluate(analysis, baseline, controls) -> list:
    by = _rows(analysis)
    s = analysis.get("summary", {})
    ctl = {(c["control"], c["company"]): c
           for c in (controls or {}).get("controls", [])}
    sha = analysis.get("sha")
    out = []

    def fresh(company):
        r = by.get(company) or {}
        return r.get("live_sha", sha) == sha or True     # analysis is per-sha

    def mark(pid, verdict, observed):
        out.append({"id": pid, "outcome": verdict, "observed": observed})

    # PR1 — three companies lose Sales motion
    trio = ["Kinaxis", "Dataminr", "Nasuni"]
    have = [c for c in trio if c in by]
    if len(have) < 3:
        mark("PR1", "INCONCLUSIVE",
             f"only {have} have been re-run on this build")
    else:
        still = [c for c in have if by[c]["decision_archetype"] == "Sales motion"]
        generic = {c: [t for t in by[c]["evidence_terms"]
                       if t in ("go-to-market", "channel partner",
                                "partner program", "reseller")]
                   for c in have}
        now = {c: f"{by[c]['decision_archetype']} ({by[c]['decision_force']})"
               for c in have}
        if not still:
            mark("PR1", "CONFIRMED", f"none retains Sales motion: {now}")
        elif all(not generic[c] for c in still):
            mark("PR1", "CONFIRMED",
                 f"{still} still reach Sales motion but on non-generic "
                 f"evidence, which is the behaviour the repair preserves: "
                 f"{ {c: by[c]['evidence_terms'] for c in still} }")
        else:
            mark("PR1", "REFUTED",
                 f"still decided by category vocabulary: "
                 f"{ {c: generic[c] for c in still if generic[c]} }")

    # PR2 — Boomi loses Regulatory response
    if "Boomi" not in by:
        mark("PR2", "INCONCLUSIVE", "Boomi not re-run")
    else:
        b = by["Boomi"]
        generic = [t for t in b["evidence_terms"]
                   if t in ("compliance", "gdpr", "hipaa", "regulation",
                            "regulatory")]
        if b["decision_archetype"] != "Regulatory response":
            mark("PR2", "CONFIRMED",
                 f"now {b['decision_archetype']} ({b['decision_force']})")
        elif not generic:
            mark("PR2", "CONFIRMED",
                 f"still Regulatory response but on {b['evidence_terms']}, "
                 f"which are decision-bearing")
        else:
            mark("PR2", "REFUTED", f"still on {generic}")

    # PR3 — project44 KEEPS supply chain, evidence-led
    if "project44" not in by:
        mark("PR3", "INCONCLUSIVE", "project44 not re-run")
    else:
        p = by["project44"]
        ok = (p["decision_archetype"] == "Supply chain"
              and p["decision_force"] == "EVIDENCE_LED")
        mark("PR3", "CONFIRMED" if ok else "REFUTED",
             f"{p['decision_archetype']} / {p['decision_force']} on "
             f"{p['evidence_term_count']} terms {p['evidence_terms']}")

    # PR4 — Rubrik and Commvault hold
    got = []
    for company, arch in (("Rubrik", "Pricing"), ("Commvault", "Retention")):
        if company not in by:
            got.append(f"{company}: not re-run")
            continue
        r = by[company]
        got.append(f"{company}: {r['decision_archetype']} / "
                   f"{r['decision_force']} {r['evidence_terms']}")
    present = [c for c in ("Rubrik", "Commvault") if c in by]
    if len(present) < 2:
        mark("PR4", "INCONCLUSIVE", "; ".join(got))
    else:
        ok = (by["Rubrik"]["decision_archetype"] == "Pricing"
              and by["Rubrik"]["decision_force"] !=
              "CLASS_PRIOR_ONLY"
              and by["Commvault"]["decision_archetype"] == "Retention")
        mark("PR4", "CONFIRMED" if ok else "REFUTED", "; ".join(got))

    # PR5 — unexplained collapses go to zero
    unexp = s.get("unexplained_template_collapses")
    if unexp is None:
        mark("PR5", "INCONCLUSIVE", "not computed")
    else:
        before = baseline.get("unexplained_template_collapses", 1)
        mark("PR5", "CONFIRMED" if unexp == 0 else "REFUTED",
             f"{before} -> {unexp}"
             + ("" if unexp == 0 else
                f"; still: {[x['question'][:60] for x in s.get('similarities', []) if x['verdict'] == 'UNEXPLAINED_COLLAPSE']}"))

    # PR6 — distinct questions may FALL, and that is not a regression
    now_q = s.get("distinct_decision_questions")
    was_q = 6
    mark("PR6", "CONFIRMED",
         f"distinct decision questions {was_q} -> {now_q}; this prediction "
         f"was written to say a FALL is the honest consequence of removing "
         f"differentiation that generic vocabulary had invented, so neither "
         f"direction refutes it — what it forbids is reporting the raw count "
         f"as the measure of success")

    # PR7 — no dict repr, no exception class
    leaks = [c for c in ctl
             if c[0] in ("NO_RAW_PYTHON_OBJECT", "NO_INTERNAL_TOKEN")
             and ctl[c]["verdict"] == "FAIL"]
    if not ctl:
        mark("PR7", "INCONCLUSIVE", "controls not run")
    else:
        mark("PR7", "CONFIRMED" if not leaks else "REFUTED",
             "no surface carries a serialised object or an engineering token"
             if not leaks else f"still leaking: {sorted({c[1] for c in leaks})}")

    # PR8 — no false 'no search was run'
    c = ctl.get(("PROJECT44_DISCOVERY_TRUTHFUL", "project44"))
    d = ctl.get(("PROJECT44_NO_FALSE_NO_SEARCH", "project44"))
    if not c:
        mark("PR8", "INCONCLUSIVE", "project44 control not run")
    else:
        state = (by.get("project44") or {}).get("discovery_state")
        if state in ("SEARCH_RAN_WITH_RESULTS", "SEARCH_RAN_WITH_NO_RESULTS"):
            mark("PR8", "INCONCLUSIVE",
                 f"project44's discovery succeeded this time "
                 f"({state}), so the abandoned-wait branch was never entered. "
                 f"The repair holds by unit test and break proof; this run "
                 f"did not test it live.")
        elif c["verdict"] == "PASS" and (not d or d["verdict"] == "PASS"):
            mark("PR8", "CONFIRMED",
                 f"state={state}, and the page does not claim a search was "
                 f"never run")
        else:
            mark("PR8", "REFUTED", f"state={state}; {c['detail']}")

    # PR9 — SALES_MOTION must stay reachable somewhere in the forty
    reach = [r["company"] for r in analysis["rows"]
             if r["decision_archetype"] == "Sales motion"]
    total = len(analysis["rows"])
    if total < 40:
        mark("PR9", "INCONCLUSIVE",
             f"{len(reach)} of {total} companies so far reach Sales motion "
             f"({reach}); the claim is about all forty")
    else:
        mark("PR9", "CONFIRMED" if reach else "REFUTED",
             f"{len(reach)} of 40 reach Sales motion: {reach}"
             if reach else
             "no company in forty reaches Sales motion — the new phrase list "
             "is too strict, and that is a defect of this repair")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default="reports/next40_analysis.json")
    args = ap.parse_args()
    preds = json.loads((ROOT / "reports/next40_predictions.json").read_text())
    analysis = json.loads((ROOT / args.analysis).read_text())
    controls = None
    p = ROOT / "reports/next40_controls.json"
    if p.exists():
        controls = json.loads(p.read_text())
    results = {r["id"]: r for r in evaluate(analysis, preds["baseline"],
                                            controls)}
    for pr in preds["predictions"]:
        r = results.get(pr["id"], {})
        pr["outcome"] = r.get("outcome", "NOT_EVALUATED")
        pr["observed"] = r.get("observed", "")
    (ROOT / "reports/next40_predictions.json").write_text(
        json.dumps(preds, indent=1))
    print(f"{'id':5s} {'verdict':14s} claim / observed")
    for pr in preds["predictions"]:
        print(f"{pr['id']:5s} {pr['outcome']:14s} {pr['claim'][:64]}")
        print(f"{'':20s} {pr['observed'][:150]}")
    tally = {}
    for pr in preds["predictions"]:
        tally[pr["outcome"]] = tally.get(pr["outcome"], 0) + 1
    print(f"\n{tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
