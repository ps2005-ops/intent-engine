#!/usr/bin/env python
"""Daily prediction runner — item 1 of docs/BA_ACCELERATION_PROPOSAL.md,
APPROVED 2026-07-18. Thin shell over core.daily_prediction_policy (all
policy is code there, unit-tested offline) + the existing, unchanged M7
pipeline pieces (fetch -> extraction -> mechanisms -> drafting -> record).

Numeric-only by design (headlines=[]) until item 3 (headline sourcing)
merges — per the approval's own sequencing.

Per-run budget: <=6 DATA calls (4 core FRED + SPY + today's rotating
extra), <=4 MODEL calls (1 extraction + 1 drafting; the +2 retry
allowance exists in the budget but this script does NOT auto-retry —
a failed call is a failed run, logged, try again tomorrow). Monthly
ESTIMATED spend ceiling $7 — checked BEFORE any call; if exceeded the
run PARKS loudly and does nothing.

Spend log: data/daily_runner_spend.jsonl (append-only, one row per
attempted run, including parked/failed ones — the ceiling check reads
this file, so it must never be trimmed by automation).

Scheduling: wired by the human, never by this script (house rule).

Usage: python scripts/daily_market_predictions.py [--entity-id macro-watch]
       [--path data/prediction_ledger.db] [--as-of YYYY-MM-DD] [--dry-run]
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from intent_engine.core import daily_prediction_policy as policy  # noqa: E402
from intent_engine.core.llm_client import LLMClient  # noqa: E402
from intent_engine.core.macro_data import get_series as get_fred_series  # noqa: E402
from intent_engine.core.market_resolution import get_prices as get_tiingo_prices  # noqa: E402
from intent_engine.core.mechanism_library import match_mechanisms  # noqa: E402
from intent_engine.core.prediction_ledger import (  # noqa: E402
    DEFAULT_LEDGER_PATH,
    list_predictions,
    record_prediction,
)
from intent_engine.core.regime_report import (  # noqa: E402
    DRAFT_SYSTEM_PROMPT,
    FAST_MODEL,
    assert_language_walls,
    extract_trigger_conditions,
    fetch_current_series_data,
    render_mechanisms_section,
    render_snapshot_numbers_for_extraction,
)

SPEND_LOG_PATH = REPO_ROOT / "data" / "daily_runner_spend.jsonl"
PLANNED_MODEL_CALLS = 2  # 1 extraction + 1 drafting; no auto-retry in this script

# Daily drafting schema: identical to M7's except maxItems matches the
# approved daily cap. The model still has NO record/include field — code
# (apply_daily_policy + record_prediction validation) decides.
DAILY_DRAFT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "predictions": {
            "type": "array",
            "minItems": 1,
            "maxItems": policy.DAILY_CAP,
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string", "maxLength": 300},
                    "probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "resolve_by": {"type": "string", "description": "ISO-8601 date"},
                    "resolution_rule": {
                        "type": "object",
                        "description": 'Either {"type":"pct_change","symbol":...,"op":...,"value":...,"window_days":...} or {"type":"level","series":...,"op":...,"value":...,"by":...}',
                    },
                },
                "required": ["claim_text", "probability", "resolve_by", "resolution_rule"],
            },
        },
    },
    "required": ["predictions"],
}


def _read_spend_rows() -> list:
    if not SPEND_LOG_PATH.exists():
        return []
    rows = []
    for line in SPEND_LOG_PATH.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a corrupt line never blocks the ceiling check; it just doesn't count
    return rows


def _append_spend_row(row: dict) -> None:
    SPEND_LOG_PATH.parent.mkdir(exist_ok=True)
    with open(SPEND_LOG_PATH, "a") as fh:
        fh.write(json.dumps(row) + "\n")


def _fetch_rotating_extra(as_of: date, fred_fetcher, price_fetcher):
    """Today's 6th DATA call. Failure is non-fatal (same discipline as
    fetch_current_series_data): warn and continue without the extra."""
    source, instrument = policy.rotating_extra_instrument(as_of)
    try:
        if source == "tiingo":
            series = price_fetcher(instrument, (as_of - timedelta(days=120)).isoformat(), as_of.isoformat())
            obs = [(d, v) for d, v in series.observations if d <= as_of.isoformat()]
            if not obs:
                return None
            first_date, first_val = obs[0]
            last_date, last_val = obs[-1]
            pct = (last_val / first_val - 1.0) * 100.0
            return (
                f"- {instrument} closed at {last_val:.2f} on {last_date}, a {pct:+.2f}% change from "
                f"{first_date} (source: Tiingo)"
            )
        series = fred_fetcher(instrument, (as_of - timedelta(days=120)).isoformat(), as_of.isoformat())
        obs = [(d, v) for d, v in series.observations if d <= as_of.isoformat()]
        if not obs:
            return None
        last_date, last_val = obs[-1]
        return f"- {instrument}: {last_val:.2f} as of {last_date} (source: FRED, series {instrument})"
    except (ValueError, RuntimeError) as exc:
        print(f"WARNING: rotating extra {instrument!r} fetch failed ({exc}) -- continuing without it.")
        return None


def _daily_draft_addendum(as_of: date) -> str:
    families = ", ".join(policy.mechanism_families_for(as_of))
    instruments = ", ".join(policy.allowed_instruments_today(as_of))
    buckets = ", ".join(f"~{b}d" for b in policy.HORIZON_BUCKETS)
    return (
        f"\n\nDAILY RUN CONSTRAINTS (enforced in code after you draft — drafts violating them are dropped):\n"
        f"- Draft up to {policy.DAILY_CAP} predictions this run (fewer is fine; zero-signal days should draft fewer).\n"
        f"- resolution_rule instruments MUST be among: {instruments} (today's grounded set).\n"
        f"- resolve_by must be at least {policy.MIN_HORIZON_DAYS} days out; spread across horizons ({buckets}), "
        f"at most 2 per horizon.\n"
        f"- Today's emphasized mechanism families: {families} — prefer these where the evidence genuinely "
        f"supports them; do not force a prediction from an unsupported family."
    )


def run_daily(
    entity_id: str,
    as_of: date = None,
    ledger_path=DEFAULT_LEDGER_PATH,
    client: LLMClient = None,
    fred_fetcher=get_fred_series,
    price_fetcher=get_tiingo_prices,
    dry_run: bool = False,
    spend_rows: list = None,
) -> dict:
    """Returns a run summary dict (also printed). Injectable fetchers/client
    for offline tests; live defaults for the real cron run."""
    as_of = as_of or date.today()
    summary = {"date": as_of.isoformat(), "status": None, "recorded": 0, "baselines": 0,
               "model_calls": 0, "data_calls": 0, "rejected": []}

    if not policy.is_trading_day(as_of):
        summary["status"] = "skipped-non-trading-day"
        print(f"[{as_of}] Non-trading day -- nothing to do.")
        return summary

    spend_rows = spend_rows if spend_rows is not None else _read_spend_rows()
    if policy.ceiling_exceeded(spend_rows, as_of, PLANNED_MODEL_CALLS):
        summary["status"] = "PARKED-spend-ceiling"
        print(f"[{as_of}] PARKED: monthly estimated spend would exceed "
              f"${policy.MONTHLY_SPEND_CEILING_USD:.2f}. No calls made. "
              f"Raising the ceiling is a human decision, not this script's.")
        if not dry_run:
            _append_spend_row({"date": as_of.isoformat(), "status": summary["status"],
                               "model_calls": 0, "data_calls": 0})
        return summary

    # --- data (<=6 calls) ---------------------------------------------------
    series_data, price_series = fetch_current_series_data(
        as_of, fred_fetcher=fred_fetcher, price_fetcher=price_fetcher)  # 5 calls
    extraction_text = render_snapshot_numbers_for_extraction(series_data, price_series, as_of)
    extra_line = _fetch_rotating_extra(as_of, fred_fetcher, price_fetcher)  # 1 call
    summary["data_calls"] = 6
    if extra_line:
        extraction_text = extraction_text + "\n" + extra_line

    if not extraction_text.strip():
        summary["status"] = "no-data"
        print(f"[{as_of}] No snapshot data available at all -- refusing to draft on nothing.")
        if not dry_run:
            _append_spend_row({"date": as_of.isoformat(), "status": summary["status"],
                               "model_calls": 0, "data_calls": summary["data_calls"]})
        return summary

    if dry_run:
        summary["status"] = "dry-run"
        print(f"[{as_of}] DRY RUN -- snapshot assembled ({summary['data_calls']} data calls), "
              f"no model calls, nothing recorded.\n{extraction_text}")
        return summary

    # --- model (<=2 calls, numeric-only: headlines=[]) ----------------------
    client = client or LLMClient(model=FAST_MODEL)
    trigger_conditions = extract_trigger_conditions(extraction_text, [], client=client)
    summary["model_calls"] += 1
    mechanisms_text = render_mechanisms_section(match_mechanisms(trigger_conditions))

    user_message = (
        f"Today's real date is {as_of.isoformat()}.\n\n"
        f"Real regime snapshot:\n{extraction_text}\n\n{mechanisms_text}\n\nDraft the predictions."
    )
    result = client.call_tool(
        system=DRAFT_SYSTEM_PROMPT + _daily_draft_addendum(as_of),
        user_message=user_message,
        tool_name="record_candidate_market_predictions",
        tool_description="Record candidate resolvable market predictions.",
        input_schema=DAILY_DRAFT_TOOL_SCHEMA,
        max_tokens=1200,
    )
    summary["model_calls"] += 1
    candidates = result.get("predictions", [])

    # --- policy gate (code decides) -----------------------------------------
    unresolved = list_predictions(source="market", unresolved_only=True, path=ledger_path)
    already_today = sum(
        1 for p in unresolved if p.created_at.startswith(as_of.isoformat())
    )
    decision = policy.apply_daily_policy(candidates, as_of, unresolved, already_recorded_today=already_today)
    summary["rejected"] = [reason for _, reason in decision.rejected]

    recorded = []
    for cand in decision.accepted:
        rule = cand.get("resolution_rule")
        key = policy.candidate_key(cand, as_of)
        try:
            p = record_prediction(
                source="market", entity_id=entity_id,
                claim_text=cand["claim_text"], probability=cand["probability"],
                resolve_by=cand["resolve_by"], path=ledger_path,
                instrument=key.instrument,
                direction=key.direction,
                horizon_days=(date.fromisoformat(cand["resolve_by"]) - as_of).days,
                resolution_rule=rule,
                resolution_source="tiingo" if isinstance(rule, dict) and rule.get("type") == "pct_change" else "fred",
            )
        except Exception as exc:  # malformed rule from the model: skipped, never persisted
            summary["rejected"].append(f"record-time validation: {exc}")
            continue
        recorded.append(p)
    summary["recorded"] = len(recorded)

    # Language wall on everything this run persisted (same phrases as A-M4).
    if recorded:
        assert_language_walls("\n".join(p.claim_text for p in recorded))

    # --- baselines (unconditional daily pair per 2026-07-18 amendment;
    # real <=2/day cap enforced against the ledger, zero extra DATA calls).
    # "Today's" baselines are identified by resolve_by == as_of + 60d (both
    # M8 baselines are exactly that by construction) -- deterministic and
    # correct under --as-of overrides, unlike a created_at timestamp match.
    baseline_resolve_by = (as_of + timedelta(days=60)).isoformat()
    baselines_today = sum(
        1 for p in list_predictions(source="baseline", path=ledger_path)
        if p.resolve_by == baseline_resolve_by
    )
    quota = max(0, policy.baseline_quota(decision.accepted, as_of) - baselines_today)
    if quota > 0:
        import record_baselines as baselines  # noqa: E402  (scripts/ on path)
        price_id, price_obs = price_series

        class _CachedSpy:
            def __init__(self, observations):
                self.observations = observations

        def cached_price_fetcher(symbol, start, end):
            if symbol != price_id:
                raise RuntimeError(f"cached fetcher only holds {price_id!r}")
            return _CachedSpy([(d, v) for d, v in price_obs if start <= d <= end])

        try:
            baselines.record_momentum_baseline(
                entity_id, path=ledger_path, price_fetcher=cached_price_fetcher, today=as_of)
            summary["baselines"] += 1
            if quota > 1:
                baselines.record_base_rate_baseline(entity_id, path=ledger_path, today=as_of)
                summary["baselines"] += 1
        except RuntimeError as exc:
            print(f"WARNING: baseline recording skipped ({exc}).")

    summary["status"] = "ok"
    _append_spend_row({"date": as_of.isoformat(), "status": "ok",
                       "model_calls": summary["model_calls"], "data_calls": summary["data_calls"],
                       "recorded": summary["recorded"], "baselines": summary["baselines"]})

    print(f"[{as_of}] recorded {summary['recorded']} market prediction(s), "
          f"{summary['baselines']} baseline(s); {len(decision.rejected)} candidate(s) rejected by policy.")
    for _, reason in decision.rejected:
        print(f"  rejected: {reason}")
    for p in recorded:
        print(f"  P={p.probability:.2f} by {p.resolve_by} [{p.instrument}]: {p.claim_text}")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-id", default="macro-watch")
    parser.add_argument("--path", default=str(DEFAULT_LEDGER_PATH))
    parser.add_argument("--as-of", default=None, help="ISO date override (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="data fetch + snapshot only; no model calls, no writes")
    args = parser.parse_args(argv)
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    summary = run_daily(args.entity_id, as_of=as_of, ledger_path=args.path, dry_run=args.dry_run)
    return 0 if summary["status"] in ("ok", "dry-run", "skipped-non-trading-day") else 1


if __name__ == "__main__":
    sys.exit(main())
