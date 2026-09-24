# Adaptive Strategic Intelligence V2 — final executive summary

*Frozen at `712613b7588fdf989f22acfc37dab90455e7c2ad`. Every figure below is computed from
`reports/asi25_state.json` by `scripts/asi25_v2_close.py`; none is typed.*

## What was proven

| | |
|---|---|
| companies qualified | 25/25 |
| result = PASS | 24/25 |
| primary Q&A, status | 150/150 |
| primary Q&A, **semantic** | 150/150 |
| contextual follow-ups | 25/25 |
| cross-company contamination | 0 |
| UNEXPLAINED_COLLAPSES (forty's instrument) | 0 |
| UNEXPLAINED_COLLAPSES (strict instrument) | 0 |
| near-identical pairs between two **non-abstaining** companies | 0 |
| UI frames checked | 2150 (233170 elements, no sampling) |
| overflow / contrast failures | 0 / 0 |
| CORE p50 / p90 / max | 25.1s / 46.6s / 61.7s (targets 60/100/120) |
| break proofs held | 24/24 |

## What improved

* **Three customer-visible P0s closed**, every one found by reading a captured
  page rather than by a test going red — a quotation ending on a conjunction,
  and a decision question rendering broken English on three of four companies
  that had established anything of their own.
* **The abstention explanation is complete on 25/25 companies**: why the prior
  applies, what evidence was considered, why it did not override (where it did
  not), what could override it, and what to learn next.
* **Information priority** is present on 96.0% of
  companies and names a decision it would change and a source that would settle
  it on 96.0% — a field that **did not
  exist** on the forty.

## What did not improve

* **`EVIDENCE_LED` is 0** on this
  cohort against **3** on the forty.
* **Template collapse on the decision question is worse as a share.** One
  question covers 16 of
  22 companies that reached one
  (72.7%),
  against 22 of
  33
  (66.7%)
  on the forty.
* **76.0% of readings are `NAME_ONLY`** — grounded
  on nothing the company published.

The previous close reported *distinct questions 4 → 8* and *largest identical
group 22-of-33 → 7-of-14*. Those came from a **seventeen-company** artifact a
collector had declined to overwrite. Measured over all 25: distinct questions
4 → 7, largest group
22 → 16.

## What remains bounded

* `DECISION_GRADE_READING` is assigned by the harness from
  `independent_origins > 0` and never reads the grounding verdict.
* A learning rehearsal needs a date **and** a body on the same document; EDGAR's
  submissions index supplies dates without bodies, so the largest filers are
  among those refused.
* Market-dependent trust is `UNRATED` on the preview, which carries no dossiers.

## Why 22 abstentions are not a failure

This cohort is overwhelmingly private security companies with thin public
records. The product's truthful output for such a company is that it could not
establish a reading — and each one says so with a reason, an information
priority and a route back. `22/25` is the system knowing when
it cannot know. Manufacturing five more positive readings would have been the
failure.

## Why raw overlap is higher than the forty's

Because the cohort is harder, and because a truthful "we could not establish
this" resembles itself. The number is not hidden: under the forty's own
instrument the 25-cohort shows
41
near-identical pairs of
1800
against
39
of
4680
on the forty.

## Why `UNEXPLAINED_COLLAPSES = 0` matters

Because it is computed, not asserted: a pair counts as explained only by a fact
readable from the state file — a run that abstained, or an identical history
state. And because the load-bearing figure is the one beside it:
**0 near-identical pairs between two non-abstaining
companies**. With most of the cohort abstaining, "one of them abstained"
explains almost any pair by construction; pairs between two real readings are
the only place a genuine collapse could hide.

## What the 25 taught the system

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
* `EVIDENCE_LED` is 0 on this cohort.
  Until a company's own record can routinely move the decision, the decision
  question stays a function of its class.
* The decision-domain vocabulary is 2 archetypes
  wide across 25 companies.

## Findings

| id | severity | status | title |
|---|---|---|---|
| P0-4 | P0 | FIXED | a quotation ending on a joining word reached the evidence surface |
| P0-5 | P0 | FIXED | the decision question rendered broken English on three of four grounded companies |
| P0-6 | P0 | FIXED | a singular billing unit landed after the word 'more' |
| P1-4 | P1 | RECORDED_NOT_FIXED | DECISION_GRADE_READING never reads the grounding verdict |
| P1-5 | P1 | BOUNDED_NOT_DEFECT | the learning refusal counts documents that carried text, beside a history page counting documents that carried dates |
| P1-6 | P1 | ENVIRONMENT_LIMITATION | first progress render exceeds the 3s target on the first request after a deploy |
| P2-1 | P2 | RECORDED | a pattern analogue renders as a bare company name |
| P2-2 | P2 | RECORDED | a buyer beginning 'IT' is refused as a fragment |
| H-5 | HARNESS | FIXED | the previous close's differentiation headlines described 17 companies, not 25 |
| H-6 | HARNESS | FIXED_BY_A_SECOND_INSTRUMENT | the forty's overlap instrument is near-blind on the history surface |
| H-7 | HARNESS | FIXED | 36 false cross-company contaminations, all the word 'material' |
| H-8 | HARNESS | FIXED | the abstention audit demanded an element that is inapplicable to a grounded reading |
| H-9 | HARNESS | AVOIDED | the old-40 controls resolve their captures to the wrong cohort inside this worktree |
| H-10 | HARNESS | FIXED | a quoted source was scored as the product's own voice |
| P1-7 | P1 | FIXED | a client-side rendering shell was quoted as company evidence |
| P1-8 | P1 | RECORDED_NOT_FIXED | a bounded run explains itself less completely than the other bounded run |
| H-11 | HARNESS | FIXED | the UI dimension had NEVER been measured, across two closes |
| H-12 | HARNESS | FIXED | the stale-spinner detector matched 'loading' inside 'uploading' |
| H-13 | HARNESS | FIXED | the collector destroyed two fresh artifacts with stale ones |
| H-14 | HARNESS | FIXED | the UI measurement read overflow and contrast from keys that do not exist |

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
