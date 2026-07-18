"""Market-engine phase, Task M7 (market-engine-execution-plan.md): the
user-facing product of this phase. Assembles (1) a regime snapshot table
with provenance, (2) a "structural mechanisms possibly in play" section
(real extraction, since M4 passed -- an isolated call, information-hiding,
the exact prompt/schema design M4's gate verified, duplicated here as
fresh production code rather than importing M4's TEST-ONLY scaffolding
per its own scope wall) -> M3's deterministic matcher, (3) 1-3 resolvable
market predictions from one isolated drafting call (house pattern: the
model's schema has ONLY claim_text/probability/resolve_by/resolution_rule
-- no record/include field, code validates the rule via M5's Prediction
model and records source="market"), and (4) a read-only calibration
footer (counts + mean Brier per source, once any resolutions exist --
display only, per A-M5, never fed back into generation).

Language walls (A-M4), enforced structurally, not just by prompt request:
assert_language_walls() greps the FULLY RENDERED report for the banned
phrases and raises if any are found -- a real, code-level backstop, not
a hope that the prompts alone are enough.

SCOPE WALLS, per the task's own spec: additive rendering only. The
premortem combined-call prompt (core/analysis.py) is untouched. No trade
advice, no position sizing, no Alpaca.
"""

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .llm_client import LLMClient
from .macro_data import FredSeries
from .macro_data import get_series as get_fred_series
from .market_resolution import TiingoSeries
from .market_resolution import get_prices as get_tiingo_prices
from .mechanism_library import RankedMechanism, TriggerCondition, match_mechanisms
from .prediction_ledger import DEFAULT_LEDGER_PATH, Prediction, brier_summary, record_prediction
from .regime_engine import (
    credit_spread_percentile,
    curve_inversion,
    drawdown_state,
    inflation_trend,
    regime_snapshot,
    unemployment_momentum,
)

FAST_MODEL = "claude-haiku-4-5-20251001"

FRED_SNAPSHOT_SERIES = ["T10Y2Y", "BAMLH0A0HYM2", "CPIAUCSL", "UNRATE"]
PRICE_INSTRUMENT = "SPY"

# --- real data fetch (M1 FRED client + M6 Tiingo client, unchanged) --------


def fetch_current_series_data(
    as_of: date, fred_fetcher=get_fred_series, price_fetcher=get_tiingo_prices,
) -> Tuple[Dict[str, FredSeries], Tuple[str, list]]:
    """4 real FRED calls (enough lookback for each M2 indicator) + 1 real
    Tiingo call (SPY, for a real drawdown_state instead of "unavailable")
    -- 5 DATA calls total, within the task's <=6 budget.

    Real finding from this task's own live verification, not glossed
    over: daily FRED series (T10Y2Y, BAMLH0A0HYM2) mark market-holiday
    dates with "." (e.g. Juneteenth) -- M1's hard NaN guard (already
    reviewed, correct, untouched here) raises on ANY such value anywhere
    in the fetched range, so a multi-day (or, for BAMLH0A0HYM2's 10-year
    lookback, near-certain) window will eventually hit one. Rather than
    weaken M1's guard or add retry/gap-skipping logic to it, a per-series
    fetch failure here is caught and that series is simply OMITTED from
    series_data -- M2's regime_snapshot() already has an explicit,
    already-tested "series missing from series_data -> unavailable" path
    for exactly this shape of gap; this reuses it rather than inventing a
    second, parallel resilience mechanism. Never silent: a warning is
    printed naming which series and why."""
    as_of_str = as_of.isoformat()
    fetch_windows = {
        # curve_inversion only ever reads observations[-1] -- a narrow
        # window (just enough to survive a long weekend) both costs
        # nothing extra (still one fetch) and is far less likely to
        # contain a market-holiday gap than a wide one; the other 3
        # series structurally need their full lookback (a 10y percentile,
        # a 24mo/15mo YoY-style calc) and can't be narrowed the same way.
        "T10Y2Y": (as_of - timedelta(days=10)).isoformat(),
        "BAMLH0A0HYM2": (as_of - timedelta(days=3653)).isoformat(),
        "CPIAUCSL": (as_of - timedelta(days=790)).isoformat(),
        "UNRATE": (as_of - timedelta(days=500)).isoformat(),
    }
    series_data: Dict[str, FredSeries] = {}
    for series_id, start in fetch_windows.items():
        try:
            series_data[series_id] = fred_fetcher(series_id, start, as_of_str)
        except (ValueError, RuntimeError) as exc:
            print(f"WARNING: could not fetch {series_id!r} ({exc}) -- omitted, will render as 'unavailable'.")

    try:
        spy = price_fetcher(PRICE_INSTRUMENT, (as_of - timedelta(days=365)).isoformat(), as_of_str)
        price_series = (PRICE_INSTRUMENT, spy.observations)
    except (ValueError, RuntimeError) as exc:
        print(f"WARNING: could not fetch {PRICE_INSTRUMENT!r} prices ({exc}) -- drawdown will render as 'unavailable'.")
        price_series = (PRICE_INSTRUMENT, [])

    return series_data, price_series


