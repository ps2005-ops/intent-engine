# Product maturity ledger

What changed, why, and what it cost. One row per iteration, recorded as the
work happened rather than reconstructed afterwards.

The measurement is the offline customer-simulation suite
(`src/intent_engine/product_eval/`): every persona, on every kind of company,
including the ones that go wrong. It runs in about a second, which is why it
could be run after every change rather than at the end.

**A pass rate is not a score.** It rose four times in this programme because
the product improved, and fell twice because the harness started measuring
something it had been ignoring. The falls are the more useful rows.

---

## Starting baseline — 2026-07-28

| | |
|---|---|
| Branch | `feat/founder-intelligence-product-maturity`, from `origin/main` @ `5e9133b` |
| Deployed | `intent-engine-oatc.onrender.com` @ `5e9133b`, app `1.5.0-executive-intelligence` |
| Tests | 2,343 passed, 11 skipped |
| Evaluation | 57 cases, 84.2% pass |
| Open PRs | #1 `verify-alpaca-config` (unrelated, untouched) |

Known failures at the start:

- Sony returned **zero documents**; three cases refused a company that has
  plenty to say.
- A local business retrieved evidence and produced **no brief, no hypothesis
  and no slide**, and the pipeline reported success.
- A company with almost nothing public produced a broken empty report instead
  of declining.
- The reader with thirty seconds could not finish anything.

---

## Iterations

### 1 — Measure the product a reader is actually served

**Hypothesis.** The harness was scoring something other than what the product
renders, so its pass rate could not be trusted in either direction.

**Change.** Passed the run's documents to the deck builder (without them the
factual slides were built from a much smaller observation set and came out
empty). Wired each persona's declared questions to the brief fields and slides
that answer them — the persona list had been documentation, not a gate. Modelled
a multinational whose primary domain refuses automated access, so every usable
source is a curated investor page or a filing on another host.

**Before → after.** 84.2% → 86.0% (57 cases).

**Why it went down before it went up.** Two scoring corrections landed with it:
a deliberate refusal stopped being scored as a quality failure, and a deck under
five slides or a brief with no hypothesis behind it started failing. Both were
release criteria that nothing enforced. The visible failure count went from 9 to
8 while the number of *real* defects the suite could see went up.

**Commit.** `327c5df`

---

### 2 — Read the shapes a company outside software exhibits

**Hypothesis.** The "domain-neutral" signal set was itself software-shaped.

**Change.** Five signals for shapes only a company with physical operations or
formal disclosure exhibits — committed capacity, a written-down buyer
dependency, formal segment reporting, disclosed risk, owning both what is sold
and the channel that reaches people. Two patterns that read them.

**Before → after.** 86.0% → 96.5%. Sony: **0 hypotheses → 2**, on evidence it
always had. Palantir, Shopify, Linear and Notion all produce a thesis.

**Regression caught.** A title read as a clause rather than a complement
(`"Acme appears to be committing capital … before the demand for it is
certain."`). The existing grammar test caught it; the title was reworded rather
than the test loosened.

**Commit.** `afbaca3`

---

### 3 — Stop erroring on a question a reader would obviously ask

**Hypothesis.** Four conversation scenarios existed in the evaluation set and
appeared in no case, so nothing had ever typed a follow-up question.

**Change.** Thirty-two cases that ask real questions. On the first run:
*"this seems like a stretch — what argues against it?"* raised `KeyError` and
served an error page, because comparison had the loosest cues in the routing
table and was tried first, so a bare "like" beat an explicit "against".
Comparison now runs last, wins only when the question names something to compare
with, and the answer table is total by construction.

**Before → after.** Evaluation set 57 → 89 cases; 96.5% → 83.1%. The drop is
the point: thirty-two situations that had never been tested.

**Commit.** `f4a7aa0`

---

### 4 — Hold a company to the evidence its kind actually has

