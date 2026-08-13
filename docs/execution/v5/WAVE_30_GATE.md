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
| learning attribution | `intent_engine.company_ingestion.learning_attribution` (`learning_attribution.v1`) |
| discovery composition | `scripts/v5_discovery_composition.py` (`discovery_composition.v1`) |
| before/after | `scripts/v5_breaker_compare.py` |
| results | `reports/v5/breaker_10/*.json` |
| break proofs | `scripts/v5_independence_break_proofs.py`, `scripts/v5_batch13_break_proofs.py` |
| this gate | this file |

## External gate

`BACKEND_CREDITS` — **BLOCKING the intelligence baseline.** Preflight in
Batches 11, 12 and 13 returned `CREDITS_EXHAUSTED` (valid key, exhausted
balance).
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
| 1 | 10/10 attempted, no substitution | **MET** — the frozen ten, six waves |
| 2 | no security regression | **MET** — 195 security tests green; the ordering change moves no eligibility, host, scheme or redirect rule; 23/23 break proofs CAUGHT across both suites |
| 3 | no catastrophic latency tail | **MET** — per-company fetch p50 10.5s, max 18.5s, cohort fetch wall 102.1s |
| 4 | failure reasons measured | **MET** — 404 = 28, 403 = 13 (was 25), `too_large` = 11 (was 2), host_unreachable 16, timeout 4 |
| 5 | Evidence Independence producer operational | **MET** — `evidence_independence.v1`, 10/10 `MEASURED` |
| 6 | duplicate inflation blocked | **MET, and now EXERCISED LIVE** — 1 `DERIVED_REPUBLICATION` observed in the b13_after wave. Batch 12 could only prove this by test, with 0 duplicates and 0 republications in production |
| 7 | missing vs zero states explicit | **MET** — `UNMEASURABLE` / `UNAVAILABLE` / `BLOCKED_EXTERNAL_CREDITS` / `NOT_ATTEMPTED` distinguished, tested, and break-proofed |
| 8 | independent evidence measured for all companies | **MET** — 10/10 |
| 9 | HIGH_ACTIVITY_LOW_LEARNING detector operational | **MET — and it has STOPPED FIRING.** `DEGRADING` → `STABLE`: independent share 12.5% → 31.0%, above the 20% floor |
| 10 | learning conversion measured | **MET as `BLOCKED_EXTERNAL_CREDITS`** — the architectural absence is gone. `company_ingestion.learning_attribution` mirrors the market ledger's vocabulary, is wired into the wave and the dossier, and reports per company. On this cohort 9 of 10 are `BLOCKED_EXTERNAL_CREDITS` and 1 is `NOT_ATTEMPTED`. **No conversion NUMBER exists, and reporting 0 would be false** |
| 11 | credit-blocked components separated from engineering failures | **MET** |
| 12 | no known SEV-1 false completion | **MET for this batch** — one was found and fixed (below) |
| 13 | artifacts reproducible from frozen SHA + manifest version | **MET** — b13_before at `6645a4f`, b13_after at `e6347e9`, clean trees |
| 14 | source concentration visible | **MET** — mean 0.82 → **0.64** |
| 15 | useful-evidence latency visible | **PARTIAL** — `seconds_per_independent_document` 11.3s → **4.6s**. The "that changed something" form still needs a MEASURED criterion 10, which needs credits |

**Verdict, split as §45 requires — the two gates are not the same question:**

* **`WAVE_30_ENGINEERING_GATE = PASS`.** Every criterion that engineering can
  close is closed. The chain retrieval → documents → lineage → independent
  evidence → dossier is measured end to end on the frozen ten, reproducible
  from a frozen SHA, and break-proofed.
* **`WAVE_30_INTELLIGENCE_GATE = BLOCKED_EXTERNAL_CREDITS`.** Criterion 10 has
  a seam and no number; criterion 15's second form waits on the same thing.
  Neither is an architecture gap any more, and neither can be closed by more
  engineering.

**Wave 30 does not open on this alone.** The engineering gate passing is a
statement about the instrument, not about the intelligence. Scaling to 30
before a single company has demonstrated evidence → belief movement would
scale a measurement apparatus whose last link has never once been exercised.

## What the b13 wave established

Batch 12 concluded the independence ceiling was structural — that discovery
only proposed the company's own domain plus filings. **Measured, that was
wrong**, and the error mattered: it pointed the next batch at building a
discovery system that already existed.

