#!/usr/bin/env python3
"""§17 and §40: what actually changed, measured against the frozen forty.

WHY A NEW SCRIPT RATHER THAN A FLAG ON THE OLD ONE
--------------------------------------------------
`next40_differentiation` answers ONE question -- do two companies receive the
same sentences? -- and answers it well. §17 asks eleven more, and every one
of them is about a field the forty could not produce: whether a slot in the
decision question came from the company, whether the reading is grounded once
its name is removed, whether the class prior alone would have said the same.
Bolting those onto a script whose whole contract is pairwise text comparison
would make both jobs harder to read.

Runs on the state file. Costs nothing, needs no analysis, and can be re-run
as often as the reading is doubted.

WHAT IS AND IS NOT COMPARABLE TO THE FORTY (§40)
-------------------------------------------------
COMPARABLE: decision-force distribution, question cardinality, semantic
overlap on the X-Ray -- same instrument, same normalisation, same surface.

NOT COMPARABLE, AND SAID SO IN THE OUTPUT: every V2 metric. The forty had no
grounding verdict, no strategic delta and no information priority, so a
baseline of zero for those is the ABSENCE OF THE MEASUREMENT and not a
measurement of zero. Reporting "0% -> 64%" as an improvement would be
comparing a number to a blank.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "reports/asi25_state.json"
OUT = ROOT / "reports/asi25_differentiation.json"
#: The frozen baseline. Read-only, and never rewritten by this script.
BASELINE = pathlib.Path(
    "/Users/prathamsharma/intent-engine-econ/docs/qualification/"
    "40_company_qualification_matrix.json")

_NUM = re.compile(r"\b\d[\d,.%$]*\b")
_WS = re.compile(r"\s+")


def _skeleton(text: str, names) -> str:
    """The sentence shape, with every trace of WHICH company removed."""
    out = str(text or "").lower()
    for name in sorted(names, key=len, reverse=True):
        if len(str(name)) > 2:
            out = out.replace(str(name).lower(), " ")
    out = _NUM.sub(" ", out)
    out = re.sub(r"\b(20\d\d-\d\d-\d\d)\b", " ", out)
    return _WS.sub(" ", out).strip()


def _sentences(text: str):
    return {s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if len(s.split()) >= 7}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 3)


def _rows(state):
    return [r for r in (state.get("rows") or {}).values()
            if isinstance(r, dict) and r.get("company")]


def _baseline():
    """The forty's distribution, read from the frozen matrix. Never inferred."""
    try:
        m = json.loads(BASELINE.read_text())
    except Exception:                                        # noqa: BLE001
        return None
    rows = m.get("rows") or []
    force = collections.Counter(r.get("decision_force") for r in rows)
    questions = collections.Counter(
        r.get("decision_question") for r in rows if r.get("decision_question"))
    return {
        "companies": len(rows),
        "decision_force": dict(force),
        "distinct_questions": len(questions),
        "companies_with_a_question": sum(questions.values()),
        "largest_identical_question_group": (
            questions.most_common(1)[0][1] if questions else 0),
        "zero_evidence_term_companies": sum(
            1 for r in rows if r.get("evidence_term_count") == 0),
        "class_prior_only_rate": round(
            force.get("CLASS_PRIOR_ONLY", 0) / max(1, len(rows)), 3),
        "evidence_led_rate": round(
            force.get("EVIDENCE_LED", 0) / max(1, len(rows)), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(STATE))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    try:
        state = json.loads(pathlib.Path(args.state).read_text())
    except Exception as exc:                                 # noqa: BLE001
        print(f"no state to measure: {exc}", file=sys.stderr)
        return 2
    rows = _rows(state)
    if not rows:
        print("no completed companies yet", file=sys.stderr)
        return 2

    n = len(rows)
    v2 = [(r.get("v2") or {}) for r in rows]
    gen = [(r.get("generalization") or {}) for r in rows]

    # --- §17 the counted distributions -------------------------------------
    force = collections.Counter(
        g.get("decision_force") or "NOT_STATED" for g in gen)
    verdicts = collections.Counter(
        v.get("grounding_verdict") or "PANEL_ABSENT" for v in v2)
    questions = collections.Counter(
        g.get("decision_question") for g in gen if g.get("decision_question"))
    units = collections.Counter(
        v.get("measured_in") for v in v2 if v.get("measured_in"))

    grounded = sum(1 for v in v2 if v.get("grounding_verdict") == "GROUNDED")
    delta_changed = sum(1 for v in v2 if v.get("delta_stated")
                        and v.get("prior_question"))
    asks = sum(1 for v in v2 if (v.get("information_priorities") or 0) > 0)
    company_specific_priority = sum(
        1 for v in v2 if (v.get("priority_text") or "").count(
            str(next((r["company"] for r in rows
                      if (r.get("v2") or {}) is v), ""))) > 0)

    # --- §16/§17 semantic overlap, on the skeleton -------------------------
    names = {r["company"] for r in rows}
    per_surface, worst = {}, []
    for surface in ("xray", "brief", "full", "why_company"):
        texts = {}
        for r in rows:
            body = (r.get("decision_text") or {}).get(surface) or ""
            if body:
                texts[r["company"]] = _sentences(
                    _skeleton(body, names | {r["company"]}))
        pairs = []
        for a, b in itertools.combinations(sorted(texts), 2):
            pairs.append((_jaccard(texts[a], texts[b]), a, b))
        pairs.sort(reverse=True)
        cat = {r["company"]: r.get("category") for r in rows}
        cross = [p for p in pairs if cat.get(p[1]) != cat.get(p[2])]
        per_surface[surface] = {
            "companies": len(texts),
            "max_overlap": pairs[0][0] if pairs else 0.0,
            "max_cross_category": cross[0][0] if cross else 0.0,
            "pairs_at_or_above_0_98": sum(1 for p in pairs if p[0] >= 0.98),
            "identical_pairs": sum(1 for p in pairs if p[0] >= 0.999),
        }
        worst.extend({"surface": surface, "overlap": p[0], "a": p[1],
                      "b": p[2],
                      "same_category": cat.get(p[1]) == cat.get(p[2])}
                     for p in pairs[:5])

    # --- §37 an identical reading is EXPLAINED or it is a collapse ---------
    by_company = {r["company"]: r for r in rows}
    explained, unexplained = [], []
    for w in worst:
        if w["overlap"] < 0.98:
            continue
        a, b = by_company.get(w["a"], {}), by_company.get(w["b"], {})
        ga, gb = (a.get("generalization") or {}), (b.get("generalization") or {})
        va, vb = (a.get("v2") or {}), (b.get("v2") or {})
        same_q = ga.get("decision_question") == gb.get("decision_question")
        both_ungrounded = (va.get("grounding_verdict") != "GROUNDED"
                           and vb.get("grounding_verdict") != "GROUNDED")
        row = dict(w, same_question=same_q, both_ungrounded=both_ungrounded)
        # A shared reading is EXPLAINED when both pages say, in their own
        # words, that the reading is the category's and not the company's.
        # That is the product telling the truth about a real similarity.
        (explained if both_ungrounded else unexplained).append(row)

    # --- §30 the eleventh measurement, per company -------------------------
    #
    # NOT A PASS REQUIREMENT, and it may not make a truthful abstention fail.
    # BOUNDED is its own class for exactly that reason: a company whose site
    # refused retrieval has not produced a LOW reading, it has produced no
    # reading, and collapsing the two would punish the product for telling
    # the truth about a company it could not read.
    peak = {}
    for w in worst:
        for side in ("a", "b"):
            peak[w[side]] = max(peak.get(w[side], 0.0), w["overlap"])
    quality = {}
    for r in rows:
        v, g = (r.get("v2") or {}), (r.get("generalization") or {})
        company = r["company"]
        overlap = peak.get(company, 0.0)
        if r.get("retrieval_limited") or not g.get("decision_question"):
            quality[company] = "BOUNDED"
            continue
        grounded_here = v.get("grounding_verdict") == "GROUNDED"
        moved = bool(v.get("prior_question")) and bool(v.get("delta_stated"))
        asked = (v.get("information_priorities") or 0) > 0
        if grounded_here and moved and asked and overlap < 0.90:
            quality[company] = "HIGH"
        elif (grounded_here or moved) and overlap < 0.98:
            quality[company] = "MEDIUM"
        else:
            quality[company] = "LOW"

    out = {
        "contract": "asi25_differentiation.v1",
        "differentiation_quality": quality,
        "differentiation_quality_counts": dict(
            collections.Counter(quality.values())),
        "companies": n,
        "decision_force": dict(force),
        "grounding_verdict": dict(verdicts),
        "distinct_questions": len(questions),
        "largest_identical_question_group": (
            questions.most_common(1)[0][1] if questions else 0),
        "distinct_billing_units": len(units),
        "billing_units": dict(units),
        "rates": {
            "grounded": round(grounded / n, 3),
            "strategic_delta_changed": round(delta_changed / n, 3),
            "asks_an_information_priority": round(asks / n, 3),
            "company_specific_priority": round(
                company_specific_priority / n, 3),
        },
        "overlap": per_surface,
        "explained_identical_readings": explained,
        "unexplained_identical_readings": unexplained,
        "worst_pairs": sorted(worst, key=lambda w: -w["overlap"])[:15],
        # §40, with the incomparables named as incomparable.
        "baseline_forty": _baseline(),
        "comparability_note": (
            "Decision-force distribution, question cardinality and X-Ray "
            "overlap are the same instrument on both cohorts and are "
            "comparable. Grounding verdict, strategic delta and information "
            "priority DID NOT EXIST on the forty: a baseline of zero there "
            "is the absence of the measurement, not a measurement of zero, "
            "and must not be reported as an improvement from zero."),
    }
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in (
        "companies", "decision_force", "grounding_verdict",
        "distinct_questions", "largest_identical_question_group",
        "distinct_billing_units", "rates",
        "differentiation_quality_counts")}, indent=2))
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
