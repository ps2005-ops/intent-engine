# BATCH 10 HANDOFF — RUN THE FIRST BREAKER WAVE

Written by Batch 9. Nothing in this file has been run.

## Worktree hazard, first

`v5/founder` and `v5/market` are checked out in other sessions' worktrees, so
a push updates **origin only** and the local refs stay behind. Always:

```bash
git fetch origin && git worktree add --detach <path> origin/v5/founder
```

Branching from the bare local name gives a stale tree and silently rebuilds
work that already exists.

## State this batch inherits

| | |
|---|---|
| FOUNDER | `origin/v5/founder` — see the Batch 9 report for the exact SHA |
| MARKET | `origin/v5/market` @ `efb1c1d` (unchanged by Batch 9) |
| PRODUCTION | untouched |
| PAPER | ENFORCED |
| V4 | COMPLETE_AND_LIVE_VERIFIED_FROZEN |
| V5 graph | 33 nodes, COMPLETE 10, READY 8, WAITING 14, BLOCKED_DATA 1 — unchanged |

The 100-company program is a **parallel track**; it is not a node in
`TASK_GRAPH.yaml`, and the graph frontier is still `A-ASSUME-001`.

## What is ready

| Thing | Where |
|---|---|
| Manifest | `docs/execution/v5/COMPANY_VALIDATION_MANIFEST.yaml`, version `1.0.0` |
| Reader / validator / selector | `intent_engine.validation.manifest` |
| Dossier assembler | `intent_engine.demo_dossier` |
| Dossier store | `DossierStore(runtime_root)` → `demo_dossiers/<company>.jsonl` |
| Inspection surface | `GET /demo-dossiers`, `/demo-dossiers/<id>`, `/demo-dossiers/telemetry` |
| Analysis entrypoint | `WebApp._compose(run_id)` — emits the snapshot, assembles, persists, stamps cohort + manifest version |
| Break proofs | `scripts/v5_dossier_break_proofs.py` — 37/37 |

Read the manifest through `intent_engine.validation.load()`. Do not parse the
YAML anywhere else; one reader is the reason there is one population.

## The breaker ten — SELECTED, NOT RUN

`intent_engine.validation.breaker_ten(load())`, deterministic from manifest
metadata. **Recompute it rather than copying this table**; it is reproduced
here only so a reader can see what it chose.

| slot | company_id | country | sector |
|---|---|---|---|
| software_platform | `cloudflare` | USA | SOFTWARE_PLATFORM |
| semiconductor | `advanced-micro-devices` | USA | SEMICONDUCTOR |
| industrial_cyclical | `boeing` | USA | INDUSTRIAL |
| regulated_financial | `bank-of-america` | USA | FINANCIAL_REGULATED |
| consumer_or_healthcare | `alimentation-couche-tard` | CANADA | CONSUMER |
| capital_intensive | `agnico-eagle-mines` | CANADA | MATERIALS_ENERGY |
| canadian | `bce` | CANADA | INFRASTRUCTURE |
| private_high_coverage | `stripe` | USA | SOFTWARE_PLATFORM |
| private_sparse | `mckinsey` | USA | SERVICES |
| identity_or_source_hard | `johnson-and-johnson` | USA | HEALTHCARE |

Nine distinct sectors, both primary countries, two private companies, one of
them withheld. All ten are DEVELOPMENT: the selector draws from that cohort
only, and a break proof holds that property.

**No swapping after seeing output.** If a company turns out to be
unanalysable, record why and leave the slot empty for the wave — do not
substitute a company that looks more likely to succeed. That substitution is
the whole reason the selection is deterministic.

## What Batch 10 does

1. Preserve the BEFORE baseline — every dossier and its telemetry, before any
   repair. Version 1 of each dossier IS the baseline; do not overwrite it.
2. Run the ten through the real analysis path.
3. Collect `CompanyDemoDossier`s and the diff for each.
4. Classify systemic defects. Repair only Class A/B/C.
5. Rerun affected companies; the store versions rather than overwrites, so
   before/after is a `compare(previous, current)` call.

### Things that will otherwise be discovered the hard way

- **`IMPACT_UNMEASURABLE_FIRST_OBSERVATION` is correct on the first wave.**
  Every company's first dossier has no `before`. It is not a defect and not a
  retrieval gap; the second run is the fix.
- **`FOUNDER_AVAILABLE_MARKET_UNAVAILABLE` is the expected crossing state**
  unless a market engine publishes into the same runtime root. Do not read it
  as "the market found nothing".
- **`DEMO_VERIFIED` is unreachable from a backend.** No count of passing
  analyses promotes a dossier into it; that gate needs a real UI proof.
- **A bounded run is `DEGRADED`, not `UNAVAILABLE`.** A completed analysis
  that reached no strategic report is a measured outcome about the company.
- **The manifest is not an answer key.** `inclusion_reason` says why a company
  is useful to test, never what the analysis should conclude. Do not add
  expected outputs while triaging; `load()` refuses them.

### Do not claim

Success rate, demo readiness, coverage, or generalization from ten companies
in one cohort. What ten companies can support is a defect taxonomy.

## Known limitations carried forward

Both are recorded in the manifest's own `known_limitations` block:

1. `coverage_expectation` is HIGH_COVERAGE for 92/100, so it barely
   stratifies. Stratify larger waves on `sparse_or_withheld`,
   `identity_difficulty`, `public_private` and `sector` instead.
2. Private representation is thin — 10 private, 7 sparse-or-withheld. Enough
   for ten, thin for thirty. Add entries in a v1.1 revision rather than
   reweighting; additions are recorded, silent cohort moves are refused.

## Where results go

Nothing exists yet for these; Batch 10 creates them.

- Baseline report → `docs/execution/v5/BREAKER_10_BASELINE.md`
- Defect taxonomy → `docs/execution/v5/DEFECT_TAXONOMY.md`
- Dossiers → the runtime root's `demo_dossiers/`, versioned, already durable
