# PRE-100 — live demo reliability

Governing priority this cycle: **the deployed guest demo, on a real device**.
An external tester typed `Meta` on a phone, was told the analysis had failed,
typed `Cloudflare`, was told the same, and then found a finished analysis by
clicking "Your analyses". Rubric scores were not the binding constraint; that
was.

Baseline deployed SHA: `eb18371`.

---

## 1. What the tester actually hit, measured not assumed

Reproduced live on `eb18371`, mobile viewport, fresh guest session.

`Meta` -> autocomplete resolved **Meta Platforms, Inc. · META · CIK 1326801**
(correct) -> run started -> progress page ended on:

> This analysis could not be completed, so there is no result to open.
> Every approved source failed to retrieve (too large).

**Both halves of that sentence were false.** The same run's `/brief` and
`/intro` listed **five sources read**, including Meta's own SEC 10-K and 10-Q,
and `/runs/<id>` rendered a readable result the whole time.

Classification of the failure, against the prompt's list: **C — a result
existed and the redirect never happened**, compounded by a failure message
that was never checked against the run's own retrieval record.

`Cloudflare` on desktop **passed** on the same build: it resolved, ran, and
auto-advanced to step 1 with a company-specific reading. Cloudflare is in the
validation manifest and has a domain; Meta has neither. That difference is the
whole story of this cycle.

---

## 2. Four distinct defects behind one symptom

### D1 — `FALSE_ANALYSIS_FAILURE` / `RESULT_READY_NOT_REDIRECTED`

`_progress` decided what to show from `run_state`, redirecting only on
`COMPLETE`/`PARTIAL`. But `_run_analysis` deliberately produces
`FAILED` + a stored bounded result — that is its documented behaviour, so a
company with usable evidence is not thrown away. Every such customer was told
there was nothing to open.

`_availability` already derived the right answer and its own docstring calls
it *"the single source every run route consults"*. The progress page never
called it. **A repair living in one function and read by another** is this
programme's oldest failure mode.

**Fix:** `result_readiness(run_id)` — the canonical customer lifecycle
(`CREATED` / `RESOLVING_IDENTITY` / `RETRIEVING` / `ANALYSING` / `COMPOSING` /
`RESULT_READY` / `DEGRADED_RESULT_READY` / `BLOCKED_RECOVERABLE` /
`FAILED_FINAL`). `opens_result` is true **iff** a customer-readable result
exists, and `FAILED_FINAL` is the only state permitted to report a final
failure. `_progress` asks it, before and after the stale-worker check.

### D2 — the failure sentence asserted "every" without counting

`_failure_explanation` printed *"Every approved source failed to retrieve"*
whenever **any** source failed. The count that contradicts it was one call
away. Now it says how many failed and how many were read.

### D3 — third-party filings fetched against the wrong byte budget

`_emit` in `third_party_filings.py` set no `max_bytes`, so `fetch_approved`
fell back to the 2MB cap meant for an arbitrary untrusted host. Every one of
these candidates is a 10-K on sec.gov — the publisher whose measured document
sizes are why `MAX_FILING_BYTES` (16MB) exists. All four of Meta's third-party
filings returned `too_large`.

This is the **only source class in the product independent of the subject**,
being discarded by a default. Fixed: same publisher, same budget, same
truncation rule.

### D4 — composition raised for every domainless filer

The real reason Meta's run transitioned `FAILED`:

```
analysis failed run=... stage=composition
UnsafeURLRejected: a company website URL is required
```

`create_run` deliberately opens a run on a CIK alone — the regulator records
no web domain, and substituting one would make **the regulator** the company's
website. But `CompanyInput.validate()` unconditionally required a website, so
**every company entered by name that resolves only to a filer** (Meta, Toyota,
Vale) failed in composition, not in retrieval.

Fixed: the URL is validated when present. The SSRF wall is not weakened — it
guards URLs we *fetch*, and still runs on all of them. A company we hold no
website for is a company whose website we will not be dialling. The run
identity seed falls back to the company name so two domainless filers on one
day cannot collide.

---

## 3. Meta produced nothing even once it completed

Fixing the lifecycle would have redirected the tester to a page saying *"No
strategic reading of Meta Platforms, Inc. cleared the evidence bar"* — an
honest sentence and a worthless demo, and explicitly forbidden by §57.

