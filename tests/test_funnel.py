"""The decision funnel.

The load-bearing property is that it REFUSES to name a bottleneck from one
day. Day 12 named strategic-reading yield the new #1 from a single cycle, and
a single cycle cannot separate a reading deficiency from a signal that
correctly declined to fire from a market with nothing to offer.
"""
from intent_engine.market.funnel import (
    STAGES, Funnel, dominant_bottleneck, from_rows,
)


def _rows(n=28, tradable=27, indep=27, thesis=4, at_signal=3):
    rows = []
    for i in range(n):
        gate = ("not_tradable" if i >= tradable else
                "no_market_evidence" if i < at_signal else "view_withheld")
        rows.append({"gate": gate, "indep": i < indep, "thesis": i < thesis,
                     "classification": "WATCH" if i < at_signal else "NO_TRADE"})
    return rows


def test_conversion_is_measured_from_the_previous_stage_not_the_top():
    """Measuring everything against the top hides where the loss is: a stage
    converting 100% looks bad if the stage above it lost 90%."""
    f = from_rows(_rows(), as_of="2026-07-31")
    assert f.rate("evaluated") is None
    assert f.rate("tradable") == 27 / 28
    assert f.rate("strategic_view") == 4 / 27


def test_the_largest_loss_is_reported_as_a_fact_about_today():
    f = from_rows(_rows(), as_of="2026-07-31")
    loss = f.largest_loss
    assert loss["stage"] == "strategic_view"
    assert loss["from"] == 27 and loss["lost"] == 23


def test_terminal_classifications_are_a_partition_not_a_chain_link():
    """Forcing a branch into a sequence produced "no_trade: 833%" (25 measured
    against sell=0) and made positions_opened look like a 25 -> 0 collapse.
    Terminals report their SHARE of the evaluated set instead."""
    f = from_rows(_rows(), as_of="2026-07-31")
    assert f.largest_loss["stage"] not in ("buy", "sell", "watch", "no_trade")
    assert f.rate("no_trade") == 25 / 28
    assert 0.0 <= f.rate("watch") <= 1.0
    assert all(0.0 <= (f.rate(t) or 0) <= 1.0
               for t in ("buy", "sell", "watch", "no_trade"))


def test_one_day_is_never_enough_to_name_a_bottleneck():
    """THE guard. This is the method error Day 12 made."""
    one = [from_rows(_rows(), as_of="2026-07-31").as_dict()]
    verdict = dominant_bottleneck(one)
    assert verdict["verdict"] == "insufficient history"
    assert verdict["days"] == 1 and verdict["needed"] == 3


def test_a_stage_must_dominate_repeatedly_to_be_called_a_bottleneck():
    history = [from_rows(_rows(), as_of=f"2026-08-0{d}").as_dict()
               for d in range(1, 5)]
    verdict = dominant_bottleneck(history)
    assert verdict["stage"] == "strategic_view"
    assert verdict["days_dominant"] == 4 and verdict["verdict"] == "dominant"


def test_a_stage_dominating_a_minority_of_days_is_not_dominant():
    mixed = [from_rows(_rows(thesis=4), as_of="2026-08-01").as_dict(),
             from_rows(_rows(thesis=27, at_signal=3),
                       as_of="2026-08-02").as_dict(),
             from_rows(_rows(thesis=27, at_signal=3),
                       as_of="2026-08-03").as_dict()]
    verdict = dominant_bottleneck(mixed)
    assert verdict["verdict"] in ("dominant", "no stage dominates")
    assert verdict["of_days"] == 3


def test_every_stage_is_reported_even_at_zero():
    """A stage silently missing from a report is a stage nobody notices is
    empty."""
    f = from_rows([], as_of="2026-07-31")
    d = f.as_dict()
    for stage in STAGES:
        assert stage in d["counts"]


def test_an_empty_cycle_does_not_crash_or_invent_a_loss():
    f = from_rows([], as_of="2026-07-31")
    assert f.largest_loss is None and f.rate("tradable") is None
