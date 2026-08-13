# Market Intelligence Learning OS — handoff to V5

The learning OS is now infrastructure. V5 should **use** it on every company,
not redesign it.

## Pins

| what | value |
|---|---|
| market source | `ec9d630` |
| market runtime (PAPER) | `ec9d630`, pinned, importing from `/Users/prathamsharma/intent-engine-market/src` |
| founder | `6645a4f` (untouched by this programme) |
| production main | untouched |
| trading mode | PAPER, enforced by launchd |
| system of record | `docs/execution/MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml` |

## Commands — these are the only supported way to ask

```bash
python -m intent_engine.market learning-status --window 7d
```
```bash
python -m intent_engine.market watchdog
```
```bash
python -m intent_engine.market learning-report --period day
```

`--period week|month` for the other windows. Never answer "what has it
learned" by reading the repository: that mistake is what began this whole
programme.

## Artifacts

| what | where |
|---|---|
| canonical ledger | `reports/market/learning_ledger.jsonl` |
| daily / weekly / monthly | `reports/learning/{daily,weekly,monthly}/` |
| strategic exports | `reports/market/strategic/*.json` |
| supervised inventory | `docs/execution/SUPERVISED_PREDICTIVE_INVENTORY.yaml` |
| completion matrix (generated) | `docs/execution/MARKET_LEARNING_OS_MATRIX.yaml` + `scripts/market_matrix.py` |

## Completion

39 axes, counts mechanically derived. **Capability: PASS on all 39. PARTIAL 0,
NOT_BUILT 0, UNMEASURED 0.**

Honest empirical states that remain, none of them an engineering gap:

- `RL_POLICY_MATURITY` — BLOCKED_DATA, 40 prospective pairs accumulating
- `CAUSAL` — LEGACY_UNDATABLE for 25 pre-stamp rows; new rows carry `estimated_at`
- `DEMAND`, `UNSUPERVISED` — SPARSE
- `HIDDEN_STATE`, `PROOF`, `ADVERSARY`, `COMPANY_DEMO_DOSSIER` — RAN_NO_CHANGE
- **`FOUNDER_CONSUMPTION` — NOT_CONSUMED. Read the next section.**

## The one thing V5 must not inherit quietly

The Market→Founder pipe is **measurably empty**: 0 of 60 companies current,
35 never consumed, 25 whose revisions predate digest recording and therefore
cannot be *proven* current. Transport is `TRANSPORT_NOT_CONFIGURED` — the
handoff is the shared filesystem and no Founder consumer runs against this
data root.

The engineering gate closed because the system can now *say* this; it was
silent for four days before. But nothing Founder-facing should be demoed until
a consumer actually runs. The watchdog raises `FOUNDER_NOT_CONSUMING`.

## Current learning bottleneck, carried into V5

Not the repeat rate — the **expectation horizon**.

The engine re-reads sources daily while every expectation window closes
between Dec 2026 and Aug 2027 and the next belief review is 2026-12-03.
Measured over 301 sightings, **not one could have resolved anything**, so
re-observation value is `UNMEASURABLE` rather than low.

The 84% repeat figure is therefore the wrong target. V5 should test whether
research scheduling driven by **event / VOI / decay-window** beats
indiscriminate daily refresh, while preserving genuinely valuable monitoring —
`evidence_independence.classify_reobservations` already separates the two, and
`VALUABLE_REOBSERVATION` names which classes earn their retrieval.

## What V5 must now measure per company

The 10→30→50→100 programme must stop measuring only page yield, latency and
dossier success. Add, from the producers above:

independent evidence · novel evidence · useful revalidation · KnowledgeEffects
· belief movement · causal learning · source diversity · retrieval cost per
useful learning · Founder freshness · decision-relevant intelligence

## First V5 action

Resume Breaker-10 → retrieval → independent-evidence → learning convergence
from the existing canonical manifest and the Wave-30 gate. Do not open more
Market-learning architecture.
