# Reproof thresholds — cb9e6b7, declared BEFORE the runs

Written before any company was run. A repair that ships inert looks exactly
like a repair that worked unless the number that would distinguish them was
named in advance.

Baseline column is the measured state on 743df06.

| leg | company | baseline on 743df06 | PASSES IF |
|---|---|---|---|
| RETRIEVAL_REFUSAL | The Goldman Sachs Group, Inc. | `RETRIEVAL_TEMPORARILY_UNAVAILABLE`, `compose=3 usable=3 families=investor failed=26/24` | families ≥ 2 **and** outcome is FULL_ANALYSIS or FULL_ANALYSIS_REFRESHING **and** `failed` < 10 |
| REFUSAL_CONTROL | NIKE, Inc. | `FULL_ANALYSIS`, `compose=11 usable=10 families=5 failed=7/6`, 159s | still FULL_ANALYSIS, families ≥ 5 — **unmoved** |
| LOW_YIELD | Advanced Micro Devices, Inc. | `TRUE_EVIDENCE_SCARCITY`, `compose=3 usable=3 families=investor attempt=3` | families ≥ 2 **and** outcome is not TRUE_EVIDENCE_SCARCITY |
| ATTRITION | NVIDIA Corporation | `TRUE_EVIDENCE_SCARCITY`, `compose=12 usable=4` (8 dropped, breakdown absent) | `unexplained=0` in the gate header — the counters close, so the attrition is *named* — **and** outcome is not TRUE_EVIDENCE_SCARCITY |
| RUN_CREATION | PepsiCo, Inc. | `FAILED` at 349s, 6 consecutive 45s progress timeouts | a run opens and reaches a terminal state within the 480s wall |
| OUTPUT_INTEGRITY | Pfizer Inc. | `/runs/<id>` **HTTP 500**, 513 chars, header said FULL_ANALYSIS | run route HTTP 200 with ≥ 1200 chars; if it 500s again, the header must say ANALYSIS_FAILED, not FULL_ANALYSIS |
| PERFORMANCE | Meta Platforms, Inc. | `FULL_ANALYSIS` at 335s first-useful | still FULL_ANALYSIS **and** first_useful < 335s. The §13 SLA is ≤30s median and is **not** expected to be met by this wave — this leg measures direction, and the gap is reported rather than hidden. |

## What would falsify the whole wave

If Goldman and AMD still compose one family, `family_of` is not on the live
path and the repair shipped inert — the same failure mode as a green suite
over a dead call site.
