"""The step that makes four built subsystems actually run.

`belief_maturity`, `knowledge_decay`, `value_of_information` and
`causal_episodes` were each built and tested, and no operating cycle called
any of them. These tests exist so that cannot silently become true again:
the registration itself is asserted, not just the functions behind it.
"""
from __future__ import annotations

import json
import pathlib
import shutil

from intent_engine.market import cycle as C
from intent_engine.market import knowledge_decay as KD
from intent_engine.market import learning_store as LS
from intent_engine.market import steps as S

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")

VIEWS = ("belief_maturity", "knowledge_decay", "value_of_information",
         "causal_episodes")


def context(root, *, dry_run=True, as_of="2026-08-07"):
    return C.CycleContext(cycle="night", as_of=as_of,
                          root=pathlib.Path(root), session=None,
                          run_id="test", dry_run=dry_run)


def test_the_step_is_registered_in_both_cycles():
    for build in (S.day_steps, S.night_steps):
        names = [name for name, _ in build()]
        assert "knowledge" in names, f"{build.__name__} never runs it"
        # After learning, so it sees this session's reconciliations, and
        # before health, so health can read what it derived.
        assert names.index("learning") < names.index("knowledge")
        assert names.index("knowledge") < names.index("learning_health")


def test_every_view_is_produced_on_an_empty_root(tmp_path):
    got = S.knowledge_step(context(tmp_path))
    assert set(VIEWS) <= set(got)
    assert all("error" not in got[v] for v in VIEWS)
    assert got["knowledge_decay"]["beliefs"] == 0


def test_a_broken_view_does_not_take_down_the_others(tmp_path, monkeypatch):
    from intent_engine.market import value_of_information as VOI

    def boom(*a, **k):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(VOI, "from_state", boom)
    got = S.knowledge_step(context(tmp_path))
    assert got["value_of_information"]["error"] == "deliberate"
    assert "error" not in got["belief_maturity"]


def test_decay_events_are_written_once_and_only_when_not_dry(tmp_path):
    store = LS.LearningStore(tmp_path / LS.DEFAULT_PATH)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"record": "belief", "belief_id": "b1", "subject": "acme",
         "proposition": "acme is doing the thing", "last_updated": "2025-09-01",
         "last_validated": "", "review_interval_days": 120,
         "decay_eligible": True, "lifecycle_state": "ACTIVE"},
        {"record": "expectation", "expectation_id": "e1",
         "hypothesis_id": "b1", "subject": "acme",
         "evaluation_window_ends": "2025-11-01",
         "metric": "demand_strengthening", "expected_event": "revenue"},
    ]
    store.path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    dry = S.knowledge_step(context(tmp_path, dry_run=True, as_of="2026-01-01"))
    assert dry["knowledge_decay"]["stale"] == 1
    assert dry["knowledge_decay"]["events_written"] == 0
    assert store.lifecycle_events() == ()

    wet = S.knowledge_step(context(tmp_path, dry_run=False,
                                   as_of="2026-01-01"))
    assert wet["knowledge_decay"]["events_written"] == 1
    assert [e["event"] for e in store.lifecycle_events()] == [KD.STALE]

    # Running again is not a second transition.
    again = S.knowledge_step(context(tmp_path, dry_run=False,
                                     as_of="2026-01-01"))
    assert again["knowledge_decay"]["events_written"] == 0
    assert len(store.lifecycle_events()) == 1


def test_a_lifecycle_event_never_edits_the_belief_row(tmp_path):
    store = LS.LearningStore(tmp_path / LS.DEFAULT_PATH)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    belief = {"record": "belief", "belief_id": "b1", "subject": "acme",
              "proposition": "p", "last_updated": "2025-09-01",
              "last_validated": "", "review_interval_days": 120,
              "decay_eligible": True, "lifecycle_state": "ACTIVE"}
    exp = {"record": "expectation", "expectation_id": "e1",
           "hypothesis_id": "b1", "subject": "acme",
           "evaluation_window_ends": "2025-11-01",
           "metric": "demand_strengthening", "expected_event": "revenue"}
    store.path.write_text(json.dumps(belief) + "\n" + json.dumps(exp) + "\n")

    S.knowledge_step(context(tmp_path, dry_run=False, as_of="2026-01-01"))
    lines = store.path.read_text().splitlines()
    assert json.loads(lines[0]) == belief          # byte-for-byte untouched
    assert json.loads(lines[-1])["record"] == LS.LIFECYCLE


def test_against_the_real_ledger(tmp_path):
    """The whole point: these numbers come from production's own ledger."""
    if not REAL_LEDGER.exists():                    # pragma: no cover
        return
    target = tmp_path / "reports" / "market"
    target.mkdir(parents=True)
    shutil.copy(REAL_LEDGER, target / "learning_ledger.jsonl")

    got = S.knowledge_step(context(tmp_path))
    decay = got["knowledge_decay"]
    assert decay["beliefs"] == 51
    assert decay["stale"] == 0 and decay["retired"] == 0
    # Three genuinely different refresh cadences are in play, which is the
    # measured reason a single global threshold would be wrong.
    assert set(decay["cadences_in_use"]) == {120, 180, 365}
    assert decay["not_eligible_because"]["TESTED"] == 5

    assert got["causal_episodes"]["episodes"] == 5
    assert got["causal_episodes"]["by_outcome"]["CONTRADICTED"] == 2
    assert got["value_of_information"]["by_priority"]["VOI_HIGH"] == 2
    assert got["belief_maturity"]["beliefs"] == 51
