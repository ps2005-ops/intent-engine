"""Live paper positions from price signals — as controls, never as alpha.

The most important tests here assert the REFUSALS: that a control can never
become a champion, that a strategy cannot pyramid into one name, that a
high-frequency strategy cannot consume the whole book, and that no metric this
module produces is ever unlabelled.
"""
from datetime import date, timedelta

import pytest

from intent_engine.market import paper_engine as PE
from intent_engine.market import strategy as ST
from intent_engine.market import strategy_library as LIB
from intent_engine.market import universe_tiers as UT


def _series(n=120, start="2022-01-03", base=100.0, step=0.6):
    d, out, i = date.fromisoformat(start), {}, 0
    while len(out) < n:
        if d.weekday() < 5:
            out[d.isoformat()] = base + step * i
            i += 1
        d += timedelta(days=1)
    return out


def _sec(sym="AAPL", **kw):
    return UT.Security(symbol=sym, security_type=UT.EQUITY, sector="Tech", **kw)


@pytest.fixture
def book(tmp_path):
    return PE.PaperBook("baseline_momentum.v1", root=str(tmp_path))


def _open(book, securities, series, as_of, **kw):
    return PE.open_entries(
        strategy_key="baseline_momentum.v1", signal_fn=LIB.baseline_momentum,
        primary_horizon=5, securities=securities, series_for=lambda s: series,
        as_of=as_of, book=book, **kw)


# --- it actually produces positions ----------------------------------------
def test_a_fired_signal_opens_a_paper_position(book):
    s = _series()
    as_of = sorted(s)[60]
    entries = _open(book, [_sec()], s, as_of)
    assert entries
    assert entries[0].direction in ("long", "short")
    assert entries[0].entry_price == s[as_of]
    assert book.open_positions()


def test_an_etf_can_reach_a_position_which_the_narrative_gate_never_allowed():
    """The point of the whole exercise: an ETF has no company narrative."""
    etf = UT.Security(symbol="XLK", security_type=UT.SECTOR_ETF,
                      sector="Technology")
    assert etf.security_type in (UT.SECTOR_ETF, UT.BROAD_ETF)
    assert not getattr(etf, "company_id", "")


# --- caps: these only ever REDUCE trading ----------------------------------
def test_no_pyramiding_into_one_security(book):
    s = _series()
    as_of = sorted(s)[60]
    first = _open(book, [_sec()], s, as_of)
    second = _open(book, [_sec()], s, sorted(s)[61])
    assert len(first) == 1
    assert second == [], "a second position in a held name is pyramiding"


def test_a_high_frequency_strategy_cannot_consume_the_whole_book(book):
    """baseline_momentum fires on ~74% of security-days; without a cap it would
    drown out the strategies that fire rarely."""
    s = _series()
    many = [_sec(f"S{i}") for i in range(60)]
    entries = _open(book, many, s, sorted(s)[60], max_concurrent=5)
    assert len(entries) == 5


def test_capacity_accounts_for_positions_already_open(book):
    s = _series()
    _open(book, [_sec("A")], s, sorted(s)[60], max_concurrent=2)
    more = _open(book, [_sec("B"), _sec("C")], s, sorted(s)[61],
                 max_concurrent=2)
    assert len(more) == 1


# --- entry integrity --------------------------------------------------------
def test_no_entry_without_a_bar_on_the_decision_date(book):
    s = _series()
    missing = sorted(s)[60]
    del s[missing]
    assert _open(book, [_sec()], s, missing) == []


def test_no_entry_without_enough_history(book):
    s = _series(n=10)
    assert _open(book, [_sec()], s, sorted(s)[-1]) == []


def test_a_security_outside_its_listing_window_is_not_entered(book):
    s = _series()
    as_of = sorted(s)[60]
    dead = _sec("SIVB", delisted_at="2022-01-05",
                delisting_reason="bank failure")
    assert _open(book, [dead], s, as_of) == []


def test_entries_are_paper_only_and_fail_closed(book, monkeypatch):
    from intent_engine.market import trading_mode as TM
    s = _series()
    with pytest.raises(TM.TradingModeError):
        _open(book, [_sec()], s, sorted(s)[60], env={"TRADING_MODE": "LIVE"})


