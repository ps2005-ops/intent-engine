"""T013 bars: consumer protocol, checkpoints, bounded retry, dead letters,
explicit redrive, replay. At-least-once delivery with idempotent-consumer
expectation, proven by tests that count deliveries."""
import pytest

from intent_engine.events import CheckpointError, CompanyEventBus, drain, redrive, replay


def _bus(tmp_path):
    return CompanyEventBus(tmp_path / "events")


def _pub(bus, i, event_type="prediction.recorded"):
    return bus.publish(event_type, subject_type="prediction",
                       subject_id=f"p-{i}", producer="premortem_pipeline",
                       actor_type="system", actor_id="premortem_pipeline",
                       source="system", idempotency_key=f"k-{i}").event


class Collector:
    consumer_name = "collector"

    def __init__(self, fail_ids=(), fail_times=0):
        self.seen = []
        self.fail_ids = set(fail_ids)
        self.fail_times = fail_times
        self.failures = {}

    def handles(self, event_type):
        return event_type == "prediction.recorded"

    def process(self, event):
        n = self.failures.get(event.event_id, 0)
        if event.event_id in self.fail_ids and n < self.fail_times:
            self.failures[event.event_id] = n + 1
            raise RuntimeError("transient boom")
        self.seen.append(event.event_id)


def test_success_advances_checkpoint(tmp_path):
    bus = _bus(tmp_path)
    evs = [_pub(bus, i) for i in range(3)]
    c = Collector()
    rep = drain(bus, c)
    assert rep.processed == 3
    assert c.seen == [e.event_id for e in evs]
    assert bus.store.get_checkpoint("collector") == 3
    # second drain: nothing redelivered
    rep2 = drain(bus, c)
    assert rep2.processed == 0 and len(c.seen) == 3


def test_failure_does_not_advance_checkpoint_and_restart_redelivers(tmp_path):
    bus = _bus(tmp_path)
    evs = [_pub(bus, i) for i in range(3)]
    c = Collector(fail_ids=[evs[1].event_id], fail_times=1)
    rep = drain(bus, c)
    assert rep.processed == 1                       # ev0 only
    assert rep.stopped_at_event_id == evs[1].event_id
    assert bus.store.get_checkpoint("collector") == 1   # NOT advanced past ev1
    # "restart": a new drain redelivers the failed event, which now succeeds
    rep2 = drain(bus, c)
    assert rep2.processed == 2                      # ev1 retried + ev2
    assert c.seen == [evs[0].event_id, evs[1].event_id, evs[2].event_id]


def test_checkpoints_are_independent_per_consumer(tmp_path):
    bus = _bus(tmp_path)
    for i in range(2):
        _pub(bus, i)
    a, b = Collector(), Collector()
    b.consumer_name = "collector_b"
    drain(bus, a)
    assert bus.store.get_checkpoint("collector") == 2
    assert bus.store.get_checkpoint("collector_b") == 0
    rep = drain(bus, b)
    assert rep.processed == 2                       # unaffected by a's state


def test_unhandled_event_types_are_skipped_safely(tmp_path):
    bus = _bus(tmp_path)
    _pub(bus, 0)
    bus.publish("report.generated", subject_type="report", subject_id="r-1",
                producer="report_renderer", actor_type="system",
                actor_id="report_renderer", source="system",
                idempotency_key="rep-1")
    _pub(bus, 1)
    c = Collector()
    rep = drain(bus, c)
    assert rep.processed == 2 and rep.skipped == 1
    assert bus.store.get_checkpoint("collector") == 3   # skip still advances


def test_checkpoint_corruption_fails_loudly(tmp_path):
    bus = _bus(tmp_path)
    _pub(bus, 0)
    bus.store.checkpoint_path.write_text("{broken")
    with pytest.raises(CheckpointError, match="unreadable"):
        drain(bus, Collector())


