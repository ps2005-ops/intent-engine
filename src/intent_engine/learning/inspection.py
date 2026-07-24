"""Read-only inspection surface over the learning platform.

This is the seam Personal AI (and the web layer) read through to *observe
and explain* the learning pipeline — the Learning & Promotion Ledger plus
the Paper-Trading Shadow Loop — without any ability to change it. It
composes existing read methods; it computes no new intelligence (the
metrics are the paper module's, the candidate state is the ledger's), so
it stays inside the Personal-AI rule "an adapter reads; it never writes;
it computes no domain intelligence".

Every returned item carries a replay handle (the candidate/position id and
the as_of) so a claim built from it is reproducible, per the workspace's
explainability contract.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class PlatformLearningReader:
    def __init__(self, learning_ledger=None, paper_loop=None):
        self.learning = learning_ledger
        self.paper = paper_loop

    # --- learning ledger -----------------------------------------------------
    def candidates(self, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.learning is None:
            return []
        out = []
        for c in self.learning.list(status=status):
            out.append({
                "id": c.id, "source": c.source, "target": c.target,
                "status": c.status, "statement": c.statement,
                "created_at": c.created_at,
                "criteria": [{"metric": s.metric, "comparator": s.comparator,
                              "threshold": s.threshold} for s in c.success_criteria],
            })
        return out

    def pipeline_summary(self) -> Dict[str, int]:
        """Candidate counts by status — the one-glance state of the brain."""
        if self.learning is None:
            return {}
        summary: Dict[str, int] = {}
        for c in self.learning.list():
            summary[c.status] = summary.get(c.status, 0) + 1
        return summary

    def explain_candidate(self, candidate_id: str) -> Dict[str, Any]:
        """Finding -> Evidence -> Confidence -> Reasoning -> Source -> Replay,
        assembled from the ledger's own records. No interpretation added."""
        if self.learning is None:
            return {"available": False, "reason": "learning ledger not connected"}
        candidate = self.learning.get(candidate_id)
        if candidate is None:
            return {"available": False, "reason": f"no candidate {candidate_id}"}
        evaluations = self.learning.evaluations_for(candidate_id)
        readiness = None
        try:
            readiness = self.learning.evaluate_promotion_readiness(candidate_id)
        except Exception:  # noqa: BLE001 - readiness is best-effort context
            readiness = None
        return {
            "available": True,
            "candidate_id": candidate_id,
            "finding": f"{candidate.status}: {candidate.statement}",
            "evidence": [
                {"evaluation_id": e.id, "kind": e.kind, "verdict": e.verdict,
                 "candidate_metrics": e.candidate_metrics,
                 "baseline_metrics": e.baseline_metrics,
                 "sample_size": e.sample_size}
                for e in evaluations],
            "confidence": (readiness or {}).get("ready"),
            "reasoning": candidate.hypothesis,      # the proposer's own basis
            "source_agent": candidate.source,
            "replay_id": f"learning:{candidate_id}:{candidate.created_at}",
            "promotion_readiness": readiness,
            "note": "the reasoning is the proposing subsystem's own recorded "
                    "hypothesis — the reader adds no interpretation",
        }

    # --- paper book ----------------------------------------------------------
    def paper_metrics(self) -> Optional[Dict[str, Any]]:
        if self.paper is None:
            return None
        m = self.paper.metrics()
        return {
            "closed_count": m.closed_count,
            "starting_equity": m.starting_equity,
            "ending_equity": m.ending_equity,
            "total_pnl": m.total_pnl,
            "win_rate": m.win_rate,
            "profit_factor": (None if m.profit_factor in (None, float("inf"))
                              else m.profit_factor),
            "expected_value": m.expected_value,
            "sharpe": m.sharpe,
            "sortino": m.sortino,
            "max_drawdown": m.max_drawdown,
            "regime_attribution": m.regime_attribution,
        }
