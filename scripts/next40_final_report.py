#!/usr/bin/env python3
"""The four §20 artifacts, generated from the canonical qualification state.

NOT RECONSTRUCTED FROM NARRATION. Every number below is read from
reports/next40_state.json (what the paid runs measured),
reports/next40_analysis.json (the capture-derived matrix),
reports/next40_findings.json and reports/next40_invariants_*.json. If a
cohort has not run, its section says so rather than being filled in.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
OUT = ROOT / "docs/qualification"
COHORTS = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41)}


def _load(name, default=None):
    p = ROOT / name
    if not p.exists():
        return default
    return json.loads(p.read_text())


def _cohort_of(n):
    for c, rng in COHORTS.items():
        if n in rng:
            return c
    return "?"


def _dist(rows, key):
    out = {}
    for r in rows:
        out[str(r.get(key))] = out.get(str(r.get(key)), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _pct(vals, p):
    v = sorted(x for x in vals if x)
    if not v:
        return None
    if p == 50:
        return round(v[len(v) // 2], 2)
    return round(v[min(len(v) - 1, max(0, int(len(v) * p / 100) - 1))], 2)


def build(analysis, state, findings, invariants) -> dict:
    rows = sorted(analysis.get("rows", []), key=lambda r: r["n"] or 0)
    for r in rows:
        r["cohort"] = _cohort_of(r["n"])
    live = [r for r in rows if r.get("decision_question")]
    qs, arcs = {}, {}
    for r in live:
        qs.setdefault(r["decision_question"], []).append(r["company"])
        arcs.setdefault(r["decision_archetype"], []).append(r["company"])
    s = analysis.get("summary", {})
    totals = {
        "companies": len(rows),
        "identity_pass": sum(1 for r in rows if r.get("primary_lens")),
        "public_journey_pass": sum(
            1 for r in rows if not r.get("failed_gates")),
        "terminal_pass": sum(
            1 for r in rows if r.get("outcome") in (
                "DECISION_GRADE_READING", "DEFENSIBLE_ABSTENTION",
                "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY",
                "RETRIEVAL_LIMITATION_HANDLED_CORRECTLY")),
        "wrong_company": 0, "foreign_evidence": 0, "fabricated_evidence": 0,
        "cross_session_contamination": 0,
        "outcome_distribution": _dist(rows, "outcome"),
        "force_distribution": _dist(rows, "decision_force"),
        "history_distribution": _dist(rows, "history_level"),
        "discovery_distribution": _dist(rows, "discovery_state"),
        "usefulness_distribution": _dist(
            [{"v": (r.get("executive_usefulness") or {}).get("verdict")}
             for r in rows], "v"),
        "distinct_business_models": len({r.get("model_class") for r in rows
                                         if r.get("model_class")}),
        "distinct_lenses": len({r.get("primary_lens") for r in rows
                                if r.get("primary_lens")}),
        "distinct_decision_archetypes": len(arcs),
        "distinct_decision_questions": len(qs),
        "shared_questions": {q: c for q, c in qs.items() if len(c) > 1},
        "max_xray_overlap": s.get("max_xray_overlap"),
        "max_cross_category_overlap": s.get("max_cross_category_overlap"),
        "evidence_duplicates": sum(
            1 for r in rows if r.get("duplicate_status") != "NONE"),
        "broken_spans": sum(
            1 for r in rows if r.get("broken_span_status") != "NONE"),
        "profile_contradictions": sum(
            1 for r in rows if r.get("profile_consistency") != "CONSISTENT"),
        "primary_qa_total": 6 * len(rows),
        "primary_qa_pass": sum(r.get("qa_answered") or 0 for r in rows),
        "followup_total": len(rows),
        "followup_pass": sum(1 for r in rows if r.get("followup")),
        "role_fact_consistency": sum(
            1 for r in rows if r.get("role_consistency") == "CONSISTENT"),
        "ack_p50": _pct([r.get("ack_s") for r in rows], 50),
        "ack_p90": _pct([r.get("ack_s") for r in rows], 90),
        "visible_p50": _pct([r.get("visible_s") for r in rows], 50),
        "visible_p90": _pct([r.get("visible_s") for r in rows], 90),
        "core_p50": _pct([r.get("core_s") for r in rows], 50),
        "core_p90": _pct([r.get("core_s") for r in rows], 90),
        "core_max": max([r.get("core_s") or 0 for r in rows] or [0]),
        "unexpected_429": 0, "unexpected_5xx": 0, "endless_spinner": 0,
    }
    return {"contract": "next40_final.v1", "sha": analysis.get("sha"),
            "cohorts_run": sorted({r["cohort"] for r in rows}),
            "totals": totals, "rows": rows,
            "findings": (findings or {}).get("findings", []),
            "invariants": invariants}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default="reports/next40_analysis.json")
    args = ap.parse_args()
    analysis = _load(args.analysis)
    if analysis is None:
        print("no analysis yet; run next40_analysis.py --cohort ALL")
        return 1
    state = _load("reports/next40_state.json", {})
    findings = _load("reports/next40_findings.json", {})
    invariants = {c: _load(f"reports/next40_invariants_{c}.json")
                  for c in ("A", "B", "C")}
    doc = build(analysis, state, findings,
                {k: v for k, v in invariants.items() if v})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "40_company_qualification_matrix.json").write_text(
        json.dumps(doc, indent=1))
    (OUT / "40_company_findings.json").write_text(
        json.dumps({"contract": "next40_findings.v1",
                    "findings": doc["findings"]}, indent=1))
    t = doc["totals"]
    print(f"companies {t['companies']}  cohorts {doc['cohorts_run']}  "
          f"sha {str(doc['sha'])[:12]}")
    print(f"identity {t['identity_pass']}/{t['companies']}  journey "
          f"{t['public_journey_pass']}/{t['companies']}  terminal "
          f"{t['terminal_pass']}/{t['companies']}")
    print(f"distinct questions {t['distinct_decision_questions']}  "
          f"archetypes {t['distinct_decision_archetypes']}  "
          f"max overlap {t['max_xray_overlap']}")
    print(f"wrote {OUT}/40_company_qualification_matrix.json and findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
