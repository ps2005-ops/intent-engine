"""Durable storage — the runtime-truth backend for the free-tier model.

WHY THIS EXISTS
---------------
The hosted operating model is: a Render FREE web service (UI only, sleeps),
GitHub Actions as the scheduled runner (a fresh, ephemeral runner every job),
and Alpaca PAPER for simulated execution. In that world there is NO durable
local filesystem — the Render disk is gone on the free plan and a GitHub
runner's disk vanishes when the job ends. So runtime truth CANNOT live in
committed repo files, a Render free filesystem, or a runner's scratch disk.

This package provides a single append-only, replayable record store that is
selected by `DATABASE_URL`:

    sqlite:///data/intent_engine.db     (default; local development)
    postgresql://user:pass@host/db      (hosted; durable across fresh runners)

It preserves the exact discipline the rest of the repo already uses — one row
per write, append-only, "latest wins" collapsing by (stream, record_id), each
record a JSON blob — just under a backend that survives ephemeral compute.

See `docs/FREE_TIER_RUNTIME.md` for the operating model and MANUAL ACTIONS.
"""
from __future__ import annotations

from intent_engine.storage.durable import (
    DurableRecord,
    DurableStore,
    IdempotencyConflict,
    resolve_database_url,
)

__all__ = [
    "DurableStore",
    "DurableRecord",
    "IdempotencyConflict",
    "resolve_database_url",
]
