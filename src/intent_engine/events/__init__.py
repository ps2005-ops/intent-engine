"""Company Event System (T013) — the integration backbone.

Boundary (load-bearing, per docs/COMPANY_OS.md Part 3 and the accepted
T013 bars):

    DecisionEvent store   = the AUTHORITATIVE domain event history for one
                            Decision Record (core/decision_record.py).
    Company Event System  = an append-only integration log used to notify
                            and coordinate independent consumers.

Decision state is folded from DecisionEvents, never inferred from company
events. The log coordinates systems; it does not replace their
authoritative stores. Stdlib only (A3): the bus is `events.jsonl` drained
synchronously — swappable for a broker later without touching producers or
consumers, because both only know the envelope contract in
`envelope.py` (the ONE canonical event contract; docs cross-reference it).
"""
from intent_engine.events.envelope import (  # noqa: F401
    COMPANY_EVENT_SCHEMA_VERSION, EVENT_PRODUCERS, EVENT_TYPES, CompanyEvent,
    EnvelopeError,
)
from intent_engine.events.store import (  # noqa: F401
    CheckpointError, CorruptLogError, EventStore,
)
from intent_engine.events.publisher import (  # noqa: F401
    CompanyEventBus, PublishResult, WallViolation,
)
from intent_engine.events.consumer import (  # noqa: F401
    DrainReport, EventConsumer, drain, redrive, replay,
)
from intent_engine.events.decision_bridge import (  # noqa: F401
    BRIDGED_EVENT_TYPES, SKIPPED_EVENT_TYPES, bridge_decision_events,
)
