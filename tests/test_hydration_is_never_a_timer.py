"""READY must be caused by output, never by elapsed time.

A progress bar that advances on a clock is a lie with a smooth animation: it
says "checking current evidence" while nothing is checking anything, and it
says ready because the seconds ran out. Every state here is derived from
whether a canonical output exists.

The second thing this pins is that BOUNDED, DEGRADED and PENDING stay
distinct. Collapsing them into one spinner is how a blocked retrieval and a
quiet company come to look identical -- the error this codebase has already
corrected at the independence, discovery, evidence-family and history layers.
"""
from intent_engine.founder_brief import hydration as H

_DECISION = {"recommended_next_move": "Hold pricing through Q3"}


def test_nothing_produced_is_never_ready_however_long_it_ran():
    """Identity is always attempted, so an empty T0 is RUNNING rather than
    PENDING. The property that matters is that nothing is SHOWABLE."""
    got = H.assess(identity=None)
    assert got["tiers"][H.T0] == H.RUNNING
    assert got["highest_showable"] == ""
    assert got["showable"] == []
    assert H.READY not in got["tiers"].values()


def test_identity_alone_makes_the_first_tier_showable():
    got = H.assess(identity={"company_name": "Cloudflare, Inc."})
    assert got["tiers"][H.T0] == H.READY
    assert got["showable"] == [H.T0]


def test_a_tier_is_ready_only_when_all_its_producers_delivered():
    partial = H.assess(identity={"x": 1}, previous_decision={"a": 1})
    assert partial["tiers"][H.T1] == H.BOUNDED
    full = H.assess(identity={"x": 1}, previous_decision={"a": 1},
                    market_snapshot={"b": 1})
    assert full["tiers"][H.T1] == H.READY


def test_a_blocked_run_degrades_rather_than_spinning():
    got = H.assess(identity={"x": 1}, blocked=True)
    assert got["tiers"][H.T2] == H.DEGRADED
    assert got["tiers"][H.T2] in H.SHOWS_CONTENT


def test_a_finished_run_has_no_running_tier_left():
    """The animated lie: a run that has stopped still claiming to work."""
    got = H.assess(identity={"x": 1}, finished=True)
    assert H.RUNNING not in got["tiers"].values()
    assert got["current_step"] == ""


def test_an_unfinished_run_names_the_step_it_is_actually_on():
    got = H.assess(identity={"x": 1})
    assert got["current_step"] == H.TIER_COPY[H.T1]


def test_the_copy_never_describes_the_machinery():
    banned = ("ai ", "model", "node", "pipeline", "processing", "generating",
              "thinking")
    for text in list(H.TIER_COPY.values()) + [s for v in H.STEP_COPY.values()
                                              for s in v]:
        assert not any(b in text.lower() for b in banned), text


def test_the_full_stack_is_ready_when_every_producer_delivered():
    got = H.assess(identity={"x": 1}, previous_decision={"a": 1},
                   market_snapshot={"b": 1}, source_coverage={"c": 1},
                   discovery_coverage={"d": 1}, decision=_DECISION,
                   economic_history={"state": "X"},
                   second_iteration={"state": "Y"}, finished=True)
    assert got["tiers"] == {H.T0: H.READY, H.T1: H.READY,
                            H.T2: H.READY, H.T3: H.READY}
    assert got["highest_showable"] == H.T3


def test_an_empty_producer_output_is_not_treated_as_delivered():
    """NEGATIVE CONTROL. An empty dict is a producer that ran and returned
    nothing; counting it as delivered is how READY stops meaning anything."""
    got = H.assess(identity={"x": 1}, previous_decision={},
                   market_snapshot={}, finished=True)
    assert got["tiers"][H.T1] != H.READY


# --- telemetry -----------------------------------------------------------------


def test_latency_targets_are_reported_never_enforced():
    out = H.telemetry({"t1_ms": 1500, "t2_ms": 20000, "t3_ms": 45000})
    assert out["met"]["t1_ms"] is True
    assert out["met"]["t2_ms"] is False
    assert out["targets_ms"]["t2_ms"] == 15_000


def test_an_unmeasured_duration_is_none_not_zero():
    """Zero would read as instant, which is the flattering direction."""
    out = H.telemetry({})
    assert out["t1_ms"] is None
    assert out["met"]["t1_ms"] is None
