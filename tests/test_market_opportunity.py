"""The opportunity reasoner: exactly one classification, and it says why.

The cases that matter most here are the REFUSALS. A reasoner that reaches BUY
from a strategic thesis alone would look like it was working, and there is no
later measurement that distinguishes that from noise — so the tests that stop
it are the load-bearing ones.
"""
import pytest

from intent_engine.market.opportunity import (
    CLASSIFICATIONS,
    NO_DATED_EVIDENCE,
    NO_MARKET_EVIDENCE,
    NO_OUTSIDE_SOURCE,
    NO_STRATEGIC_READING,
    NOT_TRADABLE,
    MarketEvidence,
    classify,
)


class _Company:
    def __init__(self, company_id="acme", instrument="ACME"):
        self.company_id = company_id
        self.canonical_name = company_id.title()
        self.tradable_instrument = instrument


def _report(*, thesis="Acme is consolidating control of key layers.",
            dated=True, independent=True, observations=4):
    obs = []
    for i in range(observations):
        obs.append({
            "observation_id": f"obs-{i}",
            "date": "2026-07-20" if dated else "",
            "source_class": ("independent_reporting"
                             if independent and i == 0 else "company_owned"),
            "text": f"observation {i}",
        })
    return {
        "thesis": {"view": thesis, "view_withheld": not thesis},
        "observations": obs,
        "source_class_coverage": ({"independent_reporting": 1}
                                  if independent else {"company_owned": 4}),
        "hypotheses": [{
            "alternative_explanations": ["Demand was already there."],
            "falsification_questions": ["Does the next filing show it?"],
        }],
        "evidence_gaps": ["no pricing evidence"],
        "questions": [{"question": "Which segment does this target?"}],
    }


def _up(**kw):
    kw.setdefault("direction", "up")
    kw.setdefault("probability", 0.62)
    kw.setdefault("horizon_days", 21)
    return MarketEvidence(**kw)


# --- every path ends in exactly one classification ---------------------------
@pytest.mark.parametrize("company,report,market", [
    (_Company(instrument=None), _report(), _up()),
    (_Company(), None, _up()),
    (_Company(), _report(thesis=""), _up()),
    (_Company(), _report(dated=False), _up()),
    (_Company(), _report(independent=False), _up()),
    (_Company(), _report(), MarketEvidence()),
    (_Company(), _report(), _up()),
])
def test_every_input_produces_exactly_one_classification(company, report,
                                                         market):
    opp = classify(company, report, as_of="2026-07-30", market=market)
    assert opp.classification in CLASSIFICATIONS
    assert opp.rationale.strip(), "a classification with no reason is not one"


# --- the refusals ------------------------------------------------------------
def test_a_private_company_is_never_a_position_but_is_still_analysed():
    """Most companies the engine knows about can never be traded. Discarding
    that reasoning would throw away the majority of what it learns."""
    opp = classify(_Company(instrument=None), _report(), as_of="2026-07-30",
                   market=_up())
    assert opp.classification == "NO_TRADE"
    assert NOT_TRADABLE in opp.blocked_by
    # the analysis survives the rejection
    assert opp.thesis and opp.alternatives and opp.invalidation
    assert opp.quality > 0


def test_a_strategic_thesis_alone_never_reaches_buy():
    """The single most important guard here.

    A strategic reading says what a company appears to be doing. It contains
    nothing about what is already priced in, and a company can execute
    perfectly while its stock falls for a year. Emitting a direction from it
    would produce records indistinguishable from noise at post-mortem.
    """
    opp = classify(_Company(), _report(), as_of="2026-07-30",
                   market=MarketEvidence())
    assert opp.classification == "WATCH"
    assert NO_MARKET_EVIDENCE in opp.blocked_by
    assert opp.direction == "" and opp.probability is None
    assert "already priced in" in opp.rationale


def test_undated_evidence_cannot_be_a_recent_change():
    opp = classify(_Company(), _report(dated=False), as_of="2026-07-30",
                   market=_up())
    assert opp.classification == "WATCH"
    assert NO_DATED_EVIDENCE in opp.blocked_by


def test_self_published_evidence_alone_is_not_worth_a_position():
    opp = classify(_Company(), _report(independent=False), as_of="2026-07-30",
                   market=_up())
    assert opp.classification == "WATCH"
    assert NO_OUTSIDE_SOURCE in opp.blocked_by


def test_a_withheld_strategic_view_is_no_trade_not_a_guess():
    opp = classify(_Company(), _report(thesis=""), as_of="2026-07-30",
                   market=_up())
    assert opp.classification == "NO_TRADE"
    assert NO_STRATEGIC_READING in opp.blocked_by