# --- extraction: same prompt/schema design M4's gate verified --------------
# (duplicated here deliberately, not imported -- M4's own script is
# TEST-ONLY scaffolding per its scope wall; this is the first real
# production instance of that verified design)

TRIGGER_CONDITIONS = list(TriggerCondition.__args__)

EXTRACTION_SYSTEM_PROMPT = f"""You are identifying which of a fixed set of structural/regime conditions are \
present, given a snapshot of raw macro/market numbers (with their source and observation date) and a short \
set of news headlines. You have no information about any historical pattern, precedent, or named phenomenon \
this might resemble -- judge ONLY what the numbers and headlines themselves state or clearly support. The \
numbers are raw facts, not pre-made judgments -- you must decide yourself whether a given number rises to the \
level each condition name describes.

The closed set of conditions you may select from (select ONLY ones the numbers or headlines actually support --\
 do not select a condition on a vague or generic resemblance):
{chr(10).join(f"- {c}" for c in TRIGGER_CONDITIONS)}

If the numbers and headlines are genuinely mixed, borderline, or don't clearly support any condition, select \
FEW or NONE -- do not force a selection to seem thorough. Confidence should track how clearly the evidence \
actually supports each condition, not how many conditions you can find a stretch for."""

EXTRACTION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "trigger_conditions": {
            "type": "array",
            "items": {"type": "string", "enum": TRIGGER_CONDITIONS},
            "description": "The subset of conditions the numbers/headlines actually, clearly support.",
        },
    },
    "required": ["trigger_conditions"],
}


