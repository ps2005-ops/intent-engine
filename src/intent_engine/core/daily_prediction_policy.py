"""Daily prediction cadence policy — item 1 of docs/BA_ACCELERATION_PROPOSAL.md,
APPROVED by direct user decision 2026-07-18 exactly as proposed.

Pure, deterministic policy: no I/O, no LLM, no clock reads (every function
takes `as_of` explicitly). The daily runner (scripts/daily_market_predictions.py)
is a thin shell over these functions; everything here is unit-tested offline.

CADENCE V2 (founder-approved 2026-07-19, docs/CADENCE_V2_PROPOSAL.md —
all three numbers approved as proposed: widened allowlist, cap 5→8,
ceiling unchanged at $7):

What this module enforces IN CODE (never left to the prompt):
- instrument allowlist (22 Tiingo tickers + 12 FRED series, exactly as
  approved — v1 was 7+6);
- hard cap of 8 recorded market predictions per day (v1: 5);
- minimum horizon floor of 14 days; horizon buckets {14, 30, 60, 90};
- per-bucket spread (max 2 per bucket per day, unchanged — 8/day fills
  4 buckets at exactly 2 each) so density can't clump;
- anti-duplication vs. unresolved live predictions AND within a day's batch
  (same instrument + rule type + direction + horizon bucket = duplicate);
- baseline cap (2/day), unconditional per the 2026-07-18 amendment;
- deterministic, date-seeded mechanism-family rotation and a rotating
  5-instrument extra window (so the ≤10 DATA-call budget holds — v1 was
  1 extra / ≤6 — while coverage widens);
- monthly spend ceiling ($7/mo, ESTIMATED — see SPEND note; unchanged in
  v2: breadth adds $0 data calls, not model calls) with park-if-exceeded
  semantics.

Unchanged walls (restated so this module can't be misread as relaxing them):
no early resolution of live predictions except by their own rules; Alpaca
stays gated behind >=30 LIVE resolved + human calibration review; append-only
ledger; calibration is read-only w.r.t. generation until that gate.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

# --- approved constants (do not widen without a new written decision) -------
# Cadence v2 (founder-approved 2026-07-19): sector ETFs (all 11 GICS SPDRs),
# broad/intl/credit breadth, and 6 more FRED macro series.

TIINGO_INSTRUMENTS: Tuple[str, ...] = (
    # v1 (2026-07-18 approval):
    "SPY", "QQQ", "IWM", "TLT", "GLD", "XLE", "XLF",
    # v2 — remaining GICS sector SPDRs:
    "XLK", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC",
    # v2 — broad/intl/credit breadth:
    "DIA", "MDY", "EFA", "EEM", "HYG", "LQD",
)
FRED_SERIES: Tuple[str, ...] = (
    # v1 (2026-07-18 approval):
    "T10Y2Y", "UNRATE", "CPIAUCSL", "BAMLH0A0HYM2", "DGS10", "VIXCLS",
    # v2 — curve ends, breakevens, dollar, oil, EURUSD:
    "DGS2", "DGS30", "T10YIE", "DTWEXBGS", "DCOILWTICO", "DEXUSEU",
)

HORIZON_BUCKETS: Tuple[int, ...] = (14, 30, 60, 90)
MIN_HORIZON_DAYS = 14
DAILY_CAP = 8  # v2 (v1: 5) — fills the 4 horizon buckets at exactly 2 each
MAX_PER_BUCKET_PER_DAY = 2
BASELINE_DAILY_CAP = 2

MECHANISM_FAMILIES: Tuple[str, ...] = (
    "curve", "credit", "inflation", "labor", "drawdown", "momentum",
)

# SPEND: the ceiling is on ESTIMATED cost, computed deterministically from
# call counts (we have no billing API here). $0.02/model call is a deliberate
# over-estimate for haiku-class calls of this size; data calls are $0
# (Tiingo/FRED free tiers). Park-if-exceeded triggers on the estimate — the
# honest failure mode is stopping too early, never overspending silently.
ESTIMATED_COST_PER_MODEL_CALL_USD = 0.02
MONTHLY_SPEND_CEILING_USD = 7.00

# Cadence v2: the rotating extras are now a WINDOW of 5 instruments per day
# (data calls 6-10) beyond the core snapshot (4 FRED + SPY = calls 1-5).
# The pool is every allowlisted instrument outside the core+SPY set (29
# entries). The window start steps by the window size each day; since
# gcd(5, 29) == 1 the rotation visits every instrument and every alignment
# — full-pool coverage with zero scheduling state. Deterministic by date
# ordinal, exactly like v1.
_ROTATING_EXTRAS: Tuple[Tuple[str, str], ...] = tuple(
    [("tiingo", t) for t in TIINGO_INSTRUMENTS if t != "SPY"]
    + [("fred", s) for s in FRED_SERIES if s not in ("T10Y2Y", "UNRATE", "CPIAUCSL", "BAMLH0A0HYM2")]
)

DAILY_EXTRA_INSTRUMENT_COUNT = 5  # v2 (v1: 1) — keeps the run at <=10 data calls

CORE_SNAPSHOT_SERIES: Tuple[str, ...] = ("T10Y2Y", "UNRATE", "CPIAUCSL", "BAMLH0A0HYM2")


def is_trading_day(as_of: date) -> bool:
    """Mon-Fri. US market holidays are NOT special-cased: on a holiday the
    fetchers simply return the last trading day's data and the run is a
    cheap, harmless near-no-op — simpler and more honest than maintaining a
    holiday calendar that can silently go stale."""
    return as_of.weekday() < 5


def mechanism_families_for(as_of: date, count: int = 3) -> Tuple[str, ...]:
    """Deterministic date-seeded rotation: which mechanism families the
    drafting prompt EMPHASIZES today (emphasis only — extraction and the
    mechanism matcher are untouched; a family outside today's emphasis can
    still match if the evidence supports it)."""
    start = as_of.toordinal() % len(MECHANISM_FAMILIES)
    doubled = MECHANISM_FAMILIES + MECHANISM_FAMILIES
    return doubled[start : start + count]


def rotating_extra_instruments(as_of: date) -> Tuple[Tuple[str, str], ...]:
    """Cadence v2: today's window of DAILY_EXTRA_INSTRUMENT_COUNT extra
    (source, instrument_id) pairs — data calls 6-10. Window start steps by
    the window size daily (gcd(window, pool) == 1 ⇒ full coverage)."""
    pool = _ROTATING_EXTRAS
    start = (as_of.toordinal() * DAILY_EXTRA_INSTRUMENT_COUNT) % len(pool)
    doubled = pool + pool
    return doubled[start : start + DAILY_EXTRA_INSTRUMENT_COUNT]


def rotating_extra_instrument(as_of: date) -> Tuple[str, str]:
    """(source, instrument_id) for today's FIRST rotating extra. Kept for
    call-site stability; v2 call sites should use rotating_extra_instruments."""
    return rotating_extra_instruments(as_of)[0]


def allowed_instruments_today(as_of: date) -> Tuple[str, ...]:
    """Rules may only reference instruments grounded in TODAY's snapshot:
    the core series, SPY, and today's rotating extras. (The full allowlist
    bounds what may EVER appear; this bounds what may appear TODAY, keeping
    the grounding-in-shown-numbers discipline intact.)"""
    extras = tuple(inst for _, inst in rotating_extra_instruments(as_of))
    return CORE_SNAPSHOT_SERIES + ("SPY",) + extras


def horizon_bucket(as_of: date, resolve_by: str) -> Optional[int]:
    """Nearest approved bucket, or None when below the 14-day floor or
    unparseable. Ties round DOWN (shorter bucket) deterministically."""
    try:
        rb = date.fromisoformat(resolve_by)
    except (ValueError, TypeError):
        return None
    days = (rb - as_of).days
    if days < MIN_HORIZON_DAYS:
        return None
    return min(HORIZON_BUCKETS, key=lambda b: (abs(days - b), b))


def rule_instrument(rule) -> Optional[str]:
    if isinstance(rule, dict):
        return rule.get("symbol") or rule.get("series")
    return getattr(rule, "symbol", None) or getattr(rule, "series", None)


def rule_direction(rule) -> Optional[str]:
    """Coarse deterministic direction key for dedup purposes: rule type +
    comparison op + (for pct_change) the sign of the threshold."""
    if isinstance(rule, dict):
        rtype, op, value = rule.get("type"), rule.get("op"), rule.get("value")
    else:
        rtype = getattr(rule, "type", None)
        op = getattr(rule, "op", None)
        value = getattr(rule, "value", None)
    if rtype is None or op is None:
        return None
    if rtype == "pct_change" and isinstance(value, (int, float)):
        sign = "+" if value >= 0 else "-"
        return f"{rtype}:{op}:{sign}"
    return f"{rtype}:{op}"


class CandidateKey(NamedTuple):
    instrument: Optional[str]
    direction: Optional[str]
    bucket: Optional[int]


def candidate_key(candidate: dict, as_of: date) -> CandidateKey:
    rule = candidate.get("resolution_rule")
    return CandidateKey(
        instrument=rule_instrument(rule),
        direction=rule_direction(rule),
        bucket=horizon_bucket(as_of, candidate.get("resolve_by")),
    )


def prediction_key(prediction, as_of: date) -> CandidateKey:
    """Same key shape for an already-ledgered Prediction, so batch-vs-ledger
    dedup compares like with like. Bucket is derived from horizon_days when
    present (new rows), else from resolve_by relative to created_at (old rows)."""
    rule = prediction.resolution_rule
    bucket: Optional[int] = None
    if prediction.horizon_days is not None:
        bucket = min(HORIZON_BUCKETS, key=lambda b: (abs(prediction.horizon_days - b), b))
    else:
        try:
            created = datetime.fromisoformat(prediction.created_at).date()
            bucket = horizon_bucket(created, prediction.resolve_by)
        except (ValueError, TypeError):
            bucket = None
    return CandidateKey(
        instrument=prediction.instrument or rule_instrument(rule) if rule is not None else prediction.instrument,
        direction=rule_direction(rule) if rule is not None else None,
        bucket=bucket,
    )


class PolicyDecision(NamedTuple):
    accepted: List[dict]
    rejected: List[Tuple[dict, str]]  # (candidate, reason)


def apply_daily_policy(
    candidates: Sequence[dict],
    as_of: date,
    unresolved_live: Sequence,
    already_recorded_today: int = 0,
) -> PolicyDecision:
    """The single code-level gate between the drafting call and the ledger.
    Processes candidates in model order (deterministic given input order);
    every rejection carries an explicit reason for the run log."""
    accepted: List[dict] = []
    rejected: List[Tuple[dict, str]] = []
    per_bucket: Dict[int, int] = {}
    seen_keys = {prediction_key(p, as_of) for p in unresolved_live}
    budget = max(0, DAILY_CAP - already_recorded_today)

    for cand in candidates:
        if len(accepted) >= budget:
            rejected.append((cand, f"daily cap ({DAILY_CAP}) reached"))
            continue
        key = candidate_key(cand, as_of)
        if key.instrument is None:
            rejected.append((cand, "no instrument in resolution_rule"))
            continue
        if key.instrument not in TIINGO_INSTRUMENTS + FRED_SERIES:
            rejected.append((cand, f"instrument {key.instrument!r} not in approved allowlist"))
            continue
        if key.instrument not in allowed_instruments_today(as_of):
            rejected.append((cand, f"instrument {key.instrument!r} not grounded in today's snapshot"))
            continue
        if key.bucket is None:
            rejected.append((cand, f"resolve_by below {MIN_HORIZON_DAYS}-day floor or unparseable"))
            continue
        if key in seen_keys:
            rejected.append((cand, "duplicate of unresolved live prediction or earlier candidate"))
            continue
        if per_bucket.get(key.bucket, 0) >= MAX_PER_BUCKET_PER_DAY:
            rejected.append((cand, f"bucket {key.bucket}d already has {MAX_PER_BUCKET_PER_DAY} today"))
            continue
        accepted.append(cand)
        seen_keys.add(key)
        per_bucket[key.bucket] = per_bucket.get(key.bucket, 0) + 1

    return PolicyDecision(accepted=accepted, rejected=rejected)


def baseline_quota(accepted: Sequence[dict], as_of: date) -> int:
    """AMENDED 2026-07-18 (user decision, option 1 after the coverage-gap
    review): the baseline pair (fixed SPY 2%-in-60d shape, per M8 — never
    tuned) is recorded UNCONDITIONALLY on every successful trading-day run,
    <= BASELINE_DAILY_CAP/day — guaranteed 60d baseline accrual regardless
    of which buckets the engine used that day. The original 60d-bucket
    matching condition traded guaranteed accrual for date-matched
    comparability; the user chose the guarantee. The real <=2/day cap
    against double runs is enforced in the runner by counting baselines
    already ledgered today. (Signature kept for call-site stability;
    `accepted`/`as_of` are deliberately unused now.)"""
    return BASELINE_DAILY_CAP


def month_estimated_spend_usd(spend_rows: Sequence[dict], year: int, month: int) -> float:
    """Sum of deterministic per-run estimates for the given month.
    Each row: {"date": "YYYY-MM-DD", "model_calls": int, ...}."""
    total = 0.0
    for row in spend_rows:
        try:
            d = date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            continue
        if d.year == year and d.month == month:
            total += row.get("model_calls", 0) * ESTIMATED_COST_PER_MODEL_CALL_USD
    return total


def ceiling_exceeded(spend_rows: Sequence[dict], as_of: date, next_run_model_calls: int) -> bool:
    """True when this run's estimate would cross the monthly ceiling —
    the runner must then PARK (refuse to run), not trim silently."""
    projected = (
        month_estimated_spend_usd(spend_rows, as_of.year, as_of.month)
        + next_run_model_calls * ESTIMATED_COST_PER_MODEL_CALL_USD
    )
    return projected > MONTHLY_SPEND_CEILING_USD
