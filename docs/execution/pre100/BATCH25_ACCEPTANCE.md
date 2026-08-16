# BATCH 25 — PRE100 ACCEPTANCE LEDGER

Source of truth. Context exhaustion must not erase progress.
Start: founder `6ef576d`, market `9b01ff1`, production `cfd4c3b` untouched.

## D14 — CLOSED (code + break-proofed); live proof pending

Two defects under one symptom, plus a third found while tracing.

**A. Prior-run lookup returned None.** Root cause was *not* the lookup logic.
A run's id is `ci-run:{subject}:{user}:{as_of}` and `as_of` was truncated to
`T00:00:00`, so the same company analysed twice by one person on one day is
**one run**. A second observation was structurally unreachable through the UI.
`/fresh` — whose entire purpose is "give me another one" — rebuilt the same key
and returned the run it was asked to replace.

**B. `/fresh` destroyed the prior.** It popped the old run's cached result,
correct only while fresh reused the same id. Once fresh gets its own run, the
pop deletes the very reading the new run is compared against.

**C. `hero()` had no state exclusivity.** All seven lines rendered in every
state, so FIRST_OBSERVATION also announced novelty and a decision effect
relative to the prior it had just said did not exist. The novelty count is the
tell: measured against the previous run's documents, so on a baseline it is the
whole corpus. `_second_iteration_body`'s "This did not add to what the system
knows" is likewise comparative and was suppressed for baseline/incomparable.

Note on the live sighting: run 1 was on `9a42372` and run 2 on `554e317` — a
deploy separated them and the preview holds sessions in memory, so that
particular pair was also EXPECTED_EPHEMERAL_LOSS. The defects above are real
and were found by reproducing it locally rather than by reasoning about it.

Break proofs (all RED for the stated reason, then restored):
lookup→None · FIRST_OBSERVATION renders delta lines · lookup crosses companies.

## D17 — CLOSED (with D22), live-verified on `8f2ea0c`

**The third instance of one defect class**, and the reason to stop patching it
locally. Same run `01M04D14B2JBT7J3HET3BZ5NBE`, same company, same moment:

- **X-Ray**: "Supported in direction, not in size · Pricing decision. For
  Cloudflare, Inc.: what to charge, and for what… The published market record
  — 6 evidence row(s) and 5 belief(s) — is consistent with the reading below."
- **Executive brief**: "No strategic reading of Cloudflare, Inc. cleared the
  evidence bar, so none is asserted here. That absence is itself the finding."
- **Presentation, slide 1**: "What Cloudflare, Inc. has published is not enough
  to read a strategy from, so none is put forward here."

**Root cause — a contract, not a bug.** Each surface consumes a *different*
decision object:

| Surface | Decision | Evidence it sees |
|---|---|---|
| X-Ray | `_executive_read(dossier)` | run retrieval **+ the market engine's published record** |
| brief / full / story / slides | `decision_of(report)` | this run's retrieval only |

Both are internally honest. They disagree because they are looking at
different evidence sets, and the customer sees a product that contradicts
itself about whether it has anything to say. This is the same seam that made
the X-Ray render empty (D13) and made every second reading INCOMPARABLE — the
third time a surface has been found reading a decision that does not carry
what it needs.

**Not fixed in place.** Repointing brief/full/slides at the composed decision
is exactly the change that broke the X-Ray in the other direction: those
renderers read reasoning-specific fields the composed object does not carry.
This needs one explicit contract naming which decision each surface consumes
and a conversion where they meet — not a fourth local patch. It is recorded as
demo-blocking: PRE100 cannot pass while a customer can read two opposite
answers on two clicks.

## LEDGER