def render_snapshot_numbers_for_extraction(
    series_data: Dict[str, FredSeries], price_series: Tuple[str, list], as_of: date,
) -> str:
    """"No interpretation" rendering, exactly M4's discipline: only the RAW
    numeric fields from regime_engine's own functions -- never the
    derived boolean/label fields (inverted, triggered, trend) that would
    hand the model its own answer."""
    as_of_str = as_of.isoformat()
    lines = []

    t10y2y_series = series_data.get("T10Y2Y")
    t10y2y_obs = [(d, v) for d, v in t10y2y_series.observations if d <= as_of_str] if t10y2y_series else []
    if t10y2y_obs:
        latest_date, latest_value = t10y2y_obs[-1]
        lines.append(f"- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): {latest_value:+.2f} percentage points as of {latest_date} (source: FRED, series T10Y2Y)")

    hy_series = series_data.get("BAMLH0A0HYM2")
    hy_obs = [(d, v) for d, v in hy_series.observations if d <= as_of_str] if hy_series else []
    if hy_obs:
        pct_result = credit_spread_percentile(hy_obs)
        lines.append(f"- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the {pct_result.percentile:.0f}th percentile of its own trailing {pct_result.lookback_years}-year window as of {pct_result.provenance.observation_date} (source: FRED, series BAMLH0A0HYM2)")

    cpi_series = series_data.get("CPIAUCSL")
    cpi_obs = [(d, v) for d, v in cpi_series.observations if d <= as_of_str] if cpi_series else []
    if len(cpi_obs) >= 24:
        infl_result = inflation_trend(cpi_obs)
        lines.append(f"- CPI year-over-year: averaged {infl_result.yoy_3m_avg:.2f}% over the last 3 months vs. {infl_result.yoy_12m_avg:.2f}% over the last 12 months (source: FRED, series CPIAUCSL, as of {infl_result.provenance.observation_date})")

    unrate_series = series_data.get("UNRATE")
    unrate_obs = [(d, v) for d, v in unrate_series.observations if d <= as_of_str] if unrate_series else []
    if len(unrate_obs) >= 15:
        unemp_result = unemployment_momentum(unrate_obs)
        lines.append(f"- Unemployment rate: 3-month moving average currently {unemp_result.delta:+.2f} percentage points relative to its own low over the prior 12 months (source: FRED, series UNRATE, as of {unemp_result.provenance.observation_date})")

    price_id, price_obs = price_series
    price_obs_filtered = [(d, v) for d, v in price_obs if d <= as_of_str]
    if price_obs_filtered:
        dd_result = drawdown_state(price_obs_filtered, series_id=price_id)
        lines.append(f"- {price_id} is currently {dd_result.pct_off_high:.2f}% off its own recent running high (source: Tiingo, as of {dd_result.provenance.observation_date})")

    return "\n".join(lines)


def extract_trigger_conditions(
    snapshot_text: str, headlines: List[str], client: Optional[LLMClient] = None,
) -> List[str]:
    """One real, isolated call -- the reliability protocol (M4) already
    verified this exact prompt/schema design; a real production run needs
    only one call, not 5."""
    client = client or LLMClient(model=FAST_MODEL)
    headlines_text = "\n".join(f'- "{h}"' for h in headlines)
    user_message = f"Regime snapshot:\n{snapshot_text}\n\nHeadlines:\n{headlines_text}\n\nWhich conditions are present?"
    result = client.call_tool(
        system=EXTRACTION_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="record_trigger_conditions",
        tool_description="Record the identified trigger conditions.",
        input_schema=EXTRACTION_TOOL_SCHEMA,
        max_tokens=200,
    )
    return sorted(result["trigger_conditions"])


def render_mechanisms_section(ranked: List[RankedMechanism]) -> str:
    if not ranked:
        return "Structural mechanisms possibly in play: none matched -- no forced match on an empty/weak signal."
    lines = ["Structural mechanisms possibly in play:"]
    for r in ranked:
        instance = r.mechanism.historical_instances[0]
        lines.append(
            f"- {r.mechanism.name} ({r.mechanism.confidence_tier}) -- matched on: "
            f"{', '.join(r.matched_conditions)}. Historical instance: {instance.case} ({instance.year})."
        )
    return "\n".join(lines)


# --- prediction drafting: house pattern (model drafts, code decides) -------

DRAFT_SYSTEM_PROMPT = """You are drafting a small number of concrete, RESOLVABLE market/macro predictions \
grounded in a real regime snapshot and any structural mechanisms flagged as possibly in play. A resolvable \
prediction is specific enough that code can check it later against real market/economic data.

Rules:
- Draft 1-3 predictions, no more. Fewer, sharper predictions beat more, vaguer ones.
- Ground every prediction in the numbers or mechanisms actually given -- never invent a scenario unconnected \
to what's stated.
- probability is your real, honest estimate that the claim happens, 0 to 1 -- not a default 0.5.
- resolve_by must be a real future date (a few weeks to a few months out, matching the resolution_rule's own \
window/target).
- Never use "will", "buy", "sell", or position-sizing language anywhere in claim_text -- phrase claims as \
falsifiable research statements ("possibly in play", "consistent with", "P=0.xx by <date>"), not trade advice.
- resolution_rule must be ONE of exactly two machine-evaluable shapes:
  pct_change: {"type":"pct_change","symbol":"SPY","op":">=","value":0.02,"window_days":60} (graded against \
Tiingo adjusted closes)
  level: {"type":"level","series":"UNRATE","op":">=","value":4.5,"by":"2026-12-31"} (graded against FRED)
  Use only real, well-known symbols/series (e.g. SPY; UNRATE, CPIAUCSL, T10Y2Y, BAMLH0A0HYM2 for level rules)."""

