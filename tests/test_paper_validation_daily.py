"""The daily job for the forward ledger: catch-up after sleep, no-op rerun,
explicit alerts, and the original ledger never touched.

Runs on a copy of the committed 2026-11-09 ledger with synthetic bars and a
simulated clock. Scores are meaningless here; only the machinery is tested.
"""
import datetime as dt
import hashlib
import json
import pathlib
import random
import shutil

import pytest

from intent_engine.paper_validation import bars as BR
from intent_engine.paper_validation import daily as D
from intent_engine.paper_validation import ledger as LG
from intent_engine.paper_validation import schedule as SCH

COMMITTED = (pathlib.Path(__file__).parents[1]
             / "reports/paper_validation/forward_shadow_ledger.jsonl")
DAYS = SCH.sessions_after("2026-10-01", 80)


@pytest.fixture
def env(tmp_path):
    if not COMMITTED.exists():                         # pragma: no cover
        pytest.skip("committed forward ledger absent")
    led = tmp_path / "ledger.jsonl"
    shutil.copy2(COMMITTED, led)
    clock = {}
    syms = sorted({s.registration["instrument"] for s in
                   LG.Ledger(led, LG.FORWARD_SHADOW).open_forecasts()})
    dead = next(s for s in syms if s != "SPY")

    def bars(upto, *, dead_from="2026-11-20", fail=False):
        def fn(ss):
            if fail:
                raise RuntimeError("feed down")
            rng, out = random.Random(7), {}
            for s in set(ss) | {"SPY"}:
                ds = tuple(d for d in DAYS if d <= upto
                           and (s != dead or d < dead_from))
                px = tuple(100 * (1 + 0.001 * rng.uniform(-5, 5)) ** i
                           for i in range(len(ds)))
                out[s] = BR.Bars(symbol=s, dates=ds, open_adj=px,
                                 close_adj=px, retrieved_at="SIM",
                                 sha256="0" * 64, source="SIM")
            return out, []
        return fn

    def run(day, **kw):
        clock["t"] = dt.datetime.fromisoformat(f"{day}T23:00:00+00:00")
        return D.run(now=clock["t"], ledger_path=led,
                     log_path=tmp_path / "runs.jsonl",
                     bars_fn=bars(day, **kw), clock=lambda: clock["t"])
    n_dead = sum(1 for s in LG.Ledger(led, LG.FORWARD_SHADOW).open_forecasts()
                 if s.registration["instrument"] == dead)
    return {"run": run, "led": led, "log": tmp_path / "runs.jsonl",
            "dead_n": n_dead, "bars": bars}


def test_before_maturity_nothing_is_fetched_or_resolved(env):
    r = env["run"]("2026-12-05")
    assert r["status"] == "OK" and r["resolved"] == 0 and r["fetched"] is False


def test_a_run_after_a_long_sleep_catches_up_and_says_so(env):
    env["run"]("2026-12-05")
    r = env["run"]("2026-12-16")
    assert r["resolved"] == 977 - env["dead_n"]
    assert r["missed_runs"] == 10
    assert any("missed" in a for a in r["alerts"]) and r["status"] == "ALERT"


def test_a_rerun_resolves_nothing_and_appends_no_outcome(env):
    env["run"]("2026-12-16")
    lines = env["led"].read_bytes()
    r = env["run"]("2026-12-17")
    assert r["resolved"] == 0 and env["led"].read_bytes() == lines


def test_a_delisted_instrument_waits_then_voids_with_its_reason(env):
    env["run"]("2026-12-16")
    late = env["run"]("2026-12-19")              # past the 7-day data grace
    assert late["voided"] == env["dead_n"] and late["still_open"] == 0
    st = LG.Ledger(env["led"], LG.FORWARD_SHADOW).states().values()
    voids = [s for s in st if s.status == LG.VOIDED]
    assert len(voids) == env["dead_n"]
    assert all("halted or delisted" in s.void_reason
               and "never moved" in s.void_reason for s in voids)


def test_a_feed_failure_is_a_logged_failed_run_never_a_resolution(env):
    lines = env["led"].read_bytes()
    r = env["run"]("2026-12-16", fail=True)
    assert r["status"] == "FAILED" and "feed down" in r["error"]
    assert env["led"].read_bytes() == lines
    assert json.loads(env["log"].read_text().splitlines()[-1])["status"] == "FAILED"


def test_an_open_forecast_past_the_grace_is_an_overdue_alert(env):
    led = LG.Ledger(env["led"], LG.FORWARD_SHADOW)
    od = D.overdue(led, "2026-12-30")
    assert len(od) == 977                        # nothing resolved, all overdue
    assert D.overdue(led, "2026-12-16") == []


def test_the_committed_ledger_is_never_modified(env):
    h = hashlib.sha256(COMMITTED.read_bytes()).hexdigest()
    env["run"]("2026-12-16")
    assert hashlib.sha256(COMMITTED.read_bytes()).hexdigest() == h