def test_transient_failure_succeeds_on_retry_before_limit(tmp_path):
    bus = _bus(tmp_path)
    ev = _pub(bus, 0)
    c = Collector(fail_ids=[ev.event_id], fail_times=2)
    assert drain(bus, c, max_attempts=3).retried == 1     # attempt 1 fails
    assert drain(bus, c, max_attempts=3).retried == 1     # attempt 2 fails
    rep = drain(bus, c, max_attempts=3)                   # attempt 3 succeeds
    assert rep.processed == 1
    assert bus.store.read_dead_letters() == []            # never dead-lettered
    assert bus.store.get_checkpoint("collector") == 1


def test_permanent_failure_dead_letters_at_bounded_limit(tmp_path):
    bus = _bus(tmp_path)
    ev = _pub(bus, 0)
    after = _pub(bus, 1)
    c = Collector(fail_ids=[ev.event_id], fail_times=99)  # always fails
    drain(bus, c, max_attempts=3)
    drain(bus, c, max_attempts=3)
    rep = drain(bus, c, max_attempts=3)                   # third attempt -> DLQ
    assert rep.dead_lettered == 1
    assert rep.processed == 1                             # stream continues
    dls = bus.store.read_dead_letters()
    assert len(dls) == 1
    assert dls[0]["original_event_id"] == ev.event_id
    assert dls[0]["attempt_count"] == 3
    assert dls[0]["error_type"] == "RuntimeError"
    assert "resolve_by" not in dls[0].get("error_message", "")  # no payload
    # the main log is untouched by the failure
    assert [e.event_id for e in bus.store.read_all()] == [ev.event_id,
                                                          after.event_id]


def test_redrive_succeeds_once_and_is_idempotent(tmp_path):
    bus = _bus(tmp_path)
    ev = _pub(bus, 0)
    c = Collector(fail_ids=[ev.event_id], fail_times=3)   # fails 3, then ok
    for _ in range(3):
        drain(bus, c, max_attempts=3)
    assert len(bus.store.read_dead_letters()) == 1
    assert redrive(bus, c, ev.event_id) == "succeeded"
    assert c.seen == [ev.event_id]
    # history preserved: original failure row + a NEW success row
    dls = bus.store.read_dead_letters()
    assert [d["redrive_status"] for d in dls] == ["pending", "succeeded"]
    # idempotent: second redrive is a no-op, no duplicate side effect
    assert redrive(bus, c, ev.event_id) == "already_redriven"
    assert c.seen == [ev.event_id]


def test_replay_redelivers_without_republishing(tmp_path):
    bus = _bus(tmp_path)
    for i in range(3):
        _pub(bus, i)
    c = Collector()
    drain(bus, c)
    n_lines = bus.store.log_path.read_text().count("\n")
    rep = replay(bus, c, from_offset=0)
    assert rep.processed == 3                        # redelivered...
    assert bus.store.log_path.read_text().count("\n") == n_lines  # ...0 new
    assert bus.store.get_checkpoint("collector") == 3  # checkpoint untouched


def test_replay_dry_run_and_bounded_range(tmp_path):
    bus = _bus(tmp_path)
    evs = [_pub(bus, i) for i in range(4)]
    c = Collector()
    rep = replay(bus, c, from_offset=1, to_offset=3, dry_run=True)
    assert rep.dry_run_events == [evs[1].event_id, evs[2].event_id]
    assert c.seen == []                              # dry run processed nothing


def test_explicit_rewind_flag_moves_checkpoint(tmp_path):
    bus = _bus(tmp_path)
    for i in range(2):
        _pub(bus, i)
    c = Collector()
    drain(bus, c)
    assert bus.store.get_checkpoint("collector") == 2
    rep = replay(bus, c, from_offset=0, rewind_checkpoint=True)
    assert rep.processed == 2                        # deliberately re-run
    assert len(c.seen) == 4                          # at-least-once, explicit
