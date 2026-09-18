"""The baseline market signal.

Its job is to make predictions RESOLVABLE, not right. Learning Velocity — the
count of evaluations that can ever be graded — was zero for the whole phase
because nothing supplied this input. The tests that matter most are the ones
keeping it honest about being a baseline.
"""
from intent_engine.market.signals import (
    BASELINE_PROBABILITY,
    BASELINE_SOURCE,
    MIN_ABS_RETURN,
    baseline_market_evidence,
    momentum_evidence,
    price_history,
)


def _series(start, step, n=20):
    return [start + step * i for i in range(n)]


# --- direction ---------------------------------------------------------------
def test_a_rising_series_reads_up_and_a_falling_one_down():
    assert momentum_evidence(_series(100, 1.0)).direction == "up"
    assert momentum_evidence(_series(100, -1.0)).direction == "down"


def test_a_move_too_small_to_distinguish_from_noise_is_no_signal():
    """Empty is a real answer: the reasoner renders it WATCH with
    `no_market_evidence`, which is the correct record for "we looked and the
    market said nothing"."""
    flat = [100.0 + 0.001 * i for i in range(20)]
    ev = momentum_evidence(flat)
    assert ev.is_empty and ev.direction == ""
    # and the threshold is the thing being tested, not an accident
    assert abs((flat[-1] - flat[0]) / flat[0]) < MIN_ABS_RETURN


def test_too_short_a_series_is_no_signal_rather_than_a_guess():
    for prices in ([], [100.0], [100.0, 101.0]):
        assert momentum_evidence(prices).is_empty


# --- honesty about being a baseline ------------------------------------------
def test_the_probability_is_a_stated_prior_not_a_measurement():
    """Barely off a coin flip on purpose. A momentum rule with no demonstrated
    edge has no business claiming more, and an inflated number here would
    poison the first calibration curve the engine ever draws."""
    ev = momentum_evidence(_series(100, 2.0))
    assert ev.probability == BASELINE_PROBABILITY
    assert 0.5 < BASELINE_PROBABILITY <= 0.6, \
        "a baseline claiming real confidence is no longer a baseline"


def test_every_signal_carries_its_source_so_it_can_be_judged_alone():
    """Without this, the first real signal and the placeholder it replaced are
    averaged together in calibration and neither can be judged."""
    assert momentum_evidence(_series(100, 2.0)).source == BASELINE_SOURCE
    # even when it declines to fire
    assert momentum_evidence([]).source == BASELINE_SOURCE


def test_the_baseline_claims_no_catalyst():
    """A momentum rule knows of no catalyst. Inventing one would put an
    unsourced claim on a record meant to be auditable."""
    assert momentum_evidence(_series(100, 2.0)).catalysts == ()


def test_risk_and_reward_are_symmetric_because_it_has_no_view_on_skew():
    """Inventing skew to make risk/reward look favourable is exactly the
    flattering assumption the reasoner's HOLD gate exists to catch."""
    ev = momentum_evidence(_series(100, 1.5))
    assert ev.upside_pct == ev.downside_pct
    assert ev.risk_reward == 1.0


def test_a_volatile_series_expects_a_larger_move_than_a_smooth_one():
    smooth = momentum_evidence([100 + i for i in range(20)])
    choppy = momentum_evidence([100 + i + (8 if i % 2 else -8)
                                for i in range(20)])
    assert choppy.upside_pct > smooth.upside_pct


# --- price fetching ----------------------------------------------------------
def test_a_missing_price_is_skipped_never_interpolated():
    """Interpolating a price the market never printed would put a fabricated
    number into the one part of this system meant to be ground truth."""
    def _price_at(symbol, day):
        if day.endswith("03"):
            raise RuntimeError("no price")
        return 100.0

    days = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"]
    prices = price_history(_price_at, "X", days)
    assert len(prices) == 3
    assert all(p == 100.0 for p in prices)


def test_no_symbol_means_no_signal():
    ev = baseline_market_evidence(lambda s, d: 100.0, "", ["2026-07-01"])
    assert ev.is_empty and ev.source == BASELINE_SOURCE


# --- the measurement this cycle turned on ------------------------------------
def test_the_baseline_makes_an_opportunity_resolvable():
    """THE point: Learning Velocity was 0 because nothing could ever be graded.

    A resolvable opportunity is one that produces a signal the prediction
    pipeline can turn into an outcome. Being *wrong* is fine and expected —
    a wrong resolved prediction teaches strictly more than an ungradable WATCH.
    """
    from intent_engine.market.opportunity import classify

    class _Co:
        company_id = "acme"
        canonical_name = "Acme"
        tradable_instrument = "ACME"

    report = {
        "thesis": {"view": "Acme is consolidating control.",
                   "view_withheld": False},
        "observations": [{"observation_id": "o1", "date": "2026-07-20",
                          "source_class": "independent_reporting",
                          "text": "an outside report"}],
        "source_class_coverage": {"independent_reporting": 1},
        "hypotheses": [], "evidence_gaps": [], "questions": [],
    }

    without = classify(_Co(), report, as_of="2026-07-30")
    assert without.to_signal() is None, "baseline for the comparison moved"

    with_signal = classify(_Co(), report, as_of="2026-07-30",
                           market=momentum_evidence(_series(100, 2.0)))
    signal = with_signal.to_signal()
    assert signal is not None, "still ungradable — LV did not move"
    assert with_signal.classification == "BUY"
    assert with_signal.market_source == BASELINE_SOURCE
    assert signal["probability"] == BASELINE_PROBABILITY
