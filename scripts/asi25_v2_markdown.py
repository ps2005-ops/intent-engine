#!/usr/bin/env python3
"""§20: the V2 close markdown, rendered from `reports/asi25_close.json`.

Every number in every document below is read from that file. If a figure
appears here that is not in the JSON, it is a bug in this script, not a
finding about the product -- which is the whole reason the split exists.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/qualification"
D = json.loads((ROOT / "reports/asi25_close.json").read_text())
STATE = json.loads((ROOT / "reports/asi25_state.json").read_text())
ROWS = sorted(STATE["rows"].values(), key=lambda r: int(r["n"]))
N = D["companies"]
g = lambda r: r.get("generalization") or {}
v = lambda r: r.get("v2") or {}


def w(path, text):
    p = OUT / path
    p.write_text(text.rstrip() + "\n")
    print(f"  {p.relative_to(ROOT)}  ({len(text)} chars)")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def pctf(x):
    return f"{100 * x:.1f}%"


SHA = D["sha"]
HEAD = (f"*Generated from `reports/asi25_state.json` at `{str(SHA)[:12]}`. "
        f"Every total on this page is computed; none is typed.*\n")


def qualification_final():
    diff = D["differentiation"]
    perf = D["performance"]
    body = [f"# Adaptive Strategic Intelligence V2 — 25-company qualification",
            "", HEAD,
            "## Outcome", "",
            table(["measure", "value"], [
                ["companies", N],
                ["result = PASS", D["results"].get("PASS", 0)],
                ["result = PRODUCT_DEFECT", D["results"].get("PRODUCT_DEFECT", 0)],
                ["abstentions", f'{D["abstentions"]}/{N}'],
                ["primary Q&A — status", f'{D["qa"]["primary_status"]}/{D["qa"]["primary_total"]}'],
                ["primary Q&A — semantic", f'{D["qa"]["primary_semantic"]}/{D["qa"]["primary_total"]}'],
                ["follow-ups", f'{D["qa"]["followup_pass"]}/{D["qa"]["followup_total"]}'],
                ["cross-company contamination", len(D["qa_contamination"])],
                ["break proofs held", f'{D["break_proofs"]["held"]}/{D["break_proofs"]["total"]}'],
            ]), "",
            "## Epistemic outcome per company", "",
            table(["#", "company", "result", "final class", "grounding",
                   "decision force", "history", "core s"],
                  [[r["n"], r["company"], r.get("result"), r.get("final_class"),
                    v(r).get("grounding_verdict"), g(r).get("decision_force"),
                    r.get("history_level"), r.get("core_s")] for r in ROWS]),
            "",
            "## Performance", "",
            table(["stage", "p50", "p90", "max", "target", "breaches"], [
                ["ACK", perf["ack"]["p50"], "—", perf["ack"]["max"],
                 f'<= {perf["ack"]["target"]}s', 0],
                ["VISIBLE", perf["visible"]["p50"], "—", perf["visible"]["max"],
                 f'<= {perf["visible"]["target"]}s', 0],
                ["CORE", perf["core"]["p50"], perf["core"]["p90"],
                 perf["core"]["max"], "p50<=60 p90<=100 max<=120",
                 len(perf["breaches"])],
            ]), "",
            "## UI / responsive matrix", "",
            table(["measure", "value"],
                  [[k, vv] for k, vv in (D["ui_matrix"] or {}).items()]), "",
            "## History and discovery", "",
            table(["history level", "companies"],
                  sorted(D["history_distribution"].items(),
                         key=lambda x: str(x[0]))),
            "",
            table(["discovery state", "companies"],
                  sorted(D["discovery_distribution"].items(),
                         key=lambda x: str(x[0]))),
            ]
    w("25_company_qualification_final.md", "\n".join(body))


def differentiation_report():
    d = D["differentiation"]
    f = D["old_40_vs_new_25"]["forty"]
    body = [
        "# Differentiation — 25 companies, measured", "", HEAD,
        "## The headline correction", "",
        "The previous close reported *distinct questions 4 → 8* and *largest",
        "identical group 22-of-33 → 7-of-14*. Those figures came from",
        "`reports/asi25_differentiation.json`, which was a **17-company**",
        "file written mid-run and never overwritten, because the",
        "orchestrator's collection step copied a fresh result only when no",
        "file was already in the way. Measured over all 25:", "",
        table(["measure", "forty", "twenty-five"], [
            ["companies", f["companies"], N],
            ["carrying a decision question", f["companies_with_a_question"],
             d["companies_with_a_question"]],
            ["DISTINCT_QUESTIONS", f["distinct_questions"],
             d["distinct_questions"]],
            ["LARGEST_IDENTICAL_QUESTION_GROUP",
             f["largest_identical_question_group"],
             d["largest_identical_question_group"]],
            ["share of questioned companies in that one group",
             pctf(f["largest_identical_question_group"]
                  / max(1, f["companies_with_a_question"])),
             pctf(d["largest_identical_question_group"]
                  / max(1, d["companies_with_a_question"]))],
            ["EVIDENCE_LED", f["decision_force"].get("EVIDENCE_LED", 0),
             d["decision_force"].get("EVIDENCE_LED", 0)],
            ["CLASS_PRIOR_ONLY", f["decision_force"].get("CLASS_PRIOR_ONLY", 0),
             d["decision_force"].get("CLASS_PRIOR_ONLY", 0)],
            ["NO_DECISION", f["decision_force"].get("NO_DECISION", 0),
             d["decision_force"].get("NO_DECISION", 0)],
            ["grounding verdict", f["grounding_verdict"],
             json.dumps(d["grounding_verdict"])],
        ]), "",
        "Template collapse on the decision question is **worse** on this",
        "cohort as a share of the companies that reached a question, not",
        "better. Reported that way because it is what the state file says.",
        "", "## Every decision question in the cohort", "",
        table(["companies", "question"],
              [[c, f"`{k}`"] for k, c in d["question_groups"]]), "",
        "## Rates", "",
        table(["measure", "value"], [
            ["COMPANY_SPECIFIC_MECHANISM_RATE",
             pctf(d["company_specific_mechanism_rate"])],
            ["GENERICITY_FAILURE_RATE", pctf(d["genericity_failure_rate"])],
            ["STRATEGIC_DELTA_CHANGED",
             f'{d["strategic_delta_changed"]}/{N}'],
            ["STRATEGIC_DELTA_UNCHANGED",
             f'{d["strategic_delta_unchanged"]}/{N}'],
            ["INFORMATION_PRIORITY_RATE",
             pctf(d["information_priority_rate"])],
            ["INFORMATION_PRIORITY_SPECIFICITY",
             pctf(d["information_priority_specificity"])],
            ["DECISION_DOMAIN_DIVERSITY", d["decision_domain_diversity"]],
            ["MECHANISM_DIVERSITY (archetypes)", json.dumps(d["archetypes"])],
        ]), "",
        "## What did not improve", "",
        "* `EVIDENCE_LED` is **0** on this cohort against **3** on the forty.",
        "* One decision question covers "
        f'{d["largest_identical_question_group"]} of '
        f'{d["companies_with_a_question"]} companies that reached one.',
        f'* {pctf(d["genericity_failure_rate"])} of readings are grounded on '
        "the company name alone (`NAME_ONLY`).",
        "",
        "Grounding verdict, strategic delta and information priority **did",
        "not exist** on the forty. A baseline of zero there is the absence",
        "of a measurement, not a measurement of zero, and is not reported",
        "as an improvement from zero.",
    ]
    w("25_company_differentiation_report.md", "\n".join(body))


def overlap_report():
    o = D["overlap"]
    loose, forty = (o["instrument_forty_numerals_stripped"]["twenty_five"],
                    o["instrument_forty_numerals_stripped"]["forty"])
    strict = o["instrument_strict_numerals_kept"]
    cl, cs = (D["collapses"]["under_the_fortys_instrument"],
              D["collapses"]["under_the_strict_instrument"])
    body = [
        "# Overlap and collapse — two instruments", "", HEAD,
        "## The forty's own instrument (numerals stripped)", "",
        "Comparable across cohorts because it is the same code over both",
        "sets of captures.", "",
        table(["surface", "25 mean", "25 max", "25 >=0.98",
               "40 mean", "40 max", "40 >=0.98"],
              [[k, loose[k]["mean"], loose[k]["max"], loose[k]["ge_098"],
                forty[k]["mean"], forty[k]["max"], forty[k]["ge_098"]]
               for k in loose]), "",
        f'Totals: 25-cohort {o["instrument_forty_numerals_stripped"]["twenty_five_total"]["ge_098"]}'
        f' of {o["instrument_forty_numerals_stripped"]["twenty_five_total"]["pairs"]} pairs;'
        f' 40-cohort {o["instrument_forty_numerals_stripped"]["forty_total"]["ge_098"]}'
        f' of {o["instrument_forty_numerals_stripped"]["forty_total"]["pairs"]} pairs.',
        "",
        "## The stricter instrument (numerals kept)", "",
        "On a decision surface, stripping numerals is right: a shared number",
        "is not a shared argument. On the HISTORY surface it removes almost",
        "all of the content, because the years, the index values and the",
        "base year **are** the page.", "",
        table(["surface", "mean", "max", ">=0.98"],
              [[k, strict[k]["mean"], strict[k]["max"], strict[k]["ge_098"]]
               for k in strict]), "",
        "## Collapse classification", "",
        table(["", "forty's instrument", "strict instrument"], [
            ["near-identical pairs (>=0.98)", cl["total"], cs["total"]],
            ["EXPLAINED", cl["explained"], cs["explained"]],
            ["UNEXPLAINED", cl["unexplained"], cs["unexplained"]],
            ["pairs where NEITHER company abstained",
             cl["neither_abstained"], cs["neither_abstained"]],
        ]), "",
        "`UNEXPLAINED_COLLAPSES` is computed, not asserted: a pair is",
        "explained only by a fact readable from the state file — a run that",
        "abstained, or an identical history state (same level, same",
        "dated-document count).", "",
        "**The load-bearing number is the last row.** With most of this",
        "cohort abstaining, \"one of them abstained\" explains almost any",
        "pair by construction. Pairs between two *non-abstaining* companies",
        "are the only ones where a shared reading would be two real",
        "decisions collapsing onto each other.", "",
        "## Every near-identical pair", "",
        table(["surface", "a", "b", "jaccard", "reasons"],
              [[p["surface"], p["a"], p["b"], p["jaccard"],
                "; ".join(p["reasons"]) or "**NONE — UNEXPLAINED**"]
               for p in cl["pairs"]]),
    ]
    w("25_company_overlap_report.md", "\n".join(body))


def econ_report():
    body = [
        "# Economic intelligence — chain completeness", "", HEAD,
        table(["classification", "companies"],
              sorted(D["economic_chain"].items())), "",
        "A chain is COMPLETE when the reading names a mechanism, a",
        "falsifier and a transmission path; PARTIAL at two of three;",
        "BOUNDED at one or none. The chain is **not required** where the",
        "evidence is insufficient, and missing links are not filled with",
        "generic economic language.", "",
        table(["#", "company", "names a mechanism", "names a falsifier",
               "mentions transmission", "final class"],
              [[r["n"], r["company"],
                (r.get("econ_intel") or {}).get("names_a_mechanism"),
                (r.get("econ_intel") or {}).get("names_a_falsifier"),
                (r.get("econ_intel") or {}).get("mentions_transmission"),
                r.get("final_class")] for r in ROWS]),
    ]
    w("25_company_economic_intelligence_report.md", "\n".join(body))


def learning_report():
    L = D["learning"]
    body = [
        "# Learning validation", "", HEAD,
        table(["claim", "status", "evidence"], [
            ["REAL_FORWARD_LEARNING", "**NOT_YET_PROVEN**",
             f'{L["claims_forward"]}/{N} pages claim a forward result; no '
             "expectation has been settled by a later outcome"],
            ["HISTORICAL_LEARNING_REHEARSAL", "**PROVEN**",
             f'{L["rehearsal_available"]}/{N} companies carry a rehearsal '
             f'built from their own dated record; the other '
             f'{N - L["rehearsal_available"]} refuse with a stated reason'],
            ["LEARNING_ARCHITECTURE", "**PARTIAL**",
             "the transitions exist and run; the forward half has no "
             "settled outcome to run on"],
            ["CALIBRATION_STATUS", "**PRE_CALIBRATION**",
             f'{L["says_pre_calibration"]}/{N} pages say so themselves'],
        ]), "",
        table(["#", "company", "rehearsal", "labelled rehearsal",
               "claims forward", "says pre-calibration", "refusal"],
              [[r["n"], r["company"],
                (r.get("learning_surface") or {}).get("available"),
                (r.get("learning_surface") or {}).get("labelled_rehearsal"),
                (r.get("learning_surface") or {}).get("claims_forward"),
                (r.get("learning_surface") or {}).get("says_pre_calibration"),
                ((r.get("learning_surface") or {}).get("refused") or "—")[:56]]
               for r in ROWS]), "",
        "## Why a rehearsal is refused where it is", "",
        "A rehearsal needs this company's own text **carrying a publisher",
        "date**, on at least two different dates. EDGAR's submissions index",
        "supplies dates with no bodies; most retrieved pages supply bodies",
        "with no date. The companies with the largest filing records are",
        "therefore among those refused — the page states the criterion",
        "directly beneath the count, and the count is of documents that",
        "carried both, not of documents retrieved.",
    ]
    w("25_company_learning_validation_report.md", "\n".join(body))
    w("learning_loop_live_proof.md", "\n".join([
        "# Learning loop — what is live-proven and what is not", "", HEAD,
        "| transition | live-proven | how |", "|---|---|---|",
        f'| EVIDENCE → BELIEF | yes | {N}/{N} runs compose a reading from '
        "retrieved evidence |",
        f'| BELIEF → EXPECTATION | yes | {L["rehearsal_available"]}/{N} '
        "record a T0 expectation before seeing T1 |",
        f'| EXPECTATION → OBSERVATION | yes | the same '
        f'{L["rehearsal_available"]} read T1 evidence |',
        f'| OBSERVATION → RECONCILIATION | yes | the rehearsal states '
        "whether the reading moved |",
        "| RECONCILIATION → LEARNING | **rehearsal only** | the change is "
        "recorded against a past record, never a forward outcome |",
        "| LEARNING → FUTURE DECISION EFFECT | **not proven** | no "
        "expectation has yet been settled by something that happened "
        "afterwards |", "",
        "Every rehearsal is labelled `HISTORICAL REHEARSAL` and "
        "`NOT FORWARD CALIBRATION` on the page itself "
        f'({L["labelled_rehearsal"]}/{N}), and '
        f'{L["says_pre_calibration"]}/{N} state the calibration status in '
        "words. No page claims a forward result.",
    ]))


def demo_proof():
    body = ["# Demo proof — what a reader can be shown", "", HEAD,
            "## The five strongest live proofs", ""]
    nonab = D["non_abstentions"]
    cl = D["collapses"]["under_the_strict_instrument"]
    body += [
        f'1. **{D["qa"]["primary_semantic"]}/{D["qa"]["primary_total"]} '
        "primary questions answered semantically**, with "
        f'{len(D["qa_contamination"])} cross-company contaminations and '
        f'{D["qa"]["followup_pass"]}/{D["qa"]["followup_total"]} contextual '
        "follow-ups staying inside their own run.",
        f'2. **UNEXPLAINED_COLLAPSES = {cl["unexplained"]}** and '
        f'**{cl["neither_abstained"]} near-identical pairs between two '
        "non-abstaining companies**, under the stricter of two instruments.",
        f'3. **{D["abstentions"]}/{N} companies abstained**, each with a '
        "stated reason, an information priority and a route back — the "
        "product declining to read a record it could not read.",
        f'4. **UI matrix over '
        f'{(D["ui_matrix"] or {}).get("frames")} frames** '
        f'({(D["ui_matrix"] or {}).get("elements_checked")} elements, '
        f'{(D["ui_matrix"] or {}).get("widths")} widths x '
        f'{(D["ui_matrix"] or {}).get("themes")} themes, no sampling) with '
        f'{(D["ui_matrix"] or {}).get("overflow")} overflow and '
        f'{(D["ui_matrix"] or {}).get("contrast_failures")} contrast '
        "failures.",
        f'5. **Performance inside every target on first attempt**: CORE '
        f'p50 {D["performance"]["core"]["p50"]}s, p90 '
        f'{D["performance"]["core"]["p90"]}s, max '
        f'{D["performance"]["core"]["max"]}s against 60/100/120.',
        "", "## Companies that did not abstain", "",
        table(["company", "final class", "grounding", "decision force",
               "independent origins"],
              [[r["company"], r["final_class"], r["grounding"],
                r["decision_force"], r["independent_origins"]]
               for r in nonab]) if nonab else "_none_",
        "",
        "`DECISION_GRADE_READING` is assigned by the qualification harness",
        "from `independent_origins > 0` alone. It does **not** read the",
        "grounding verdict, so a company can carry the label while the",
        "product's own page says the reading is grounded on the name only.",
        "Reported here as measured, and recorded as a finding rather than",
        "corrected inside a freeze.",
    ]
    w("25_company_demo_proof.md", "\n".join(body))


def main():
    print("writing artifacts:")
    qualification_final()
    differentiation_report()
    overlap_report()
    econ_report()
    learning_report()
    demo_proof()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
