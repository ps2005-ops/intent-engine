"""Monthly promotion-review packet (1H) — human decision support.

Builds a persisted, auditable packet of every candidate that is promotable
on the evidence, so a HUMAN can review and (separately, via the ledger's
human-gated promote()) approve. This module NEVER promotes — it only
assembles the review. Each entry carries the candidate, its evidence, the
readiness audit, the exact proposed config diff, and a rollback note, per
the 1H requirements.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Union


def build_packet(learning_ledger) -> dict:
    entries = []
    for candidate in learning_ledger.list(status="evaluated"):
        readiness = learning_ledger.evaluate_promotion_readiness(candidate.id)
        evaluations = learning_ledger.evaluations_for(candidate.id)
        entries.append({
            "candidate_id": candidate.id,
            "source": candidate.source,
            "target": candidate.target,
            "statement": candidate.statement,
            "hypothesis": candidate.hypothesis,
            "proposed_change": candidate.param_diff,     # exact config diff
            "success_criteria": [{"metric": c.metric, "comparator": c.comparator,
                                  "threshold": c.threshold} for c in candidate.success_criteria],
            "evidence": [{"evaluation_id": e.id, "kind": e.kind,
                          "verdict": e.verdict, "sample_size": e.sample_size,
                          "candidate_metrics": e.candidate_metrics,
                          "baseline_metrics": e.baseline_metrics}
                         for e in evaluations],
            "sample_size_total": sum(e.sample_size for e in evaluations),
            "ready_for_promotion": readiness["ready"],
            "unresolved_concerns": readiness["reasons"],
            "rollback": ("promotion is a versioned ledger record; to roll back, "
                         "the human promotes a superseding candidate or reverts "
                         "the deployed config — production is never mutated by "
                         "this system, so a rollback is a config revert"),
        })
    ready = [e for e in entries if e["ready_for_promotion"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_evaluated": len(entries),
        "ready_for_human_promotion": len(ready),
        "entries": entries,
        "note": "no candidate is promoted here; a human promotes via the "
                "ledger's human-gated path after review",
    }


def write_packet(learning_ledger, root: Union[str, Path]) -> Path:
    packet = build_packet(learning_ledger)
    root = Path(root)
    (root / "packets").mkdir(parents=True, exist_ok=True)
    stamp = packet["generated_at"][:10]
    path = root / "packets" / f"promotion_review_{stamp}.json"
    path.write_text(json.dumps(packet, indent=2, sort_keys=True, default=str))
    return path
