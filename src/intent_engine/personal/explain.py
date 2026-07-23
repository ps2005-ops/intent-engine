"""Explainability (T023) — a defining product characteristic.

Any conclusion the workspace presents expands into a fixed chain:

    Finding -> Evidence -> Confidence -> Reasoning -> Source Agent -> Replay ID

This is a first-class read, not a debug feature. It is assembled from the
owning agent's lineage; the workspace adds no reasoning of its own — the
"Reasoning" step is the agent's own recorded basis, quoted, not the
workspace's interpretation.
"""
from __future__ import annotations

from intent_engine.personal.records import PersonalError

EXPLAIN_VERSION = "personal_explain.v1"


def explain_decision(executive_adapter, package_id: str) -> dict:
    """The chain for a decision package, from the executive layer's lineage
    and trace. Every step cites the executive artifact + replay id."""
    resolved = executive_adapter.trace_decision(package_id)
    if not resolved.get("available"):
        return {"explain_version": EXPLAIN_VERSION, "available": False,
                "reason": resolved.get("reason", "unavailable"),
                "package_id": package_id}
    lineage = resolved["lineage"]
    trace = resolved["trace"]
    source_ref = resolved["source_ref"]
    return {
        "explain_version": EXPLAIN_VERSION,
        "available": True,
        "package_id": package_id,
        "finding": f"decision package {package_id} is "
                   f"{trace.get('state')} ({trace.get('reason', '')})",
        "evidence": lineage.get("references", []),
        "confidence": lineage.get("package_outcome"),
        "reasoning": trace.get("reason", ""),      # the agent's own basis
        "source_agent": "executive",
        "replay_id": source_ref["replay_id"],
        "source_ref": source_ref,
        "note": "the reasoning is the executive layer's own recorded basis, "
                "quoted — the workspace adds no interpretation",
    }


def explain_claim(claim) -> dict:
    """The chain for any SourceClaim the workspace presented. The claim
    already carries its source refs; explainability just lays them out."""
    if not claim.source_refs and claim.availability in (
            "SUPPORTED", "PARTIALLY_SUPPORTED", "CONFLICTED", "STALE"):
        raise PersonalError("a present claim must carry a source ref to be "
                            "explainable")
    refs = [r.as_dict() for r in claim.source_refs]
    return {
        "explain_version": EXPLAIN_VERSION,
        "finding": claim.text,
        "availability": claim.availability,
        "evidence": refs,
        "confidence": claim.confidence,
        "freshness": claim.freshness_status,
        "source_agent": refs[0]["subsystem"] if refs else None,
        "replay_id": refs[0]["replay_id"] if refs else None,
        "note": "every step resolves to a source artifact; nothing here is "
                "the workspace's own conclusion",
    }
