# Paper validation: system of record

Written 2026-11-09, before any code in this program existed. It answers
three questions: which stores already speak for the market and economic
engines, which of them this program may touch, and where this program's
own records live.

## Who writes what today (read, not assumed)

| Store | Writer | State on 2026-11-09 | This program |
|---|---|---|---|
| `~/intent-engine-market/reports/market/learning_ledger.jsonl` | launchd `com.intentengine.market.{day,night}` running `python -m intent_engine.market` with `PYTHONPATH=~/intent-engine-market/src`, `TRADING_MODE=PAPER`; runtime pinned detached at `195c6f4a` | **CANONICAL** per `docs/execution/MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml`; 18.2 MB, last written 2026-11-09 07:27 | READ-ONLY. Never opened for writing, never imported from. |
| `~/intent-engine-market/status/market_cycles.jsonl`, `reports/market/learning_health_history.jsonl`, `reports/market/decision_impact.jsonl` | same launchd jobs | canonical companions of the ledger above | READ-ONLY |
| `~/intent-engine/data/prediction_ledger.db` | user crontab in `~/intent-engine` (`scripts/daily_market_predictions.py` 18:30 Mon-Fri, `scripts/resolve_market_predictions.py` 06:00) | **LEGACY** per the system-of-record file; cron still fires (logs dated 2026-11-09) but the DB was last written 2026-10-16 | READ-ONLY, not used as evidence |
| `reports/real_forward_expectations.jsonl` (tracked) | `econ.forward_ledger.append`; last real write 2026-08-28 in `~/intent-engine-econ` (`v6/unified`); no scheduler | econ macro-series forward record, dormant | Not written. Not reused for instrument forecasts (different target: macro series direction). |
| `~/ie-econ-runtime/` | a separate runtime root used for econ dry runs 2026-08-24..27 | dormant since 2026-08-27; not a git checkout | READ-ONLY |
| `data/paper_book.db`, `data/learning_ledger.db` (hosted/paper loop) | `paper.PaperTradingLoop`, `learning.LearningLedger` default paths | runtime state of the hosted loop | Not written. The learning loop here uses `LearningLedger` at a separate shadow path. |
| Alpaca paper broker (`paper/broker.py`, `paper/execution.py`) | hosted jobs, credentialed | | **Not imported.** No broker, no order surface, no credentials. A test asserts the package never imports either module. |

## What the economic engine actually is, for this test

The economic engine's decision output is company-facing: the shared
economic state (`scripts/publish_econ_state.build_state`, vintage-walled
over `reports/panel/historical_panel.jsonl`) is joined to a company's
business-model class (`executive.company_profile.profile_for`, from the
curated validation manifest) through `external_intel.econ_decision.
transmissions`, which marks a channel ADVERSE when the condition moved
materially in the direction `_ADVERSE_DIRECTION` says hurts that class.
That join is pure and can be replayed as of any historical date. It is
the "existing Intent Engine policy" replayed here, on the 54 US-listed
public companies in the manifest. The engine has no instrument mapping
for Treasuries, gold or broad ETFs and none is invented.

The canonical market engine's own price policy is
`market.strategy_library.baseline_momentum.v1` (20-session move beyond
2%), which the engine itself records as measured at 0.500. It is replayed
as the existing market-side policy.

## Data this program may use

* Prices: Yahoo chart endpoint, keyless (`market/prices.py` documents why
  it is the only route available). Adjusted close (`adjclose`, split and
  dividend adjusted) and open, cached with retrieval time and sha256.
* Macro: the committed vintage panel (ALFRED/FRED, keyless) for the
  historical replay; a separately stored FRED current-vintage snapshot,
  stamped with its retrieval date as its vintage, for forward
  registrations only (the panel ends 2026-08-28).
* No `.env` value is read or printed. Nothing is purchased.

## Where this program's records live (owned here, never production)

| Path | Kind | Notes |
|---|---|---|
| `reports/paper_validation/forward_shadow_ledger.jsonl` | FORWARD_SHADOW | append-only, hash-chained; registrations dated today onward; resolution is a separate event |
| `reports/paper_validation/rehearsal_ledger.jsonl` | REHEARSAL | backdated, constant-probability records that exercise the resolver; never evidence |
| `reports/paper_validation/replay/` | REPLAY | historical walk-forward outputs; reported separately from forward results |
| `reports/paper_validation/prices/`, `forward_macro/` | data vintages | cached inputs with sha256 |
| `data/paper_validation_shadow_learning.db` | shadow LearningLedger | gitignored runtime state; promotion is a human act |

Nothing here is wired to a scheduler. A daily or 21-session registration
job is PROPOSED in the report, not installed.
