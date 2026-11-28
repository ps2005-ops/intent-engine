"""register --if-due must not crash when the benchmark fetch fails.

MEASURED 2026-11-27 19:17 ET (learning.daily on f7690938): one SPY request
timed out, forward_bars recorded it in `failed`, and cmd_register indexed
spy_now['SPY'] -> KeyError, rc=1, traceback in the scheduler log. Nothing was
registered (safe), but a timeout on the cohort's due day (~2026-12-09) would
have crashed registration the same way.

These tests pin: bounded retry on a transient network failure, no retry on a
parse failure, an explicit BENCHMARK_UNAVAILABLE result (rc 2) that writes
nothing, and the real CLI path reaching it.
"""
from __future__ import annotations

import argparse
import json

import pytest

from intent_engine.paper_validation import bars as BR
from intent_engine.paper_validation import forward as FW
from intent_engine.market import prices as MP


def _doc(sym):
    rows = [["2026-11-20", 1.0, 1.0], ["2026-11-21", 1.0, 1.0]]
    return {"symbol": sym, "source": BR.SOURCE, "retrieved_at": "2026-11-27T00:00:00+00:00",
            "url": "u", "fields": list(BR.FIELDS), "rows": rows, "sha256": BR._content_sha(rows)}


class _Flaky:
    def __init__(self, failures, message="timeout"):
        self.failures, self.message, self.calls = failures, message, 0

    def __call__(self, sym, *, now):
        self.calls += 1
        if self.calls <= self.failures:
            raise MP.PriceUnavailable(f"{sym}: {self.message}")
        return _doc(sym)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(FW, "FORWARD_PRICES", tmp_path / "prices")
    monkeypatch.setattr(BR, "to_bars", lambda doc: ("BARS", doc["symbol"]))
    return tmp_path


def test_a_transient_timeout_is_retried_and_recovers(cache):
    f, slept = _Flaky(2), []
    out, failed = FW.forward_bars(["SPY"], now=None, log=lambda *_: None, fetch=f, sleep=slept.append)
    assert "SPY" in out and failed == {}
    assert f.calls == 3 and slept == list(FW.RETRY_BACKOFF_S)


def test_retries_are_bounded(cache):
    f = _Flaky(99)
    out, failed = FW.forward_bars(["SPY"], now=None, log=lambda *_: None, fetch=f, sleep=lambda s: None)
    assert out == {} and "timeout" in failed["SPY"]
    assert f.calls == 1 + len(FW.RETRY_BACKOFF_S)


def test_a_parse_failure_is_an_answer_and_is_not_retried(cache):
    f = _Flaky(99, message="empty result")
    out, failed = FW.forward_bars(["SPY"], now=None, log=lambda *_: None, fetch=f, sleep=lambda s: None)
    assert out == {} and f.calls == 1


def test_transient_classification():
    assert FW.is_transient("SPY: timeout") and FW.is_transient("SPY: URLError")
    assert not FW.is_transient("SPY: empty result") and not FW.is_transient("SPY: no usable bars")


def test_the_cli_refuses_explicitly_and_writes_nothing(tmp_path, monkeypatch, capsys):
    ledger = tmp_path / "forward_shadow_ledger.jsonl"
    monkeypatch.setattr(FW, "FORWARD_LEDGER", ledger)
    monkeypatch.setattr(FW, "forward_bars",
                        lambda syms, now: ({}, {"SPY": "SPY: timeout"}))
    inputs = {"etfs": [], "companies": [], "panel": None}
    p = argparse.ArgumentParser(); sub = p.add_subparsers()
    FW.add_commands(sub, lambda: inputs)
    for argv, stage in ((["register", "--if-due"], "cadence check"), (["register"], "registration")):
        args = p.parse_args(argv)
        rc = args.fn(args)
        out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert rc == FW.RC_BENCHMARK_UNAVAILABLE == 2
        assert out["status"] == "BENCHMARK_UNAVAILABLE" and out["stage"] == stage
        assert out["registered"] == 0 and out["price_failures"] == {"SPY": "SPY: timeout"}
    assert not ledger.exists()
