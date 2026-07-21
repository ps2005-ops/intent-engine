"""T018 bars: store, identity, namespaces, folded state, terminal archival."""
import threading

import pytest

from intent_engine.core.decision_ids import is_ulid
from intent_engine.growth import (
    NAMESPACE_PRODUCTION, NAMESPACE_SYNTHETIC, GrowthError, GrowthService,
)
from intent_engine.growth.store import GrowthCorruptLogError, GrowthStore


@pytest.fixture()
def svc(tmp_path):
    return GrowthService(tmp_path, NAMESPACE_PRODUCTION)


def _draft(svc, **over):
    kw = dict(originating_decision_id=None, campaign_id=None)
    kw.update(over)
    return svc.draft_experiment("Method CTA test", **kw)


def test_ids_opaque_and_unique(svc):
    a, b = _draft(svc), _draft(svc)
    assert is_ulid(a) and is_ulid(b) and a != b
    assert svc.get_history(a)[0].payload["name"] == "Method CTA test"


def test_append_only_no_mutation_api(svc):
    _draft(svc)
    banned = [m for m in dir(svc.store)
              if any(w in m.lower() for w in ("update", "delete", "remove"))
              and not m.startswith("_")]
    assert banned == []


def test_idempotent_retry_and_conflict(svc):
    a = _draft(svc, idempotency_key="e1")
    b = _draft(svc, idempotency_key="e1")
    assert a == b and len(svc.store.read_all()) == 1
    with pytest.raises(ValueError, match="different content"):
        svc.draft_experiment("A different experiment", idempotency_key="e1")


def test_corrupt_log_fails_loudly(svc):
    _draft(svc)
    with open(svc.store.path, "a") as f:
        f.write("not json\n")
    with pytest.raises(GrowthCorruptLogError, match="malformed"):
        svc.store.read_all()


def test_namespaces_use_separate_files_and_never_mix(tmp_path):
    prod = GrowthService(tmp_path, NAMESPACE_PRODUCTION)
    synth = GrowthService(tmp_path, NAMESPACE_SYNTHETIC)
    p = prod.draft_experiment("production run")
    s = synth.draft_experiment("synthetic run")
    assert prod.store.path != synth.store.path
    assert [r.experiment_id for r in prod.store.read_all()] == [p]
    assert [r.experiment_id for r in synth.store.read_all()] == [s]
    # a production store can never read a synthetic experiment
    assert prod.store.for_experiment(s) == []
    with pytest.raises(KeyError):
        prod.get_history(s)


def test_cross_namespace_row_is_a_corruption_error(tmp_path):
    prod = GrowthService(tmp_path, NAMESPACE_PRODUCTION)
    p = prod.draft_experiment("production run")
    row = prod.store.read_all()[0]
    # hand-write a synthetic row into the production file
    import dataclasses, json
    tampered = dataclasses.asdict(row)
    tampered["namespace"] = NAMESPACE_SYNTHETIC
    with open(prod.store.path, "a") as f:
        f.write(json.dumps(tampered, sort_keys=True) + "\n")
    with pytest.raises(GrowthCorruptLogError, match="never mix"):
        prod.store.read_all()


def test_store_rejects_foreign_namespace_row(tmp_path):
    from intent_engine.growth.records import GrowthEvent
    from intent_engine.core.decision_ids import new_ulid
    store = GrowthStore(tmp_path, NAMESPACE_PRODUCTION)
    row = GrowthEvent(event_type="growth.experiment_drafted",
                      experiment_id=new_ulid(), namespace=NAMESPACE_SYNTHETIC,
                      actor_type="human", actor_id="founder", source="cli")
    with pytest.raises(GrowthError, match="does not match this store"):
        store.append(row)


def test_concurrent_writers_do_not_corrupt(svc):
    a = _draft(svc)
    errors = []

    def worker(n):
        try:
            for i in range(6):
                svc._record(a, "growth.exploratory_analysis_recorded",
                            actor_type="system", actor_id="agent",
                            payload={"analysis_class": "EXPLORATORY",
                                     "description": f"d{n}-{i}",
                                     "findings": "f", "may_drive_label": False},
                            idempotency_key=f"x-{n}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(svc.get_history(a)) == 19


def test_initial_state_folds(svc):
    a = _draft(svc)
    state = svc.get_state(a)
    assert state.registration_status == "drafted"
    assert state.lifecycle_status == "not_started"
    assert state.approved_version is None
    assert state.started is False and state.terminal is False


def test_tampered_history_fails_validated_fold(svc):
    from intent_engine.growth.records import GrowthEvent
    a = _draft(svc)
    svc.store.append(GrowthEvent(
        event_type="growth.experiment_started", experiment_id=a,
        namespace=NAMESPACE_PRODUCTION, actor_type="human",
        actor_id="tamper", source="cli"))
    with pytest.raises(GrowthError, match="invalid at"):
        svc.get_state(a)


def test_terminal_states_end_activity_without_deleting(svc):
    a = _draft(svc)
    svc.archive_experiment(a, "no longer relevant", actor_id="founder")
    state = svc.get_state(a)
    assert state.lifecycle_status == "archived" and state.terminal is True
    assert len(svc.get_history(a)) == 2          # history retained
    with pytest.raises(GrowthError, match="archived"):
        svc.define_hypothesis(a, "late", predicted_direction="increase",
                              rationale="r")


@pytest.mark.parametrize("method,status", [
    ("invalidate_experiment", "invalidated"),
    ("withdraw_experiment", "withdrawn"),
])
def test_other_terminal_states(svc, method, status):
    a = _draft(svc)
    getattr(svc, method)(a, "reason", actor_id="founder")
    assert svc.get_state(a).lifecycle_status == status
    assert svc.get_result(a)["label"] == status.upper()


def test_terminal_transitions_are_human_only(svc):
    a = _draft(svc)
    for method in ("archive_experiment", "invalidate_experiment",
                   "withdraw_experiment", "abandon_experiment"):
        with pytest.raises(GrowthError, match="human wall"):
            getattr(svc, method)(a, "r", actor_id="bot", actor_type="system")