DRAFT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "predictions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string", "maxLength": 300},
                    "probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "resolve_by": {"type": "string", "description": "ISO-8601 date, e.g. 2026-12-31"},
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


def draft_market_predictions(
    entity_id: str,
    snapshot_text: str,
    mechanisms_text: str,
    client: Optional[LLMClient] = None,
    ledger_path: Union[str, Path] = DEFAULT_LEDGER_PATH,
    as_of: Optional[date] = None,
) -> List[Prediction]:
    """Drafts 1-3 market predictions and records them, source="market".
    Model drafts; code decides: the tool schema has no record/include
    field (only claim_text/probability/resolve_by/resolution_rule -- the
    same house pattern as premortem_prediction_bridge.py, checked
    directly by a test, not just asserted here). A malformed
    resolution_rule (from the model, not from us) is skipped, not
    persisted -- record_prediction()'s own pydantic validation is the
    real backstop."""
    client = client or LLMClient(model=FAST_MODEL)
    as_of = as_of or datetime.now(timezone.utc).date()
    today_str = as_of.isoformat()

    user_message = (
        f"Today's real date is {today_str}.\n\n"
        f"Real regime snapshot:\n{snapshot_text}\n\n{mechanisms_text}\n\nDraft the predictions."
    )
    result = client.call_tool(
        system=DRAFT_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="record_candidate_market_predictions",
        tool_description="Record candidate resolvable market predictions.",
        input_schema=DRAFT_TOOL_SCHEMA,
        max_tokens=800,
    )

    recorded: List[Prediction] = []
    for candidate in result["predictions"]:
        try:
            resolve_by_date = date.fromisoformat(candidate["resolve_by"])
        except (ValueError, TypeError):
            continue
        if resolve_by_date <= as_of:
            continue  # code-level backstop: never persist a non-future resolve_by
        rule = candidate.get("resolution_rule")
        instrument = rule.get("symbol") if isinstance(rule, dict) else rule.get("series") if isinstance(rule, dict) else None
        try:
            p = record_prediction(
                source="market",
                entity_id=entity_id,
                claim_text=candidate["claim_text"],
                probability=candidate["probability"],
                resolve_by=candidate["resolve_by"],
                path=ledger_path,
                instrument=instrument,
                resolution_rule=rule,
                resolution_source="tiingo" if isinstance(rule, dict) and rule.get("type") == "pct_change" else "fred",
            )
        except Exception:
            continue  # malformed rule/probability from the model -- skipped, never persisted as garbage
        recorded.append(p)
    return recorded


# --- rendering: snapshot table, calibration footer, language walls ---------


