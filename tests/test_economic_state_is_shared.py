"""One economic world, read once -- and never served stale as current.

`econ_context.load` re-read and re-validated the state snapshot from disk on
every call, so a fifty-company cohort rebuilt one identical macro world fifty
times, each rebuild a file read plus a full contract validation on the
interactive path. The economy is not a property of the company being analysed.

The saving is the smaller half. A cache that could serve yesterday's world as
today's would be the stale-as-current defect this codebase refuses everywhere
else, so the key carries the state file's own mtime and size.
"""
from __future__ import annotations

import json

from intent_engine.external_intel import econ_context as EC


def _root(tmp_path, payload):
    d = tmp_path / "econ"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "state_snapshot.jsonl"
    f.write_text(json.dumps(payload) + "\n")
    return tmp_path, f


def test_the_same_world_is_not_rebuilt_per_company(tmp_path, monkeypatch):
    EC._CACHE.clear()
    root, _f = _root(tmp_path, {"as_of": "2026-08-30"})
    calls = []
    # The READ is stubbed on purpose: this file is about the memoisation
    # layer, and calling through would make every assertion depend on the
    # state-snapshot schema instead of on caching.
    monkeypatch.setattr(EC, "_load_uncached",
                        lambda r, **k: (calls.append(1),
                                        EC.unavailable("stub"))[1])
    for _company in range(5):
        EC.load(root, as_of="2026-08-30")
    assert len(calls) == 1, (
        f"the shared economic state was rebuilt {len(calls)} times for five "
        f"company analyses")


def test_a_republished_state_is_picked_up(tmp_path, monkeypatch):
    """POSITIVE CONTROL, and the one that matters.

    A cache without this serves a world that has since changed, which is
    worse than the cost it saves.
    """
    EC._CACHE.clear()
    root, f = _root(tmp_path, {"as_of": "2026-08-30"})
    calls = []
    # The READ is stubbed on purpose: this file is about the memoisation
    # layer, and calling through would make every assertion depend on the
    # state-snapshot schema instead of on caching.
    monkeypatch.setattr(EC, "_load_uncached",
                        lambda r, **k: (calls.append(1),
                                        EC.unavailable("stub"))[1])
    EC.load(root, as_of="2026-08-30")
    EC.load(root, as_of="2026-08-30")
    assert len(calls) == 1
    # the market engine republishes
    import os
    import time
    f.write_text(json.dumps({"as_of": "2026-08-31", "extra": "x"}) + "\n")
    os.utime(f, (time.time() + 5, time.time() + 5))
    EC.load(root, as_of="2026-08-30")
    assert len(calls) == 2, (
        "a republished economic state was served from cache -- stale world "
        "presented as current")


def test_a_different_as_of_is_a_different_world(tmp_path, monkeypatch):
    EC._CACHE.clear()
    root, _f = _root(tmp_path, {"as_of": "2026-08-30"})
    calls = []
    # The READ is stubbed on purpose: this file is about the memoisation
    # layer, and calling through would make every assertion depend on the
    # state-snapshot schema instead of on caching.
    monkeypatch.setattr(EC, "_load_uncached",
                        lambda r, **k: (calls.append(1),
                                        EC.unavailable("stub"))[1])
    EC.load(root, as_of="2026-08-30")
    EC.load(root, as_of="2026-01-01")
    assert len(calls) == 2, "two different cutoffs collapsed into one cache entry"


def test_an_unreadable_root_is_never_cached(tmp_path, monkeypatch):
    """An unknown fingerprint means 'do not trust a cache entry'."""
    EC._CACHE.clear()
    monkeypatch.setattr(EC, "_state_fingerprint", lambda r: ())
    calls = []
    # The READ is stubbed on purpose: this file is about the memoisation
    # layer, and calling through would make every assertion depend on the
    # state-snapshot schema instead of on caching.
    monkeypatch.setattr(EC, "_load_uncached",
                        lambda r, **k: (calls.append(1),
                                        EC.unavailable("stub"))[1])
    EC.load(tmp_path, as_of="2026-08-30")
    EC.load(tmp_path, as_of="2026-08-30")
    assert len(calls) == 2, "cached on an unknown fingerprint"
    assert not EC._CACHE


def test_the_cache_is_bounded(tmp_path, monkeypatch):
    EC._CACHE.clear()
    root, _f = _root(tmp_path, {"as_of": "2026-08-30"})
    monkeypatch.setattr(EC, "_load_uncached",
                        lambda r, **k: EC.unavailable("stub"))
    for i in range(EC._CACHE_MAX * 3):
        EC.load(root, as_of=f"2026-08-{(i % 28) + 1:02d}")
    assert len(EC._CACHE) <= EC._CACHE_MAX


def test_the_cache_returns_the_reads_own_result_unchanged(tmp_path,
                                                          monkeypatch):
    """POSITIVE CONTROL: memoising must not have altered what `load` returns.

    Asserted against the READ rather than against a fabricated snapshot, so
    this does not silently become a test of the state-snapshot schema. The
    loader's behaviour on a malformed row is unchanged by this commit and is
    not what is being measured here.
    """
    EC._CACHE.clear()
    root, _f = _root(tmp_path, {"as_of": "2026-08-30"})
    sentinel = EC.EconContext(available=True, as_of="2026-08-30",
                              area="US", reason="")
    monkeypatch.setattr(EC, "_load_uncached", lambda r, **k: sentinel)
    assert EC.load(root, as_of="2026-08-30") is sentinel
    assert EC.load(root, as_of="2026-08-30") is sentinel
