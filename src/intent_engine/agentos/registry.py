"""The canonical agent registry (T022).

The declared list of production agents, in one place. This is the only
part of AgentOS the T022 brief authorizes as genuinely new — and it is
pure metadata, not behaviour: a frozen description of the three agents
that already exist, so a future layer discovers them here rather than by
grepping `src/`.

The registry knows the SHAPE of each agent (name, contract, store,
indexes, checkpoint, posture, what it reads and its permissions) and
nothing of their logic. It imports no domain module — every field is a
string or a tuple of strings — so the kernel stays free of research,
product, and executive code.

Every agent registered here is propose/recommend-only and holds no
autonomous authority; `assert_no_autonomous_authority` is applied to each
at import so the posture cannot silently weaken.
"""
from __future__ import annotations

from intent_engine.agentos.agent import AgentDescriptor
from intent_engine.agentos.permissions import (
    MODEL, READ, WRITE, AgentPermissions, assert_no_autonomous_authority,
)

RESEARCH = AgentDescriptor(
    name="research", task="T019",
    contract_module="intent_engine.research.records",
    store_path="data/research.jsonl",
    indexes=("evidence_index",),
    checkpoint="research", posture="propose_only",
    reads=("company_events",),
    note="the first agent; the Evidence Index is the shared evidence "
         "substrate T020-T021 read")

PRODUCT = AgentDescriptor(
    name="product", task="T020",
    contract_module="intent_engine.product.records",
    store_path="data/product.jsonl",
    indexes=("problem_index", "opportunity_index"),
    checkpoint="product", posture="propose_only",
    reads=("research", "growth", "crm", "analytics", "knowledge",
           "decisions"),
    note="owns proposals, never decisions; never writes ROADMAP.md")

EXECUTIVE = AgentDescriptor(
    name="executive", task="T021",
    contract_module="intent_engine.executive.records",
    store_path="data/executive.jsonl",
    indexes=("decision_index",),
    checkpoint="executive", posture="recommend_only",
    reads=("decisions", "predictions", "research", "product", "growth",
           "crm", "analytics", "knowledge"),
    note="owns decision candidates, never decisions; resolves decision "
         "state through DecisionService and mirrors nothing")

PRODUCTION_AGENTS = (RESEARCH, PRODUCT, EXECUTIVE)

# Permissions per agent — metadata, recording the posture each already
# enforces in its own walls.
PERMISSIONS = {
    "research": AgentPermissions(
        agent="research", capabilities=frozenset({READ, WRITE, MODEL}),
        writes_store="data/research.jsonl",
        human_only_transitions=("research.plan_approved",
                                "research.plan_rejected", "research.reviewed",
                                "research.source_retired")),
    "product": AgentPermissions(
        agent="product", capabilities=frozenset({READ, WRITE, MODEL}),
        writes_store="data/product.jsonl",
        human_only_transitions=("product.reviewed", "product.decision_linked",
                                "product.execution_candidate_marked",
                                "product.theme_declared",
                                "product.alignment_declared")),
    "executive": AgentPermissions(
        agent="executive", capabilities=frozenset({READ, WRITE, MODEL}),
        writes_store="data/executive.jsonl",
        human_only_transitions=("executive.reviewed",
                                "executive.override_recorded",
                                "executive.decision_linked",
                                "executive.alignment_declared",
                                "executive.budget_declared")),
}

# The posture cannot silently weaken: applied at import.
for _perms in PERMISSIONS.values():
    assert_no_autonomous_authority(_perms)


def list_agents() -> list:
    """Every production agent, as plain dicts, in registration order."""
    return [a.as_dict() for a in PRODUCTION_AGENTS]


def get_agent(name: str) -> AgentDescriptor:
    for agent in PRODUCTION_AGENTS:
        if agent.name == name:
            return agent
    raise KeyError(f"no such agent: {name!r} — registered: "
                   f"{[a.name for a in PRODUCTION_AGENTS]}")


def get_permissions(name: str) -> AgentPermissions:
    if name not in PERMISSIONS:
        raise KeyError(f"no permissions registered for agent: {name!r}")
    return PERMISSIONS[name]
