# Unified Learning Platform

*Written 2026-07-24. Implements the founder's "bring the four systems back
together into one continuously improving platform" directive — the gated
machinery, respecting every existing wall. This is the engineering record
of what was built, what was reused, and what deliberately was NOT done.*

## The organizing idea

The four long-term systems (Decision Engine, Synthetic Worlds, Personal AI,
Autonomous Marketing) already existed as substantial subsystems. What was
missing was the **shared primitive that lets them improve one another**.
This build adds it:

```
        Decision Engine
              │  predictions (core/prediction_ledger.py)
              ▼
        Paper-Trading Shadow Loop  ── recurring mistakes ─┐
              │  scored feedback                          │
              ▼                                           ▼
        Learning & Promotion Ledger  ◄── weaknesses ── Synthetic Worlds
              ▲            │
   observe/explain        │ (human promotes; nothing auto-applies)
              │            ▼
        Personal AI    production change (separate, human-owned)
```

The **Learning & Promotion Ledger** is the brain: every subsystem that
learns proposes a *candidate* here, evidence accrues as *evaluations*, and
only a human-authorized, criteria-met *promotion* ever changes production.
Marketing (growth_studio) can later plug into this exact primitive instead
of keeping its own acceptance path.

## The walls (why this is the *gated* machinery)

The founder's own code encodes safety gates whose preconditions are not yet
met (the prediction ledger has 0 resolved predictions; `A-M5` forbids
feedback into generation until a human opens the gate). This build **does
not open those gates**. Instead it builds the machinery that will be ready
when they open:

1. **Promotion wall.** `LearningLedger.promote()` refuses unless the actor
   is a **human** AND every predefined success criterion is met
   consistently across `MIN_EVALUATIONS_TO_PROMOTE` evaluations. Defence in
   depth: `learning.candidate_promoted` is also in the event bus's
   `_HUMAN_ONLY_EVENTS`, so no agent can even emit the fact.
2. **No-production-mutation wall.** Nothing in `learning/` or `paper/`
   applies a candidate's `param_diff` to any generation prompt, weight, or
   other subsystem store. Promotion records a *decision*; acting on it is a
   separate, human-owned deploy step outside these modules.
3. **Paper trading is shadow-only.** No broker, no real money, no order
   surface (asserted by test). It opens none of the live-trading walls.
4. **Synthetic Phase 2 is read-only.** The bridge proposes candidates from
   weaknesses; it never touches the frozen synthetic module or any weight.

## Cadence — learn every day, promote on evidence

Per the founder's final recommendation, learning ≠ training. The cadence is
a state machine, enforced in `LearningLedger`, and orchestrated by the
deployable runtime `python -m intent_engine.runtime <job>` (locked, evented,
idempotent — see `docs/RUNTIME_DEPLOYMENT.md`). *(The earlier
`scripts/learning_cadence.py` prototype was removed in the production
hardening pass — the `runtime/` jobs supersede it.)*

| Cadence | Job | What it does |
|---|---|---|
| **Daily** | `runtime daily` | resolve due predictions, open eligible paper positions, generate candidates |
| **Weekly** | `runtime weekly-eval` | real walk-forward candidate evaluation |
| **Monthly** | `runtime monthly-packet` | writes the promotion-review packet **for human review** — never promotes |

Everything is idempotent (re-running proposes no duplicates; a still-open
candidate for a regime/mechanism is not re-proposed) and replayable from the
append-only ledger.

## Reused components (no duplication)

Per the "NO ARCHITECTURE DUPLICATION" directive, this build reused:

- **Event system** (`events/`) — new event types registered in the existing
  closed taxonomy, one authoritative producer each; the human wall extended
  in `publisher.py`. No new transport.
- **Decision identity** (`core/decision_ids.py`) — ULIDs for candidate /
  position ids; positions carry the prediction's `decision_id`.
- **Prediction ledger** (`core/prediction_ledger.py`) — the storage
  discipline (append-only SQLite, JSON blob, collapse-to-latest) is mirrored
  exactly by `learning/ledger.py` and `paper/ledger.py`; `db.get_connection`
  reused.
- **growth_studio acceptance wall** (`growth_studio/learning.py`) — the
  candidate→accepted pattern generalized (not copied) into the platform-wide
  ledger.
- **Synthetic worlds** (`core/synthetic_worlds.py`) — consumed read-only via
  its `WorldResult`; the module is untouched.
- **Personal AI adapters** (`personal/adapters/`) — a new `LearningAdapter`
  follows the anti-corruption-boundary pattern; the workspace stays
  read-only.
- **Webapp** (`webapp/app.py`) — a read-only `/learning` surface using the
  existing `_chrome`/`_nav`/`_html` and session gate.

## New components

| Module | Role |
|---|---|
| `learning/records.py` | Candidate / Evaluation / PromotionDecision + pure criteria math |
| `learning/ledger.py` | append-only store (candidates, evaluations, promotions) |
| `learning/service.py` | the lifecycle + the two walls + event publishing |
| `learning/synthetic_bridge.py` | Synthetic Worlds → candidates (Phase 2) |
| `learning/inspection.py` | read-only reader for Personal AI / web |
| `paper/records.py` | PaperPosition with enforced traceability |
| `paper/portfolio.py` | equity, drawdown, Sharpe, Sortino, profit factor, win rate, EV, regime attribution — all in code |
| `paper/ledger.py` | append-only position store |
| `paper/service.py` | the shadow loop + learning-candidate emission |
| `personal/adapters/learning.py` | Personal AI's read adapter over the platform |
| `runtime/` (jobs, market, __main__) | daily/weekly/monthly orchestrator (locked, evented, deployable) |

## Integrations (how the four reinforce each other)

- **Synthetic Worlds → Decision Engine.** Weaknesses discovered in stress
  tests become candidates; when promoted (by a human), they inform the
  engine — the synthetic set is the intelligence gym.
- **Paper loop → Learning brain.** The first objective feedback source:
  recurring regime-specific losses become candidates.
- **Personal AI → everything.** Observes the pipeline and paper book,
  explains any candidate (Finding→Evidence→Confidence→Reasoning→Source→
  Replay), from the web — permission-gated, read-only.
- **Marketing → same architecture (next).** growth_studio's learning path
  is the template; it can emit `source="marketing"` candidates into the same
  ledger rather than its own store.

## Remaining limitations (honest)

- **The comparison harness is an interface, not a data pipeline yet.**
  `LearningLedger.evaluate()` records candidate-vs-baseline metrics; wiring
  it to a real rolling backtest over live market data is the next build
  (deferred with the market-engine flow — gated on resolved predictions).
- **The paper loop does not auto-open positions from the daily prediction
  run yet.** Opening/closing is a public API; the market-engine daily flow
  is the intended caller and is not wired in this slice.
- **Marketing is not yet migrated** onto the shared ledger (backlog).
- **No automated promotion**, by design — it is and stays a human act.
- **Synthetic Phase 2 live feed** depends on the Mac-only `--live` eval
  producing a machine-readable report; the offline leg yields no weaknesses
  by construction (it identifies planted conditions), so candidates flow
  from the live leg.