def test_the_gate_named_is_the_first_one_that_stopped_it():
    """Blocked_by names the reason worth acting on, not every reason."""
    opp = classify(_Company(instrument=None), _report(thesis="", dated=False),
                   as_of="2026-07-30", market=MarketEvidence())
    assert opp.blocked_by == (NOT_TRADABLE,)


# --- the positions -----------------------------------------------------------
def test_a_corroborated_dated_reading_with_a_market_view_becomes_a_position():
    opp = classify(_Company(), _report(), as_of="2026-07-30", market=_up())
    assert opp.classification == "BUY"
    assert opp.direction == "up" and opp.probability == 0.62
    assert opp.is_tradable_decision
    signal = opp.to_signal()
    assert signal["direction"] == "up" and signal["horizon_days"] == 21


def test_downside_becomes_sell():
    opp = classify(_Company(), _report(), as_of="2026-07-30",
                   market=_up(direction="down"))
    assert opp.classification == "SELL" and opp.direction == "down"


def test_an_unfavourable_payoff_is_a_hold_not_a_forced_trade():
    """"Not at this price" is a real answer. The mission is explicit that trade
    count is never what is being optimised."""
    opp = classify(_Company(), _report(), as_of="2026-07-30",
                   market=_up(upside_pct=3.0, downside_pct=9.0))
    assert opp.classification == "HOLD"
    assert opp.risk_reward is not None and opp.risk_reward < 1.0


def test_an_unrecognised_direction_is_not_a_coin_flip():
    opp = classify(_Company(), _report(), as_of="2026-07-30",
                   market=_up(direction="sideways"))
    assert opp.classification == "HOLD"


# --- what only a position may carry ------------------------------------------
def test_a_non_position_carries_no_direction_or_probability():
    """A WATCH row with a probability on it would be indistinguishable from a
    position at post-mortem, and would quietly enter calibration."""
    for market in (MarketEvidence(), _up()):
        for report in (_report(dated=False), _report(independent=False)):
            opp = classify(_Company(), report, as_of="2026-07-30",
                           market=market)
            assert opp.classification not in ("BUY", "SELL")
            assert opp.direction == ""
            assert opp.probability is None
            assert opp.to_signal() is None


# --- quality ranks auditability, not confidence ------------------------------
def test_quality_rewards_what_makes_a_post_mortem_possible():
    strong = classify(_Company(), _report(observations=8), as_of="2026-07-30",
                      market=_up()).quality
    thin = classify(_Company(), _report(observations=1, dated=False,
                                        independent=False),
                    as_of="2026-07-30", market=_up()).quality
    assert 0.0 <= thin < strong <= 1.0


def test_quality_does_not_rise_with_confidence():
    """Ranking by confidence is how a system learns to sound sure."""
    base = _report()
    low = classify(_Company(), base, as_of="2026-07-30",
                   market=_up(probability=0.51)).quality
    high = classify(_Company(), base, as_of="2026-07-30",
                    market=_up(probability=0.99)).quality
    assert low == high


# --- calibration is carried, never applied -----------------------------------
def test_calibration_is_recorded_but_does_not_change_the_decision():
    """A-M5 gates accuracy claims behind >=30 resolved predictions plus a human
    review. There are zero resolved predictions today, so wiring feedback now
    would build a path that silently activates later, unreviewed."""
    overconfident = {"calibration_error": 0.4, "resolved_count": 12,
                     "notes": ["overconfident"]}
    with_cal = classify(_Company(), _report(), as_of="2026-07-30",
                        market=_up(), calibration=overconfident)
    without = classify(_Company(), _report(), as_of="2026-07-30", market=_up())
    assert with_cal.classification == without.classification
    assert with_cal.probability == without.probability
    # but it is on the record, so the later review has what it needs
    assert with_cal.calibration["calibration_error"] == 0.4


# --- the record is complete enough to review later ---------------------------
def test_every_opportunity_serialises_with_its_reasoning_intact():
    opp = classify(_Company(), _report(), as_of="2026-07-30", market=_up())
    d = opp.as_dict()
    for key in ("company_id", "as_of", "classification", "rationale", "thesis",
                "alternatives", "uncertainty", "invalidation", "monitoring",
                "quality", "blocked_by", "regime", "calibration"):
        assert key in d, f"missing {key} — a record that cannot be reviewed"
    assert d["classification"] == "BUY"


def test_a_missing_report_is_a_decision_not_a_crash():
    opp = classify(_Company(), None, as_of="2026-07-30", market=_up())
    assert opp.classification == "NO_TRADE"
    assert NO_STRATEGIC_READING in opp.blocked_by
