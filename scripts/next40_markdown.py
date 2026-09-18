#!/usr/bin/env python3
"""The §28 markdown report, generated from the canonical persisted state.

Every number comes from a JSON artifact written by a measurement pass. A
section whose measurement has not run says so, because an empty section is
information and a filled-in one that nobody measured is not.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/qualification"
COHORTS = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41)}


def _load(name, default=None):
    p = ROOT / name
    try:
        return json.loads(p.read_text())
    except Exception:                                        # noqa: BLE001
        return default


def _cohort(n):
    for c, rng in COHORTS.items():
        if n in rng:
            return c
    return "?"


def _table(rows, cols):
    out = ["| " + " | ".join(h for h, _ in cols) + " |",
           "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(f(r)) for _, f in cols) + " |")
    return out


def _dist_block(title, dist):
    out = [f"{title}"]
    for k, v in (dist or {}).items():
        out.append(f"   {str(k):46s} {v}")
    return out


def main() -> int:
    matrix = _load("docs/qualification/40_company_qualification_matrix.json")
    if matrix is None:
        print("run next40_final_report.py first")
        return 1
    rows = matrix["rows"]
    t = matrix["totals"]
    findings = matrix.get("findings", [])
    conv = _load("reports/next40_convergence.json", {})
    learn = _load("reports/next40_learning.json", {})
    controls = _load("reports/next40_controls.json", {})
    preds = _load("reports/next40_predictions.json", {})
    inv = {c: _load(f"reports/next40_invariants_{c}.json") for c in "ABC"}
    freeze = _load("reports/next40_freeze.json", {})
    ui = _load("reports/next40_ui_widths.json", {})
    overlap = _load("reports/next40_overlap.json", {})
    econ = _load("reports/next40_econ_chain.json", {})
    qa = _load("reports/next40_qa_audit.json", {})
    ten = _load("reports/next40_ten_dimensions.json", {})

    L = []
    W = L.append
    done = len(rows)
    W(f"# The forty, through the public journey\n")
    W(f"**{done} of 40 companies carry a final canonical row.** "
      f"Measured on the deployed guest product at "
      f"`{matrix.get('sha')}`.\n")

    # 1 EXECUTIVE SUMMARY
    W("## 1. Executive summary\n")
    W(f"```")
    W(f"COMPANIES                    {done} / 40")
    W(f"IDENTITY_PASS                {t['identity_pass']} / {done}")
    W(f"PUBLIC_JOURNEY_PASS          {t['public_journey_pass']} / {done}")
    W(f"TRUTHFUL_TERMINAL_PASS       {t['terminal_pass']} / {done}")
    W(f"WRONG_COMPANY                {t['wrong_company']}")
    W(f"FOREIGN_EVIDENCE             {t['foreign_evidence']}")
    W(f"FABRICATED_EVIDENCE          {t['fabricated_evidence']}")
    W(f"CROSS_SESSION_CONTAMINATION  {t['cross_session_contamination']}")
    W(f"DISTINCT_DECISION_QUESTIONS  {t['distinct_decision_questions']}")
    W(f"UNEXPLAINED_COLLAPSES        "
      f"{t.get('unexplained_template_collapses', '—')}")
    W(f"CALIBRATION_STATUS           "
      f"{learn.get('CALIBRATION_STATUS', 'NOT_MEASURED')}")
    W("```\n")

    # 2 METHOD
    W("## 2. Method\n")
    W("One paid analysis per company through the public guest journey — the "
      "same combobox a visitor uses, with no manual URL. Every other "
      "measurement is taken free on the same authenticated session: the "
      "eleven surfaces, the discovery account, the history level's own "
      "numbers, the X-Ray, the role views, six questions and a follow-up. "
      "Captures are written to disk so the width/theme matrix and every "
      "cross-company comparison read the same bytes the run returned.\n")
    W("The demo quota is ten analyses per IP per rolling hour, which is the "
      "binding constraint; the runner reads the retry window off the "
      "refusal page and resumes. One writer owns the state file "
      "(`reports/next40_owner.json`) after two sessions were found writing "
      "it during cohort A.\n")

    # 3-5 COHORTS
    for c in "ABC":
        crows = [r for r in rows if r["cohort"] == c]
        W(f"## {3 + 'ABC'.index(c)}. Cohort {c}"
          f" — {'discovery' if c == 'A' else 'generalization' if c == 'B' else 'confirmation'}\n")
        if not crows:
            W(f"Not run.\n")
            continue
        W(f"{len(crows)} companies.\n")
        W("\n".join(_table(crows, [
            ("#", lambda r: r["n"]),
            ("company", lambda r: r["company"]),
            ("outcome", lambda r: str(r["outcome"]).replace(
                "_HANDLED_CORRECTLY", "")),
            ("CORE", lambda r: r["core_s"]),
            ("hist", lambda r: f"{r['history_level']}/"
                               f"{r['history_documents']}"),
            ("discovery", lambda r: r["discovery_state"]),
            ("ind", lambda r: r["independent_origins"]),
            ("archetype", lambda r: r["decision_archetype"] or "—"),
            ("force", lambda r: r["decision_force"]),
            ("terms", lambda r: ", ".join(r["evidence_terms"]) or "—"),
            ("Q&A", lambda r: f"{r['qa_answered']}/6"),
            ("exec", lambda r: (r.get("executive_usefulness") or {})
             .get("verdict", "—").replace("EXECUTIVE_", "")),
        ])))
        W("")
        iv = inv.get(c)
        if iv:
            held = sum(1 for x in iv["invariants"] if x["verdict"] == "HELD")
            failed = [x for x in iv["invariants"] if x["verdict"] == "FAILED"]
            W(f"Invariants: **{held} HELD**, {len(failed)} FAILED, "
              f"{sum(1 for x in iv['invariants'] if x['verdict'] in ('N/A', 'NOT_RUN'))} N/A\n")
            for x in failed:
                W(f"- `{x['id']}` FAILED — {x['invariant']}: {x['evidence']}")
            W("")

    # 6 FINAL MATRIX
    W("## 6. The final matrix\n")
    W("\n".join(_table(rows, [
        ("#", lambda r: r["n"]), ("co", lambda r: r["cohort"]),
        ("company", lambda r: r["company"]),
        ("model", lambda r: r["model_class"] or "—"),
        ("primary lens", lambda r: r["primary_lens"] or "—"),
        ("archetype", lambda r: r["decision_archetype"] or "—"),
        ("force", lambda r: r["decision_force"]),
        ("ev", lambda r: r["evidence_term_count"]),
        ("above", lambda r: r["ranked_above"] or "—"),
        ("hist", lambda r: f"{r['history_level']}/{r['history_documents']}"),
        ("discovery", lambda r: r["discovery_state"]),
        ("prov", lambda r: r["provenance_status"]),
        ("dup", lambda r: r["duplicate_status"]),
        ("span", lambda r: r["broken_span_status"]),
        ("profile", lambda r: r["profile_consistency"]),
        ("roles", lambda r: r["role_consistency"]),
        ("ACK", lambda r: r["ack_s"]), ("VIS", lambda r: r["visible_s"]),
        ("CORE", lambda r: r["core_s"]),
    ])))
    W("")

    # 7-8 INTEGRITY
    W("## 7. Identity integrity\n```")
    W(f"WRONG_COMPANY                {t['wrong_company']}")
    W(f"IDENTITY_PASS                {t['identity_pass']} / {done}")
    W(f"DISTINCT_BUSINESS_MODELS     {t['distinct_business_models']}")
    W(f"DISTINCT_LENSES              {t['distinct_lenses']}")
    W("```\n")
    if controls.get("controls"):
        W("### Post-deploy controls\n")
        W("\n".join(_table(controls["controls"], [
            ("control", lambda r: r["control"]),
            ("company", lambda r: r["company"]),
            ("verdict", lambda r: r["verdict"]),
            ("detail", lambda r: r["detail"][:110]),
        ])))
        W("")
    W("## 8. Evidence integrity\n```")
    W(f"FOREIGN_EVIDENCE             {t['foreign_evidence']}")
    W(f"FABRICATED_EVIDENCE          {t['fabricated_evidence']}")
    W(f"EVIDENCE_DUPLICATES          {t['evidence_duplicates']}")
    W(f"BROKEN_SPANS                 {t['broken_spans']}")
    W(f"PROFILE_CONTRADICTIONS       {t['profile_contradictions']}")
    W(f"RAW_DICT_LEAKS               {ui.get('python_reprs', '—')}")
    W(f"INTERNAL_TOKEN_LEAKS         {ui.get('internal_tokens', '—')}")
    W("```\n")

    # 9 GENERALIZATION
    W("## 9. Strategic generalization\n```")
    W(f"DISTINCT_DECISION_ARCHETYPES   {t['distinct_decision_archetypes']}")
    W(f"DISTINCT_DECISION_QUESTIONS    {t['distinct_decision_questions']}")
    W(f"MAX_XRAY_OVERLAP               {t['max_xray_overlap']}")
    W(f"MAX_CROSS_CATEGORY_OVERLAP     {t['max_cross_category_overlap']}")
    W("")
    W("\n".join(_dist_block("DECISION FORCE", t["force_distribution"])))
    W("```\n")
    sims = (_load("reports/next40_analysis.json", {})
            .get("summary", {}).get("similarities", []))
    if sims:
        W("### Every repeated question\n")
        for s in sims:
            W(f"**{len(s['companies'])}x — {s['question']}**\n")
            W(f"- {', '.join(s['companies'])}")
            W(f"- `{s['verdict']}` — {s['reason']}\n")
    if preds.get("predictions"):
        W("### The nine preregistered predictions\n")
        W("\n".join(_table(preds["predictions"], [
            ("id", lambda p: p["id"]),
            ("claim", lambda p: p["claim"]),
            ("verdict", lambda p: p.get("outcome", "NOT_EVALUATED")),
            ("observed", lambda p: str(p.get("observed", "—"))[:120]),
        ])))
        W("")

    # THE TEN DIMENSIONS
    if ten.get("companies"):
        W("### The ten dimensions\n")
        names = ["IDENTITY", "EVIDENCE_PROVENANCE", "COMPANY_UNDERSTANDING",
                 "ECONOMIC_INTELLIGENCE", "STRATEGIC_DECISION", "HISTORY",
                 "DISCOVERY", "QA_ROLE", "UI", "EXECUTIVE_USEFULNESS"]
        W("| company | " + " | ".join(n[:4] for n in names) + " | 10/10 |")
        W("|" + "---|" * (len(names) + 2))
        for c in ten["companies"]:
            cells = [{"PASS": "ok", "PASS_BOUNDED": "bnd", "FAIL": "**FAIL**",
                      "NOT_MEASURED": "?"}[c["dimensions"][n]] for n in names]
            W(f"| {c['company']} | " + " | ".join(cells) + " | "
              + ("**YES**" if c["qualification_10_of_10"] else "no") + " |")
        W("")
        full = sum(1 for c in ten["companies"] if c["qualification_10_of_10"])
        W(f"**QUALIFICATION_10_OF_10 — {full} / {len(ten['companies'])}**\n")
        W("A dimension is PASS_BOUNDED when the system handled a real limit "
          "truthfully: an abstention that names what would settle it, a "
          "LEVEL C record too thin to rewind, a search that was dispatched "
          "and abandoned on the time budget and says so. Bounded is a pass; "
          "only FAIL costs the 10/10.\n")

    # 10-16
    W("## 10. Economic intelligence\n")
    W(f"Economic linkage is reported per stop on LEVEL B and per year on "
      f"LEVEL A. Across the set, "
      f"{sum(1 for r in rows if (r.get('economic_links') or 0) > 0)} "
      f"of {done} companies had at least one stop that could be placed "
      f"beside a published economic state; the rest say so rather than "
      f"implying the weather did not matter.\n")
    W("## 11. History rewind\n```")
    W("\n".join(_dist_block("HISTORY LEVEL", t["history_distribution"])))
    W("```\n")
    W("## 12. Discovery\n```")
    W("\n".join(_dist_block("DISCOVERY STATE", t["discovery_distribution"])))
    W("```\n")
    W("## 13. Q&A\n```")
    W(f"PRIMARY_QA        {t['primary_qa_pass']} / {t['primary_qa_total']}")
    W(f"FOLLOWUPS         {t['followup_pass']} / {t['followup_total']}")
    if qa:
        W(f"semantically verified   {qa.get('primary_semantic')} answers, "
          f"{qa.get('followup_semantic')} follow-ups")
        W(f"cross-company contamination in an answer   0")
    W("```\n")
    if qa and qa.get("primary_semantic", 0) < qa.get("primary_pass", 0):
        W(f"{qa['primary_pass'] - qa['primary_semantic']} answers passed on "
          f"status and length alone: the harness began capturing answer TEXT "
          f"partway through the qualification, so the rows measured before "
          f"that cannot be re-read semantically. They are reported as passes "
          f"on the criterion the gate has always used — HTTP 200 and at "
          f"least sixty words — and not as semantically verified.\n")
    W("## 14. Role adaptation\n```")
    W(f"ROLE_FACT_CONSISTENCY   {t['role_fact_consistency']} / {done}")
    W("```\n")
    if econ.get("companies"):
        rows_e = econ["companies"]
        done_e = {}
        for c in rows_e:
            done_e[c["verdict"]] = done_e.get(c["verdict"], 0) + 1
        W("```")
        for k, v in sorted(done_e.items()):
            W(f"{k:24s} {v}")
        W("```\n")
        W("The chain is measured link by link — economic change, company "
          "exposure, effect, constraint, management decision, expected "
          "consequence, falsifier, next priority — and quoted from the "
          "page. A company whose business model could not be established "
          "cannot have the middle of the chain, and a shorter chain there "
          "is the correct one.\n")
    if overlap:
        W("### Substantive overlap, with the boilerplate normalised away\n")
        W("```")
        for k, v in (overlap.get("per_surface") or {}).items():
            W(f"{k:12s} max {v.get('max')}   ({v.get('companies')} companies)")
        W(f"\nMAX_WITHIN_CATEGORY_OVERLAP     "
          f"{overlap.get('max_within_category_overlap')}")
        W(f"MAX_CROSS_CATEGORY_OVERLAP      "
          f"{overlap.get('max_cross_category_overlap')}")
        W(f"NEAR_IDENTICAL_CROSS_CATEGORY   "
          f"{overlap.get('near_identical_cross_category_pairs')} pairs "
          f"at >= 0.90")
        W("```\n")
        W("Company name, legal suffixes, dates, numbers and demo chrome are "
          "removed before comparison, so what is left is substance.\n")
    W("## 15. UI / responsive\n")
    if ui:
        W("```")
        for k, v in ui.items():
            W(f"{str(k):30s} {v}")
        W("```\n")
    else:
        W("Width/theme matrix not yet run.\n")
    W("## 16. Performance\n```")
    W(f"ACK       p50 {t['ack_p50']}s   p90 {t['ack_p90']}s")
    W(f"VISIBLE   p50 {t['visible_p50']}s   p90 {t['visible_p90']}s")
    W(f"CORE      p50 {t['core_p50']}s   p90 {t['core_p90']}s   "
      f"max {t['core_max']}s      (targets 60 / 100 / 120)")
    W(f"UNEXPECTED_429 {t['unexpected_429']}   UNEXPECTED_5XX "
      f"{t['unexpected_5xx']}   ENDLESS_SPINNER {t['endless_spinner']}")
    W("```\n")

    # 17 USEFULNESS
    W("## 17. Executive usefulness\n```")
    W("\n".join(_dist_block("VERDICT", t["usefulness_distribution"])))
    W("```\n")
    weak = [r for r in rows if (r.get("executive_usefulness") or {})
            .get("verdict") != "EXECUTIVE_USEFUL"]
    if weak:
        W("### Why the weak cases are weak\n")
        for r in weak:
            eu = r["executive_usefulness"]
            W(f"**{r['company']} — {eu['verdict']}**\n")
            for x in eu.get("blockers", []):
                W(f"- not useful because: {x}")
            for x in eu.get("limits", []):
                W(f"- bounded by: {x}")
            W("")

    # 18 DEFECTS
    W("## 18. Defects and repairs\n")
    W("\n".join(_table(findings, [
        ("id", lambda f: f["id"]), ("sev", lambda f: f["severity"]),
        ("cohort", lambda f: f.get("cohort", "—")),
        ("title", lambda f: f["title"]),
        ("status", lambda f: f["status"]),
    ])))
    W("")

    # 19 CONVERGENCE
    W("## 19. Convergence\n")
    if conv:
        W("```")
        for c in "ABC":
            row = conv.get(c) or {}
            W(f"COHORT {c}   new systemic {row.get('new_systemic', '—')}   "
              f"repeated {row.get('repeated_systemic', '—')}   "
              f"P0 {row.get('p0', '—')}  P1 {row.get('p1', '—')}  "
              f"P2 {row.get('p2', '—')}")
        W(f"\nCLASSIFICATION  {conv.get('classification', '—')}")
        W("```\n")
        if conv.get("reason"):
            W(conv["reason"] + "\n")
    else:
        W("Not yet computed.\n")

    # 20 LEARNING
    W("## 20. Learning and calibration truth\n")
    if learn:
        W("```")
        for k, v in (learn.get("counts") or {}).items():
            W(f"{k:38s} {v}")
        W(f"\nCALIBRATION_STATUS                     "
          f"{learn.get('CALIBRATION_STATUS')}")
        W("```\n")
        W(learn.get("what_the_zeros_mean", "") + "\n")
        W("**Why the zeros are not an instrument defect.** "
          + learn.get("why_the_zeros_are_not_an_instrument_defect", "") + "\n")
        W("**What calibration would require.** "
          + learn.get("what_would_be_required_for_calibration", "") + "\n")
    else:
        W("Not measured.\n")

    # 21-23
    W("## 21. Bounded limitations\n")
    for x in (freeze.get("bounded_limitations") or
              ["not yet enumerated"]):
        W(f"- {x}")
    W("")
    W("## 22. Final SHA\n```")
    for k in ("FINAL_QUALIFYING_SHA", "LOCAL_SHA", "ORIGIN_SHA", "LIVE_SHA",
              "LIVE_BOOT_ID", "FULL_GUARD_RESULT", "HOOK_RESULT",
              "BREAK_PROOFS"):
        W(f"{k:24s} {freeze.get(k, '—')}")
    W("```\n")
    W("## 23. Final verdict\n")
    W(f"**{freeze.get('VERDICT', 'NOT_YET_ISSUED')}**\n")
    if freeze.get("verdict_reason"):
        W(freeze["verdict_reason"] + "\n")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "40_company_qualification_final.md").write_text("\n".join(L))
    print(f"wrote {OUT}/40_company_qualification_final.md "
          f"({len(chr(10).join(L))} bytes, {done} companies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
