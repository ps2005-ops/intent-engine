"""Traceability (T021) — the new standing repository invariant.

    recommendation -> Decision Record -> Prediction -> Outcome -> Knowledge

Every recommendation must trace along this chain to a TERMINAL state.
The word "terminal" is load-bearing: `rejected` and `deferred` are
legitimate terminals. A hard chain that demanded every recommendation
reach a Decision Record would make a recommendation the founder DECLINED
into a violation — which is the exact distortion T020 removed when it made
`deferred` and `merged_into` first-class founder answers.

So this checks for DEAD ENDS, not for completion. A recommendation that
went to review and was accepted-but-never-linked is a dead end. A
recommendation the founder rejected is complete.
"""
from __future__ import annotations

from intent_engine.executive.records import (
    DISPOSITION_ACCEPTED, DISPOSITION_DEFERRED, DISPOSITION_MERGED,
    DISPOSITION_REJECTED, OUTCOME_NO_RECOMMENDATION, TERMINAL_DISPOSITIONS,
)

TRACEABILITY_VERSION = "traceability.v1"


def trace_package(index, package_id: str) -> dict:
    """Where a package sits on the chain, and whether it is a dead end."""
    package = index.packages.get(package_id)
    if package is None:
        raise KeyError(f"no such package: {package_id}")
    status = package["status"]

    # A no-recommendation that has set its review date is complete: it said
    # "not yet", honestly, and named when to look again.
    if package["outcome"] == OUTCOME_NO_RECOMMENDATION \
            and status not in ("review_requested",):
        return {"package_id": package_id, "terminal": True,
                "state": "no_recommendation",
                "reason": "declined to recommend, with a review date — a "
                          "legitimate terminal"}

    if status in (DISPOSITION_REJECTED, DISPOSITION_DEFERRED,
                  DISPOSITION_MERGED):
        return {"package_id": package_id, "terminal": True, "state": status,
                "reason": f"the founder's answer was {status}, which "
                          "terminates the chain — declining is an answer, "
                          "not a dead end"}

    if status == DISPOSITION_ACCEPTED:
        if not package.get("decision_id"):
            return {"package_id": package_id, "terminal": False,
                    "state": "accepted_unlinked",
                    "reason": "accepted but not linked to a Decision Record — "
                              "a dead end: the founder said yes and nothing "
                              "carries it forward"}
        outcome = index.outcomes.get(package_id)
        return {"package_id": package_id, "terminal": True,
                "state": "accepted_linked",
                "decision_id": package["decision_id"],
                "outcome_observed": outcome is not None,
                "reason": "accepted and linked to a Decision Record; the "
                          "chain continues through the ledger and knowledge, "
                          "which own their own steps"}

    # Still open / in review: not a dead end, just not terminal yet.
    return {"package_id": package_id, "terminal": False, "state": status,
            "reason": "still in progress; not yet terminal, and not a dead "
                      "end"}


def assert_no_dead_ends(index) -> dict:
    """The invariant: no recommendation is a dead end. A recommendation is
    a dead end only when it reached a founder answer that should carry
    forward and did not.

    Open and in-review packages are NOT dead ends — they simply have not
    terminated yet.
    """
    dead_ends = []
    traced = 0
    for package_id in sorted(index.packages):
        trace = trace_package(index, package_id)
        if trace["state"] == "accepted_unlinked":
            dead_ends.append(trace)
        if trace["terminal"]:
            traced += 1

    return {
        "traceability_version": TRACEABILITY_VERSION,
        "packages": len(index.packages),
        "terminal": traced,
        "dead_ends": dead_ends,
        "ok": not dead_ends,
        "terminal_states": sorted(TERMINAL_DISPOSITIONS | {"no_recommendation",
                                                          "accepted_linked"}),
        "note": ("every recommendation traces to a terminal state; rejected "
                 "and deferred are legitimate terminals, so declining a "
                 "recommendation is never a violation"),
    }
