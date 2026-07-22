"""The Decision Context (T021) — the object between candidate and package.

A package is a RENDERING of a context. Keeping them apart is what lets a
later layer answer the question a founder actually asks:

    "Why is this decision in my queue today when it was not yesterday?"

The answer is in the context: it records a per-input FINGERPRINT of every
load-bearing fact it rests on, so the next build can say exactly which
input moved. That one mechanism does three jobs at once:

    recent_changes   which inputs differ from the prior context version
    expiry           a decision expires when an input it rested on changed
                     — never when a clock ran out
    replay           the same inputs rebuild the same context, byte for byte

A context owns:

    current_assumptions     external_constraints    relevant_history
    recent_changes          open_dependencies       decision_horizon
    decision_class          input_fingerprints

and nothing else. It states the situation; the package argues about it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from intent_engine.executive.records import (
    DECISION_CLASSES, DECISION_HORIZONS, ExecutiveError, assign_queue,
)

CONTEXT_VERSION = "decision_context.v1"
AGING_VERSION = "decision_aging.v1"


def _hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]


def reference_key(ref: dict) -> str:
    return f"{ref['kind']}:{ref['ref_id']}"


def input_fingerprints(resolved_inputs: dict) -> dict:
    """One fingerprint per load-bearing input, so "something changed"
    becomes "THIS changed"."""
    return {key: _hash(value) for key, value in sorted(resolved_inputs.items())}


def overall_fingerprint(fingerprints: dict) -> str:
    return _hash(dict(sorted(fingerprints.items())))


def changed_inputs(prior: dict, current: dict) -> dict:
    """Deterministic diff between two context versions' inputs."""
    prior = prior or {}
    current = current or {}
    added = sorted(set(current) - set(prior))
    removed = sorted(set(prior) - set(current))
    changed = sorted(key for key in set(prior) & set(current)
                     if prior[key] != current[key])
    return {"added": added, "removed": removed, "changed": changed,
            "any_change": bool(added or removed or changed)}


def describe_changes(diff: dict) -> list:
    """Human-readable, and deliberately literal: it names the inputs
    rather than characterising what they mean."""
    lines = []
    for key in diff["changed"]:
        lines.append(f"{key} changed since the prior context version")
    for key in diff["added"]:
        lines.append(f"{key} became load-bearing since the prior version")
    for key in diff["removed"]:
        lines.append(f"{key} stopped being load-bearing since the prior "
                     "version")
    return lines


def build_context(*, candidate_id: str, decision_horizon: str,
                  decision_class: str, resolved_inputs: dict,
                  current_assumptions=None, external_constraints=None,
                  relevant_history=None, open_dependencies=None,
                  prior_fingerprints=None) -> dict:
    """Assembled from recorded facts only. No model touches this."""
    if decision_horizon not in DECISION_HORIZONS:
        raise ExecutiveError(
            f"unknown decision horizon {decision_horizon!r} — one of "
            f"{list(DECISION_HORIZONS)}")
    if decision_class not in DECISION_CLASSES:
        raise ExecutiveError(
            f"unknown decision class {decision_class!r} — one of "
            f"{sorted(DECISION_CLASSES)}")

    fingerprints = input_fingerprints(resolved_inputs)
    diff = changed_inputs(prior_fingerprints or {}, fingerprints)
    queue, queue_reason = assign_queue(decision_horizon, decision_class)

    return {
        "context_contract_version": CONTEXT_VERSION,
        "candidate_id": candidate_id,
        "decision_horizon": decision_horizon,
        "decision_class": decision_class,
        "queue": queue,
        "queue_reason": queue_reason,
        "current_assumptions": list(current_assumptions or []),
        "external_constraints": list(external_constraints or []),
        "relevant_history": list(relevant_history or []),
        "open_dependencies": list(open_dependencies or []),
        "input_fingerprints": fingerprints,
        "input_fingerprint": overall_fingerprint(fingerprints),
        "recent_changes": describe_changes(diff),
        "changed_inputs": diff,
        "note": ("a context states the situation a decision sits in; the "
                 "package argues about it. Recent changes name which inputs "
                 "moved, which is what makes a queue position explainable"),
    }


# =============================================================================
# Aging — reported, and deliberately separate from readiness
# =============================================================================

def decision_age(created_at: str, as_of: str) -> dict:
    """How long a candidate has been waiting. Reported so a founder can
    prioritise, and kept OUT of every readiness dimension: a decision does
    not become more ready by sitting still, and a queue that rewards age
    would surface stale work over current work."""
    age_days = (datetime.fromisoformat(as_of)
                - datetime.fromisoformat(created_at)).total_seconds() / 86400.0
    return {"aging_version": AGING_VERSION,
            "created_at": created_at, "as_of": as_of,
            "age_days": round(age_days, 2),
            "feeds_readiness": False,
            "note": ("age is reported, not scored — a decision does not "
                     "become more ready by waiting")}


# =============================================================================
# Expiry — a changed input, not a clock
# =============================================================================

def expiry_check(*, recorded_fingerprints: dict, current_fingerprints: dict,
                 as_of: str) -> dict:
    """A decision expires when a load-bearing input changed underneath it.

    Time alone expires nothing. A clock manufactures urgency, and this
    subsystem exists to reduce the founder's attention load rather than to
    generate reasons to spend it.
    """
    diff = changed_inputs(recorded_fingerprints, current_fingerprints)
    return {
        "expired": diff["any_change"],
        "as_of": as_of,
        "changed_inputs": diff,
        "reasons": describe_changes(diff) or [
            "every load-bearing input is unchanged since this decision was "
            "framed, so it stands regardless of how long it has waited"],
        "rule": ("expiry follows a changed input; elapsed time on its own "
                 "expires nothing"),
    }
