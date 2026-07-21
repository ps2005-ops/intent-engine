"""Release bundles (T020) — a named group of proposals, read together.

A bundle is a grouping for review, not a commitment and not a release.
It reports the aggregate state of its members: what is ready, what is
blocked, what order the dependency graph permits, and which members carry
decision debt. Assembling a bundle changes nothing about its members.
"""
from __future__ import annotations

from intent_engine.product.graph import sequence
from intent_engine.product.portfolio import BLOCKED, READY, readiness_report
from intent_engine.product.records import ProductError

BUNDLE_VERSION = "release_bundle.v1"


def assemble_bundle(state, index, *, name: str, proposal_ids,
                    scores_by_proposal=None) -> dict:
    """Deterministic: the same members over the same log produce the same
    bundle."""
    members = sorted(set(proposal_ids))
    if not members:
        raise ProductError("a bundle names at least one proposal")
    missing = [pid for pid in members if pid not in state.proposals]
    if missing:
        raise ProductError(f"bundle references undrafted proposals: {missing}")

    readiness = readiness_report(state, index,
                                 scores_by_proposal=scores_by_proposal)
    entries = {pid: readiness["entries"][pid] for pid in members}

    external_dependencies = sorted(
        {dep for pid in members for dep in entries[pid]["depends_on"]
         if dep not in set(members)})
    blocked = sorted(pid for pid in members
                     if entries[pid]["readiness"] == BLOCKED)
    ready = sorted(pid for pid in members
                   if entries[pid]["readiness"] == READY)
    decision_debt = [{"proposal_id": pid, **item}
                     for pid in members
                     for item in entries[pid]["decision_debt"]]

    return {
        "bundle_version": BUNDLE_VERSION,
        "name": name,
        "proposal_ids": members,
        "internal_sequence": sequence(index.graph, members),
        "external_dependencies": external_dependencies,
        "ready": ready,
        "blocked": blocked,
        "readiness_by_proposal": {pid: entries[pid]["readiness"]
                                  for pid in members},
        "decision_debt": decision_debt,
        "note": ("a bundle groups proposals for review; assembling one "
                 "changes nothing about its members and commits to nothing"),
    }