**Hypothesis.** Every gate was written against a public company, so a dental
practice was failed for having no strategy page — which only restates that it is
small.

**Change.** Research modes inferred from the evidence, not declared by the user.
Public-company numbers repeated unchanged, with a test pinning that a filer still
fails the direction check it always did. A small business is no longer required
to carry a venture-style hypothesis. Where no view can be supported, the brief
says so in its most prominent line instead of leaving it blank.

**Before → after.** 83.1% → 96.6%.

**Trade-off recorded.** `test_company_owned_pages_alone_cannot_pass` asserted a
specific check name in `failed_checks`. The guarantee it exists for — company
pages alone cannot carry a full report — still holds and is still asserted; the
check moved to `unmet_checks` for private companies. A second test was added so
the public-company path stays pinned.

**Commit.** `7b57daa`

---

### 5 — Answer the reader who will not scroll

**Hypothesis.** Shortening the brief for the thirty-second reader would cost
every other reader; truncating it would call cutting someone off "serving them".

**Change.** A headline that is a complete unit — what the company does, what is
thought to be happening, how much to trust it — in sixty words, creating no
claim of its own. The "what it does" line did not exist anywhere: the thesis
answers what is *changing*, which teaches a stranger nothing. Sentences are
scored rather than taken in order, with penalties for mission language, founding
history, corporate status and a sub-brand wearing the company's name.

**Before → after.** 96.6% → 100% (89 cases). All eight fixtures answer "what
does this company do" in a sentence a stranger can use.

**Commit.** `67aeeb7`

---

### 6 — Count vantage points, and say how each claim is known

**Hypothesis.** Every fixture scored an independent share of exactly zero, so
"independent corroboration raises confidence" and "company-owned evidence caps
it" were two rules no case could tell apart.

**Change.** Shopify gained customer reviews nobody at the company wrote. That
immediately exposed a miscalibration: confidence counted *source classes* as
diversity, so a company's investor page and its product page read as two
independent supports. Diversity is now counted in vantage points, and high
confidence is hard-capped without one outside the company. Every hypothesis
carries its provenance beside its confidence.

**Before → after.** Shopify's leading hypothesis: **high → moderate**
confidence, which is what the evidence supports. Pass rate unchanged at 100%
across 89 cases.

**Commit.** `93f52cd`

---

### 7 — Check the word "compatible" before printing it

**Hypothesis.** The brief said "reusing a compatible earlier analysis" with
nothing behind the word.

**Change.** Every stage that can change what a reader sees declares a version; a
composed analysis records what produced it; reuse compares them and re-runs on
any difference. An unstamped analysis is not assumed compatible, which also
means a run that ended badly no longer stays ended.

Fifty-one deterministic release tests, several constructing the failing case on
purpose — a gate only tested against inputs that pass is a gate nobody has tried
to open. One immediately caught that the mobile scenario appeared in no case.

**Before → after.** 89 → 91 cases, 100%. Suite 2,344 → 2,463 tests.

**Correction recorded.** The first mobile check reported two failures that were
the check's fault, not the product's: it read `max-width:900px` as a fixed width
and looked for a viewport declaration in a fragment that never carries one — the
page wrapper emits it. The check was fixed; no product change was made on the
strength of a false finding.

**Commit.** `062ccbf`

---

## Where the numbers ended

| | Start | End |
|---|---|---|
| Evaluation cases | 57 | 91 |
| Personas exercised | 20 | 24 |
| Scenarios exercised | 19 (4 declared, never run) | 25 (all run) |
| Pass rate | 84.2% | 100% |
| Tests | 2,343 | 2,463 |
| Companies with a strategic view | 3 of 8 | 8 of 11 (3 decline on purpose) |

A 100% pass rate means the harness has stopped finding things, not that the
product is finished. Every time it reached 100% in this programme, the next step
was to make it harder — and each time that produced real defects. The honest
reading of the final number is: *these 91 situations are handled; the next
useful information comes from a person, not from this suite.*
