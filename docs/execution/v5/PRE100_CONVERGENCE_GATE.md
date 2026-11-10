# PRE-100 CONVERGENCE GATE — measured, not declared

**FOUNDER SHA** `5e913ff` · **MARKET SHA** `9b01ff1` · **DEPLOYED SHA** `5e913ff`
**GUARD** 6261 passed, 16 skipped, no `--no-verify`
**Branches** `v5/founder` and `feat/founder-market-integration` both at `5e913ff`

    PRE100_EXECUTIVE_PRODUCT_GATE        = NOT PASS  (9 of 10 criteria met)
    SAFE_TO_BEGIN_100_COMPANY_PERFECTION = NO

One criterion is short. It is named in §3 with its measurement, and it is the
only thing between this and the gate. Everything else the convergence run was
asked for is built, deployed and proven on the live service.

---

## 1. What the screenshots were showing, and what replaced it

History Rewind changed **blocks of prose** when you moved the slider. It kept
the vintage wall honestly and a reader learned almost nothing from it, because
the question an executive asks about the past is comparative and quantitative:
*where did this company go, where did the record at the time imply it was
going, and where could it have gone?*

Three lines now answer that on one axis, in three declared epistemic states.

| Line | Basis | Where it comes from |
|---|---|---|
| Actual path | **OBSERVED** | XBRL company facts filed with the SEC |
| Market expectation | **MODELLED** | the prefix of that series knowable at the date |
| Better strategy | **COUNTERFACTUAL** | the same path with one decision changed |

**Why XBRL is the right series, and the thing that is easy to miss.** Every
fact carries *two* dates: the period it describes (`end`) and the day it was
filed (`filed`). Fiscal 2022 revenue is a fact about 2022 and was not
information anybody held until February 2023. The wall keys on `filed`, so
"what was knowable then" means what had actually been published — and leakage
is not a matter of discipline, because a later fact is not in the argument
list. `expectation_path` is a pure function of `index.knowable_by(cutoff)`,
and the adversarial test appends later years and asserts the answer does not
move.

**The index is not share price** (§20). It is revenue adjusted by the
operating margin it was earned at, so growth bought with losses counts for
less than the same growth earned profitably — which is the reading this
product exists to argue. The multiplier is floored at 0.10 because an
early-stage company can lose more than its revenue (Palantir, 2018) and an
index that inverts sign is a chart that is wrong in a way that looks like a
finding.

**The expectation model is written down** (§24). Two numbers per business
model class — a reversion anchor and a persistence — each with a stated
reason. A subscription base renews, so an unusual year decays slowly; a
commodity producer's unusual year was a price, and prices mean-revert fast
because supply responds to them. Nothing is fitted and nothing is per-company.

**The counterfactual is chosen by where the company actually is.** The class
supplies the mechanism; the *observed trajectory* — growth accelerating or
slowing, margin widening or narrowing — supplies the lever, the assumption
and the risk. Without that, Cloudflare's and Shopify's date panels were 94%
identical, because both are subscription software.

---

## 2. Absence became a rung, and did not become invention

The sentence that opened this run's brief:

> "No market snapshot has been published for this company, so there is no read
> on what investors currently expect."

True about our price feed; useless to a reader who asked a business question.
`executive/resolution.py` makes the intermediate rungs first-class —
OBSERVED, SUPPORTED, MODELLED, BENCHMARK, BOUNDED, COUNTERFACTUAL,
UNRESOLVED — and enforces at construction that anything below OBSERVED names
what it came from, and that UNRESOLVED carries a next measurement.

**The limit is absolute and is enforced, not remembered.** The same expectation
model answers that question from the company's own filed results, labelled
MODELLED, never called a consensus — and it returns `None`, and the passage
still says so, when there is no series to model from. Stripe has no filed
series and gets no chart; it gets the strategic alternative argued without
numbers, which is the honest answer for a private company rather than a
degraded one.

**Measured**: 0 unresolved absences and 0 absence headlines across 48 primary
pages, 7 companies (`scripts/customer_copy_sweep.py`).

---

## 3. The gate, criterion by criterion

Golden set: Cloudflare, Caterpillar, Shopify, Johnson & Johnson, Bank of
America, Stripe, plus Palantir.

| §92 criterion | Required | Measured | |
|---|---|---|---|
| Golden mean | ≥ 9.25 | **9.54** | PASS |
| History | ≥ 9 | **9.71** | PASS |
| Strategic synthesis | ≥ 9 | **10.0** | PASS |
| Full Analysis | ≥ 9 | **10.0** | PASS |
| Flow | ≥ 9 | **10.0** | PASS |
| Identity | ≥ 9.5 | **10.0** | PASS |
| SEV1 | 0 | **0** | PASS |
| Demo-blocking SEV2 | 0 | **0** | PASS |
| Forbidden absence copy | 0 | **0** | PASS |
| Persona mean (simulated) | ≥ 4.5 | **4.79** | PASS |
| **No core dimension < 8.5** | ≥ 8.5 | **company_specificity 8.0** | **FAIL** |

### The one blocker, stated exactly

`company_specificity` reads **8.0** on Cloudflare, Shopify, Johnson & Johnson,
Bank of America and Stripe. It is 10.0 on Caterpillar and Palantir.

The cap is applied by one rule in `report_rubric`: rivals are asserted, and
**none of them was named by the company itself in what this run read**. The
competitor set falls back to structural peers, which are honest and are not
this company's stated rivals — the row says so on the page.

