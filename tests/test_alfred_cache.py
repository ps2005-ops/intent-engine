"""§3/§4/§31: the acquisition must be resumable, planned, and honest.

The failure this replaces: 2,760 serial requests that wrote nothing until the
end, ran for 25 minutes, were interrupted, and threw every request away.
"""
from __future__ import annotations

import pytest

from intent_engine.market import alfred_cache as AC


def _csv(rows, col="X"):
    return f"observation_date,{col}\n" + "\n".join(f"{d},{v}"
                                                   for d, v in rows)


# =============================================================================
# The cache is the resumability
# =============================================================================

def test_a_cached_key_is_never_requested_again(tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        return _csv([("2008-06-01", 2.5)])

    AC.fetch_one("PSAVERT", "2008-09-15", fetcher=fetcher, root=tmp_path)
    assert len(calls) == 1
    body, source = AC.fetch_one("PSAVERT", "2008-09-15", fetcher=fetcher,
                                root=tmp_path)
    assert source == "cache"
    assert len(calls) == 1, (
        "a second call hit the network for an immutable key; an interrupted "
        "acquisition would restart from zero")


def test_acquire_is_resumable_after_a_partial_run(tmp_path):
    """The property that matters: dying at 87% costs 13%, not 100%."""
    reqs = [AC.Request("A", "2008-09-15", "r"),
            AC.Request("B", "2008-09-15", "r"),
            AC.Request("C", "2008-09-15", "r")]
    calls = []

    def flaky(url):
        calls.append(url)
        if "id=C" in url:
            raise RuntimeError("connection reset")
        return _csv([("2008-06-01", 1.0)])

    first = AC.acquire(reqs, fetcher=flaky, root=tmp_path, concurrency=1)
    assert first["fetched"] == 2 and first["failed"] == 1

    calls.clear()

    def ok(url):
        calls.append(url)
        return _csv([("2008-06-01", 1.0)])

    second = AC.acquire(reqs, fetcher=ok, root=tmp_path, concurrency=1)
    assert second["already_cached"] == 2, (
        "the resumed run re-fetched work the first run completed")
    assert second["fetched"] == 1
    assert all("id=C" in c for c in calls), (
        f"the resumed run touched more than the missing key: {calls}")


def test_a_completed_acquisition_makes_zero_network_calls_on_rerun(tmp_path):
    reqs = [AC.Request("A", "2008-09-15", "r"), AC.Request("B", "", "r")]
    AC.acquire(reqs, fetcher=lambda u: _csv([("2008-06-01", 1.0)]),
               root=tmp_path, concurrency=1)

    def explode(url):
        raise AssertionError(f"network call on a fully cached rerun: {url}")

    out = AC.acquire(reqs, fetcher=explode, root=tmp_path, concurrency=1)
    assert out["already_cached"] == 2
    assert out["fetched"] == 0


def test_a_partial_write_never_becomes_a_cache_hit(tmp_path):
    """A half-written entry from an interrupted run would be indistinguish-
    able from a real one and would poison every later run."""
    p = AC.cache_path("A", "2008-09-15", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_suffix(".csv.part").write_text("observation_date,X\n2008-06-01,1")
    assert AC.cached("A", "2008-09-15", tmp_path) is None, (
        "a .part file was read as a completed cache entry")


def test_an_empty_response_is_not_cached(tmp_path):
    with pytest.raises(AC.AcquisitionError):
        AC.fetch_one("A", "2008-09-15",
                     fetcher=lambda u: "observation_date,X\n",
                     root=tmp_path)
    assert AC.cached("A", "2008-09-15", tmp_path) is None


def test_a_404_is_not_retried(tmp_path):
    """A 404 is a fact about the series, not a hiccup."""
    import urllib.error
    calls = []

    def gone(url):
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    with pytest.raises(AC.AcquisitionError) as e:
        AC.fetch_one("A", "2008-09-15", fetcher=gone, root=tmp_path)
    assert len(calls) == 1, f"a 404 was retried {len(calls)} times"
    assert "404" in str(e.value)


# =============================================================================
# The planner
# =============================================================================

def _profiles():
    return [
        AC.RevisionProfile("STABLE_ONE", AC.STABLE, overlap=800, differing=0),
        AC.RevisionProfile("REVISED_ONE", AC.REVISED, overlap=600,
                           differing=550, max_relative_change=0.31),
        AC.RevisionProfile("NO_HIST", AC.NO_VINTAGE_HISTORY,
                           note="404 at historical vintages"),
    ]


def test_a_stable_series_costs_one_request_not_one_per_origin():
    origins = [f"20{y:02d}-05-15" for y in range(10, 26)]
    reqs, s = AC.plan(_profiles(), origins)
    stable = [r for r in reqs if r.series_id == "STABLE_ONE"]
    assert len(stable) == 1, (
        f"a series that never revises was planned {len(stable)} times; the "
        "current series IS its own vintage history")
    assert stable[0].vintage == ""


def test_a_revised_series_gets_one_vintage_per_origin():
    origins = [f"20{y:02d}-05-15" for y in range(10, 26)]
    reqs, s = AC.plan(_profiles(), origins)
    revised = [r for r in reqs if r.series_id == "REVISED_ONE"]
    assert len(revised) == len(origins)
    assert {r.vintage for r in revised} == set(origins)


def test_a_series_with_no_vintage_history_is_excluded_with_a_reason():
    """Using its current values at a historical origin would leak."""
    reqs, s = AC.plan(_profiles(), ["2020-05-15"])
    assert not any(r.series_id == "NO_HIST" for r in reqs)
    assert "NO_HIST" in s["excluded_series"]
    assert s["excluded_series"]["NO_HIST"]


def test_the_plan_is_materially_smaller_than_the_naive_one():
    origins = [f"20{y:02d}-05-15" for y in range(10, 26)]
    reqs, s = AC.plan(_profiles(), origins)
    assert s["requests_planned"] < s["requests_naive"]
    assert s["reduction"] > 0.3


def test_the_plan_is_deterministic():
    origins = ["2020-05-15", "2021-05-15"]
    a, _ = AC.plan(_profiles(), origins)
    b, _ = AC.plan(_profiles(), origins)
    assert [r.key for r in a] == [r.key for r in b]


# =============================================================================
# The revision probe is a measurement
# =============================================================================

def test_an_unrevised_series_is_measured_stable(tmp_path):
    same = _csv([("2010-01-01", 1.0), ("2011-01-01", 2.0)])
    p = AC.probe_revisions(["S"], early="2015-05-15", late="2024-05-15",
                           fetcher=lambda u: same, root=tmp_path)[0]
    assert p.behaviour == AC.STABLE
    assert not p.needs_vintages
    assert p.note, "a stable verdict must say what was measured"


def test_a_heavily_revised_series_is_measured_revised(tmp_path):
    bodies = {}

    def fetcher(url):
        v = url.split("vintage_date=")[-1]
        if v not in bodies:
            bodies[v] = _csv([("2010-01-01", 1.0 if "2015" in v else 2.0),
                              ("2011-01-01", 1.0 if "2015" in v else 2.0)])
        return bodies[v]

    p = AC.probe_revisions(["S"], early="2015-05-15", late="2024-05-15",
                           fetcher=fetcher, root=tmp_path)[0]
    assert p.behaviour == AC.REVISED
    assert p.needs_vintages
    assert p.max_relative_change > 0.5


def test_a_tiny_revision_does_not_trigger_a_vintage_grid(tmp_path):
    """CPIAUCSL revises 6% of its points by 0.14%. That is a rounding
    artefact, and fetching 115 vintages for it would be waste."""
    def fetcher(url):
        v = url.split("vintage_date=")[-1]
        bump = 0.0 if "2015" in v else 0.0001
        return _csv([(f"20{y:02d}-01-01", 100.0 + bump)
                     for y in range(0, 20)])

    p = AC.probe_revisions(["S"], early="2015-05-15", late="2024-05-15",
                           fetcher=fetcher, root=tmp_path)[0]
    assert p.behaviour == AC.STABLE


def test_a_404_during_the_probe_becomes_no_vintage_history(tmp_path):
    import urllib.error

    def gone(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    p = AC.probe_revisions(["S"], early="2015-05-15", late="2024-05-15",
                           fetcher=gone, root=tmp_path)[0]
    assert p.behaviour == AC.NO_VINTAGE_HISTORY
    assert "leak" in p.note, (
        "the exclusion must say WHY, or a later run will re-add the series")


def test_concurrency_is_bounded(tmp_path):
    reqs = [AC.Request(f"S{i}", "2020-05-15", "r") for i in range(8)]
    out = AC.acquire(reqs, fetcher=lambda u: _csv([("2020-01-01", 1.0)]),
                     root=tmp_path, concurrency=99)
    assert out["concurrency"] <= AC.MAX_CONCURRENCY, (
        "an unbounded worker pool against a free public service")
