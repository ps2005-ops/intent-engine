"""Hosted free-tier runtime — the daily cycle as GitHub-Actions-callable jobs.

This package wires the durable store, the Alpaca PAPER broker, the company
universe, and the learning loop into discrete, idempotent, catch-up-safe jobs
(`hosted.jobs`) that a fresh GitHub-Actions runner executes and records durably
(`hosted.records`). Nothing here needs an always-on process: each job connects,
does bounded work, persists, and exits — so Render's free web service can sleep
without interrupting anything.
"""
from __future__ import annotations

from intent_engine.hosted.budget import Budget, BudgetLedger, record_skip
from intent_engine.hosted.context import HostedContext

__all__ = ["Budget", "BudgetLedger", "record_skip", "HostedContext"]
