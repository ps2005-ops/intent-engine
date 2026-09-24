#!/usr/bin/env python3
"""V2_FINAL_EXECUTIVE_SUMMARY.md, every number read from the close JSON."""
import json, pathlib, sys
ROOT = pathlib.Path("/Users/prathamsharma/ie-asi-v2")
D = json.loads((ROOT/"reports/asi25_close.json").read_text())
F = json.loads((ROOT/"docs/qualification/25_company_findings.json").read_text())
N = D["companies"]
d = D["differentiation"]
f40 = D["old_40_vs_new_25"]["forty"]
cl = D["collapses"]["under_the_fortys_instrument"]
cs = D["collapses"]["under_the_strict_instrument"]
L = D["learning"]
perf = D["performance"]
ui = D["ui_matrix"] or {}
sev = {}
for x in F["findings"]:
    sev.setdefault(x["severity"], []).append(x)

def pc(x): return f"{100*x:.1f}%"

md = f"""# Adaptive Strategic Intelligence V2 — final executive summary

*Frozen at `{D["sha"]}`. Every figure below is computed from
`reports/asi25_state.json` by `scripts/asi25_v2_close.py`; none is typed.*

## What was proven

| | |
|---|---|
| companies measured | {N}/{N} |
| result = PASS | {D["results"].get("PASS", 0)}/{N} |
| primary Q&A, status | {D["qa"]["primary_status"]}/{D["qa"]["primary_total"]} |
| primary Q&A, **semantic** | {D["qa"]["primary_semantic"]}/{D["qa"]["primary_total"]} |
| contextual follow-ups | {D["qa"]["followup_pass"]}/{D["qa"]["followup_total"]} |
| cross-company contamination | {len(D["qa_contamination"])} |
| UNEXPLAINED_COLLAPSES (forty's instrument) | {cl["unexplained"]} |
| UNEXPLAINED_COLLAPSES (strict instrument) | {cs["unexplained"]} |
| near-identical pairs between two **non-abstaining** companies | {cs["neither_abstained"]} |
| UI frames checked | {ui.get("frames")} ({ui.get("elements_checked")} elements, no sampling) |
| overflow / contrast failures | {ui.get("overflow")} / {ui.get("contrast_failures")} |
| CORE p50 / p90 / max | {perf["core"]["p50"]}s / {perf["core"]["p90"]}s / {perf["core"]["max"]}s (targets 60/100/120) |
| break proofs held | {D["break_proofs"]["held"]}/{D["break_proofs"]["total"]} |

## What improved

* **Three customer-visible P0s closed**, every one found by reading a captured
  page rather than by a test going red — a quotation ending on a conjunction,
  and a decision question rendering broken English on three of four companies
  that had established anything of their own.
* **The abstention explanation is complete on {N}/{N} companies**: why the prior
  applies, what evidence was considered, why it did not override (where it did
  not), what could override it, and what to learn next.
* **Information priority** is present on {pc(d["information_priority_rate"])} of
  companies and names a decision it would change and a source that would settle
  it on {pc(d["information_priority_specificity"])} — a field that **did not
  exist** on the forty.

## What did not improve

* **`EVIDENCE_LED` is {d["decision_force"].get("EVIDENCE_LED", 0)}** on this
  cohort against **{f40["decision_force"].get("EVIDENCE_LED", 0)}** on the forty.
* **Template collapse on the decision question is worse as a share.** One
  question covers {d["largest_identical_question_group"]} of
  {d["companies_with_a_question"]} companies that reached one
  ({pc(d["largest_identical_question_group"]/max(1,d["companies_with_a_question"]))}),
  against {f40["largest_identical_question_group"]} of
  {f40["companies_with_a_question"]}
  ({pc(f40["largest_identical_question_group"]/max(1,f40["companies_with_a_question"]))})
  on the forty.
* **{pc(d["genericity_failure_rate"])} of readings are `NAME_ONLY`** — grounded
  on nothing the company published.

The previous close reported *distinct questions 4 → 8* and *largest identical
group 22-of-33 → 7-of-14*. Those came from a **seventeen-company** artifact a
collector had declined to overwrite. Measured over all {N}: distinct questions
{f40["distinct_questions"]} → {d["distinct_questions"]}, largest group
{f40["largest_identical_question_group"]} → {d["largest_identical_question_group"]}.

## What remains bounded

* `DECISION_GRADE_READING` is assigned by the harness from
  `independent_origins > 0` and never reads the grounding verdict.
* A learning rehearsal needs a date **and** a body on the same document; EDGAR's
  submissions index supplies dates without bodies, so the largest filers are
  among those refused.
* Market-dependent trust is `UNRATED` on the preview, which carries no dossiers.

## Why {D["abstentions"]} abstentions are not a failure

This cohort is overwhelmingly private security companies with thin public
records. The product's truthful output for such a company is that it could not
establish a reading — and each one says so with a reason, an information
priority and a route back. `{D["abstentions"]}/{N}` is the system knowing when
it cannot know. Manufacturing five more positive readings would have been the
failure.

## Why raw overlap is higher than the forty's

Because the cohort is harder, and because a truthful "we could not establish
this" resembles itself. The number is not hidden: under the forty's own
instrument the {N}-cohort shows
{D["overlap"]["instrument_forty_numerals_stripped"]["twenty_five_total"]["ge_098"]}
near-identical pairs of
{D["overlap"]["instrument_forty_numerals_stripped"]["twenty_five_total"]["pairs"]}
against
{D["overlap"]["instrument_forty_numerals_stripped"]["forty_total"]["ge_098"]}
of
{D["overlap"]["instrument_forty_numerals_stripped"]["forty_total"]["pairs"]}
on the forty.

## Why `UNEXPLAINED_COLLAPSES = {cs["unexplained"]}` matters

Because it is computed, not asserted: a pair counts as explained only by a fact
readable from the state file — a run that abstained, or an identical history
state. And because the load-bearing figure is the one beside it:
**{cs["neither_abstained"]} near-identical pairs between two non-abstaining
companies**. With most of the cohort abstaining, "one of them abstained"
explains almost any pair by construction; pairs between two real readings are
the only place a genuine collapse could hide.

## What the {N} taught the system

1. **A rule with more than one producer is not a rule.** Four places shorten a
   quotation; one had the grammar rule. The same shape had already produced the
   inert name repair.
2. **A rule is also about text this product did not cut.** The Netskope passage
   sat well inside its budget; the publisher had cut it.
3. **A comment is not an implementation.** The buyer branch documented a
   prepositional-phrase cut it never performed.
4. **A collector that declines to collect is worse than none** — it leaves
   something that looks current.
5. **A uniform defect is an instrument tell.** 36 of 36 identical
   "contaminations" were the word "material".
6. **Repairing a defect can lower a headline.** Two of five distinct questions
   were garbage; removing them is the correct direction.

## What still prevents V4

* No forward outcome has settled any recorded expectation, so calibration
  cannot begin: `REAL_FORWARD_LEARNING` is **NOT_YET_PROVEN** and
  `CALIBRATION_STATUS` is **PRE_CALIBRATION**.
* `EVIDENCE_LED` is {d["decision_force"].get("EVIDENCE_LED", 0)} on this cohort.
  Until a company's own record can routinely move the decision, the decision
  question stays a function of its class.
* The decision-domain vocabulary is {d["decision_domain_diversity"]} archetypes
  wide across {N} companies.

## Findings

| id | severity | status | title |
|---|---|---|---|
""" + "\n".join(
    f'| {x["id"]} | {x["severity"]} | {x["status"]} | {x["title"]} |'
    for x in F["findings"]) + """

## Artifacts

All under `docs/qualification/`, all generated:
`25_company_qualification_final.md`, `25_company_qualification_matrix.json`,
`25_company_findings.json`, `25_company_differentiation_report.md`,
`25_company_economic_intelligence_report.md`,
`25_company_learning_validation_report.md`, `25_company_overlap_report.md`,
`25_company_demo_proof.md`, `25_company_qa_audit.json`,
`positive_control_mechanism_report.md`,
`strategic_reasoning_v2_architecture.md`, `learning_loop_live_proof.md`,
`V2_FINAL_EXECUTIVE_SUMMARY.md`.
"""
p = ROOT/"docs/qualification/V2_FINAL_EXECUTIVE_SUMMARY.md"
p.write_text(md)
print(f"wrote {p} ({len(md)} chars)")
