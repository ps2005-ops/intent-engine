"""Executive read adapter (T023).

Reads the executive health dashboard, triage queues, lineage, and trace —
and translates them into SourceClaims. It computes nothing: every number
here was produced by `ExecutiveService`, and the adapter only names it and
attaches provenance.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, FRESH_UNKNOWN, SourceClaim, SourceRef,
)


class ExecutiveAdapter(Adapter):
    subsystem = "executive"

    def _ref(self, artifact_type: str, artifact_id: str, replay_id: str,
             **over) -> SourceRef:
        return SourceRef(subsystem="executive", artifact_type=artifact_type,
                         artifact_id=artifact_id, replay_id=replay_id,
                         as_of=self.as_of,
                         freshness_status=over.pop("freshness_status",
                                                   FRESH_UNKNOWN), **over)

    # --- morning brief inputs -----------------------------------------------
    def decision_load(self) -> list:
        """The executive health dashboard as cited claims — decision
        backlog, conflicts, decision debt, expired, blocked. One claim per
        recorded figure, each pointing at the dashboard artifact."""
        if not self.available:
            return [unavailable_claim("exec.dashboard",
                                      "the executive subsystem is not connected")]
        dash = self.service.health_dashboard(as_of=self.as_of)
        replay = f"executive:dashboard:{self.as_of}"
        claims = []
        for key, phrasing in (
                ("decision_backlog", "open decision candidate(s) awaiting the "
                                     "founder's attention"),
                ("conflict_count", "cross-system conflict(s) recorded, stated "
                                   "rather than averaged"),
                ("decision_debt", "open decision-debt item(s) waiting on a "
                                  "person"),
                ("expired_decisions", "decision(s) a load-bearing input "
                                      "changed underneath"),
                ("blocked_decisions", "blocked decision(s)"),
                ("review_queue", "package(s) in the review queue")):
            value = dash.get(key, 0)
            claims.append(SourceClaim(
                claim_id=f"exec.{key}",
                text=f"{value} {phrasing}",
                availability=AVAIL_SUPPORTED,
                source_refs=(self._ref("health_dashboard", key, replay),),
                transformation="direct"))
        return claims

    def top_decisions(self, limit: int = 5) -> list:
        """The operational triage queue order, as cited claims. Ordering is
        the executive subsystem's, preserved — the adapter does not re-rank."""
        if not self.available:
            return [unavailable_claim("exec.queue",
                                      "the executive subsystem is not connected")]
        queues = self.service.triage_queues(as_of=self.as_of)
        claims = []
        for queue_name in ("strategic", "operational", "maintenance"):
            block = queues["queues"][queue_name]
            for position, candidate_id in enumerate(block["order"][:limit], 1):
                replay = f"executive:queue:{queue_name}:{candidate_id}:{self.as_of}"
                claims.append(SourceClaim(
                    claim_id=f"exec.queue.{queue_name}.{position}",
                    text=f"{queue_name} queue position {position}: decision "
                         f"candidate {candidate_id}",
                    availability=AVAIL_SUPPORTED,
                    source_refs=(self._ref("triage_queue_entry", candidate_id,
                                           replay),),
                    transformation="direct"))
        return claims

    # --- explainability / trace ---------------------------------------------
    def trace_decision(self, package_id: str) -> dict:
        """The lineage + terminal state of one decision package, for
        'why is this in my queue'. Returned raw-but-referenced; the caller
        composes it, the adapter attaches the replay id."""
        if not self.available:
            return {"available": False,
                    "reason": "the executive subsystem is not connected"}
        try:
            lineage = self.service.lineage(package_id)
            trace = self.service.trace(package_id)
        except Exception as exc:                            # noqa: BLE001
            return {"available": False,
                    "reason": f"executive could not resolve {package_id}: "
                              f"{type(exc).__name__}"}
        return {
            "available": True,
            "lineage": lineage,
            "trace": trace,
            "source_ref": self._ref("decision_package", package_id,
                                    f"executive:lineage:{package_id}:{self.as_of}",
                                    lineage_ref=lineage.get("context_id")).as_dict(),
        }

    def open_decision_debt(self) -> list:
        """Decision debt items as investigation-ready references. The
        urgency/order is whatever the executive index already reports."""
        if not self.available:
            return []
        index = self.service.get_index()
        out = []
        for item in index.open_decision_debt():
            out.append({
                "kind": item.get("kind"),
                "detail": item.get("detail", ""),
                "clears_when": item.get("clears_when", ""),
                "candidate_id": item.get("candidate_id"),
                "source_ref": self._ref(
                    "decision_debt", f"{item.get('candidate_id')}:{item.get('kind')}",
                    f"executive:debt:{item.get('candidate_id')}:{self.as_of}").as_dict(),
            })
        return out
