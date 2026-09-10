# Adaptive Strategic Intelligence — handoff

> Status of this document: written during the build, completed after the
> frozen live matrix. Numbers below that describe a measurement were taken
> from the run named beside them; nothing here is estimated.

## What changed, in one paragraph

The product's entire differentiation machinery — pattern library, per-class
metrics, macro transmission table, causal questions, competitor set — is keyed
on `business_model_class`, which could previously only come from a curated
100-company manifest or an SEC industry code. Ten private companies had
neither, so all ten resolved `UNKNOWN` and every one of those tables switched
off. This phase adds a **third classifier** that reads the company's own
published account of how it is paid, ranked strictly below the other two, plus
an **adaptive layer** on top of it that selects a strategic lens from the
company's own evidence, ranks where better intelligence could change a
decision, builds an evidence-linked causal chain, states why the analysis is
different for this company, composes the report accordingly, and reorders it
for the reader's role without changing a single fact.

## Where the code is

| module | what it produces |
|---|---|
| `adaptive/classify.py` | business model class from the subject's own words |
| `adaptive/profile.py` | `CompanyStrategicProfile` — every field provenance-tagged |
| `adaptive/lens.py` | 12-lens library, hard applicability gate, published refusals |
| `adaptive/opportunity.py` | ranked `DecisionOpportunity` map, components exposed |
| `adaptive/causal.py` | change → mechanism → … → decision, each edge labelled |
| `adaptive/differentiation.py` | why-this-company, plus the collapse detector |
| `adaptive/composer.py` | which modules, in what order, at what depth, and why |
| `adaptive/roles.py` | nine roles, two live, an ordering and never a fact |
| `adaptive/engine.py` | one entry point, fixed order, never raises, full telemetry |
| `adaptive/render.py` | HTML only; decides nothing |

Seams into the existing product:

- `executive/company_profile.profile_for(..., published_text=)` — rung 3
- `executive/analysis_selection.select(..., published_text=)` — pass-through
- `executive/strategic_read.compose(..., published_text=)` — pass-through
- `webapp/app.WebApp._subject_published_text` — one assembler, two consumers
- `webapp/app.WebApp._adaptive` — per-request, per-role memo
- `webapp/app.WebApp._intro_page` — the adaptive block leads step 1
- `GET /runs/<id>/adaptive.json` — the telemetry the matrix reads
- `GET /runs/<id>/intro?role=<ceo|cso>` — the live role views

## Tests and proofs

| artefact | what it holds |
|---|---|
| `tests/test_adaptive_intelligence.py` | 36 properties, each with the measurement that forced it |
| `tests/test_adaptive_guards.py` | the 7 invariants the break proofs mutate |
| `scripts/break_proofs_adaptive.py` | 16 mutations, each replaying a defect that actually happened |
| `scripts/adaptive_ten_matrix.py` | the live qualification against the deployed service |

## Pre-flight validation, against real pages rather than fixtures

Before any live analysis was spent, the classifier and the lens router were run
over the ten companies' **actual published homepage text**, fetched directly.
A fixture I wrote to please my own rules proves nothing; real marketing prose
is what the retrieval layer will hand these producers.

    5 distinct primary lenses across the cohort, every one matching the
    section 13 expectation, and 0 of 28 pairwise collapses on the
    company-specific half.

It also found four defects that would each have cost a live analysis to
discover, and one that would have cost the primary screen:

| defect | what it did | how it was found |
|---|---|---|
| a rival's page classified the subject | Highspot read as a consulting firm at 13.0 against its own 9.0 | exercising the `_subject_published_text` seam directly |
| a customer testimonial became the self-description | *"Cyera gives me is almost immeasurable"* was about to be printed to an executive as "in its own words" | real page text |
| a client industry classified the vendor | Slalom scored 5.0 for `REGULATED_PRODUCT_OR_PROVIDER` on "clinical trials" and "patients" — the industries it *serves* | real page text |
| a product page carried no revenue statement | Monte Carlo resolved `UNKNOWN` while plainly selling software | real page text |
| the adaptive block could 500 the primary screen | `engine.build` cannot raise, but rendering can | reading the call site |

The first three were repairs to the producers. The fourth added four
first-party signals a real product page carries (`pricing`, `talk to sales`,
`contact sales`, `start free`) — general statements that a thing is sold, not
tuning for a company. The fifth made the block fail open, which is the same
contract the follow-up box beside it already had: losing the block costs a
feature, raising would cost the report.

### The seams, exercised rather than assumed

Two integration points decide whether any of this reaches a customer, and both
were driven directly rather than trusted:

- `_analyst_analysis` reconstructs a `StrategicAnalysis` from
  `strategic_report["strategic_analysis"]` — round-tripped and asserted,
  including the `None` case;
- `_subject_published_text` hands the classifier subject-owned material —
  which is where the rival-classifies-the-subject defect was caught.

A guard the caller does not honour is not a guard.

## What a reader should be suspicious of

**The class prior is still doing a lot of work.** `revenue_drivers`,
`cost_drivers`, `pricing_model`, `customer_structure` and
`competitive_structure` are all `CLASS_PRIOR` for a company with no filings.
They are true of the class and tagged as such, and `specificity` reports
exactly how much of each profile is class rather than company. Do not read a
high-confidence lens as a high-specificity profile — they are different
numbers and the product prints both.

**Two consultancies are hard to tell apart from marketing text alone.**
Slalom and Point B produce the closest pair in the cohort. That is a real
limit of what a consulting firm's public site says about itself, not a hidden
template — the detector flags it rather than hiding it.

**The evidence classifier reads marketing.** It is ranked last for exactly
that reason, and it refuses rather than guesses: applicability is enforced,
the margin is proportional, and the matched span is quoted so a reader can
disagree with it.
