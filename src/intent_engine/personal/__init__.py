"""Personal AI Workspace (T023) — the first founder-facing product.

The workspace is a **conductor, not an analyst.** It owns conversation,
context, memory, and orchestration, and **zero business intelligence.**
Every fact it presents came from an existing agent; it never computes a
score, a readiness, a conflict, a stance, or a metric. It asks the
appropriate agent (through a read adapter it owns), composes the answers
into one narrative, and cites every claim to its source artifact and a
replay id.

    Domain artifact -> SourceRef -> SourceClaim -> composition ->
        optional model wording (over a closed ClaimSet) ->
        deterministic claim validation -> cited answer

It may summarize, prioritize (only by preserving an owner's ordering),
explain, organize, and DRAFT. It may not publish, email, modify business
state, or execute anything — those are V2.5, behind a human gate.

Built on the AgentOS kernel (T022): the store subclasses `AppendOnlyStore`,
the language wall and model boundary are the kernel's. It reuses the three
agent indexes rather than building a fourth memory.

Canonical workspace contract: `records.py`.
"""
from intent_engine.personal.records import (  # noqa: F401
    AVAILABILITY_STATES, FRESHNESS_STATES, MEMORY_CLASSES, PersonalError,
    PersonalEvent, SecretRejected, SourceClaim, SourceRef, freshness_of,
    scan_banned_language,
)
from intent_engine.personal.store import (  # noqa: F401
    DEFAULT_PERSONAL_PATH, PersonalCorruptLogError, PersonalStore,
)
from intent_engine.personal.state import (  # noqa: F401
    WorkspaceState, fold_personal,
)
from intent_engine.personal.router import (  # noqa: F401
    INTENTS, classify, resolve_subsystems, supported_capabilities,
)
