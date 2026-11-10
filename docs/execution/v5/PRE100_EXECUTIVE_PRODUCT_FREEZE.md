# PRE-100 EXECUTIVE PRODUCT FREEZE

The Pre-100 engineering gate passed on `377ea63` and the customer gate was
reopened, because the product that gate approved opened, for Cloudflare, with

> "No strategic reading of Cloudflare, Inc. cleared the evidence bar, so none
> is asserted here."

and, where it did reach a conclusion, reached one about a different kind of
company: the primary screen described a global anycast network as committing
*"fixed cost in large increments"* against *"take-or-pay terms"* while
replacing *"ageing lines"* — while its own X-Ray, two clicks away, read the
same company correctly as recurring software with high operating leverage.

This document freezes what replaced that.

---

## 1. The frozen product flow

Six steps, one order, `← Back · Step X of 6 · Next →` and nothing else.

| # | Step | Route | What it is for |
|---|---|---|---|
| 1 | Introduction | `/runs/<id>/intro` | what this company is, and the question worth arguing about |
| 2 | Presentation | `/runs/<id>/slides` | the case, in slides |
| 3 | Full analysis | `/runs/<id>/full` | the reasoning, at board depth |
| 4 | The full story | `/runs/<id>/story` | the same conclusion as a narrative you can retell |
| 5 | History rewind | `/runs/<id>/history` | how it got here, and what could have gone differently |
| 6 | Connect your company | `/runs/<id>/connect` | what changes when it knows your own numbers |

`/runs/<id>` redirects to step 1.

**The eight-link grid is gone.** Every surface it named is still served and is
reached from inside the step that raises the question it answers:

| Secondary surface | Route |
|---|---|
| The answer (scrollable narrative) | `/runs/<id>/answer` |
| Executive X-Ray | `/runs/<id>/xray` |
| Intelligence | `/runs/<id>/dashboard` |
| Evidence — why this reading exists | `/runs/<id>/evidence` |
| Sources | `/runs/<id>/sources` |
| Executive brief | `/runs/<id>/brief` |

Owned by `founder_brief/flow.py`. `flow.STEPS` is the contract; a page that
wants a different order changes it there or not at all.

---

## 2. The frozen narrative contract

One object, `executive.strategic_read.StrategicRead`, composed once per
request and projected by every surface. Nothing else composes a strategic
read; the verdict register (`docs/execution/pre100/EXECUTIVE_VERDICT_SITES.md`)
records every site that touches one and where its verdict comes from.

**The rule that reopened the gate, and the rule that closes it.** A missing
third-party source reduces confidence, causal strength and measured
magnitude. It does not delete the synthesis, the recommendation, the scenario
or the experiment.

Three standings for the whole read:

- `SUPPORTED` — the company's own regulatory disclosure plus two or more
  sources it does not control;
- `BOUNDED` — supported in direction, not in size. The ordinary state for a
  public company read from public sources, and a real answer;
- `UNIDENTIFIED` — the ONE state in which no strategy is put forward. It is
  reached only when the business model is unclassified **and** the run's own
  reasoning concluded nothing. It still ships an experiment.

Four standings for any single sentence: `OBSERVED`, `STRONGLY_INFERRED`,
`BOUNDED_INFERENCE`, `UNMEASURED`. A surface may render what it likes as long
as it does not present a bounded inference as an observation.

Every read carries the complete bridge (§7): causal confidence, what is
known, what remains unknown, why it matters, the action now, the minimum
viable experiment, the kill switch, the falsifier, a VOI band and a guardrail.
`test_the_bridge_is_complete_or_it_is_not_a_bridge` fails if any is empty.

---

## 3. Frozen quality rubric

`product_eval/report_rubric.py` — 23 dimensions, scored 0–10,
deterministically, with no model call. Gate: overall ≥ 9.0; strategic
synthesis, actionability, company specificity and provenance each ≥ 9.0; no
core dimension < 8.0.

