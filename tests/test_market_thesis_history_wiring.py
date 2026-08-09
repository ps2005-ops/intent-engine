"""The thesis seam inside the CYCLE, not the module beside it.

G-THE-004. Every thesis-history test until now called `reconcile` directly.
That proved the function and left the production step untested, which is how
three counted things went unnoticed for two live cycles:

  * the cycle built eleven theses and persisted seven, because two theses
    sharing an identity are one row to an idempotent store;
  * `compared` exceeded `loaded`, because several current theses matched one
    prior;
  * the chain was rebuilt empty every night, so every revision ever written
    had an empty parent.

None of those are visible from `reconcile` alone with a hand-built fixture.
They are properties of the step: what it loads, what it writes, and what it
reads back on the next run. So this file drives `knowledge_step` twice
against one root, the way a second night follows a first.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.market import cycle as C
from intent_engine.market import learning_store as LS
from intent_engine.market import steps as ST
from intent_engine.market import thesis_history as TH

AS_OF = "2026-08-09"

#: One company that has said it is capital-intensive, in its own filing. The
#: source role matters: a headline mentioning capex rates the exposure
#: INFERRED and no transmission is proposed from it.
EVIDENCE = {
    "record": "evidence", "evidence_id": "ev_capex_1",
    "subject_company": "acme", "actor": "acme",
    "observed_at": AS_OF, "available_at": AS_OF,
    "fact": "Our capital expenditure programme for the year is unchanged.",
    "evidence_type": "GUIDANCE", "source_role": "regulatory_filing",
    "source": "https://www.sec.gov/acme.htm",
    "reliability": 0.9, "relevance": 0.6, "independence": 0.2,
}


def _rate(area, series_id, value, period, published):
    """One MARKET_RATE figure for one economy."""
    return {
        "record": "macro_observation", "state_kind": "MARKET_RATE",
        "series_id": series_id, "label": f"{area} 10-year yield",
        "value": value, "unit": "%", "measure": "LEVEL",
        "standing": "OBSERVED", "area": area,
        "reference_period": period, "published_at": published,
        "retrieved_at": published, "publication_basis": "PUBLISHER",
        "source": "https://example.test/series",
    }


@pytest.fixture()
def root(tmp_path):
    """A runtime root holding one exposed company and two economies' rates.

    CA and US both move MARKET_RATE. That is the live shape: one condition,
    two economies, one company exposed to both — and it produced two theses
    that the engine could not tell apart.
    """
    (tmp_path / "reports" / "market").mkdir(parents=True)
    ledger = tmp_path / LS.DEFAULT_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        EVIDENCE,
        _rate("CA", "CA10Y", 3.1, "2026-07-01", "2026-07-02"),
        _rate("CA", "CA10Y", 3.6, "2026-08-01", "2026-08-02"),
        _rate("US", "DGS10", 4.1, "2026-07-01", "2026-07-02"),
        _rate("US", "DGS10", 4.6, "2026-08-01", "2026-08-02"),
    ]
    ledger.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return tmp_path


def _payload(root, *, as_of=AS_OF, run_id="k1"):
    ctx = C.CycleContext(cycle="market", as_of=as_of, root=root,
                         session=None, run_id=run_id)
    return ST.knowledge_step(ctx)


def _run(root, *, as_of=AS_OF, run_id="k1"):
    return _payload(root, as_of=as_of, run_id=run_id).get(
        "thesis_history") or {}


def test_the_fixture_actually_produces_two_theses_under_one_condition(root):
    """Guard the guard: a fixture yielding no thesis proves nothing.

    Every assertion below would pass vacuously against zero theses, which is
    the shape a green suite takes when the seam quietly stops running.
    """
    got = _run(root)
    assert got.get("theses_built", 0) >= 2, (
        f"the fixture produced {got.get('theses_built')} theses; the "
        "collision this file exists for needs at least two")


def test_every_thesis_the_cycle_builds_is_persisted(root):
    """Eleven built, seven stored. The four were never refused out loud."""
    got = _run(root)
    assert got["theses_sharing_an_identity"] == 0, (
        "two theses this cycle built are indistinguishable to the store; the "
        "second is dropped and the next cycle cannot compare against it")
    assert got["snapshots_refused_as_duplicate"] == 0
    assert got["snapshot_records_written"] == got["theses_built"]


def test_re_running_one_date_is_idempotent_and_not_reported_as_a_collision(
        root):
    """A refusal is not evidence of a collision.

    The store is keyed `(thesis_id, as_of)`, so a second run of the same date
    refuses every snapshot — correctly. Reading that refusal count as the
    collision count would make a clean re-run look like a mass drop.
    """
    _run(root, run_id="k1")
    again = _run(root, run_id="k2")
    assert again["snapshots_refused_as_duplicate"] == again["theses_built"]
    assert again["theses_sharing_an_identity"] == 0


def test_the_two_economies_are_two_theses_not_one(root):
    """CA:MARKET_RATE and US:MARKET_RATE must not share an identity."""
    _run(root)
    store = LS.LearningStore(root / LS.DEFAULT_PATH)
    snapshots = store.thesis_snapshots()
    areas = {r.get("area") for r in snapshots}
    assert {"CA", "US"} <= areas, f"areas persisted: {areas}"
    assert len({r["thesis_id"] for r in snapshots}) == len(snapshots), (
        "two persisted theses share a thesis_id")


def test_a_second_cycle_compares_no_more_theses_than_it_loaded(root):
    """`compared: 11` against `loaded: 7` is the arithmetic that started this."""
    first = _run(root, run_id="k1")
    assert first["loaded"] == 0, "nothing was persisted before the first run"

    second = _run(root, run_id="k2")
    assert second["loaded"] == first["snapshot_records_written"]
    assert second["compared"] <= second["loaded"]
    assert second["compared"] == second["loaded"], (
        "every persisted thesis was rebuilt, so every one should have been "
        "compared; a shortfall means an identity moved between cycles")
    assert second["identity_collisions"] == 0
    assert second["unmatched_prior"] == 0
    assert second["unmatched_current"] == 0


def test_an_unchanged_second_cycle_writes_no_revision(root):
    _run(root, run_id="k1")
    second = _run(root, run_id="k2")
    assert second["unchanged"] == second["compared"]
    assert second["written"] == 0, (
        "a revision per cycle per thesis buries the real movements")


def test_the_chain_is_reloaded_rather_than_rebuilt_empty(root):
    """A history built empty each night writes only first links, forever."""
    _run(root, run_id="k1")
    store = LS.LearningStore(root / LS.DEFAULT_PATH)
    written = store.thesis_revisions()
    assert written, "the first cycle wrote no revision at all"

    reloaded, dropped = TH.ThesisHistory.load(written)
    assert dropped == [], f"the cycle wrote rows it cannot read back: {dropped}"
    assert len(reloaded.chain_all()) == len(written)

    second = _run(root, run_id="k2")
    assert second["unreadable_prior_revisions"] == 0
    assert second["created"] == 0, (
        "the second cycle re-created theses it had already recorded, which "
        "means it did not recognise its own history")
    # THE COUNT THAT DISCRIMINATES. `written == 0` reads the same whether the
    # chain was reloaded and nothing moved, or the chain was never reloaded
    # at all. Only this one separates them.
    assert second["prior_revisions_on_disk"] == len(written)
    assert second["prior_revisions_loaded"] == len(written), (
        "the step reported no revisions in hand while the ledger held "
        f"{len(written)}; it is rebuilding the chain empty every night")


def test_a_collision_the_step_cannot_prevent_is_still_counted(root,
                                                              monkeypatch):
    """The counter must be able to report a number other than zero.

    A diagnostic asserted only against a fixture that cannot produce the
    fault is a test that cannot fail. Identity now makes a real collision
    hard to reach from the corpus, so one is injected: what is under test is
    the step's REPORTING, and the only way to see it report is to give it
    something to report.
    """
    from intent_engine.market import economic_thesis as ETH

    real_build_all = ETH.build_all

    def duplicating_build_all(transmissions, *, as_of):
        built = real_build_all(transmissions, as_of=as_of)
        return built + built[:1] if built else built

    monkeypatch.setattr(
        "intent_engine.market.economic_thesis.build_all",
        duplicating_build_all)

    got = _run(root)
    assert got["theses_sharing_an_identity"] == 1, (
        "the step built two theses the store cannot tell apart and reported "
        "no collision; that is exactly how eleven built became seven stored")
    assert got["snapshot_records_written"] < got["theses_built"]


#: Blocks of `knowledge_step` that must not report an error on a fixture
#: holding ordinary data. Each is wrapped in `except Exception` so that a
#: derived view cannot fail the cycle — correct, and it is also how a
#: `NameError` in the delayed-reward block survived every cycle it ever ran,
#: reported as `{"error": "name 'RD' is not defined"}` into a payload nothing
#: projected. A capability that had never once executed was marked COMPLETE.
_MUST_NOT_ERROR = (
    "thesis_history", "delayed_reward", "economic_thesis", "founder_v4",
    "macro_state", "company_exposure", "transmission", "economic_method",
)


def test_no_knowledge_block_reports_an_error_on_ordinary_data(root):
    """The guard that would have caught A-RD-009 never running.

    `except Exception` around a derived view is right — a projection must not
    be able to stop the cycle that produces the thing being projected. What
    is not right is nobody ever looking at what it caught.
    """
    payload = _payload(root)
    errored = {name: (payload.get(name) or {}).get("error")
               for name in _MUST_NOT_ERROR
               if isinstance(payload.get(name), dict)
               and (payload.get(name) or {}).get("error")}
    assert not errored, (
        "knowledge blocks failed silently and were swallowed into an error "
        f"string: {errored}")


def test_the_delayed_reward_block_actually_runs(root):
    """Its counts must be present, not merely absent-without-error."""
    got = _payload(root).get("delayed_reward") or {}
    assert "error" not in got, got["error"]
    for key in ("delayed_outcomes_written", "decisions_credited",
                "revisions_credited", "untraceable_revisions",
                "reward_delta_total"):
        assert key in got, (
            f"{key} missing; an operator cannot tell a delayed reward that "
            "credited a real decision from one that credited nobody")


def test_each_briefing_carries_its_own_economys_reason(root):
    """A sourced-looking sentence about the wrong country.

    `reasons` was keyed by state_kind alone, so CA:MARKET_RATE and
    US:MARKET_RATE collapsed to one entry and whichever state was read last
    supplied the reason for both briefings.
    """
    briefings = (_payload(root).get("founder_v4") or {}).get("briefings") or []
    by_area = {}
    for view in briefings:
        text = f"{view.get('what_changed', '')} {view.get('economic_context', '')}"
        for area in ("CA", "US"):
            if f"{area} 10-year yield" in text:
                by_area.setdefault(area, []).append(view)
    assert set(by_area) == {"CA", "US"}, (
        f"briefings cited these economies: {sorted(by_area)}; both should "
        "appear exactly once, each in its own briefing")
    assert all(len(v) == 1 for v in by_area.values()), (
        "one economy's reason was attached to more than one briefing")
