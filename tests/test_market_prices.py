"""The price feed — the channel that turns a decision into a graded decision.

Parsing is where the bugs live, not the socket, so every case here injects a
payload. The load-bearing tests are the ones that refuse to invent a price:
a fabricated close is worse than a gap, because a gap is visible.
"""
import pytest

from intent_engine.market.prices import (
    SOURCE,
    PriceSeries,
    PriceUnavailable,
    fetch_series,
    price_at_factory,
    trading_window,
)

# 2026-07-01 .. 2026-07-06 UTC
_STAMPS = [1782950400, 1783036800, 1783123200, 1783209600, 1783296000]


def _payload(closes):
    return {"chart": {"result": [{"timestamp": _STAMPS[:len(closes)],
                                  "indicators": {"quote": [{"close": closes}]}}]}}


def _opener(payload):
    def _open(url, timeout):
        return payload
    return _open


def _series(closes=(10.0, 11.0, 12.0, 13.0, 14.0)):
    return fetch_series("X", opener=_opener(_payload(list(closes))))


# --- parsing -----------------------------------------------------------------
def test_real_closes_are_parsed_into_dated_prices():
    s = _series()
    assert len(s.closes) == 5 and s.source == SOURCE
    assert all(d.startswith("2026-07") for d in s.closes)


def test_a_null_close_is_dropped_never_carried_forward():
    """A null close is real in this feed (halted session, bad tick). An
    invented price is worse than a gap because a gap is visible."""
    s = fetch_series("X", opener=_opener(_payload([10.0, None, 12.0])))
    assert len(s.closes) == 2
    assert 11.0 not in s.closes.values()


def test_an_empty_or_error_payload_raises_rather_than_returning_nothing():
    for payload in ({"chart": {"result": []}},
                    {"chart": {"error": "not found"}},
                    _payload([None, None])):
        with pytest.raises(PriceUnavailable):
            fetch_series("X", opener=_opener(payload))


def test_a_transport_failure_becomes_price_unavailable():
    def _boom(url, timeout):
        raise OSError("network down")
    with pytest.raises(PriceUnavailable):
        fetch_series("X", opener=_boom)


# --- never look forward ------------------------------------------------------
def test_a_missing_day_falls_back_to_the_most_recent_earlier_close():
    """Markets shut at weekends. Exact-match-only would report "no price" for
    a third of calendar dates and quietly halve every sample."""
    s = _series()
    days = sorted(s.closes)
    assert s.on(days[2]) == s.closes[days[2]]
    later = "2026-12-31"
    assert s.on(later) == s.closes[days[-1]]


def test_it_never_returns_a_price_from_after_the_date_asked_for():
    """Lookahead would make every backtest optimistic in a way that is
    invisible afterwards."""
    s = _series()
    assert s.on("2020-01-01") is None


def test_as_of_is_the_last_date_returned_not_the_date_requested():
    """A stale feed answering an old close is the failure most likely to be
    mistaken for success."""
    s = _series()
    assert s.as_of == max(s.closes)


# --- an unelapsed horizon stays unresolved -----------------------------------
def test_a_horizon_that_has_not_elapsed_is_not_graded():
    """Grading a 3-day-old position as though its 21-day horizon had passed is
    the most flattering possible error."""
    s = _series()
    entry, exit_ = trading_window(s, sorted(s.closes)[-1], horizon_days=21)
    assert entry is not None and exit_ is None


def test_an_elapsed_horizon_returns_both_ends():
    s = _series()
    entry, exit_ = trading_window(s, sorted(s.closes)[0], horizon_days=2)
    assert entry is not None and exit_ is not None


# --- the injected callable ---------------------------------------------------
def test_price_at_fetches_once_per_symbol_and_reuses_it():
    calls = []

    def _fetch(symbol, days=400):
        calls.append(symbol)
        return _series()

    price_at = price_at_factory(fetcher=_fetch)
    day = sorted(_series().closes)[1]
    price_at("X", day)
    price_at("X", day)
    assert calls == ["X"], "one fetch per symbol, reused across dates"


def test_price_at_raises_rather_than_returning_a_placeholder():
    price_at = price_at_factory(fetcher=lambda s, days=400: _series())
    with pytest.raises(PriceUnavailable):
        price_at("X", "2019-01-01")
