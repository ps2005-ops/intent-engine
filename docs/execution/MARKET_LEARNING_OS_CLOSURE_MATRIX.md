# Market Intelligence Learning OS — closure matrix

**This file is no longer the source.** It printed "PARTIAL (10)" above a table
containing twelve PARTIAL rows, and that miscount was carried into a handoff
as the authoritative remaining work.

The matrix is now machine-readable and its counts are derived, never typed:

| what | where |
|---|---|
| source | `docs/execution/MARKET_LEARNING_OS_MATRIX.yaml` |
| generator | `scripts/market_matrix.py` |
| self-count test | `tests/test_market_matrix.py` |

```bash
PYTHONPATH=src python3 scripts/market_matrix.py
```

## Why the PARTIAL count collapsed from 12 to 2

Not by lowering a bar — by measuring on the right axis. The old matrix had one
column, so a subsystem that was fully built, called, persisted, reloaded and
reported but had produced no movement today was recorded PARTIAL, identically
to one that was genuinely half-finished.

The generated matrix separates them:

- **capability** — is the seam built, called, persisted, reloaded, consumed,
  reported and proven?
- **empirical** — has enough real data arrived for the numbers to mean
  anything?

Hidden state, proof, adversary and the CompanyDemoDossier are
`capability=PASS / empirical=RAN_NO_CHANGE`. Demand and unsupervised are
`PASS / SPARSE`. RL policy maturity is `PASS / BLOCKED_DATA` with its
collection path running. Causal is `PASS / LEGACY_UNDATABLE` — its producer now
stamps `estimated_at`, and the 25 historical rows are deliberately not
back-filled.