A sparse company can score 10: almost every dimension is scored against what
the READ contains rather than how much evidence existed. Evidence volume is
measured once, under `data_completeness`, and is not allowed to depress
anything else.

## 4. Frozen defect taxonomy

`product_eval/defect_taxonomy.py` — 20 detectors over the customer-facing
TEXT of a page, each carrying a severity, the surfaces it applies to and a
repair class (`SELECTION`, `COMPOSITION`, `ROUTING`, `EVIDENCE`,
`PRESENTATION`). Every one corresponds to a defect that was observed live.

## 5. Frozen self-correction loop

`product_eval/self_correction.py` — audit, targeted repair, re-evaluate,
bounded at two passes. Every repair either supplies a MISSING structural
element or REMOVES something unsupported. **No repair can make the product
assert more than it did before the audit**, which is the property that keeps a
self-correcting loop from becoming a self-convincing one.

`REQUIRED_ANTHROPIC_CALLS = 0` is a property of these files, not a
configuration of them.

---

## 6. Golden six — final scores

Scored by `scripts/golden_cycle.py`, which drives the real guest journey,
captures the visible text of every step, runs the taxonomy and scores the
rubric.

| Company | Business model | Overall | Min core | Findings |
|---|---|---|---|---|
| Cloudflare | SUBSCRIPTION_SOFTWARE | **9.78** | 10.0 | 0 |
| Caterpillar | MANUFACTURE_AND_AFTERMARKET | **9.78** | 10.0 | 0 |
| Shopify | SUBSCRIPTION_SOFTWARE | **9.78** | 10.0 | 0 |
| Bank of America | BALANCE_SHEET_OR_NETWORK | **9.78** | 10.0 | 0 |
| Stripe | BALANCE_SHEET_OR_NETWORK | **9.78** | 10.0 | 0 |
| Johnson & Johnson | REGULATED_PRODUCT_OR_PROVIDER | **9.42** | 8.0 | 0 |

Mean **9.72 / 10**. Zero SEV1, zero SEV2, zero SEV3 across all six.

J&J's 8.0 on company specificity is honest and is stated on the page: no
rival was found named in the filings this run retrieved, so its competitive
section carries classified peers labelled as peers rather than as rivals.

**Bank of America is the sharpest single result.** On `377ea63` it produced a
withheld recommendation — it has no market snapshot, so nothing rescued the
run's own silence. It now reads as a balance-sheet-and-network business with
spread economics, a named decision, and a bounded action.

---

## 7. Zero-Anthropic proof

`scripts/zero_anthropic_proof.py`, run on the frozen tree:

```
run 01M06RVVP23H73GGNT8CZX7P2Y — no credential, and `anthropic` raises on import use
  1. intro     200  22,740 chars  ok  Cloudflare — introduction
  2. slides    200  24,490 chars  ok  Cloudflare — presentation
  3. full      200  37,759 chars  ok  Strategic Intelligence — Cloudflare
  4. story     200  26,111 chars  ok  Cloudflare — the full story
  5. history   200  50,863 chars  ok  Cloudflare — history rewind
  6. connect   200  22,543 chars  ok  Cloudflare — connect your company
  + xray 200 · evidence 200 · sources 200 · brief 200 · answer 200 · Q&A 200

REQUIRED_ANTHROPIC_CALLS = 0
PASS
```

It removes every credential **and** replaces `anthropic` with a module whose
every entry point raises, so a path that tries anyway fails loudly rather than
degrading into a fallback nobody notices.

The hosted preview cannot serve this half — its key is set and the Render CLI
cannot unset an environment variable — so "absent" is proven here against the
same code the preview serves, and "completes" is proven there.

---

## 8. History proof

`executive/history_rewind.py`, live on Render for Cloudflare:

- **83 dated company filings, 2021-02-11 → 2026-08-13**, eight vintages, six
  annual accounts among them;
- the CSS-only slider works on the deployed page — selecting 2021-02 changes
  the vintage to *"February 2021 — the annual account"* and the company panel
  to *"By February 2021, Cloudflare had put 2 company filing(s) on the public
  record"*;
