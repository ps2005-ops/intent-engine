# BATCH 18 — PRE100 convergence run

Committed IN-TREE deliberately. Batch 17's handoff lived only in a temp
worktree and is gone; a handoff that does not survive the worktree is not a
handoff.

## Starting state
founder `701eddf` (== origin/v5/founder == origin/feat/founder-market-integration)
market `9b01ff1` · production `cfd4c3b` untouched

## Wave 1A — fetch-then-select (DONE, tests green)

FOUND (live probe, decisive): EDGAR full-text search returns neither
`_snippet` nor `highlight` on any hit. Confirmed against the live index for
"Cloudflare" 10-K, 94 hits, every one `_snippet: None`. So the pre-fetch
relevance gate built in batch 17 was structurally inert: it was handed "" and
correctly returned UNMEASURABLE, which is permissive.

FOUND (second, worse): `discovery_coverage` was READ by the provenance drawer
and WRITTEN BY NOTHING. Zero producers. Every analysis reported
DISCOVERY_NOT_RUN, so the drawer could never say more than "we failed to find".

FIX:
- `discover_third_party_filings` inverts the order — search, oversample to 30
  structurally-eligible candidates, FETCH up to 12 documents, adjudicate
  relevance against the filing's own text, score by decision value, keep the
  best `limit`. Budget-bounded, never result-count-bounded.
- Coverage is now DERIVED from what the run did (BLOCKED / NOT_RUN / PARTIAL /
  ADEQUATE / EXHAUSTED), never set.
- Full producer -> bridge -> read-model chain wired:
  service.discovery_report(run_id) -> build_payload(discovery=) ->
  FOUNDER_ADDITIVE + FounderBlock.discovery_coverage -> assembler ->
  drawer reads `.get("coverage")` and renders the WORK.
- Rejection filer NAMES never cross the bridge; only reason counts do.
- An injected search with no injected fetcher refuses to fetch and reports
  DISCOVERY_NOT_RUN — no test can reach the live archive by accident.

PROOF: `tests/test_discovery_coverage_is_measured.py` (12), migrated
`tests/test_third_party_filings.py` (24). 669 pass across the
dossier/bridge/contract/provenance cluster.

Legacy fixtures encoded the defect: they carried the substantive sentence in
`_snippet`, a field production never has. Migrated by intent — the prose now
lives in the fetched document, which is the only place the real system reads.

## NEXT
1. Live matrix measurement of the fix (does it actually yield independent
   relevant origins?) — this gates whether the rest is worth building on.
2. Hydration backend · economic history · second-iteration delta.
3. Full Guard A, deploy, then live break/fix loops.

## Wave 1A RESULT (commit fa8389f, deployed, Guard A green 5994/0)

Live matrix, real EDGAR, before -> after:

| company     | hits | considered | fetched | BEFORE | AFTER | coverage           |
|-------------|------|-----------|---------|--------|-------|--------------------|
| Cloudflare  |  37  |     5     |    5    |   4    |   3   | DISCOVERY_EXHAUSTED |
| Caterpillar | 222  |    15     |   12    |   4    |   4   | DISCOVERY_PARTIAL   |
| Shopify     |  47  |     9     |    9    |   4    |   4   | DISCOVERY_ADEQUATE  |

The count is NOT the finding. Reading the four origins the fixed retrieval
returned for Cloudflare is what mattered:

- 2 were executive biographies (Adobe, Coursera) — the company named in an
  individual's career history.
- 2 were customers disclosing their own vendor arrangements (ChargePoint,
  OneSpan). ChargePoint's has no first-person pronoun; the filer names ITSELF,
  so the author-voice rule never saw it was self-description.
- Caterpillar's TOP-RANKED independent source was CATERPILLAR FINANCIAL
  SERVICES CORP — its own captive finance arm, own CIK, own name, past both
  independence locks.

All three are now demoted on POSITIVE findings only. Controls that must
survive and do: a rival naming itself beside the subject; "Linear Minerals
Corp." against subject "Linear" (the over-match that made a previous fix worse
than its defect).

Known miss, deliberate: "John Deere Capital Corp" vs "Deere & Company" shares
no name prefix, so the affiliate rule cannot reach it. Closing that needs a
registry, not a wider string rule.

## NOT DONE THIS SESSION — do not read as blocked
HYDRATION, ECONOMIC_HISTORY, SECOND_ITERATION, EXECUTIVE_XRAY polish,
FULL_ANALYSIS, PRESENTATION, CEO_QA, CUSTOMER_ACCEPTANCE, SECURITY,
ZERO_ANTHROPIC. None started.

## Live-proof gap
Deployed SHA verified = fa8389f. The rendered drawer was NOT read on the
deployed service: /analyze 403s and /demo 403s to curl (CSRF + session not
obtainable headlessly; deploy also clears stored runs). The producer->bridge->
read-model chain is proven by test incl. negative controls, but the SENTENCE a
buyer sees for a fresh live run is unverified. First next task.
