"""The agent descriptor (T022).

A small, frozen record of what a production agent IS, from the kernel's
point of view: its name, the store it writes, the indexes it owns, the
company-event checkpoint it consumes under, and its posture (propose-only
/ recommend-only — the agent never decides or executes).

This is metadata, not behaviour. It carries no logic; it lets the registry
list the agents and the permissions module attach capabilities without the
kernel importing any domain module.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentDescriptor:
    name: str                       # "research" | "product" | "executive"
    task: str                       # "T019" ...
    contract_module: str            # dotted path to the canonical contract
    store_path: str                 # the append-only log it writes
    indexes: tuple = ()             # the canonical memories it owns
    checkpoint: str | None = None   # its company-event consumer checkpoint
    posture: str = "propose_only"   # never decides, never executes
    reads: tuple = ()               # subsystems it reads (by name)
    note: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "task": self.task,
                "contract_module": self.contract_module,
                "store_path": self.store_path, "indexes": list(self.indexes),
                "checkpoint": self.checkpoint, "posture": self.posture,
                "reads": list(self.reads), "note": self.note}
