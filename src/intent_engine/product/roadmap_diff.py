"""Roadmap candidates and the PROPOSED diff (T020).

The wall this module exists to hold: **`ROADMAP.md` is never written by
code.** A diff is a suggestion, and a person applies it.

That wall is structural rather than promised. This module never opens a
file — not for reading and not for writing. The caller passes the current
roadmap text in and gets diff text back, so there is no filesystem path
through which a write could be added by accident later.

Two further bars:

    a candidate is marked NEEDS-SPEC unless every one of its bars is a
        checkable condition
    a candidate is never marked RUNNABLE by the agent — only a person
        moves an item into the queue the nightly loop picks from
"""
from __future__ import annotations

import difflib

from intent_engine.product.records import ProductError
from intent_engine.product.specs import assert_checkable

CANDIDATE_VERSION = "roadmap_candidate.v1"
DIFF_VERSION = "roadmap_diff.v1"

STATUS_NEEDS_SPEC = "NEEDS-SPEC"
STATUS_PROPOSED = "PROPOSED — REVIEW REQUIRED"

# The one status an agent may not produce, under any circumstance.
FORBIDDEN_STATUS = "RUNNABLE"


def assert_never_runnable(text: str, *, where: str = "roadmap candidate") -> None:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- **Status**:") \
                and FORBIDDEN_STATUS in stripped \
                and STATUS_NEEDS_SPEC not in stripped:
            raise ProductError(
                f"{where} sets Status to {FORBIDDEN_STATUS} — an agent does "
                "not move an item into the queue the nightly loop picks "
                "from; a person does")


def build_roadmap_candidate(*, proposal_id: str, proposal_version: int,
                            spec_id: str, spec_version: int,
                            title: str, spec: dict, opportunity_id: str,
                            problem_id: str, size: str = "M",
                            priority: int = None) -> dict:
    """A task block in this repository's own format, emitted as a
    candidate. `Files in scope` is deliberately unresolved: a spec draft
    carries no file paths, so the candidate says so rather than inventing
    them."""
    criteria = list(spec.get("acceptance_criteria") or [])
    if not criteria:
        raise ProductError("a roadmap candidate requires acceptance criteria")

    verifiable, unverifiable = [], []
    for criterion in criteria:
        try:
            assert_checkable(criterion)
        except ProductError as exc:
            unverifiable.append({"criterion": criterion, "reason": str(exc)})
        else:
            verifiable.append(criterion)

    status = STATUS_NEEDS_SPEC if unverifiable else STATUS_PROPOSED
    walls = list(spec.get("constraints") or []) + [
        f"non-goal: {goal}" for goal in (spec.get("non_goals") or [])]

    lines = [
        f"## CANDIDATE — {title}",
        "",
        f"- **Status**: {status}",
        f"- **Priority**: {priority if priority is not None else 'unranked'}."
        f" **Size**: {size}.",
        f"- **Source**: product proposal {proposal_id} v{proposal_version}, "
        f"spec draft {spec_id} v{spec_version}, opportunity "
        f"{opportunity_id}, problem {problem_id}.",
        "- **Files in scope**: unresolved — a spec draft carries no file "
        "paths, so a person names the scope before this enters any queue.",
        "- **Definition of done (bars)**:",
    ]
    lines += [f"  - {criterion}" for criterion in verifiable]
    if unverifiable:
        lines.append("- **Bars that are not yet checkable** (why this stays "
                     f"{STATUS_NEEDS_SPEC}):")
        lines += [f"  - {item['criterion']}" for item in unverifiable]
    if walls:
        lines.append("- **Walls**: " + "; ".join(walls) + ".")
    lines += [
        "- **Disposition**: a candidate for review. It enters no queue, and "
        "no code applies it.",
        "",
    ]
    text = "\n".join(lines)
    assert_never_runnable(text)

    return {
        "candidate_version": CANDIDATE_VERSION,
        "status": status,
        "title": title,
        "proposal_id": proposal_id,
        "proposal_version": proposal_version,
        "spec_id": spec_id,
        "spec_version": spec_version,
        "opportunity_id": opportunity_id,
        "problem_id": problem_id,
        "verifiable_bars": verifiable,
        "unverifiable_bars": unverifiable,
        "text": text,
        "note": ("a candidate is emitted for a person to apply; nothing here "
                 "writes ROADMAP.md"),
    }


def render_roadmap_diff(candidate: dict, roadmap_text: str) -> dict:
    """A unified diff a person could apply by hand. Nothing is written.

    The current roadmap text is passed IN. This module holds no path, no
    file handle, and no write call, so the wall does not depend on anyone
    remembering it.
    """
    if not isinstance(roadmap_text, str):
        raise ProductError(
            "the current roadmap text is passed in as a string; this module "
            "does not read the file, so that the wall holds structurally")
    before = roadmap_text.splitlines(keepends=True)
    after = before + ["\n"] + [
        line + "\n" for line in candidate["text"].splitlines()]
    diff = "".join(difflib.unified_diff(
        before, after, fromfile="ROADMAP.md", tofile="ROADMAP.md (proposed)",
        n=3))
    assert_never_runnable(diff, where="roadmap diff")
    return {
        "diff_version": DIFF_VERSION,
        "candidate_version": candidate["candidate_version"],
        "proposal_id": candidate["proposal_id"],
        "proposal_version": candidate["proposal_version"],
        "spec_id": candidate["spec_id"],
        "spec_version": candidate["spec_version"],
        "status": candidate["status"],
        "diff": diff,
        "applied": False,
        "note": ("emitted, not applied — ROADMAP.md is byte-identical after "
                 "this call, and this module contains no write path"),
    }