This is a **retrieval** limit, not a composition one, and it is the same
constraint recorded across several previous cycles: a company-published source
names customers and partners freely and names competitors almost never, so
`COMPETES_WITH` needs a third party. It is not attempted here because closing
it means changing evidence selection, and a change to selection late in a run
with no budget left to re-measure it across seven companies is exactly the
kind of repair this programme has shipped inert before.

**What would close it**: extraction of the Competition section of the
subject's own annual filing, which does name rivals under obligation to be
accurate, gated by the grammatical rule already proven in `competitor_finder`
(a candidate's own sentence must name a contest and carry a verb). One wave
re-run measures whether it holds.

---

## 4. What is live and proven on `5e913ff`

Verified in a browser against the deployed service, not inferred from JSON.

* **Entity autocomplete.** Typing `cloudfl` returns *Cloudflare, Inc. · NET ·
  USA · cloudflare.com*. Keyboard path confirmed: ArrowDown sets
  `aria-activedescendant`, Enter confirms, `aria-selected` follows. A real
  combobox, and the form still submits without the script.
* **Entity confirmation.** "Analysing **Cloudflare, Inc.** NET · USA ·
  cloudflare.com — *change*" before the run, and again on the progress page
  as "not this company?".
* **Auto-advance.** Company name typed → suggestion picked → Analyse →
  progress → **Step 1, with no click**. Confirmed twice (Cloudflare,
  Palantir).
* **Progress page.** One stage ladder of eight named stages driven by
  producers, not by elapsed time. "This page moves to the analysis by itself
  … no need to click anything or come back later." The preview's in-memory
  limit is a footnote, not a boxed warning.
* **History simulator.** Three lines, six selectable dates, per-vintage
  scale, decision-point marker, band, and a date panel of six cards. Live for
  Cloudflare and Palantir.
* **Step 6 feedback.** Complete workflow. On the deployed preview it
  *honestly refuses* — no durable storage, so it says so rather than
  collecting under a false promise. Proven end-to-end where storage is
  durable: 1–5 score, three tags surviving the POST, four structured
  questions, run-scoped isolation, and tags landing in the existing defect
  taxonomy (`HISTORY_QUALITY`, `DATA_RESOLUTION_GAP`) with praise excluded.

**ZERO_ANTHROPIC re-proved**: all six steps and every secondary surface render
with no credential and `anthropic` raising on import. `REQUIRED_ANTHROPIC_CALLS
= 0`.

**Accessibility / responsive**: `surface_matrix` PASS on all six steps —
headings, landmarks, labels, media, colour tokens; viewports 375/390/768/1280/1440.

---

## 5. What reading the deployed pages found that the suite could not

Every one of these was green in 6,261 tests and visible in a browser.

1. **Stripe's chart was another company's revenue.** The CIK was read out of
   any SEC URL the run held, and a run legitimately holds third-party filings
   that merely mention the subject. Identity now comes from a source that is
   *about* the subject — and the discriminator was already in the data, since
   the subject's own filings are classed `investor_material` while a third
   party's are classed `competitor`.
2. **A third party's self-description on a Cloudflare slide.** "We are an
   emerging financial technology platform company" — Aether Holdings,
   describing itself, in a filing that mentions Cloudflare once as a vendor.
   A claim belongs to whoever made it; a third party's first-person sentence
   can never be about anyone else.
3. **A 10-K contents page opened slide 4** — and hardening the filing filter
   did not reach it, because the deck asked a *different* filter. One seam,
   two lists, and a defect that survived its own fix.
4. **The deck named no action, no risk and nothing to watch**, and the Full
   Analysis carried no bridge for Caterpillar. Both existed in the canonical
   read and on the *shallower* surfaces: a reader who went deeper got less.
5. **The counterfactual argued about two different decisions at once** —
   "a pricing action" paired with "cutting into a cyclical trough" — because
   two of its four fields came from a run scenario and two from the class.
   An alternative is a quadruple and is now taken whole.
6. **The progress page said the same thing twice** in two vocabularies.

And one that was not a product defect: five structural tests failed in the
full suite and passed in isolation, because `inspect.getsource` reads a file
by line number and the tree was being edited while the suite ran. Settled
against a clean baseline rather than argued about.

---

## 6. Built for the 100-company programme, deliberately not run

* `product_eval/company_matrix.py` — RUN → RUBRIC → DEFECTS → **CLUSTER** →
  REPAIR → RERUN → **DELTA** → PROMOTE. The two steps hand-running keeps
  skipping. A cluster of one produces nothing, because the repair would be a
  special case; a shared attribute counts only when somebody *outside* the
  cluster lacks it, because ninety of a hundred companies are public and
  "both are public" explains nothing.
* `product_eval/executive_personas.py` — CEO, CFO, CSO, PE operating partner,
  CISO. Carries `simulated=True` in every payload it produces, through
  aggregation, so it can never be reported as customer feedback (§72).
* `scripts/golden_wave.py`, `scripts/customer_copy_sweep.py` — the wave
  harness and the dead-end sweep, both exercised on seven companies so the
  framework is proven before a hundred runs are spent on it.

Cohorts come from the manifest and spread across business model class, so a
ten-company wave meets at least five kinds of business rather than ten
software companies.

---

## 7. Known and non-blocking

* `macroeconomics` 6.0 — correct when no macro channel has a mechanism for
  the company; the rubric rewards a channel that is shown, and showing one
  without a mechanism is the defect the score is protecting against.
* `qa_quality` 7.0 — the follow-up answers against the same state rather than
  re-reading; pre-existing and unchanged by this run.
* Feedback is switched off on the deployed preview for want of durable
  storage. The refusal is the correct behaviour and the reason it cannot be
  demonstrated live.
