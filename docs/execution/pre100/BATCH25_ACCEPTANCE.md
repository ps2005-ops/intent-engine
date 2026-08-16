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

## LEDGER

| TEST | STATUS | SHA | COMPANY | ROUTE | DEFECT | PROOF |
|---|---|---|---|---|---|---|
| D14_LOOKUP | PASS | local | Acme | `_prior_run` | D14A/B | 9 focused tests + 3 break proofs |
| D14_HERO_EXCLUSIVITY | PASS | local | — | `hero`/xray | D14C | state matrix over all states |
| D14_LIVE_RUN_A | PASS | dfe3a3a | Cloudflare | /runs/01M04B7B0V…/xray | — | baseline card, and ONLY the baseline sentence |
| D14_LIVE_RUN_B | PASS | dfe3a3a | Cloudflare | /runs/01M04BFQFG…/xray | — | "New evidence arrived, tested the view, and it held" · 2 new sources · recommendation unchanged |
| D14_LIVE_RUN_C | BLOCKED_DATA | dfe3a3a | Cloudflare | /runs/01M04BQF1P…/xray | — | not an exact replay: 1 source's content hash differed, so the live web returned something genuinely new. Exact replay is proven in unit tests; it cannot be staged against the live web, which changes between runs. |
| D16_RAW_EVIDENCE_IDS | OPEN SEV3 | dfe3a3a | Cloudflare | /xray second-look | D16 | "What it tested" renders `ev_1dccf2f4d0bd8562; ev_1fb641572cc55989; …` — opaque ids where a reader expects source names. The X-Ray already solved this once for its sources list (`citation_labels`); the second-look card never asked for the map. |
| CLOUDFLARE_JOURNEY | NOT_RUN | — | — | — | — | — |
| CATERPILLAR_JOURNEY | NOT_RUN | — | — | — | — | — |
| BOA_JOURNEY | NOT_RUN | — | — | — | — | — |
| SHOPIFY_JOURNEY | NOT_RUN | — | — | — | — | — |
| JNJ_JOURNEY | NOT_RUN | — | — | — | — | — |
| STRIPE_JOURNEY | NOT_RUN | — | — | — | — | — |
| TOYOTA_JOURNEY | NOT_RUN | — | — | — | — | — |
| VALE_JOURNEY | NOT_RUN | — | — | — | — | — |
| CEO_QA | NOT_RUN | — | — | — | — | — |
| PROVENANCE_LIVE | NOT_RUN | — | — | — | — | — |
| LEARNING_LIVE | NOT_RUN | — | — | — | — | — |
| ECONOMIC_HISTORY_LIVE | NOT_RUN | — | — | — | — | — |
| CROSS_SURFACE_CONSISTENCY | NOT_RUN | — | — | — | — | — |
| PRESENTATION_SLIDES | NOT_RUN | — | — | — | — | — |
| TEMPLATE_SPECIALIZATION | NOT_RUN | — | — | — | — | — |
| HOSTILE_BUYER | NOT_RUN | — | — | — | — | — |
| CUSTOMER_ACCEPTANCE | NOT_RUN | — | — | — | — | — |
| RESPONSIVE | NOT_RUN | — | — | — | — | — |
| DARK_LIGHT | NOT_RUN | — | — | — | — | — |
| ACCESSIBILITY | NOT_RUN | — | — | — | — | — |
| PROCESS_RESTART | NOT_RUN | — | — | — | — | — |
| SECURITY | NOT_RUN | — | — | — | — | — |
| ZERO_ANTHROPIC | NOT_RUN | — | — | — | — | — |
| FINAL_SHA_SMOKE | NOT_RUN | — | — | — | — | — |