Discovery was already proposing 69 independence-bearing candidates across the
cohort, 39 of them filings BY OTHER REGISTRANTS returned by an EDGAR full-text
query. Thirteen were approved. The ceiling was **selection and lineage**, not
discovery:

| | before | after |
|---|---|---|
| independent candidates approved | 13 of 69 | **25 of 69** |
| — of which attested filings | 1 | **25** |
| — of which guessed review URLs | 12 | **0** |
| documents | 72 | 71 |
| retrieval yield | 46.4% | 48.6% |
| HTTP 403 | 25 | **13** |
| independent documents | 9 | **22** |
| independent share | 12.5% | **31.0%** |
| `INDEPENDENT_EXTERNAL_SOURCE` | **0** | **15** |
| mean concentration | 0.82 | **0.64** |
| seconds per independent document | 11.3 | **4.6** |
| companies `INDEPENDENTLY_CORROBORATED` | 0 | **6 of 10** |

Cohort lineage: `SAME_ORIGIN` 56 → 41, `COMPANY_SELF_REPORT` 7 → 7,
`REGULATOR_OR_PRIMARY_FILING` 9 → 7, `INDEPENDENT_EXTERNAL_SOURCE` 0 → **15**,
`DERIVED_REPUBLICATION` 0 → 1.

**Raw document count fell by one.** That is the correct trade and the report
should not hide it: the cohort exchanged small failing review-site probes for
large third-party filings, and `too_large` rose 2 → 11 because a 10-K is a big
document. Four companies lost a document to the size cap; none lost one to a
new failure.

## The two defects behind "zero independent external sources"

**SELECTION.** Inside the `independent` evidence family a guessed review URL
and an attested third-party filing both scored 4, and the family takes one
candidate — so insertion order decided. Ten of ten companies spent their only
independent slot on a slug-built `g2.com` URL, for a bank, a miner, an
airframer and a pharmaceutical company alike. Batch 12 made exactly this
"attested beats guessed" repair for the company's own domain and the identical
defect survived one bucket over, where it was costing far more.

**LINEAGE.** `origin_family` read the HOST, so every document filed with the
SEC was one origin. United Airlines' own 10-K describing Boeing was labelled
`SAME_ORIGIN` as Boeing's own filing and dropped from the independent count.
Three distinct authors collapsed into one observation. A regulator is a venue,
not an author.

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

## The 100-company program's permanent metrics (§46)

These are now produced by the wave runner for every company and are the
measurements the 30/50/100 cohorts inherit. Each is named for the population
it divides, because this programme has shipped a "rate" whose numerator and
denominator counted different things.

| metric | population | b13_after |
|---|---|---|
| documents per company | documents | 7.1 |
| independent origins per company | origins | 2.2 |
| independent external evidence per company | documents | 1.5 |
| source-family diversity per company | origins | measured per row |
| source concentration per company | max origin / documents | 0.64 mean |
| effect-producing evidence per company | evidence rows | `BLOCKED_EXTERNAL_CREDITS` |
| learning conversion per company | rows / rows | `BLOCKED_EXTERNAL_CREDITS` |
| retrieval seconds per independent evidence | seconds / documents | 4.6s |
| dossier provenance quality | state | `AVAILABLE` (independence block crosses) |
| company specialization | requires reasoning | `BLOCKED_EXTERNAL_CREDITS` |

Two of these are permanently a state rather than a number until credits are
restored, and that is the honest form. A zero in either would assert that the
evidence taught the system nothing.

## What is NOT closed

**No company has demonstrated evidence → belief movement.** The seam exists,
is wired into production and the dossier, is break-proofed, and has never
carried a single real effect — because nothing on this cohort produced a
knowledge state to attribute against. Criterion 10 is met in the sense §44
requires (architecture is present) and unmeasured in the sense that matters
most.

**Independence is now measured and still not consumed by reasoning.** The
dossier carries origins, corroboration and a wording wall; no analyst reads
them, because the analyst is credit-blocked.

**`too_large` is the next retrieval bottleneck, and it is new.** It rose 2 →
11 because third-party filings are large. The codebase already knows the shape
of this fix — a 10-K is front-loaded, so truncation is survivable where
rejection is not — but changing a retrieval rule after the SHA was frozen
would have invalidated the comparison this batch exists to make.
