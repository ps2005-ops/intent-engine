"""The router — the conductor's switchboard (T023).

Routing is **closed-taxonomy and deterministic.** A founder request is
classified into one of a small, fixed set of intents by an explicit
command or a tested phrase matcher — never by a model, and never by an
open-ended planner. An unrecognized request returns the supported
capabilities and an honest unsupported result. There is no general-purpose
planner here; building one would turn T023 into a speculative autonomous
agent, which it is not.

"Routes through the kernel" means: the router resolves which agent owns a
capability through the **AgentOS registry** (the declared list of
production agents), and invokes that agent's public read surface through
an **adapter owned by `personal/`**. AgentOS is read-only infrastructure —
it is not a message broker or a domain orchestrator, and this router does
not turn it into one. No agent ever calls another; every hop is the
workspace reading an adapter.
"""
from __future__ import annotations

import re

from intent_engine.agentos.registry import list_agents
from intent_engine.personal.records import PersonalError

ROUTING_VERSION = "personal_routing.v1"

# --- the closed intent taxonomy ---------------------------------------------
EXPLAIN_FINDING = "EXPLAIN_FINDING"
SHOW_EVIDENCE = "SHOW_EVIDENCE"
TRACE_DECISION = "TRACE_DECISION"
SUMMARIZE_COMPETITORS = "SUMMARIZE_COMPETITORS"
CHALLENGE_ASSUMPTION = "CHALLENGE_ASSUMPTION"
LIST_INVESTIGATIONS = "LIST_INVESTIGATIONS"
DRAFT_BOARD_UPDATE = "DRAFT_BOARD_UPDATE"
DRAFT_INVESTOR_EXPLANATION = "DRAFT_INVESTOR_EXPLANATION"
MORNING_BRIEF = "MORNING_BRIEF"
UNKNOWN = "UNKNOWN"

INTENTS = (EXPLAIN_FINDING, SHOW_EVIDENCE, TRACE_DECISION,
           SUMMARIZE_COMPETITORS, CHALLENGE_ASSUMPTION, LIST_INVESTIGATIONS,
           DRAFT_BOARD_UPDATE, DRAFT_INVESTOR_EXPLANATION, MORNING_BRIEF,
           UNKNOWN)

# Which subsystems an intent draws on. Read straight through the registry
# so the router never hard-codes an agent that is not registered.
INTENT_SUBSYSTEMS = {
    EXPLAIN_FINDING: ("executive", "research"),
    SHOW_EVIDENCE: ("research", "executive"),
    TRACE_DECISION: ("executive", "decisions"),
    SUMMARIZE_COMPETITORS: (),          # dependency gap 1 — no owner
    CHALLENGE_ASSUMPTION: ("research", "executive"),
    LIST_INVESTIGATIONS: ("research", "executive"),
    DRAFT_BOARD_UPDATE: ("executive", "product", "research"),
    DRAFT_INVESTOR_EXPLANATION: ("executive", "product", "research"),
    MORNING_BRIEF: ("research", "executive", "product"),
}

# A tested phrase matcher — deterministic, order-stable. First match wins.
_PATTERNS = (
    (MORNING_BRIEF, (r"\bmorning brief\b", r"what.?s changed",
                     r"what has changed", r"good morning")),
    (TRACE_DECISION, (r"why is this (decision|in my queue)",
                      r"why.*in my queue", r"trace .*decision")),
    (SHOW_EVIDENCE, (r"show (me )?(the )?evidence", r"what.?s the evidence")),
    (EXPLAIN_FINDING, (r"why are we", r"explain (this|why)",
                       r"what do we (know|believe)")),
    (SUMMARIZE_COMPETITORS, (r"competitor", r"competition")),
    (CHALLENGE_ASSUMPTION, (r"challenge (this )?assumption",
                            r"push back on", r"is this assumption")),
    (LIST_INVESTIGATIONS, (r"what should i investigate",
                           r"investigat", r"what.?s worth looking into")),
    (DRAFT_BOARD_UPDATE, (r"board update", r"board report", r"draft.*board")),
    (DRAFT_INVESTOR_EXPLANATION, (r"investor", r"explain.*to an investor")),
)


def classify(text: str) -> str:
    """Deterministic phrase match into the closed taxonomy. No model."""
    lowered = " ".join((text or "").lower().split())
    for intent, patterns in _PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return intent
    return UNKNOWN


def resolve_subsystems(intent: str) -> dict:
    """Resolve an intent to the registered agents that can serve it.

    Returns which required subsystems are registered and which are missing,
    so the caller can degrade honestly rather than guess. This is the
    'routes through the registry' step, made explicit.
    """
    if intent not in INTENTS:
        raise PersonalError(f"unknown intent: {intent!r}")
    registered = {a["name"] for a in list_agents()}
    # the registry lists the three agents; other subsystems (crm, analytics,
    # knowledge, decisions) are read directly and are not agent-registered,
    # so they are treated as always-resolvable-if-connected.
    required = INTENT_SUBSYSTEMS.get(intent, ())
    agent_required = tuple(s for s in required
                           if s in {"research", "product", "executive"})
    missing = tuple(s for s in agent_required if s not in registered)
    return {"intent": intent, "required": list(required),
            "agent_registered": sorted(registered & set(agent_required)),
            "missing_agents": list(missing),
            "routing_version": ROUTING_VERSION}


def supported_capabilities() -> list:
    """What an UNKNOWN request is answered with — the closed list, honest."""
    return [i for i in INTENTS if i != UNKNOWN]
