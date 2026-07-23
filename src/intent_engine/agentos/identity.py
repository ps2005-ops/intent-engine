"""Shared stable identity (T022).

Extracted from the `_stable_id(key)` method that appeared, byte-identical,
in all three agent services: mint a new ULID for a fresh idempotency key,
or return the id already recorded against that key on a retry — so a
retried write keeps the SAME id.

The ULID allocator itself already lived in `core/decision_ids`; this only
lifts the store-lookup wrapper the three agents shared, and re-exports the
allocator so an agent has one import for identity.
"""
from __future__ import annotations

from intent_engine.core.decision_ids import is_ulid, new_ulid  # noqa: F401


def stable_id(store, key: str) -> str:
    """The id already recorded against `key`, or a fresh ULID.

    `store` is any AppendOnlyStore; the row it returns exposes
    `subject_id`, as every agent event does.
    """
    existing = store.find_by_idempotency_key(key)
    return existing.subject_id if existing is not None else new_ulid()
