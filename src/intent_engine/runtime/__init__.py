"""Runtime operations layer — the deployable seam.

This package turns the platform's learning primitives (learning/, paper/,
core/prediction_ledger, simulator/) into REAL runtime paths: scheduled,
locked, idempotent, restart-safe, observable jobs, plus secure
configuration preflight and health. It owns no domain intelligence — it
invokes the existing services and records what happened.

Nothing here enables real-money trading or real external publication; those
walls live in their own modules and are preserved.
"""
