"""Offline tests for core/macro_data.py (Task M1, market-engine-execution-plan.md).

Everything here runs against saved fixture JSON (tests/fixtures/fred/) or a
monkeypatched requests.get -- no network, no key required. The one live
call is tests/test_macro_data_live.py, gated separately.
"""

import json
from pathlib import Path

import pytest
import requests

from intent_engine.core.macro_data import (
    SEED_SERIES,
    FredSeries,
    _fetch_with_retry,
    _parse_response,
    get_series,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fred"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES / name) as f:
        return json.load(f)


# --- parsing + hard guards, against real/constructed fixture JSON ---------


def test_parse_response_on_real_dff_fixture():
    """DFF_2024-01-01_2024-01-10.json is a real, live-captured FRED response
    (10 real daily fed-funds-rate observations) -- not synthetic."""
    raw = _load_fixture("DFF_2024-01-01_2024-01-10.json")
    series = _parse_response(raw, "DFF")
    assert series.series_id == "DFF"
    assert series.realtime_date == "2026-07-16"
    assert len(series.observations) == 10
    assert series.observations[0] == ("2024-01-01", 5.33)
    assert series.observations[-1] == ("2024-01-10", 5.33)


def test_parse_response_raises_on_empty_observations():
    """Truncated/missing-series guard: a real-shaped FRED response with zero
    observations (e.g. a range with no data) must raise, never return an
    empty-but-valid FredSeries."""
    raw = _load_fixture("truncated_empty_observations.json")
    with pytest.raises(ValueError, match="no observations"):
        _parse_response(raw, "DFF")


def test_parse_response_raises_on_nan_observation():
    """NaN guard, against a REAL FRED quirk: VIXCLS_2024-01-01_2024-01-31.json
    is a real, live-captured response whose first observation (2024-01-01,
    New Year's Day) is FRED's own '.' missing-value marker -- not a
    fabricated edge case."""
    raw = _load_fixture("VIXCLS_2024-01-01_2024-01-31.json")
    with pytest.raises(ValueError, match="missing/NaN"):
        _parse_response(raw, "VIXCLS")


def test_parse_response_never_returns_unknown_string():
    """The guard's whole point: no code path in _parse_response can produce
    a placeholder string in place of a real value -- it always either
    returns real floats or raises."""
    raw = _load_fixture("truncated_empty_observations.json")
    try:
        _parse_response(raw, "DFF")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unknown" not in str(exc)


# --- cache round-trip -------------------------------------------------------


def test_get_series_cache_hit_never_touches_network(tmp_path, monkeypatch):
    """Pre-seed the cache with the real DFF fixture at the exact path
    get_series would look for; a cache hit must return correctly parsed
    data without calling requests.get at all (and without needing an API
    key -- monkeypatched absent here on purpose)."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    def _network_call_forbidden(*args, **kwargs):
        raise AssertionError("cache hit should never call requests.get")

    monkeypatch.setattr(requests, "get", _network_call_forbidden)

    cache_dir = tmp_path / "fred_cache"
    cache_dir.mkdir()
    raw = _load_fixture("DFF_2024-01-01_2024-01-10.json")
    (cache_dir / "DFF_2024-01-01_2024-01-10.json").write_text(json.dumps(raw))

    series = get_series("DFF", "2024-01-01", "2024-01-10", cache_dir=cache_dir)
    assert isinstance(series, FredSeries)
    assert len(series.observations) == 10


def test_get_series_writes_cache_after_a_fresh_fetch(tmp_path, monkeypatch):
    """A cache miss fetches (mocked here) and writes the cache file, so the
    SECOND call for the same series+range is a genuine cache hit."""
    raw = _load_fixture("DFF_2024-01-01_2024-01-10.json")
    call_count = {"n": 0}

    def _fake_get(url, params, timeout):
        call_count["n"] += 1
        class _Resp:
            status_code = 200
            def json(self_inner):
                return raw
        return _Resp()

    monkeypatch.setattr(requests, "get", _fake_get)
    cache_dir = tmp_path / "fred_cache"

    series1 = get_series("DFF", "2024-01-01", "2024-01-10", api_key="fake-key-for-test", cache_dir=cache_dir)
    assert call_count["n"] == 1
    assert (cache_dir / "DFF_2024-01-01_2024-01-10.json").exists()

    series2 = get_series("DFF", "2024-01-01", "2024-01-10", api_key="fake-key-for-test", cache_dir=cache_dir)
    assert call_count["n"] == 1  # second call was a cache hit, no new network call
    assert series1.observations == series2.observations


def test_get_series_raises_when_key_missing_and_no_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        get_series("DFF", "2024-01-01", "2024-01-10", cache_dir=tmp_path / "empty_cache")


# --- retry-with-backoff ------------------------------------------------------


def test_fetch_with_retry_retries_transient_errors_then_succeeds(monkeypatch):
    raw = _load_fixture("DFF_2024-01-01_2024-01-10.json")
    monkeypatch.setattr("intent_engine.core.macro_data.time.sleep", lambda _: None)
    attempts = {"n": 0}

    def _flaky_get(url, params, timeout):
        attempts["n"] += 1
        class _Resp:
            status_code = 503 if attempts["n"] < 3 else 200
            text = "server hiccup"
            def json(self_inner):
                return raw
        return _Resp()

    monkeypatch.setattr(requests, "get", _flaky_get)
    result = _fetch_with_retry("DFF", "2024-01-01", "2024-01-10", "fake-key", max_retries=3, timeout=15)
    assert attempts["n"] == 3
    assert result == raw


def test_fetch_with_retry_does_not_retry_non_transient_errors(monkeypatch):
    """A 400 (bad series_id) or 403 (bad key) is a real, permanent failure --
    retrying would just delay reporting it. Exactly one attempt expected."""
    monkeypatch.setattr("intent_engine.core.macro_data.time.sleep", lambda _: None)
    attempts = {"n": 0}

    def _bad_key_get(url, params, timeout):
        attempts["n"] += 1
        class _Resp:
            status_code = 403
            text = "Bad Request. The value for variable api_key is not registered."
        return _Resp()

    monkeypatch.setattr(requests, "get", _bad_key_get)
    with pytest.raises(RuntimeError, match="403"):
        _fetch_with_retry("DFF", "2024-01-01", "2024-01-10", "bad-key", max_retries=3, timeout=15)
    assert attempts["n"] == 1


def test_fetch_with_retry_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("intent_engine.core.macro_data.time.sleep", lambda _: None)

    def _always_fails(url, params, timeout):
        class _Resp:
            status_code = 503
            text = "still down"
        return _Resp()

    monkeypatch.setattr(requests, "get", _always_fails)
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        _fetch_with_retry("DFF", "2024-01-01", "2024-01-10", "fake-key", max_retries=3, timeout=15)


# --- no key material in the module ------------------------------------------


def test_seed_series_matches_the_plans_seed_set():
    assert SEED_SERIES == ["DFF", "CPIAUCSL", "UNRATE", "T10Y2Y", "BAMLH0A0HYM2", "GDPC1", "M2SL", "VIXCLS"]


def test_module_source_never_hardcodes_a_key_value():
    """Guard bar (d): zero key material anywhere in the diff. FRED_API_KEY
    is only ever read via os.environ / passed as a parameter -- this asserts
    the source module contains no literal key-shaped string."""
    import re
    import intent_engine.core.macro_data as module

    source = Path(module.__file__).read_text()
    # A real FRED key is a 32-char lowercase hex string; assert none appears.
    assert re.search(r"\b[0-9a-f]{32}\b", source) is None
