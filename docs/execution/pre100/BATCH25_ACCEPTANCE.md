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

## D17 — SEV2, DEMO-BLOCKING, OPEN

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
| SHOPIFY_JOURNEY | NOT_RUN | — | — | — | — | — |
| JNJ_JOURNEY | NOT_RUN | — | — | — | — | — |
| STRIPE_JOURNEY | NOT_RUN | — | — | — | — | — |
| VALE_JOURNEY | NOT_RUN | — | — | — | — | — |
| CEO_QA | NOT_RUN | — | — | — | — | — |
| PROVENANCE_LIVE | NOT_RUN | — | — | — | — | — |
| LEARNING_LIVE | NOT_RUN | — | — | — | — | — |
| ECONOMIC_HISTORY_LIVE | NOT_RUN | — | — | — | — | — |
| PRESENTATION_SLIDES | NOT_RUN | — | — | — | — | — |
| TEMPLATE_SPECIALIZATION | NOT_RUN | — | — | — | — | — |
| HOSTILE_BUYER | NOT_RUN | — | — | — | — | — |
| CUSTOMER_ACCEPTANCE | NOT_RUN | — | — | — | — | — |
| PROCESS_RESTART | NOT_RUN | — | — | — | — | — |
| SECURITY | NOT_RUN | — | — | — | — | — |
| ZERO_ANTHROPIC | NOT_RUN | — | — | — | — | — |
| FINAL_SHA_SMOKE | NOT_RUN | — | — | — | — | — |
