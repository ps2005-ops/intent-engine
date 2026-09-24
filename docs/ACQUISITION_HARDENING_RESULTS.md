# Evidence-acquisition hardening — results

SHA under test: `d4ce3318`. Baseline SHA: `142ae2c6` (the PRE-100 candidate).
All local numbers are 20 companies of the frozen `QUALIFY_50`, driven through
production call sites with no model. Live numbers are the deployed preview.

## 1. The root cause, and how it was isolated

The live 50-company requalification produced 26/50 usable reports and 23
bounded abstentions. Two hypotheses were live: hosts refusing under cohort
load, or something in our own pipeline.

Applying the PRODUCTION time budget locally settled it. `_run_analysis` runs
discovery and retrieval under `Deadline.for_tier` reserving
`COMPOSE_RESERVE_S` — 40s of a 60s tier-1 budget — and the preview runs at a
~15% CPU share, so the effective budget is a small multiple tighter.

| condition (20 companies) | report-eligible | slot yield | failures |
|---|---|---|---|
| unbounded, memory cold | 19/20 | 73% | 125 |
| unbounded, memory warm | 19/20 | 80% | 106 |
| **8s budget, memory off** | **10/20** | 48% | 267 |
| **8s budget, memory warm** | **13/20** | 57% | 204 |

10/20 under a preview-equivalent budget reproduces the live 26/50 rate. The
same code unbounded reaches 19/20. **The constraint is the acquisition budget,
not host refusal**, and the way to buy evidence back is to stop spending the
budget on requests that cannot succeed.

## 2. Where the budget was going

A run has 14 approved slots (`MAX_APPROVED_SOURCES`) and the slot, not the
request, is the scarce resource. Slot success by how the URL was found:

| discovery method | succeeded |
|---|---|
| `third_party_filing` | **41/41 (100%)** |
| `entered` | 7/8 |
| `homepage_link` | 26/33 |
| `external_proposed` | 50/66 |
| `known_path` (guessed) | **33/80 (41%)** |

One clean Johnson & Johnson run spent NINE of fourteen slots on `/api`,
`/docs`, `/developers`, `/plans`, `/business`, `/case-studies` and
`/documentation` — against a pharmaceutical company. Every one 404'd, and the
next run bought the same nine answers again.

## 3. Cold vs warm (Section 20)

Same 20 companies, same code, memory cold then warm:

| | cold | warm |
|---|---|---|
| report-eligible | 19/20 | 19/20 |
| documents | 197 | 203 |
| approved slots | 270 | 255 |
| **slot yield** | 73% | **80%** |
| failures | 125 | **106** |
| requests avoided | 107 | **217** |
| `external_proposed` slot success | 79% | **100%** |

The review-site templates (g2/trustpilot/capterra) leave the approved set
entirely once remembered — 70 slots become 55, all of which succeed.

## 4. Replay: is judgement healthy when acquisition is? (Section 18)

`scripts/acquisition_replay.py` replays stored evidence bundles through every
deterministic gate with the network cut.

    20 bundles → 19/20 READY_FOR_FULL_REPORT, 20/20 deterministic

Each bundle is judged twice and the verdicts must be identical, so a gate
reading a clock or a filesystem would surface here rather than as drift in a
live cohort. **This proves the deterministic layer only.** Model-backed
synthesis needs a configured reasoning key and is proven live, not here.

## 5. Live matrix on `d4ce3318` (Section 22)

Eight companies that took the bounded-abstention path on `142ae2c6`, plus two
controls. Preview freshly deployed, so every cache started cold.

| | |
|---|---|
| terminal outcome observed | **10/10** |
| full-length briefs (>=30k chars) | **10/10** |
| all three evidence roles filled | 5/10 |
| submit latency | median **1.47s**, max **8.78s** |
| CORE p50 / max | 96.3s / 171.5s |
| CORE <= 120s | 9/10 |

**Submission ambiguity is resolved.** Meta Platforms — the company that
returned `analyze_status: 0` on a 90s client timeout in the last cohort —
submitted in **1.42s** and reached a terminal usable report at 98.2s. No
submit exceeded 8.78s across ten companies.

**The remaining loss is now attributable**, which is the point of the
taxonomy. Three companies, three different causes:

| company | yield | dominant cause |
|---|---|---|
| Johnson & Johnson | 6/23 | **8 sources lost to the time budget** |
| Eli Lilly | 5/25 | **18 refusals** (lilly.com × 16) |
| Deere & Company | 5/26 | **17 not-found** (deere.com × 18, guessed paths) |

Under the previous single "insufficient evidence" label these three were
indistinguishable.

## 6. Instrument defects found (and what they cost)

Both were caught before they reached a conclusion, and both are the same
class: an instrument that names product state wrongly invents uniform defects.

**Shared store directory.** `acquisition_probe.py` wrote every run into one
directory, and `create_run` is idempotent on (domain, user, as_of) — so the
second probe of a company on the same day rejoined the first run's event log.
Oracle read `{investor: 5, independent: 4}` / RETRYABLE_EVIDENCE_GAP under the
shared directory and `{identity: 2, independent: 4, investor: 1, strategy: 1,
talent: 1}` / READY_FOR_FULL_REPORT with a fresh one, same code, minutes
apart. It produced a confident and wholly false conclusion that the network
had degraded mid-session. Every measurement taken through it was discarded.

**Keyword abstention detection.** `live_recovery_matrix.py` classified a brief
as an abstention on "could not be retrieved" — which is what a GOOD report
says while listing sources it could not read. Three of ten rows were reported
as bounded abstentions while carrying 52-59k-character briefs with every
evidence role filled, against ~12k for a real abstention page. Corrected to
sentences the abstention branch alone emits, plus a length check.

## 7. Deliberately not built

Search and financial provider adapters (Tavily, Exa, FMP, Polygon, SEC-API)
were not added. The independent-evidence supplier already in the repo —
`third_party_filings`, EDGAR full-text — succeeded **41 of 41 times** and was
underused not because it was missing but because
`retry.FAMILY_TARGETS["independent"]` was unreachable from any code path.
Fixing reachability cost nothing and added no dependency.

## 8. Known limitation

The preview reports `durability: EPHEMERAL_LIKELY` with no persistent mount,
so the acquisition memory there is a within-instance cache that resets on
every deploy. It is durable wherever a disk is declared (`render.yaml` mounts
one at `/var/data` for `intent-engine-web`). The live matrix above therefore
ran entirely COLD and still produced 10/10 terminal outcomes; the warm
benefit measured in §3 is additional to it.
