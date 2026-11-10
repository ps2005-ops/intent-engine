"""The paper-only boundary — fails closed, and has no live path to open."""
import pytest

from intent_engine.market import trading_mode as TM


def test_missing_configuration_resolves_to_paper():
    """Absent configuration resolves to the SAFE state, never a permissive one."""
    assert TM.resolve({})["mode"] == TM.PAPER
    assert TM.resolve({})["source"] == "default"


def test_explicit_paper_is_accepted():
    resolved = TM.resolve({TM.ENV_VAR: "PAPER"})
    assert resolved == {"mode": TM.PAPER, "source": "env"}
    assert TM.resolve({TM.ENV_VAR: "paper"})["mode"] == TM.PAPER


@pytest.mark.parametrize("value", ["LIVE", "live", "REAL", "production",
                                   "PAPER_TRADING", "1", "true", "yes"])
def test_anything_that_is_not_paper_refuses_to_start(value):
    """A typo or a half-finished experiment stops the run. It is NOT coerced
    to paper silently -- the error is the useful output, because it says the
    operator's intent and the system's capability disagree."""
    with pytest.raises(TM.TradingModeError):
        TM.resolve({TM.ENV_VAR: value})


def test_the_refusal_explains_that_there_is_no_live_capability():
    with pytest.raises(TM.TradingModeError) as exc:
        TM.resolve({TM.ENV_VAR: "LIVE"})
    message = str(exc.value)
    assert "paper trading only" in message
    assert "no broker integration" in message


def test_assert_paper_only_is_the_gate_every_cycle_calls():
    assert TM.assert_paper_only({}) == TM.PAPER
    with pytest.raises(TM.TradingModeError):
        TM.assert_paper_only({TM.ENV_VAR: "LIVE"})


def test_only_one_mode_is_supported_at_all():
    """Structural, not a matter of restraint: there is nothing else to select."""
    assert TM.SUPPORTED == frozenset({"PAPER"})


def test_no_order_submission_path_exists_anywhere_in_the_cycle():
    """The guarantee that matters most, asserted against the source rather
    than trusted. If someone adds an order path, this fails."""
    import inspect

    from intent_engine.market import cycle, steps
    forbidden = ("submit_order", "place_order", "broker_connect", "send_order",
                 "create_order", "live_trade", "execute_trade")
    for module in (cycle, steps):
        source = inspect.getsource(module)
        for name in forbidden:
            assert name not in source, f"{module.__name__} references {name}"


def test_the_positions_step_reports_zero_orders_and_no_broker():
    from intent_engine.market import session as S
    from intent_engine.market.cycle import CycleContext
    from intent_engine.market.steps import positions_step
    import datetime
    import pathlib

    ctx = CycleContext(cycle="day", as_of="2026-07-31", root=pathlib.Path("."),
                       session=S.classify(datetime.date(2026, 7, 31)),
                       run_id="x")
    out = positions_step(ctx)
    assert out["trading_mode"] == TM.PAPER
    assert out["broker"] is None
    assert out["orders_submitted"] == 0
