"""The shared agent contracts (T022) — as structural protocols.

These are `typing.Protocol` definitions: they describe the shape every
production agent already implements, WITHOUT forcing inheritance and
WITHOUT changing a single line of behaviour. An agent class satisfies a
protocol by having the right methods, which the three already do — the
conformance test proves it.

Why protocols rather than base classes: the point of T022 is extraction,
not redesign. Making the three agents inherit from a kernel base would
change their MRO and risk behaviour drift. A protocol records the contract
that already holds and lets a test enforce it, at zero behavioural cost.

What is deliberately a CONTRACT here rather than an extracted
implementation, and why:

  * **Index** — the Evidence, Problem, Opportunity, and Decision Indexes
    share the shape `build_index(rows) / assert_invariants() / lineage()`
    but nothing of their content. Each is domain-specific and correctly
    local; unifying the implementations would be inventing an abstraction
    over four different memories. So the shape is a protocol; the code
    stays in the agents.
  * **Consumer** and **Replayable** — the drain / replay / checkpoint
    framework already lives in `events/consumer.py` (T013) and is already
    shared. There is nothing to extract; the per-agent consumers are thin
    adapters implementing `consumer_name / handles / process`. The
    protocol records that adapter shape.
  * **Snapshot** — the three snapshot modules share the envelope
    (snapshot_id, versions, as_of, source high watermarks, reproducible
    from the log) but not the payload. The protocol records the envelope;
    the payloads stay local, exactly as the T022 brief requires.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentEvent(Protocol):
    """The event every append-only store persists."""
    idempotency_key: str | None
    subject_id: str | None

    def validate(self) -> None: ...
    def to_json(self) -> str: ...
    def content_fingerprint(self) -> str: ...


@runtime_checkable
class AgentStore(Protocol):
    """The append-only store contract — now implemented once, in
    `agentos.append_only.AppendOnlyStore`, and subclassed by each agent."""

    def read_all(self) -> list: ...
    def find_by_idempotency_key(self, key: str): ...
    def append(self, row): ...


@runtime_checkable
class Index(Protocol):
    """A canonical agent memory: reproducible from append-only rows,
    never model-written, orphan-rejecting, lineage-answering.

    The four production indexes (Evidence, Problem, Opportunity, Decision)
    each satisfy this shape. The kernel owns the CONTRACT, never the
    implementations — those are domain memories and stay in their agents.
    """

    def assert_invariants(self) -> dict: ...


@runtime_checkable
class Consumer(Protocol):
    """A company-event consumer. The drain/replay/checkpoint machinery is
    already shared in `events/consumer.py`; this records the adapter shape
    the three agents implement."""
    consumer_name: str

    def handles(self, event_type: str) -> bool: ...
    def process(self, event) -> None: ...


@runtime_checkable
class Snapshot(Protocol):
    """The frozen, reproducible snapshot envelope. Payloads stay local;
    the envelope shape is shared."""
    # A snapshot is a dict in every agent; the protocol documents the keys
    # the kernel and the diff report treat as the shared envelope.


SNAPSHOT_ENVELOPE_KEYS = ("as_of", "computed_at", "versions",
                          "source_high_watermarks")


@runtime_checkable
class Replayable(Protocol):
    """Anything that rebuilds a derived artifact from the append-only log
    alone — every index, and every snapshot's reproducibility note."""

    def read_all(self) -> list: ...


def conforms(obj, protocol) -> bool:
    """A small helper the conformance test uses, so the assertion reads as
    intent rather than isinstance plumbing."""
    return isinstance(obj, protocol)
