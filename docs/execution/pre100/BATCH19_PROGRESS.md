# BATCH 19 — PRE100 convergence

IN-REPO ON PURPOSE. Batch 17's handoff lived only in a temp worktree and is
gone; a handoff that does not survive its worktree is not a handoff.

## Starting state
founder `1533358` · market `9b01ff1` · production `cfd4c3b` untouched

## §2 Harness race — FIXED
`break_proof_harness.verify()` wrote each mutation into the shared `src/` and
restored it in a `finally`. While that window is open every other reader of the
repo sees deliberately broken source.

CORRECTION to batch 18's diagnosis: `pytest-xdist` is NOT installed. The guard
is serial, and the extra pytest processes were the harness's own subprocesses.
The hazard is the shared-tree write itself, not parallelism.

Mutations now happen in a private hard-linked copy of `src/`; the shared tree
is never written. `-o pythonpath=<mirror>` is required because pytest.ini pins
`pythonpath = src` at the FRONT of sys.path — without it every mutation is
inert and all twenty proofs report NOT_CAUGHT, a harness that cannot fail
dressed as one that passes. Pinned by
`tests/test_break_proof_harness_is_isolated.py` (mtime is the negative
control: the old harness bumped it deliberately).

## §5 Retrieval matrix — COMPLETE (8 companies, excerpts read)

| company     | considered | fetched | origins | coverage            |
|-------------|-----------|---------|---------|---------------------|
| Cloudflare  |     5     |    5    |    3    | DISCOVERY_EXHAUSTED |
| Caterpillar |    15     |   12    |    4    | DISCOVERY_PARTIAL   |
| Shopify     |     9     |    9    |    4    | DISCOVERY_ADEQUATE  |
| J&J         |    29     |   12    |    4    | DISCOVERY_PARTIAL   |
| Bank of America |  20   |   12    |    3    | DISCOVERY_PARTIAL   |
| Toyota      |    19     |   12    |    4    | DISCOVERY_PARTIAL   |
| Vale        |     7     |    7    |    4    | DISCOVERY_ADEQUATE  |
| Stripe      |  not run (private; no EDGAR registrant)                    |

Four correctness defects found by READING, not by counting:

1. SEV1-class — generic leading word. `_terms("Bank of America Corporation")`
   emitted the bare term "Bank", so any sentence containing `bank` counted.
   All four BoA origins were documents that never named the company.
2. SEV2 — table rows as prose. BoA's top evidence was a fund holdings row;
   Toyota's was a customer-concentration row; Aurora's was a bullet.
3. SEV2 — the excerpt was not the span that drove the verdict, so the drawer
   printed a holdings row beside DIRECTLY_RELEVANT.
4. SEV3 — `_BIOGRAPHICAL` missed "served at" (Tesla proxy on Toyota).

RESIDUAL, ACCEPTED: biography fragments inside director/officer lists still
pass ("from May 2018 to June 2022, and Cloudflare, Inc."; "His experience at
Vale included advising on M&A"). Bounded SEV3.

NOT FIXED, NEXT RETRIEVAL TASK: `filing_text` already knows which lines came
from a `<tr>`; carrying that provenance into relevance would refuse table rows
structurally instead of by numeric ratio.

## ACQUISITION_PRE100_FROZEN = TRUE
No further changes to EDGAR ranking, discovery channels, source filtering,
retrieval/relevance/independence policy unless a live customer flow proves a
new high-severity correctness defect.

## NOT DONE — do not read as blocked
Cluster A (hydration, economic history, second-iteration) and Cluster B (X-Ray
polish, Full Analysis, Presentation, CEO Q&A, Personal AI integration, learning
UI) were NOT started. Live iterations, acceptance, security and the
zero-Anthropic proof were NOT run.
