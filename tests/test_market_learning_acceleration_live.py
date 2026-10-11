"""LIVE ACCEPTANCE CHECKS -- read the real production ledger.

Split out of `test_market_learning_acceleration.py` on 2026-10-11. These tests read
`/Users/prathamsharma/intent-engine-market` directly, so their results move
whenever a scheduled cycle appends. That makes them **monitors of production
state**, not regression tests: a legitimate new observation can turn one red
with nothing broken, and a concurrent cycle writing the ledger makes them
nondeterministic outright.

They are deliberately NOT weakened and NOT skipped. Every assertion is
unchanged and they remain runnable on demand:

    env PYTHONPATH=src python -m pytest tests/test_market_learning_acceleration_live.py

Repository convention: live tests live in `tests/test_*_live.py` and the
pre-commit guard deselects them by filename, alongside
`test_calendar_live.py`, `test_macro_data_live.py` and the others. The
invariants stay covered in the offline suite by the 14 deterministic
tests remaining in `test_market_learning_acceleration.py`.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import learning_acceleration as LA
from intent_engine.market import learning_health as LH

MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")


class Obs:
    """A cycle, with only the fields a rate needs."""

    def __init__(self, **kwargs):
        defaults = dict(
            as_of="2026-08-01", cycle="night", accepted_evidence=10,
            duplicate_evidence=0, self_tests_refused=0, beliefs_accepted=1,
            beliefs_strengthened=0, beliefs_weakened=0, beliefs_retired=0,
            beliefs_decayed=0, expectations_created=1,
            expectations_evaluated=10, expectations_resolved=1,
            hidden_states_moved=0, causal_edges=0, interactions_observed=0,
            information_priorities=0, dossiers_written=1,
            companies_with_new_evidence=1, candidate_event_sentences=10,
            documents_considered=1, refused={}, binding_refused={},
            backlog_drain=False)
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(self, key, value)


def real_observations():
    return LH.load_cycle_observations(MARKET_ROOT)


def real_ledger():
    path = MARKET_ROOT / "reports" / "market" / "learning_ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]


# --- volume alone is never acceleration ----------------------------------

# --- the things that must not count as learning --------------------------

def test_the_real_report_sees_the_twenty_self_tests():
    got = LA.report(real_observations(), ledger=real_ledger())
    # The production runtime appends nightly, so this constant has an
    # expiry date. What is durable is that the self-tests are SEEN.
    assert got["windows"]["recent"]["metrics"]["self_tests_refused"] >= 20.0


# --- levels, not only trends ---------------------------------------------

def test_no_quality_dimension_can_exceed_one():
    for name, value in LA.quality(real_observations(),
                                  ledger=real_ledger()).items():
        if value is None or name == "source_diversity" \
                or name.startswith("_"):
            continue
        assert 0.0 <= float(value) <= 1.0, name


# --- windows are computed only where the history defends them ------------

def test_windows_beyond_the_history_report_insufficient_with_the_real_count():
    """A window the history cannot defend says so, and names the shortfall.

    THE LIST USED TO BE HARD-CODED — ("7_cycle", "14_cycle", "30_cycle") —
    which asserted a fact about how much history existed on the day it was
    written. Production appends nightly, so the history grew past seven cycles
    and `7_cycle` became computable: the suite went red because the engine had
    LEARNED MORE, with no code change. The durable claim is the relationship
    between what a window requires and what exists, so it is now read off the
    report rather than remembered.
    """
    got = LA.report(real_observations(), ledger=real_ledger())
    beyond = [n for n, w in got["windows"].items()
              if w["cycles_required"] > w["cycles_available"]]
    assert beyond, "no window exceeds the history; the case is unexercised"
    for name in beyond:
        window = got["windows"][name]
        assert window["status"] == LA.INSUFFICIENT_HISTORY
        assert str(window["cycles_available"]) in window["reason"]
    # ...and the converse, so this cannot pass by calling everything short.
    for name, window in got["windows"].items():
        if window["cycles_required"] <= window["cycles_available"]:
            assert window["status"] != LA.INSUFFICIENT_HISTORY


# --- the real history -----------------------------------------------------

def test_the_real_history_reads_degrading_on_the_self_test_rate():
    got = LA.report(real_observations(), ledger=real_ledger())
    assert got["cycles_total"] >= 6
    assert got["backlog_cycles_excluded"] == 1
    # Exactly the windows the history can defend — derived, not remembered.
    # Pinning `[RECENT]` asserted that only four cycles existed, which stopped
    # being true the moment production ran again.
    expected = [n for n, size in LA.WINDOWS
                if size <= got["windows"][n]["cycles_available"]]
    assert got["windows_computed"] == expected
    assert LA.RECENT in got["windows_computed"]
    assert got["status"] == LA.DEGRADING
    assert any("self_test_rate" in d for d in got["degradations"])
    assert got["quality"]["self_test_rate"] >= 0.8


# --- a rate without its denominator is not a measurement -----------------

def test_every_rate_carries_the_pair_it_came_from():
    got = LA.quality(real_observations(), ledger=real_ledger())
    pairs = got["_denominators"]
    for name in LA.QUALITY_NAMES:
        if got.get(name) is None or name == "source_diversity":
            continue
        assert name in pairs, name
        numerator, denominator = pairs[name]
        assert numerator <= denominator


def test_a_trend_degradation_is_tagged_with_its_maturity_too():
    """An untagged trend would be read as mature by default."""
    got = LA.report(real_observations(), ledger=real_ledger())
    assert any("USABLE]" in d or "MATURE]" in d or "EARLY]" in d
               for d in got["degradations"])


def test_the_real_verdict_still_degrades_and_says_on_which_dimension():
    """DEGRADING is retained, and now for a stated reason: it rests on
    false_positive_rate at 23/90 (USABLE), not on the EARLY self-test rate."""
    got = LA.report(real_observations(), ledger=real_ledger())
    assert got["status"] == LA.DEGRADING
    mature = [d for d in got["degradations"]
              if "USABLE]" in d or "MATURE]" in d]
    assert mature, got["degradations"]
    assert any("self_test_rate" in d
               for d in got["degradations"])
