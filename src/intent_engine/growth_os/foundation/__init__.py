"""Shared foundation for every Growth-OS intelligence module.

One enforced envelope so provenance, confidence, timestamps, replay and learning
are structural — not per-module discipline that can drift. Mirrors the
marketing/CRM/knowledge store discipline (append-only JSONL, flock,
fsync-before-success, fingerprint idempotency, deterministic folds).
"""
from intent_engine.growth_os.foundation.records import (  # noqa: F401
    ACTOR_TYPES,
    PROVENANCE_METHODS,
    Confidence,
    GrowthOSError,
    IntelRecord,
    LearningCandidate,
    Provenance,
)
from intent_engine.growth_os.foundation.store import IntelStore  # noqa: F401

__all__ = [
    "ACTOR_TYPES", "PROVENANCE_METHODS", "Confidence", "GrowthOSError",
    "IntelRecord", "LearningCandidate", "Provenance", "IntelStore",
]
