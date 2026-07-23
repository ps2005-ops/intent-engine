"""Shared permissions (T022) — pure metadata, no new enforcement.

The capability vocabulary the three agents already embody, written down so
a future layer (T023 Personal AI, T024 public APIs) can reason about what
an agent may do without re-deriving it. This module ENFORCES nothing
beyond what the agents already enforce in their own walls — it records the
posture, it does not add a gate.

The five capabilities:

    READ        may read another subsystem's public surface
    WRITE       may append to its OWN store (never another's)
    MODEL       may call a model, behind the shared boundary, for prose
    PUBLISH     may publish a company event (via the shared bus)
    HUMAN_ONLY  the transitions only a person may make (approve, review,
                accept, reject, link a Decision Record, declare strategy)

Every production agent has READ + WRITE + MODEL. None has autonomous
authority: none may execute, promote, schedule, or decide. That posture is
recorded here, not invented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

READ = "read"
WRITE = "write"
MODEL = "model"
PUBLISH = "publish"
HUMAN_ONLY = "human_only"
CAPABILITIES = (READ, WRITE, MODEL, PUBLISH, HUMAN_ONLY)


@dataclass(frozen=True)
class AgentPermissions:
    agent: str
    capabilities: frozenset
    human_only_transitions: tuple = ()   # events only a person may emit
    writes_store: str = ""               # the ONE store it may write
    never: tuple = ("execute", "promote", "schedule", "decide",
                    "ticket", "write_other_store")

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def as_dict(self) -> dict:
        return {"agent": self.agent,
                "capabilities": sorted(self.capabilities),
                "human_only_transitions": list(self.human_only_transitions),
                "writes_store": self.writes_store,
                "never": list(self.never)}


def assert_no_autonomous_authority(perms: AgentPermissions) -> None:
    """A standing check: no production agent may hold a capability that
    lets it act without a human. The kernel records the posture; this makes
    a violation loud if a future agent tries to weaken it."""
    forbidden = {"execute", "decide", "promote", "schedule"}
    granted = {c.lower() for c in perms.capabilities}
    overlap = forbidden & granted
    if overlap:
        raise ValueError(
            f"agent {perms.agent!r} claims autonomous capabilities "
            f"{sorted(overlap)} — no production agent may act without a human")
