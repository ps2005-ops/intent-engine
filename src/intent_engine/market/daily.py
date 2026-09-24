"""The daily opportunity sweep — the job that makes the loop produce data.

Before this, `daily-prediction-generation` asked `predict_fn` for a signal and
got None every time, so the cycle stored nothing and there was nothing to learn
from. This job evaluates the whole eligible universe, classifies every company,
and STORES EVERY RESULT — including the rejections, which are the majority and
which the mission is explicit about keeping ("rejected opportunities are
training data").

It is separate from `daily-prediction-generation` rather than a rewrite of it:
that job's contract is "turn signals into predictions", and it keeps it. This
one's contract is "decide, about every company, and write down why". Only the
BUY/SELL rows become predictions, and they do so through the same
`build_prediction` path everything else already uses.

IDEMPOTENT per (company, day), like every other hosted job: the idem key is the
company and the date, so a workflow that fires twice records one opinion per
company per day rather than two.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from intent_engine.hosted.budget import record_skip
from intent_engine.market.opportunity import MarketEvidence, classify
from intent_engine.predictions.generation import build_prediction

OPPORTUNITY_STREAM = "opportunity"

# Cost of one classification in the budget ledger. The reasoning itself is
# deterministic and free; what costs is the research that produced the report
# it reads, and that is accounted where it happens (company-intelligence-
# refresh). Charging here as well would double-count the same spend.
_CAD_PER_CLASSIFY = 0.0


# How a hosted evidence `kind` maps to the source classes the strategic layer
# reasons about. Anything not named here is treated as the company's own
# publishing, which is the conservative default: mis-classifying a company blog
# as independent would let a position through on the company's own account of
# itself, and that is the exact thing `no_outside_source` exists to stop. A
# kind is added here only when it genuinely denotes a third party.
_KIND_TO_SOURCE_CLASS = {
    "filing": "investor_material",
    "earnings": "investor_material",
    "investor": "investor_material",
    "news": "independent_reporting",
    "press_coverage": "independent_reporting",
    "analyst": "analyst_coverage",
    "review": "customer_voice",
    "customer": "customer_voice",
    "competitor": "competitor_statement",
}


def _report_for(state: Dict[str, Any],
                evidence: Optional[list] = None) -> Optional[dict]:
    """A report-shaped view of what this company's research actually found.

    Two shapes arrive here. A full Founder Intelligence `strategic_report` is
    used as-is. Otherwise the hosted research path's own state is adapted —
    it stores a thesis on the company record and its evidence in a SEPARATE
    stream, which is why the first version of this sweep classified every
    public company `no_strategic_reading` while sitting on real evidence: it
    was reading the state and never the evidence.

    Adapting rather than re-reasoning is deliberate. This is the same evidence,
    read the same way the strategic renderers read it, so the opportunity and
    a report a human opens cannot disagree about what was found.
    """
    if not isinstance(state, dict):
        return None
    report = state.get("strategic_report") or state.get("report")
    if isinstance(report, dict):
        return report

    thesis = " ".join(str(state.get("thesis") or "").split())
    rows = [e for e in (evidence or []) if isinstance(e, dict)]
    if not thesis and not rows:
        return None

    observations = []
    coverage: Dict[str, int] = {}
    for i, row in enumerate(rows):
        source_class = _KIND_TO_SOURCE_CLASS.get(
            str(row.get("kind") or "").lower(), "company_owned")
        coverage[source_class] = coverage.get(source_class, 0) + 1
        observations.append({
            "observation_id": f"ev-{i}",
            # `published_at` is the evidence's own date, already leakage-checked
            # upstream (research.py drops anything dated after as_of).
            "date": str(row.get("published_at") or "")[:10],
            "source_class": source_class,
            "text": row.get("summary") or "",
        })
    return {"thesis": {"view": thesis, "view_withheld": not thesis},
            "observations": observations,
            "source_class_coverage": coverage,
            "hypotheses": [], "evidence_gaps": [], "questions": []}


def _market_for(state: Dict[str, Any]) -> MarketEvidence:
    """A market view supplied on the company's state, if anything put one there.

    Kept as the first source so a richer signal can be attached upstream
    without touching this job. When it is absent the sweep falls back to the
    baseline below.
    """
    raw = (state or {}).get("market_evidence")
    if not isinstance(raw, dict):
        return MarketEvidence()
    return MarketEvidence(
        direction=str(raw.get("direction") or ""),
        probability=raw.get("probability"),
        horizon_days=raw.get("horizon_days"),
        upside_pct=raw.get("upside_pct"),
        downside_pct=raw.get("downside_pct"),
        catalysts=tuple(raw.get("catalysts") or ()),
        source=str(raw.get("source") or ""))


def _lookback_days(as_of: str, sessions: int = 30) -> list:
    """Calendar days back from `as_of`, most recent last.

    Calendar rather than trading days on purpose: `price_history` drops any
    date the price source cannot answer, so weekends and holidays fall out on
    their own. Reimplementing a market calendar here would duplicate
    `runtime/market_calendar` to produce the same list.
    """
    from datetime import date, timedelta
    end = date.fromisoformat(as_of[:10])
    return [(end - timedelta(days=n)).isoformat()
            for n in range(sessions, -1, -1)]


def _baseline_market(ctx, company, as_of: str) -> MarketEvidence:
    """The labelled baseline: real price history, no claim of skill.

    Its purpose is to make predictions RESOLVABLE. Learning Velocity -- the
    count of evaluations that can ever be graded -- was zero for the whole
    phase because nothing supplied this input, so nothing downstream of it
    (resolution, post-mortems, calibration) had anything to run on.
    """
    from intent_engine.market.signals import baseline_market_evidence
    symbol = getattr(company, "tradable_instrument", None)
    price_at = getattr(ctx, "price_at", None)
    if not symbol or price_at is None:
        return MarketEvidence()
    return baseline_market_evidence(price_at, symbol,
                                    _lookback_days(as_of))


def daily_opportunity_sweep(ctx, as_of: str) -> Dict:
    """Classify every eligible company once, store all of it, trade none of it
    that the evidence does not support."""
    from intent_engine.universe.research import all_states, evidence_for

    states = all_states(ctx.store)
    cap = ctx.budget.max_companies_per_daily_refresh
    day = as_of[:10]

    counts: Dict[str, int] = {}
    blocked: Dict[str, int] = {}
    generated = 0
    evaluated = 0

    calibration_by_company = {}
    try:
        for state in ctx.learning_store.all_latest():
            cid = getattr(state, "company_id", None) or (
                state.get("company_id") if isinstance(state, dict) else None)
            if cid:
                calibration_by_company[cid] = (
                    state if isinstance(state, dict) else
                    getattr(state, "__dict__", {}))
    except Exception:  # noqa: BLE001 — calibration is carried, never required
        calibration_by_company = {}

    for company in ctx.universe.prediction_companies()[:cap]:
        ok, why = ctx.budget_ledger.can_spend(as_of, calls=0,
                                              cad=_CAD_PER_CLASSIFY)
        if not ok:
            record_skip(ctx.store, as_of,
                        item=f"opportunity:{company.company_id}",
                        reason=why, company_id=company.company_id)
            continue

        state = states.get(company.company_id, {}) or {}
        evidence = evidence_for(ctx.store, company.company_id)
        # An upstream-supplied view wins; otherwise the labelled baseline.
        market = _market_for(state)
        if market.is_empty:
            market = _baseline_market(ctx, company, as_of)
        # The hypothesis a position would be testing. Attached from the signal
        # that produced the view, so every gradable decision is attributable to
        # a claim rather than only to a rule.
        from intent_engine.market.hypothesis import BASELINE_HYPOTHESIS
        from intent_engine.market.signals import BASELINE_SOURCE
        hypothesis_id = (BASELINE_HYPOTHESIS.hypothesis_id
                         if market.source == BASELINE_SOURCE else "")
        opportunity = classify(
            company, _report_for(state, evidence), as_of=as_of,
            market=market, regime=ctx.regime, hypothesis_id=hypothesis_id,
            calibration=calibration_by_company.get(company.company_id, {}))

        # EVERY result is stored, which is the whole point of the job.
        ctx.store.append(
            OPPORTUNITY_STREAM, record_id=f"{company.company_id}:{day}",
            payload=opportunity.as_dict(),
            status=opportunity.classification,
            idem_key=f"opportunity:{company.company_id}:{day}",
            company_id=company.company_id)

        evaluated += 1
        counts[opportunity.classification] = counts.get(
            opportunity.classification, 0) + 1
        for gate in opportunity.blocked_by:
            blocked[gate] = blocked.get(gate, 0) + 1

        # Only a position becomes a prediction. Everything else has already
        # been recorded and stops here.
        signal = opportunity.to_signal()
        if not signal:
            continue
        already = {p.entity_id for p in ctx.predictions.all_latest()
                   if (p.created_at or "")[:10] == day}
        if company.company_id in already:
            continue
        ctx.predictions.add(build_prediction(company, signal, as_of))
        generated += 1

    return {"evaluated": evaluated, "by_classification": counts,
            "blocked_by": blocked, "predictions_generated": generated}
