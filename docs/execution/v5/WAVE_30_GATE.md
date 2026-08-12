# The Wave-30 gate, and the 100-company program as a non-node invariant

The 100-company program is **not a node in `TASK_GRAPH.yaml`** and should not
be forced into one. The graph requires every node to name its producer,
persistence, reload, consumer, surface, telemetry, failure states, live proof,
adversarial proof and mutation target before implementation, and
`frontier.py --check` refuses anything less. A validation *programme* is not
that shape — it is a loop that runs over the whole product.

So it is recorded here as an **explicit non-node invariant**. Its durable
state lives in:

| what | where |
|---|---|
| population | `docs/execution/v5/COMPANY_VALIDATION_MANIFEST.yaml` (v1.0.0, 100 companies) |
| cohort selection | `intent_engine.validation.breaker_ten()` — deterministic |
| wave runner | `scripts/v5_breaker_wave.py` |
| independence | `intent_engine.company_ingestion.independence` (`evidence_independence.v1`) |
| results | `reports/v5/breaker_10/*.json` |
| break proofs | `scripts/v5_independence_break_proofs.py` |
| this gate | this file |

## External gate

`BACKEND_CREDITS` — **BLOCKING the intelligence baseline.** Preflight in
Batches 11 and 12 returned `CREDITS_EXHAUSTED` (valid key, exhausted balance).
No amount of engineering clears it. Everything below the line "requires
reasoning" is `BLOCKED_EXTERNAL_CREDITS`, **not FAILED**.

In the b12_after wave this shows up as `observations = 0` for all ten. That
zero is downstream of the backend, not a property of the evidence, and the
runner now says so in `cohort_summary.evidence.observations_state`.

## The gate is now the CHAIN, not the yield

Wave 30 does not open because a document-yield percentage moved. It opens when
retrieval → valid evidence → **independent** evidence → learning → decision
value can each be read.

| # | criterion | status |
|---|---|---|
| 1 | 10/10 attempted, no substitution | **MET** — the frozen ten, four waves |
| 2 | no security regression | **MET** — 56 security tests green; the ordering change moves no eligibility rule; break proof 10 drives the reachability demotion |
| 3 | no catastrophic latency tail | **MET** — max 47.0s, p50 19.4s, cohort wall 226.6s |
| 4 | failure reasons measured | **MET** — `http_status_counts` populated: 404 = 28, 403 = 25 |
| 5 | Evidence Independence producer operational | **MET** — `evidence_independence.v1`, 10/10 companies `MEASURED` |
| 6 | duplicate inflation blocked | **MET** — proven by metamorphic tests and 10/10 break proofs; **0 duplicates and 0 republications actually observed**, so the guard is unexercised in production |
| 7 | missing vs zero states explicit | **MET** — `UNMEASURABLE` / `UNAVAILABLE` / `BLOCKED_EXTERNAL_CREDITS` distinguished and tested |
| 8 | independent evidence measured for all companies | **MET** — 10/10 |
| 9 | HIGH_ACTIVITY_LOW_LEARNING detector operational | **MET** — and it is **FIRING** (see below) |
| 10 | learning conversion measured | **NOT MET** — `UNAVAILABLE`: no per-row evidence→belief attribution exists on the founder path |
| 11 | credit-blocked components separated from engineering failures | **MET** |
| 12 | no known SEV-1 false completion | **MET for this batch** — one was found and fixed (below) |
| 13 | artifacts reproducible from frozen SHA + manifest version | **MET** — and it was **FALSE until this batch** |
| 14 | source concentration visible | **MET** — mean 0.82 |
| 15 | useful-evidence latency visible | **PARTIAL** — `seconds_per_independent_document` = 9.6s; the "that changed something" form needs criterion 10 |

**Verdict: Wave 30 is CLOSED.** Criteria 10 and 15 are not met, and criterion
9 is met by a detector that is reporting a problem.

## Why criterion 13 was false, and why that matters most

`.gitignore` carried an unanchored `validation/`, intended for live-preview
screenshots. Unanchored, it matched a directory at any depth and silently
swallowed `src/intent_engine/validation/` — the manifest loader, the cohort
deriver, and `breaker_ten()` itself.

Nothing complained. `git status` read clean in every worktree that happened to
have the file. But at a fresh checkout of the frozen SHA the wave could not
start, two tracked test modules failed at collection (80 assertions that had
never run there), and ten of the dossier break proofs mutated a file that did
not exist. When it was found, the only copy in existence was an untracked file
in one ephemeral `/private/tmp` scratchpad.

Criterion 13 had been reported MET while it was structurally impossible.

## What the b12 waves established

Retrieval got better and the system did **not** learn more, and that is the
finding.

| | before | after |
|---|---|---|
| document yield | 40.0% | **46.4%** |
| successful documents | 56 | **65** |
| HTTP 404 | 38 | **28** |
| HTTP 403 | 24 | 25 |
| documents retrieved | 64 | **72** |
| companies losing documents | — | **0** |
| independent documents | UNAVAILABLE | **9** |
| independent document share | UNAVAILABLE | **12.5%** |

The 404 fix worked: **52 of 52 404s came from guessed `known_path` probes and
zero from publisher-rendered `homepage_link`s.** Ranking attested URLs above
guesses removed 10 of 38, with no company losing a document.

But the lineage breakdown of all 72 documents is:

| lineage | n |
|---|---|
| `SAME_ORIGIN` | 56 |
| `REGULATOR_OR_PRIMARY_FILING` | 9 |
| `COMPANY_SELF_REPORT` | 7 |
| `INDEPENDENT_EXTERNAL_SOURCE` | **0** |

**Zero independent external sources across the entire cohort.** Every
independent observation the system has is a regulatory filing. Nine of ten
companies are `PARTIALLY_INDEPENDENT` — exactly one outside vantage point,
their own filing. Alimentation Couche-Tard is `SINGLE_SOURCE`: it has none.

So the extra documents this batch bought were 56 more pages of the companies'
own websites. `HIGH_ACTIVITY_LOW_LEARNING` is **DETECTED / DEGRADING**, and it
names the stage: *documents → independent evidence*.

## First next task

Not more yield. The measured bottleneck is that **discovery only ever proposes
the company's own domain plus filings**, so independence is structurally
capped near 12% no matter how well retrieval performs. Either off-domain
discovery becomes real, or the honest position is that this system reports what
companies say about themselves.

Second, criterion 10: independence is now measurable but nothing consumes it.
`evidence_independence` is not in `demo_dossier.contracts.FOUNDER_ALLOWED`, so
a founder block carrying it would have the field silently dropped into
`unknown_fields` — the "bridge never opened" failure, one line away.