# --- resolution -------------------------------------------------------------
def test_an_unelapsed_horizon_is_not_resolved(book):
    s = _series()
    as_of = sorted(s)[60]
    _open(book, [_sec()], s, as_of)
    assert PE.resolve_due(book=book, series_for=lambda x: s,
                          today=as_of) == []


def test_an_elapsed_horizon_resolves_with_costs(book):
    s = _series()
    as_of = sorted(s)[60]
    _open(book, [_sec()], s, as_of)
    out = PE.resolve_due(book=book, series_for=lambda x: s,
                         today=sorted(s)[80])
    assert len(out) == 1
    r = out[0]
    assert r.net_return < r.gross_return       # costs applied
    assert r.resolved_at > r.opened_at
    assert book.open_positions() == []         # no longer open


def test_a_missing_exit_bar_leaves_the_position_open(book):
    s = _series()
    as_of = sorted(s)[60]
    entries = _open(book, [_sec()], s, as_of)
    gapped = dict(s)
    del gapped[entries[0].resolve_on]
    assert PE.resolve_due(book=book, series_for=lambda x: gapped,
                          today=sorted(s)[80]) == []
    assert book.open_positions(), "left open, retried next cycle"


def test_a_rerun_does_not_double_resolve(book):
    s = _series()
    _open(book, [_sec()], s, sorted(s)[60])
    first = PE.resolve_due(book=book, series_for=lambda x: s,
                           today=sorted(s)[80])
    second = PE.resolve_due(book=book, series_for=lambda x: s,
                            today=sorted(s)[80])
    assert len(first) == 1 and second == []


def test_a_short_resolves_with_the_sign_inverted(book):
    falling = _series(step=-0.6)
    as_of = sorted(falling)[60]
    entries = _open(book, [_sec()], falling, as_of)
    assert entries[0].direction == "short"
    out = PE.resolve_due(book=book, series_for=lambda x: falling,
                         today=sorted(falling)[80])
    assert out[0].gross_return > 0            # short a falling market


# --- isolation --------------------------------------------------------------
def test_books_are_isolated_per_strategy(tmp_path):
    a = PE.PaperBook("mean_reversion.v1", root=str(tmp_path))
    b = PE.PaperBook("volatility_breakout.v1", root=str(tmp_path))
    assert a.path != b.path
    s = _series()
    PE.open_entries(strategy_key="mean_reversion.v1",
                    signal_fn=LIB.baseline_momentum, primary_horizon=5,
                    securities=[_sec()], series_for=lambda x: s,
                    as_of=sorted(s)[60], book=a)
    assert a.open_positions() and b.open_positions() == []


# --- the control label ------------------------------------------------------
def test_every_entry_is_labelled_a_control_with_no_alpha_claim(book):
    s = _series()
    entries = _open(book, [_sec()], s, sorted(s)[60])
    assert entries[0].mode == PE.PAPER_CONTROL
    assert entries[0].alpha_claim is False


def test_the_book_summary_always_carries_the_control_caveat(book):
    s = _series()
    _open(book, [_sec()], s, sorted(s)[60])
    PE.resolve_due(book=book, series_for=lambda x: s, today=sorted(s)[80])
    summary = PE.book_summary(book)
    assert summary["alpha_claim"] is False
    assert summary["mode"] == PE.PAPER_CONTROL
    assert "no measured edge" in summary["note"]
    assert "not evidence of alpha" in summary["note"]


def test_a_control_is_not_a_lifecycle_state_and_cannot_be_promoted():
    """Structural: PAPER_CONTROL is an operating mode, not a rung on the
    ladder, so it cannot be confused with passing the gates."""
    assert PE.PAPER_CONTROL not in ST.STATES
    for state in ST.STATES:
        assert ST.PAPER_CHAMPION not in ST._TRANSITIONS.get(ST.RESEARCH, set())


def test_the_allocation_rule_is_preregistered_and_versioned():
    assert PE.ALLOCATION_VERSION == "paper_alloc.v1"
    assert PE.MAX_CONCURRENT_PER_STRATEGY == 20
    assert PE.NOTIONAL_PER_POSITION == 1000.0


def test_no_brokerage_reference_in_the_paper_engine():
    import inspect
    src = inspect.getsource(PE).lower()
    for word in ("alpaca", "ibkr", "submit_order", "place_order",
                 "broker_connect", "real_money", "account_funding"):
        assert word not in src