Cause: `business_model_class` was `UNKNOWN`. The intro said *"not in the
validation manifest and no regulator industry classification was found"* — but
the second clause was untrue. A SIC-based classifier already existed; nothing
on the strategic-read path ever passed it a `registrant`. **A capability with
no caller.**

Wiring it alone would have been worse than the bug: SIC 7370 maps to
`SUBSCRIPTION_SOFTWARE`, and reading Meta as a contracted-subscription
business selects every downstream mechanism, metric and competitor wrongly —
confidently wrong rather than incomplete.

The taxonomy had **nine rows and none of them was Meta's business**. SIC 7370
holds both halves of a split with opposite economics: Salesforce sells a
contracted seat that renews; Meta sells an auction-priced impression that must
be re-won every time a user returns. The SIC code cannot separate them.

**Fix, in two parts:**

1. A tenth class, `ADVERTISING_PLATFORM`, with its own economics (auction
   price per impression, engagement as the revenue driver, distribution
   platforms as the binding supplier, discretionary and cyclical demand).
2. `revenue_model_hint()` — the discriminator reads **the filer's own revenue
   sentence**, not the industry code. Meta's 10-K: *"we generate substantially
   all of our revenue from selling advertising placements on our family of
   apps to marketers."*

Deliberately narrow: it requires "revenue" and "advertis-" in one clause, so
"advertising expense" — a cost line in nearly every filing — cannot reclassify
a consumer brand as an ad platform.

**Measured, live filings:**

| company | hint | outcome |
|---|---|---|
| Meta | `ADVERTISING_PLATFORM` | reclassified |
| Alphabet | `ADVERTISING_PLATFORM` | reclassified |
| Cloudflare | `None` | stays subscription software |
| Salesforce | `None` | stays subscription software |
| Adobe | `None` | stays subscription software |

Wired at every call site: `strategic_read.compose`, the history selection and
the simulation, each fed from the run's **own** CIK and its **own** documents
(competitor filings excluded, so a rival's advertising revenue can never
classify this company).

Meta now opens with:

> Meta Platforms, Inc. is a software platform business that runs on attention
> resold to advertisers: revenue is an auction price per impression, so
> nothing is contracted forward and each period's revenue has to be re-earned
> by engagement.

---

## 4. Flow and first-screen repairs

* **Landing is no longer the form** (§8). `/` carries the promise, `Try the
  demo` and `Log in`, and nothing else. The form moved to `/demo`.
* **`Try the demo` reaches the company question** rather than looping back to
  the pitch.
* **Positioning updated** (§9) — the old copy described retrieval; the product
  produces a strategic read.
* **"Your analyses" removed from the progress page** (§5). It was how the
  tester found their result, and needing it is the defect. The page now says
  *"We're building the analysis now."* and redirects itself.
* **Primary buttons were invisible as primary in dark mode** — a blanket
  `:root button` floor outranked the accent, so the dominant control on the
  first screen and an inert text field were the same colour. Affected the
  existing `Analyse company` button too.
* **Empty ARIA status box** — the autocomplete live region inherited a tinted
  `[role=status]` panel and rendered a 38px empty box directly under the only
  input on the entry screen. It now paints nothing until it has something to
  say, and stays in the DOM so assistive technology keeps watching it.

---

## 5. Proof

`tests/test_demo_reliability.py` — 10 tests. **All 10 fail on `eb18371` and
pass after the repair** (verified by checking out the pre-repair files and
re-running).

Two existing tests were found to be **vacuous** under the new invariant: they
asserted wording against what had become an empty redirect body. Both were
repaired to clear the result first, so they can fail for the reason they were
written.

A retry is offered **only** where retrieval graded the failure retryable
(429/5xx) or the worker vanished. Treating every `FAILED` run as recoverable
would put a button in front of a customer whose sources all answered 403 — a
recovery loop wearing a helpful face, and `manual_recoveries` must be 0.

---

## 6. Open, and honestly not closed

* **Competitive specificity.** Meta's live intro lists *"AT&T Inc, Alphabet
  Inc and Automation absorbing the task itself"* as its most direct
  contest. Alphabet is right; AT&T is an artefact of third-party filing
  search. `company_specificity` and `competitive_specificity` remain open from
  the previous cycle and were **not** re-tuned.
* **A prose defect** on the Meta intro: a sentence starting lower-case and an
  awkwardly embedded question clause.
* `NAMED_BY_RIVAL` remains unmeasured.

**Gate: NOT PASS. Not frozen. Breaker-10 not started.**
