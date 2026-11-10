"""The vintage wall, the registries agreeing, and the false-LIVE guard.

§29 asks for a guard that makes the previous run's six falsely-LIVE series
impossible to repeat. The guard is not "check more carefully"; it is that a
LIVE claim in `econ.series` must have an adapter in `market.alfred` that
names the same series id, and that a vintage request carrying observations
after its own vintage is refused rather than warned.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import series as SER
from intent_engine.econ import vocabulary as V
from intent_engine.market import alfred as AL


# =============================================================================
# The vintage wall (§6, §7, §30)
# =============================================================================

def _csv(rows, col="PSAVERT_20080915"):
    body = f"observation_date,{col}\n"
    return body + "\n".join(f"{d},{v}" for d, v in rows)


def test_a_vintage_response_carrying_the_future_is_refused():
    """The exact symptom of an endpoint ignoring `vintage_date`.

    fredgraph accepts the parameter and returns today's series. If that
    response were accepted, every fold of a historical replay would be scored
    against revisions published years later, and the replay would report
    itself as walled.
    """
    leaky = _csv([("2008-06-01", 2.5), ("2026-07-01", 3.0)])
    with pytest.raises(AL.VintageIgnored) as e:
        AL.fetch_series("PSAVERT", vintage="2008-09-15",
                        fetcher=lambda url: leaky)
    assert "2026-07-01" in str(e.value)


def test_a_clean_vintage_response_is_accepted():
    """The positive control. Without it the test above is satisfied by a
    fetcher that refuses everything."""
    clean = _csv([("2008-05-01", 2.4), ("2008-06-01", 2.5)])
    col, rows = AL.fetch_series("PSAVERT", vintage="2008-09-15",
                                fetcher=lambda url: clean)
    assert len(rows) == 2
    assert dict(rows)["2008-06-01"] == 2.5


def test_the_vintage_url_is_alfred_and_the_plain_url_is_fred():
    """Routing matters more than it looks: the two endpoints accept the same
    parameter and only one honours it."""
    seen = []

    def fetcher(url):
        seen.append(url)
        return _csv([("2008-06-01", 2.5)])

    AL.fetch_series("PSAVERT", vintage="2008-09-15", fetcher=fetcher)
    assert "alfred.stlouisfed.org" in seen[0]
    assert "vintage_date=2008-09-15" in seen[0]

    seen.clear()
    AL.fetch_series("PSAVERT", fetcher=lambda u: (seen.append(u) or
                                                  _csv([("2026-07-01", 3.0)],
                                                       col="PSAVERT")))
    assert "fred.stlouisfed.org" in seen[0]
    assert "vintage_date" not in seen[0]


def test_a_vintage_node_takes_its_availability_from_the_publisher():
    """With a vintage the publisher has said what was knowable; an assumed
    lag would be a worse answer sitting on top of a better one."""
    rows = [("2008-06-01", 2.5)]
    nodes = AL.to_nodes(AL.BY_ID["PSAVERT"], rows, vintage="2008-09-15",
                        retrieved_at="2026-08-27")
    assert nodes[0].available_at == "2008-09-15"
    assert "publisher vintage" in nodes[0].provenance.producer


def test_a_keyless_node_says_its_availability_was_assumed():
    rows = [("2026-06-01", 3.0)]
    nodes = AL.to_nodes(AL.BY_ID["PSAVERT"], rows, retrieved_at="2026-08-27")
    assert nodes[0].available_at > nodes[0].occurred_at
    assert "assumed" in nodes[0].provenance.producer


# =============================================================================
# §29: the false-LIVE guard
# =============================================================================

def test_every_alfred_series_is_declared_in_the_registry():
    """An adapter reading a series nobody declared means the coverage figure
    is computed from a different set than the one that runs.

    The reverse direction -- every LIVE series has SOME adapter -- lives in
    `test_behavioral_ingest`, which knows about both adapters. Two tests
    asserting the same property against one adapter each is how a second
    adapter breaks a guard that was right.
    """
    declared = {s.key for s in SER.BEHAVIOURAL}
    undeclared = set(AL.BEHAVIOURAL_IDS) - declared
    assert not undeclared, (
        f"{sorted(undeclared)} are fetched by the adapter and not declared "
        "in econ.series; coverage would be computed from the wrong set")


def test_only_the_alfred_route_can_serve_a_vintage():
    """The BLS route is keyless and works and cannot serve a vintage, so it
    may never back a walled replay. Recorded as a property, because the two
    routes serve the same two quantities under different ids and the
    difference between them is invisible at the call site."""
    from intent_engine.market import behavioral_ingest as BI
    bls_only = set(BI.BLS_BEHAVIOURAL) - set(AL.BEHAVIOURAL_IDS)
    assert bls_only, "this test is vacuous if the two adapters overlap fully"
    for key in bls_only:
        spec = next((s for s in SER.BEHAVIOURAL if s.key == key), None)
        assert spec is not None
        assert "superseded" in (spec.reason or "").lower(), (
            f"{key} is served only by the vintage-less BLS route and does "
            "not say so; a caller could reach for it in a replay")


def test_the_two_registries_agree_on_what_each_series_measures():
    for s in SER.BEHAVIOURAL:
        if s.key in AL.BY_ID:
            assert AL.BY_ID[s.key].kind == s.kind, (
                f"{s.key}: econ.series calls it {s.kind!r}, the adapter calls "
                f"it {AL.BY_ID[s.key].kind!r}. Two spellings of one quantity "
                "is how corroboration silently stops working.")


def test_every_adapter_kind_is_in_the_vocabulary():
    for s in AL.REGISTRY:
        assert s.kind in V.ALL_KINDS
        assert s.node_class in V.NODE_CLASSES


def test_behavioural_series_are_not_filed_as_macro():
    """If quits arrived as a macro labour reading, the incremental-value
    comparison would be scoring a model against itself."""
    for s in AL.REGISTRY:
        if s.node_class == V.BEHAVIORAL:
            assert s.kind in V.NODE_KINDS[V.BEHAVIORAL]
        if s.node_class == V.MACRO:
            assert s.kind in V.NODE_KINDS[V.MACRO]


# =============================================================================
# Parsing and failure semantics
# =============================================================================

def test_missing_observations_are_dropped_not_zero_filled():
    """ALFRED writes '.' for a period with no observation. A zero saving rate
    and an unpublished saving rate support opposite conclusions."""
    body = "observation_date,PSAVERT\n2008-05-01,.\n2008-06-01,2.5\n"
    col, rows = AL.fetch_series("PSAVERT", fetcher=lambda u: body)
    assert rows == [("2008-06-01", 2.5)]


def test_a_series_with_no_numeric_rows_says_so_specifically():
    body = "observation_date,X\n2008-05-01,.\n2008-06-01,.\n"
    with pytest.raises(AL.AlfredError) as e:
        AL.fetch_series("X", fetcher=lambda u: body)
    assert "no numeric observations" in str(e.value)


def test_collect_reports_failures_rather_than_looking_empty():
    def broken(url):
        raise AL.AlfredError("publisher refused")
    out = AL.collect(retrieved_at="2026-08-27", only=("PSAVERT",),
                     fetcher=broken)
    assert out["collected"] == 0
    assert out["series_failed"]
    assert out["empty_because"] == "every series failed"


def test_collect_succeeds_and_counts_per_series():
    def ok(url):
        return "observation_date,PSAVERT\n2026-06-01,3.0\n2026-07-01,3.1\n"
    out = AL.collect(retrieved_at="2026-08-27", only=("PSAVERT",), fetcher=ok)
    assert out["collected"] == 2
    assert out["per_series"]["PSAVERT"] == 2
    assert out["empty_because"] == ""


def test_since_filters_without_changing_availability_semantics():
    def ok(url):
        return ("observation_date,PSAVERT\n2000-01-01,4.0\n"
                "2026-07-01,3.1\n")
    out = AL.collect(retrieved_at="2026-08-27", only=("PSAVERT",),
                     since="2020-01-01", fetcher=ok)
    assert out["collected"] == 1
    assert out["nodes"][0].occurred_at == "2026-07-01"
