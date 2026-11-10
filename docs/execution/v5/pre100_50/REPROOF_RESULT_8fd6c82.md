# Reproof result — measured against the thresholds declared before the runs

Thresholds: `REPROOF_THRESHOLDS_cb9e6b7.md`, written before any company ran.

| leg | company | before (743df06) | after | verdict |
|---|---|---|---|---|
| RETRIEVAL_REFUSAL | Goldman Sachs | `RETRIEVAL_TEMPORARILY_UNAVAILABLE` · `compose=3 families=investor` | **`FULL_ANALYSIS`** · `compose=5 families=identity\|investor\|strategy\|talent` | **PASS on 2 of 3** — families and outcome met; `failed=27/23` was to fall under 10 and did not |
| REFUSAL_CONTROL | NIKE | `FULL_ANALYSIS` · `compose=11 usable=10 families=5` | `FULL_ANALYSIS` · `compose=11 usable=10 families=5` | **PASS — unmoved** |
| LOW_YIELD | UPS (domainless) | `TRUE_EVIDENCE_SCARCITY` · `compose=2 families=investor` | **`FULL_ANALYSIS`** · `compose=4 families=identity\|investor\|talent`, /full 20,630 chars | **PASS** |
| LOW_YIELD | AMD | `TRUE_EVIDENCE_SCARCITY` | `FAILED` — progress route silent from t=102 | **NOT MEASURED** (see SEV-1) |
| ATTRITION | NVIDIA | `compose=12 usable=4`, no breakdown | `dropped=0/0/0/8 unexplained=0` | **PASS as an instrument** — the mechanism is named: the LANGUAGE filter took 8 of 12. Outcome is still not FULL. |
| RUN_CREATION | PepsiCo | never reached a terminal state (349s) | **`FULL_ANALYSIS` at 340s** | **PASS** |
| OUTPUT_INTEGRITY | Pfizer | `/runs/<id>` **HTTP 500**, 513 chars, header said `FULL_ANALYSIS` | `/runs/<id>` **HTTP 200**, 3,941 chars | **PASS** |
| PERFORMANCE | Meta | `FULL_ANALYSIS` at 335s | **`TRUE_EVIDENCE_SCARCITY`** · `compose=1 stored=9` | **FAIL — regression, SEV-1** |

## What the thresholds bought

Two legs would have read as successes without a number written down first.

Goldman turning `FULL_ANALYSIS` is the headline, and it is real — but the
declared threshold also required the fetch-failure count to drop below ten,
and it did not move at all (26/24 → 27/23). The repair that was supposed to
do that did not fire, and no mechanism for why has been established. Without
the pre-declared number that would have been invisible under a green result.

NVIDIA is the mirror image: the outcome did not improve, so the leg looks
failed — but the declared threshold was `unexplained=0`, the counters
closing, and that is exactly what happened. The instrument now names the
filter, which is what the leg existed to buy.

## Open, and honest

**SEV-1 — the progress route stalls, and the store was not the cause.**
`/runs/<id>/progress` stops answering for 100+ consecutive seconds during
analysis (AMD t=102, and t=109/t=129 on the previous SHA) while `/version`
and `/healthz` answer in 0.15s. Six 45-second timeouts is how a live company
becomes a FAILED row. The measured store cost was removed — 153 ms per poll
to ~1 ms — **and the stall is unchanged**, so the hypothesis that the
append-only re-parse caused it is FALSIFIED by direct measurement. Ruled out:
the whole worker being blocked (light routes stay fast), the handler's own
store reads, and an exception (no 5xx on those polls). Not yet tested: GIL
starvation by a CPU-bound analysis on a shared half-CPU instance, and memory
pressure. AMD is unmeasurable until this is fixed.

**SEV-1 — Meta regressed.** `compose=1 usable=1 families=identity stored=9`
at 47s: the gate judged ONE document while the store ended with nine. This is
the seam the previous wave repaired, and the repair explicitly declined to
fix the underlying race ("NOT A FIX TO THE RACE. Which caller composed early
is not established"). The re-gate only fires when the store is already larger
at the moment it runs; here composition finished before the other eight
arrived. Meta reads `TRUE_EVIDENCE_SCARCITY` on the live service now.

**SEV-2 — NVIDIA's language filter takes 8 of 12.** Named, not fixed. Either
`is_english` is refusing English pages, or discovery is approving localised
nvidia.com paths it should not have proposed. The two call for different
repairs and the breakdown does not yet distinguish them.

**SEV-2 — Pfizer renders §17 failure language on abundant evidence.**
`compose=12 usable=12` across five families, and `/full` says "No strategic
reading of Pfizer Inc. cleared the evidence bar, so none is asserted here."
Its headline is also a filing fragment: "Pfizer Inc. Financial Statements and
Supplementary Data in this Form 10-K."

**SEV-2 — Goldman's fetch-failure count did not move.** 23 requests still go
to a host already observed refusing. The exclusion added this wave is proved
by unit test and break proof, so it works where it is reached; it is not
being reached on this path, and why is not established.

## A count that was inflating

Pfizer's `/full` reads 3,941 chars against 21,718 on 743df06. That is not a
loss of content: the text extractor was counting an inline `<style>` block as
prose, and both Goldman's and Pfizer's "before" numbers were inflated the
same way. Character counts across those two SHAs are not comparable.