def render_snapshot_table(snapshot: dict) -> str:
    rows = [f"REGIME SNAPSHOT -- as of {snapshot['snapshot_date']}", "-" * 70]

    ci = snapshot["curve_inversion"]
    if ci == "unavailable":
        rows.append("Yield curve (T10Y2Y):        unavailable")
    else:
        state = f"inverted, depth {ci.depth:.2f}pp" if ci.inverted else "not inverted"
        rows.append(f"Yield curve (T10Y2Y):        {state}  [FRED T10Y2Y, {ci.provenance.observation_date}]")

    cs = snapshot["credit_spread_percentile"]
    if cs == "unavailable":
        rows.append("Credit spreads (HY OAS):     unavailable")
    else:
        rows.append(f"Credit spreads (HY OAS):     {cs.percentile:.0f}th percentile of {cs.lookback_years}y window  [FRED BAMLH0A0HYM2, {cs.provenance.observation_date}]")

    it = snapshot["inflation_trend"]
    if it == "unavailable":
        rows.append("Inflation trend (CPI YoY):   unavailable")
    else:
        rows.append(f"Inflation trend (CPI YoY):   {it.trend} (3m avg {it.yoy_3m_avg:.2f}% vs 12m avg {it.yoy_12m_avg:.2f}%)  [FRED CPIAUCSL, {it.provenance.observation_date}]")

    um = snapshot["unemployment_momentum"]
    if um == "unavailable":
        rows.append("Unemployment momentum:       unavailable")
    else:
        rows.append(f"Unemployment momentum:       {'triggered' if um.triggered else 'not triggered'} (delta {um.delta:+.2f}pp)  [FRED UNRATE, {um.provenance.observation_date}]")

    dd = snapshot["drawdown_state"]
    if dd == "unavailable":
        rows.append("Drawdown (SPY):              unavailable")
    else:
        rows.append(f"Drawdown ({dd.provenance.series_id}):              {dd.pct_off_high:.2f}% off recent high  [Tiingo, {dd.provenance.observation_date}]")

    return "\n".join(rows)


def render_data_gaps_section(series_data: Dict[str, FredSeries]) -> str:
    """2026-07-18 guard amendment: genuine FRED gaps (macro_data rule 3) are
    surfaced LOUDLY in the rendered report, not just in logs. Returns ""
    when there are no gaps -- the section only exists when there's
    something a human must see."""
    gap_lines = []
    for series_id in sorted(series_data):
        gaps = getattr(series_data[series_id], "gaps", [])
        if gaps:
            first, last = gaps[0], gaps[-1]
            span = first if first == last else f"{first}..{last}"
            gap_lines.append(f"- {series_id}: {len(gaps)} missing observation(s) ({span}) -- genuine data "
                             "gap(s), excluded from every number above; NOT holiday placeholders.")
    if not gap_lines:
        return ""
    return "\n".join(["!! DATA GAPS DETECTED (review before trusting affected indicators)",
                      "-" * 70] + gap_lines)


def render_calibration_footer(path: Union[str, Path] = DEFAULT_LEDGER_PATH) -> str:
    lines = ["CALIBRATION (read-only; no feedback into generation)", "-" * 70]
    any_resolved = False
    for source in ("market", "baseline"):
        summary = brier_summary(source=source, path=path)
        if summary.count == 0:
            lines.append(f"{source}: no resolutions yet.")
        else:
            any_resolved = True
            lines.append(f"{source}: {summary.count} resolved, mean Brier {summary.mean_brier:.4f}")
    if not any_resolved:
        lines.append("(The ledger accumulates from here -- per A-M5, no confidence adjustment happens until "
                      "at least 30 resolved predictions per source exist.)")
    return "\n".join(lines)


LANGUAGE_WALL_FORBIDDEN = ["will happen", "buy", "sell", "position size"]


def assert_language_walls(rendered_report: str) -> None:
    lowered = rendered_report.lower()
    violations = [phrase for phrase in LANGUAGE_WALL_FORBIDDEN if phrase in lowered]
    if violations:
        raise ValueError(f"Language wall violation(s) in rendered report: {violations}")


def render_full_report(
    snapshot: dict, mechanisms_text: str, predictions: List[Prediction], ledger_path: Union[str, Path] = DEFAULT_LEDGER_PATH,
    data_gaps_text: str = "",
) -> str:
    sections = [
        render_snapshot_table(snapshot),
        "",
    ]
    if data_gaps_text:
        sections += [data_gaps_text, ""]
    sections += [
        mechanisms_text,
        "",
        "RESOLVABLE PREDICTIONS RECORDED THIS RUN (source=market)",
        "-" * 70,
    ]
    if not predictions:
        sections.append("None recorded this run.")
    else:
        for p in predictions:
            sections.append(f"- P={p.probability:.2f} by {p.resolve_by}: {p.claim_text}")
    sections += ["", render_calibration_footer(ledger_path)]
    report = "\n".join(sections)
    assert_language_walls(report)
    return report