- the vintage wall is **structural**: `_before(filings, cutoff)` is the only
  way material enters a vintage, and the "what happened afterward" panel is
  built by a different function taking the complement. There is no code path
  in which a later filing reaches an earlier panel, so the wall cannot be
  breached by adding a field;
- three states stay distinct — `HISTORICAL_REPLAY`, `DESCRIPTIVE_HISTORY`,
  `REPLAY_NOT_YET_VALID` — and a descriptive vintage is never called a replay.

Ownership reports are excluded. Measured: 40 consecutive Cloudflare filings
covered seven weeks and 23 of them were Forms 4 and 144, so a timeline built
on the raw feed rewound to the summer and never reached an annual account.

---

## 9. Security, responsive, accessibility

- **Security**: the six new routes add no new authorisation surface. All three
  step handlers go through `_step_guard`, which does the ownership check and
  the in-flight redirect together, and
  `test_every_run_layer_route_calls_the_ownership_guard` now verifies the
  helper itself calls `_owned` before accepting delegation from any route. No
  route added here reads a tenant, writes a store, or takes a URL from
  retrieved content.
- **Responsive**: measured in a browser on the deployed page at 375px —
  `scrollWidth == clientWidth`, zero overflowing elements. The date rail
  scrolls inside its own container.
- **Dark mode**: measured on the deployed page in dark — worst text contrast
  **6.87:1** against an AA bar of 4.5:1, 58 elements checked, zero below AA.
- **Accessibility**: `scripts/surface_matrix.py` passes on all six steps —
  one `<h1>`, one `<main>`, no skipped heading level, every image with alt
  text, every SVG with a role, every control labelled. Three heading jumps
  introduced by the new steps were found here and fixed. The history slider is
  a radio group, so it is keyboard-navigable without any JavaScript.

---

## 10. Frozen invariants

| Invariant | State |
|---|---|
| Company entry | name only; no wrong-company fallback |
| Product story | six steps, sequential |
| Strategy | bounded strategic read, always, for an identifiable operating company |
| Evidence | strict provenance, four statement standings |
| Refusal | sub-claim level; never a whole-product dead end when a bounded read is possible |
| History | vintage-walled, structurally |
| Learning | permanent Learning Acceleration loop, surfaced in step 1 |
| Q&A | intent-complete, falls back to the canonical read, never denies what a step asserts |
| Security | zero trust |
| Hosted model | not required |

---

## 11. Remaining non-blocking defects

- **SEV3 — J&J competitive specificity.** No rival named in the filings that
  run retrieved, so peers are shown as peers. Honest and stated; would resolve
  with the Competition section of its 10-K in the retrieval set.
- **SEV3 — competitor recall.** The precision rule refuses single-word brands
  without mixed case, so "Fastly" and "Zscaler" are missed where "Akamai
  Technologies" is kept. Deliberate: a missed rival is a quiet omission, a
  fabricated one goes into a board meeting.
- **SEV3 — macro channels are empty for companies with no market snapshot.**
  The transmission chain requires published economic exposure; without it the
  section is correctly absent rather than generic.
- **SEV3 — Shopify is classified `SUBSCRIPTION_SOFTWARE`** by the validation
  manifest, though its merchant-solutions half is take-rate economics. The
  read is right about the subscription half and silent on the other.
- **SEV3 — `/feedback` guest exposure** unverified in this cycle.

**KNOWN_SEV1: 0 · KNOWN_DEMO_BLOCKING_SEV2: 0**

---

## 12. What this cycle should teach the 100-company programme

Every defect closed here was found by **scoring the deployed product**, not by
running the suite — which was green at 6,124 tests when the cycle began and is
green at 6,190 now. Two of them were found only in a browser, after the same
code had scored 9.78 locally: a certification scheme and the company's own
product were being named as its competitors, twice, in successive runs.

The instrument that found them is `scripts/golden_cycle.py`, and the reason it
works is that it reads what a customer reads. Carry it into the 100.