| TEST | STATUS | SHA | COMPANY | ROUTE | DEFECT | PROOF |
|---|---|---|---|---|---|---|
| D14_LOOKUP | PASS | local | Acme | `_prior_run` | D14A/B | 9 focused tests + 3 break proofs |
| D14_HERO_EXCLUSIVITY | PASS | local | — | `hero`/xray | D14C | state matrix over all states |
| D14_LIVE_RUN_A | PASS | dfe3a3a | Cloudflare | /runs/01M04B7B0V…/xray | — | baseline card, and ONLY the baseline sentence |
| D14_LIVE_RUN_B | PASS | dfe3a3a | Cloudflare | /runs/01M04BFQFG…/xray | — | "New evidence arrived, tested the view, and it held" · 2 new sources · recommendation unchanged |
| D14_LIVE_RUN_C | BLOCKED_DATA | dfe3a3a | Cloudflare | /runs/01M04BQF1P…/xray | — | not an exact replay: 1 source's content hash differed, so the live web returned something genuinely new. Exact replay is proven in unit tests; it cannot be staged against the live web, which changes between runs. |
| D16_RAW_EVIDENCE_IDS_ORIG | SUPERSEDED | dfe3a3a | Cloudflare | /xray second-look | D16 | "What it tested" renders `ev_1dccf2f4d0bd8562; ev_1fb641572cc55989; …` — opaque ids where a reader expects source names. The X-Ray already solved this once for its sources list (`citation_labels`); the second-look card never asked for the map. |
| CLOUDFLARE_JOURNEY | FAIL | fbb62ff | Cloudflare | all 6 surfaces | **D17** | all 6 surfaces render (682–2212 words), identity canonical everywhere, but X-Ray and brief/full/slides contradict on the central question |
| CROSS_SURFACE_CONSISTENCY | FAIL | fbb62ff | Cloudflare | X-Ray vs brief/full/slides | **D17** | see below |
| D16_RAW_EVIDENCE_IDS | FIXED (undeployed) | local | — | /xray second-look | D16 | labels threaded from `_citation_labels`; negative control pins unknown-stays-unknown |
| CATERPILLAR_JOURNEY | FAIL | fbb62ff | Caterpillar Inc. | X-Ray/brief | D17 | canonical identity PASS · SEC 10-K (2026-02-13) present · *capacity* decision (vs Cloudflare's *pricing*) = real specialization · D17 reproduces |
| BOA_JOURNEY | BLOCKED_DATA | fbb62ff | Bank of America Corporation | X-Ray | D18 | identity PASS, **no generic-"bank" regression** · X-Ray WITHHELD because no market snapshot is published · X-Ray and brief AGREE here, which pins D17's trigger to "market record present" · rate/credit mechanism unreachable without the snapshot |
| TOYOTA_JOURNEY | FAIL | fbb62ff | Toyota | X-Ray/sources | **D19**, D20 | no Northwind leakage (that regression holds) · but "no approved source could be retrieved" — the domainless EDGAR-first path returned nothing · /xray additionally showed a product-fault page (D20) |
| RESPONSIVE | PASS (partial scope) | fbb62ff | Cloudflare | /xray | — | 375px: scrollWidth==clientWidth, zero overflowing elements |
| DARK_LIGHT | PASS (partial scope) | fbb62ff | Cloudflare | /xray | — | dark: effective bg rgb(15,20,28), text rgb(243,244,246), ~16.8:1; secondary rgb(195,202,214) also AA |
| ACCESSIBILITY | PASS (partial scope) | fbb62ff | Cloudflare | /xray | D21 | one h1, no heading skips, nav+main landmarks, no raw JSON, details natively keyboard-operable · 1 unlabelled control (D21, SEV3) |
| SHOPIFY_JOURNEY | PASS (with D23) | 8f2ea0c | Shopify Inc. | /xray | D23 | "Supported in direction, not in size · Pricing decision"; identity canonical. **D23 (SEV3)**: classified "recurring software subscription" — same model class as Cloudflare — so merchant/GMV/take-rate economics never surface. A business_model_class selection gap, not prose. |
| JNJ_JOURNEY | PASS | 8f2ea0c | Johnson & Johnson | /xray | — | "Development roadmap decision — which programmes to fund and which to stop, given how long it takes a programme to reach approved products and indications"; model class = regulator-gated product. Genuine segment/regulatory specialization. |
| STRIPE_JOURNEY | PASS (partial) | 8f2ea0c | Stripe, Inc. | /xray | — | private/sparse handled: "earnings from a balance sheet or from a transaction network — spread and fees on volume the firm intermediates". No fabricated filings observed. MDR/MVE/VOI/kill-switch not individually re-read this batch. |
| VALE_JOURNEY | FAIL | 8f2ea0c | Vale | /sources, /xray | **D24** | run stalled at "Step 2 of 2 · Review sources" instead of auto-running, and that page reads "We found candidate evidence for ." — **empty company name**. /xray showed the product-fault page because the run was not terminal, so D20's guard did not apply. |
| CEO_QA | PASS | a7f60cd | Cloudflare + BoA | POST /conversation | D25 CLOSED | Cloudflare: "A supported reading of Cloudflare, Inc. exists and is set out on the Executive X-Ray… This run did not add enough independent evidence." BoA control: still refuses, agreeing with a Withheld X-Ray. One question exercised of the 22-question matrix. |
| PROVENANCE_LIVE | NOT_RUN | — | — | — | — | not opened in detail this batch |
| LEARNING_LIVE | NOT_RUN | — | — | — | — | — |
| ECONOMIC_HISTORY_LIVE | BLOCKED_DATA (honest) | a7f60cd | Cloudflare | /xray | — | re-verified: "Replay not yet valid. We hold 0 month(s)… clears on 2027-02-16" plus why today's revised data cannot be substituted into a historical T0. Correct state, useful while blocked. Caterpillar/BoA not read for this row. |
| PRESENTATION_SLIDES | FAIL | fbb62ff | Cloudflare | /slides | D17 | deck renders 7 slides and does not fabricate unsupported ones, but slide 1 asserts "not enough to read a strategy from" while the X-Ray asserts a supported pricing decision — the deck is downstream of D17, so this row cannot pass until D17 does. |
| TEMPLATE_SPECIALIZATION | PASS (partial scope) | fbb62ff | Cloudflare vs Caterpillar | /xray | — | genuinely different canonical state, not reworded prose: Cloudflare = *pricing* decision, "what to charge, and for what, without losing more customer count than the price gains", recurring-subscription model; Caterpillar = *capacity* decision, "how much capacity to commit, and when", long-lived manufactured product + parts/service stream. 2 of 6 companies, so scope is partial. |
| HOSTILE_BUYER | NOT_RUN | — | — | — | — | — |
| CUSTOMER_ACCEPTANCE | NOT_RUN | — | — | — | — | — |
| PROCESS_RESTART | EXPECTED_EPHEMERAL_LOSS | fbb62ff | Cloudflare | /runs/<id>/brief | — | preview restarted mid-session; run ownership and session were lost. This is DESIGNED ephemerality and it is disclosed to the reader on the progress page ("This preview stores runs in memory, so a restart can interrupt one") and on /analyses. Not classified as data loss. Durable persistence remains unproven here. |
| SECURITY | PASS (suite scope) | a7f60cd | — | — | — | 157 passed across tenant scope, event-consumer isolation, redirect-may-not-leave-approved-host, ingestion validation (SSRF/URL), run-route ownership, demo-mode gating. Adversarial live probes (prompt injection via filing, poisoned company name) NOT separately run. |
| ZERO_ANTHROPIC | PARTIAL | a7f60cd | — | — | — | `test_composition_makes_no_model_call` passes; `executive/contract.py` has zero HTTP/anthropic imports by construction. Full deployed-flow log inspection with the key removed was NOT run, so REQUIRED_ANTHROPIC_CALLS is proven 0 only for the executive composition path. |
| FINAL_SHA_SMOKE | NOT_RUN | — | — | — | — | — |


## D17 — BATCH 27 OUTCOME

**Fixed with a contract, not by normalising the objects.**
`src/intent_engine/executive/contract.py` settles one question — *does a
supported reading of this company exist* — with named merge states
(`CURRENT_RUN_SUPPORTED`, `MARKET_SUPPORTED`, `BOTH_SUPPORTED`,
`MARKET_STALE`, `MARKET_INVALID`, `MARKET_UNAVAILABLE`,
`NO_SUPPORTED_READING`). Surfaces keep their own prose and depth; none of them
recomputes that verdict. The asymmetry is deliberate: a market reading can
rescue a run that retrieved little, never manufacture support the run
contradicts, and a stale or unidentified snapshot contributes nothing.

Wired: primary screen, executive brief, full analysis, deck. 13 focused tests.
Four break proofs, hash-verified and restored byte-exact.

**Live on `ff92005`:**

| Control | Result |
|---|---|
| Cloudflare | **PASS** — X-Ray "Supported in direction, not in size · Pricing decision"; deck now reads "A supported reading of Cloudflare, Inc. exists and is set out on the Executive X-Ray. This run did not add enough independent evidence to strengthen the existing reading; it neither established nor contradicted it." |
| Bank of America (control) | **PASS** — X-Ray "Withheld" and deck "not enough to read a strategy from" **agree**. The fix did not make a market-unavailable company inherit a reading. |
| Caterpillar | **FAIL** — a fourth surface |

**D22 — the fourth site, SEV2, OPEN.** Caterpillar's `/slides` does not render a
deck at all: the route serves the insufficient-evidence page, which asserts
"There is not enough public evidence to build a briefing on this company"
while the X-Ray for the same run says "Supported in direction, not in size ·
Capacity decision". The contract fixed the surfaces that *render* a verdict;
this one **routes** on its own verdict before any renderer is reached, so
wiring the renderers could not reach it. Same class, one layer earlier.

**Two of my own fixes this batch shipped inert before working**, both found
only by re-reading the live page: the deck guard asked "is the thesis view
empty?" when the refusal *is* the view, and an earlier break proof silently
failed to apply until hash-verified. Both are the same lesson — a green test
plus a landed deploy is not evidence.


## D17 + D22 — CLOSED on `8f2ea0c`

D22 was the fourth instance of one class, and the sweep changed the fix. Three
routes funnel into `_insufficient_evidence_page`, so patching `/slides` — the
route that was caught — would have produced a fifth instance elsewhere. Fixed
once, at the sink. `docs/execution/pre100/EXECUTIVE_VERDICT_SITES.md` now
registers every site that decides this, MIGRATED or JUSTIFIED, with the sweep
terms to re-run.

| Control | X-Ray | Brief | Slides | Verdict |
|---|---|---|---|---|
| Cloudflare | Supported · Pricing decision | asserts the reading | "A supported reading of Cloudflare, Inc. exists…" | **PASS** |
| Caterpillar | Supported · Capacity decision | asserts the reading | "A supported reading of Caterpillar Inc. exists…" | **PASS** |
| Bank of America (control) | **Withheld** | denies | "not enough to read a strategy from" | **PASS** — no inherited reading |

Two of my own fixes shipped inert before working, both caught only by
re-reading the live page or by hash-verifying a mutation: the deck guard asked
"is the thesis view empty?" when the refusal *is* the view, and the first D22
test asserted on the contract object rather than the page and stayed green
when the page was mutated to ignore it. Live-payload fixtures, not authored
ones, is the rule that follows.

FEATURE_FREEZE = TRUE from this point.


## D19 — Toyota, narrowed not closed

`/xray` now shows the honest failed-run page (D20's fix working live): "did not
produce a report: not enough of what it needed could be retrieved, so no
reading is asserted here — we do not invent…". Retrieval itself still returns
nothing.

Tested and **disproved**: the "foreign private issuer files 20-F, not 10-K"
hypothesis — `20-F` is already in `_PERIODIC_FORM_PREFIXES`, `SUBSTANTIVE_FORMS`,
`_FORM_SCORE` and `_PREFERRED_FORMS`. Caterpillar and Bank of America were
entered the same name-only way on the same SHA and both retrieved filings, so
the domainless path works in general and this is Toyota-specific. Still
unclassified between PRODUCT_REGRESSION and BLOCKED_EXTERNAL; needs the CIK →
candidate → fetch-status trace, which is one bounded run with logging.


## BATCH 29 OUTCOME

**D25 CLOSED, live-verified on `a7f60cd`.** Q&A was the fifth surface deciding
for itself whether a reading exists. It now consumes the contract and keeps
everything else it does — explanation, citations, counter-evidence.

**The process fix is the durable part.** The hand-written register did not
prevent D25: Q&A was inside the sweep's search scope and never given a row, so
it was looked at and not written down.
`test_every_strategic_surface_is_declared_in_the_verdict_register` now walks
the dispatch table and fails when a strategic surface has no declaration. On
its first run it named five undeclared surfaces and surfaced two more
candidate gaps (`/story`, `/dashboard`) — found by a test, before deploy,
rather than by a customer reading a live page as the first five were.

**D26 disproved by measurement.** `/story` and `/dashboard` render through
`layers.py`, whose withheld branch gates on the same `brief.key_insight` — so
they looked like sites six and seven. Measured live on `a7f60cd`: neither
denies. The branch is not reached on a market-backed run. Fixing them would
have been wasted work, and this is the second time this batch that measuring
first saved a change (the Toyota 20-F hypothesis was the first).

| Row | Result on `a7f60cd` |
|---|---|
| CROSS_SURFACE_CONSISTENCY | **PASS** — Cloudflare: X-Ray, brief, full, slides, sources and Q&A all assert the same supported reading; BoA control: all withhold together |
| ACCESSIBILITY | **PASS** (structural, 6 surfaces) — one h1 each, no heading skips, one `main`, no raw JSON, zero unlabelled controls |
| RESPONSIVE | **PASS** at 375 — `/xray`, `/full`, `/slides`: scrollWidth == clientWidth, zero overflowing elements |
| DARK_LIGHT | **PASS** — effective bg `rgb(15,20,28)`, body text `rgb(243,244,246)`, ~16.8:1 |
| PRESENTATION | **PASS** — 7 slides, none fabricated, slide 1 now carries the contract |
| SECURITY | **PASS** (suite scope) — 157 tests |
| ZERO_ANTHROPIC | **PARTIAL** — composition proven no-model; deployed-flow log inspection not run |

**Still open:** D19 (Toyota retrieval, unclassified — the bounded trace was not
run), D24 (Vale), D23 (specialization census: 4 of 6 companies land on
"Pricing decision"; Cloudflare/Shopify/Stripe/BoA share it while Caterpillar
= capacity and J&J = development roadmap. Whether that is collapse or correct
is not yet adjudicated), PROVENANCE_LIVE, LEARNING_LIVE, HOSTILE_BUYER,
CUSTOMER_ACCEPTANCE.
