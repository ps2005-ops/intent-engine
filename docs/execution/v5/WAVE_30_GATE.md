# The Wave-30 gate, and the 100-company program as a non-node invariant

The 100-company program is **not a node in `TASK_GRAPH.yaml`** and should not
be forced into one. The graph requires every node to name its producer,
persistence, reload, consumer, surface, telemetry, failure states, live proof,
adversarial proof and mutation target before implementation, and
`frontier.py --check` refuses anything less. A validation *programme* is not
that shape — it is a loop that runs over the whole product.

So it is recorded here as an **explicit non-node invariant**, which is what the
Batch 11 instruction allows when something load-bearing is not a node. Its
durable state lives in:

| what | where |
|---|---|
| population | `docs/execution/v5/COMPANY_VALIDATION_MANIFEST.yaml` (v1.0.0, 100 companies) |
| cohort selection | `intent_engine.validation.breaker_ten()` — deterministic |
| wave runner | `scripts/v5_breaker_wave.py` |
| results | `reports/v5/breaker_10/*.json` |
| defects | `reports/v5/breaker_10/defects.json` |
| this gate | this file |

## External gate

`BACKEND_CREDITS` — **BLOCKING the intelligence baseline.** Preflight in
Batch 11 returned `CREDITS_EXHAUSTED` (valid key, exhausted balance). This is
not a product defect and no amount of engineering clears it. Everything below
the line "requires reasoning" is `BLOCKED_EXTERNAL_CREDITS`, **not FAILED**.

## Wave-30 gate — current status

Wave 30 opens only when every row is satisfied. It is not "the runner works".

| criterion | status |
|---|---|
| identity joins correct 10/10 | **MET** — 10/10 stamped `DEVELOPMENT` / `1.0.0` after BW10-001 |
| no substitutions | **MET** — the frozen ten, twice |
| no crashes | **MET** — 10/10 completed in both waves |
| typed failure funnel | **PARTIAL** — types are typed; counts land next wave (BW10-008) |
| same-company subdomain policy coherent and security-tested | **MET** — BW10-004, 42 adversarial cases, 35 negative controls pre-verified against the old code |
| timeout tail understood and materially improved | **MET** — BW10-005, cohort wall 467s→221s, max 178.9s→45.8s, no evidence lost |
| evidence-family coverage measured | **MET** — measured; `strategy` still missing 7/10 |
| independence measured | **NOT MET** — `EVIDENCE_INDEPENDENCE_UNAVAILABLE`; no producer exists |
| dossier states truthful | **MET** — partial/unavailable/first-observation all correct |
| no retrieval failure shown as company inactivity | **MET** — `host_unreachable` is retryable and about us |
| no backend outage shown as evidence weakness | **MET** — BW10-002 |
| no unresolved false completion at a load-bearing seam | **MET** for this batch |
| intelligence specialization measured | **BLOCKED_EXTERNAL_CREDITS** |
| evidence independence measured | **BLOCKED_EXTERNAL_CREDITS** |
| causal / refusal behaviour measured | **BLOCKED_EXTERNAL_CREDITS** |
| adversarial behaviour measured | **BLOCKED_EXTERNAL_CREDITS** |
| no universal-template collapse | **BLOCKED_EXTERNAL_CREDITS** |

**Verdict: Wave 30 is CLOSED.** Five criteria are blocked externally and one
(independence) has no producer. Retrieval is materially healthier; the
intelligence instrument has still never been read.

## What the two waves actually established

Retrieval convergence is real but **narrower than hoped**, and that is the
useful finding:

- The redirect policy was a genuine defect and recovered exactly the two
  refused subdomain redirects (+2 documents cohort-wide, 39%→40%). It was
  **not** the main cause of missing strategy evidence — that moved 8→7 of 10.
- The timeout tail was a genuine defect and is largely gone: 20 timeouts→4,
  cohort wall halved, and critically **no evidence was lost** (AMD 3→3 docs,
  McKinsey 1→1). That negative control held in production, not just in a test.
- **The yield story is HTTP 403/404 — 62 of 86 failures, unchanged by either
  fix.** Every one of the ten hits at least one 403; six also hit 404s. The
  403:404 split is not yet counted (BW10-008, counter now shipped).

403 and 404 are different defects. 403 is *we are being refused* — user-agent,
robots, bot defences. 404 is *we asked for the wrong URL* — a discovery
defect. Merging them would produce a fix aimed at neither.

## First next task

Populate `http_status_counts` on a rerun, split 403 from 404, and attack
whichever dominates. Do not scale to 30, and do not treat 40% as the target —
the target is decision-relevant independent evidence per unit of latency, and
independence still has no producer at all.
