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
