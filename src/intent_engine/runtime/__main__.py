"""Runtime CLI — the scheduler's entrypoint.

    python -m intent_engine.runtime <job> [--root data] [--as-of YYYY-MM-DD]

Jobs (each is locked, evented, idempotent, restart-safe — see jobs.run_job):

    preflight          config/credential health (never prints secrets)
    market-open        eligible predictions -> paper positions   [needs TIINGO]
    resolve            resolve due predictions + close linked paper positions
    daily-candidates   generate learning candidates from resolved evidence
    daily              preflight + market-open + resolve + daily-candidates
    weekly-eval        real walk-forward candidate evaluation
    monthly-packet     write the human promotion-review packet
    synthetic-daily    offline synthetic eval -> weakness candidates
    health             print the latest status of every job (JSON)

Real market data is wired here from the environment (TIINGO_API_KEY,
FRED_API_KEY). A missing key makes the credential-dependent jobs FAIL LOUDLY
(persistent job.failed), not silently produce an empty day.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.learning.evaluation import weekly_evaluate
from intent_engine.learning.promotion_packet import write_packet
from intent_engine.runtime.jobs import latest_status, require_config, run_job
from intent_engine.runtime.market import MarketRuntime
from intent_engine.runtime.market_calendar import today_ny


# --- real market-data adapters (env-configured) ------------------------------
def _real_price_at():
    from intent_engine.core.market_resolution import get_prices
    key = os.environ.get("TIINGO_API_KEY", "")

    def price_at(symbol: str, as_of: str) -> float:
        series = get_prices(symbol, as_of, as_of, api_key=key)
        if not series.observations:
            raise RuntimeError(f"no price for {symbol} at {as_of}")
        return series.observations[-1][1]
    return price_at


def _real_regime_for():
    def regime_for(as_of: str) -> str:
        try:
            from intent_engine.core.regime_engine import current_regime  # type: ignore
            return str(current_regime())
        except Exception:  # noqa: BLE001 - regime is best-effort context
            return "unknown"
    return regime_for


def _resolved_predictions(ledger_path):
    from intent_engine.core import prediction_ledger as pl
    return [p for p in pl.list_predictions(path=ledger_path)
            if p.outcome in ("happened", "did_not_happen")]


# --- jobs --------------------------------------------------------------------
def cmd_preflight(root, bus, as_of):
    from intent_engine.runtime.config_health import preflight
    return run_job("preflight", lambda: preflight(bus=bus, root=root),
                   root=root, bus=bus)


def cmd_market_open(root, bus, as_of, mr, price_at, regime_for):
    def work():
        require_config(root, bus, "market-open", {"TIINGO_API_KEY"})
        return mr.open_paper_from_predictions(
            as_of=as_of, price_at=price_at, regime_for=regime_for)
    return run_job("market-open", work, root=root, bus=bus)


def cmd_resolve(root, bus, as_of, mr, price_at):
    def work():
        require_config(root, bus, "resolve", {"TIINGO_API_KEY", "FRED_API_KEY"})
        return mr.resolve_and_link(as_of=as_of, price_at=price_at)
    return run_job("resolve", work, root=root, bus=bus)


def cmd_daily_candidates(root, bus, as_of, mr):
    return run_job("daily-candidates", mr.generate_daily_candidates,
                   root=root, bus=bus)


def cmd_weekly_eval(root, bus, as_of, mr):
    def work():
        return weekly_evaluate(mr.learning,
                               _resolved_predictions(mr.ledger_path))
    return run_job("weekly-eval", work, root=root, bus=bus)


def cmd_monthly_packet(root, bus, as_of, mr):
    def work():
        path = write_packet(mr.learning, Path(root) / "learning")
        return {"packet": str(path)}
    return run_job("monthly-packet", work, root=root, bus=bus)


def cmd_synthetic_daily(root, bus, as_of):
    def work():
        from intent_engine.core.synthetic_worlds import (
            generate_worlds, run_offline_eval,
        )
        from intent_engine.learning.synthetic_bridge import (
            candidates_from_synthetic_eval,
        )
        learning = LearningLedger(Path(root) / "learning_ledger.db", bus=bus)
        results = run_offline_eval(generate_worlds())
        ids = candidates_from_synthetic_eval(results, learning,
                                             eval_id=f"synthetic_{as_of}")
        if bus is not None:
            bus.publish("synthetic.run_completed", subject_type="synthetic_run",
                        subject_id=f"synthetic_{as_of}",
                        producer="synthetic_runner", actor_type="system",
                        actor_id="synthetic_runner", source="system",
                        payload={"worlds": len(results), "candidates": len(ids),
                                 "mode": "offline"},
                        idempotency_key=f"synthetic_run:{as_of}")
        return {"worlds": len(results), "candidates": ids}
    return run_job("synthetic-daily", work, root=root, bus=bus)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.runtime",
                                 description=__doc__)
    ap.add_argument("job", choices=[
        "preflight", "market-open", "resolve", "daily-candidates", "daily",
        "weekly-eval", "monthly-packet", "synthetic-daily", "health"])
    ap.add_argument("--root", default="data", type=Path)
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args(argv)
    as_of = args.as_of or today_ny().isoformat()
    bus = CompanyEventBus(args.root / "events")
    mr = MarketRuntime(args.root, bus=bus)

    if args.job == "health":
        print(json.dumps(latest_status(args.root), indent=2, default=str))
        return 0

    results = []
    if args.job in ("preflight", "daily"):
        results.append(cmd_preflight(args.root, bus, as_of))
    if args.job in ("market-open", "daily"):
        results.append(cmd_market_open(args.root, bus, as_of, mr,
                                       _real_price_at(), _real_regime_for()))
    if args.job in ("resolve", "daily"):
        results.append(cmd_resolve(args.root, bus, as_of, mr, _real_price_at()))
    if args.job in ("daily-candidates", "daily"):
        results.append(cmd_daily_candidates(args.root, bus, as_of, mr))
    if args.job == "weekly-eval":
        results.append(cmd_weekly_eval(args.root, bus, as_of, mr))
    if args.job == "monthly-packet":
        results.append(cmd_monthly_packet(args.root, bus, as_of, mr))
    if args.job == "synthetic-daily":
        results.append(cmd_synthetic_daily(args.root, bus, as_of))

    for r in results:
        print(json.dumps({"job": r.name, "status": r.status,
                          "error": r.error, "detail": r.detail},
                         indent=2, default=str))
    return 0 if all(r.status == "succeeded" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
