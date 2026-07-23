"""AgentOS — the shared kernel (T022).

AgentOS is **not another agent**. It is the infrastructure three
production agents — Research (T019), Product (T020), and Executive
(T021) — were already reimplementing in parallel, extracted once.

The governing rule of this package: **three implementations first,
abstraction second.** Nothing lives here that did not already exist,
byte-for-byte, in all three agents. Anything that appeared in only one or
two of them stayed where it belonged.

AgentOS owns:

    append-only store mechanics   the flock/fsync/idempotency/parse-cache
                                  discipline every store repeated
    stable identity               the `_stable_id(key)` helper
    the language wall             the word-boundary + phrase scanner
    the model boundary            the provenance shape and the recursive
                                  forbidden-field scan
    the shared contracts          Store / Index / Consumer / Snapshot /
                                  Replayable, as structural protocols
    the agent registry            the declared list of production agents
    permissions                   the capability vocabulary (metadata)
    telemetry + budgeting         read-only derivations over any store

AgentOS owns **nothing domain-specific**. It does not know research,
product, growth, CRM, decisions, or knowledge. Scoring, readiness,
conflicts, debt, portfolios, and every graph stay in their agents forever
— extracting them would be inventing a shared abstraction where none
exists, which is the failure this session refuses.
"""
from intent_engine.agentos.append_only import (  # noqa: F401
    AppendOnlyStore, CorruptLogError,
)
from intent_engine.agentos.identity import stable_id  # noqa: F401
from intent_engine.agentos.language_wall import (  # noqa: F401
    scan_banned_language, word_boundary_hit,
)
from intent_engine.agentos.model_boundary import (  # noqa: F401
    find_forbidden_fields, model_provenance,
)
from intent_engine.agentos.contracts import (  # noqa: F401
    AgentStore, Consumer, Index, Replayable, Snapshot,
)
from intent_engine.agentos.permissions import (  # noqa: F401
    CAPABILITIES, AgentPermissions,
)
from intent_engine.agentos.telemetry import store_telemetry  # noqa: F401
from intent_engine.agentos.budgeting import model_budget  # noqa: F401
from intent_engine.agentos.agent import AgentDescriptor  # noqa: F401
from intent_engine.agentos.registry import (  # noqa: F401
    PRODUCTION_AGENTS, get_agent, list_agents,
)
