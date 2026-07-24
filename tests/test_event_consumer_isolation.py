"""Integration guarantee: the new runtime event types (job.*,
prediction.resolved, config.preflight_failed, synthetic.run_completed,
content.publish_dry_run, marketing.performance_ingested) flow on the SAME
company bus as the existing domain consumers. Those consumers must SKIP them
(not process, not dead-letter), because each whitelists its own types.

This locks that guarantee so a future consumer that switches to a
process-everything model is caught by a failing test rather than silently
dead-lettering runtime events in production.
"""
from intent_engine.events import CompanyEventBus, drain

NEW_RUNTIME_TYPES = [
    ("job.started", "job", "scheduler"),
    ("job.succeeded", "job", "scheduler"),
    ("job.failed", "job", "scheduler"),
    ("config.preflight_failed", "job", "config_preflight"),
    ("prediction.resolved", "prediction", "resolution_job"),
    ("synthetic.run_completed", "synthetic_run", "synthetic_runner"),
    ("marketing.performance_ingested", "campaign", "marketing_performance"),
]


def _seed_new_events(bus):
    for etype, subject_type, producer in NEW_RUNTIME_TYPES:
        bus.publish(etype, subject_type=subject_type, subject_id="s1",
                    producer=producer, actor_type="system", actor_id="t",
                    source="system", payload={})


class _StubService:
    def __getattr__(self, _name):
        def _noop(*a, **k):
            return None
        return _noop


def _all_real_consumers(tmp_path):
    """Instantiate each domain consumer with its real constructor shape."""
    from intent_engine.marketing.consumer import MarketingCompanyEventConsumer
    from intent_engine.crm.consumer import CRMCompanyEventConsumer
    return [
        MarketingCompanyEventConsumer(drafts_root=tmp_path / "drafts"),
        CRMCompanyEventConsumer(_StubService()),
    ]


def test_new_runtime_events_are_skipped_not_dead_lettered(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    _seed_new_events(bus)
    consumers = _all_real_consumers(tmp_path)
    for consumer in consumers:
        report = drain(bus, consumer)
        assert report.dead_lettered == 0, (
            f"{consumer.consumer_name} dead-lettered a runtime event")
        for etype, _, _ in NEW_RUNTIME_TYPES:
            assert not consumer.handles(etype), (
                f"{consumer.consumer_name} unexpectedly handles {etype}")


def test_no_domain_consumer_handles_everything(tmp_path):
    """A consumer that handles() everything would process (and could
    dead-letter) unrelated runtime events. Guard against that regression."""
    for consumer in _all_real_consumers(tmp_path):
        assert consumer.handles("job.failed") is False
        assert consumer.handles("prediction.resolved") is False
