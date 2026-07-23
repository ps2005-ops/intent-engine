"""Decision Platform read adapter (T023).

Reads a Decision Record's folded state through `DecisionService` — status,
owner, execution/evaluation state — for a decision the executive layer
linked. It writes nothing to the decision store (the workspace holds no
decision authority) and infers no status: it names what DecisionService
returned.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, SourceClaim, SourceRef,
)


class DecisionsAdapter(Adapter):
    subsystem = "decisions"

    def status(self, decision_id: str) -> SourceClaim:
        if not self.available:
            return unavailable_claim("decisions.status",
                                     "the decision platform is not connected")
        record = self.service.get_decision(decision_id)
        if record is None:
            return unavailable_claim(
                "decisions.status",
                f"no Decision Record {decision_id} exists")
        state = self.service.get_current_state(decision_id)
        return SourceClaim(
            claim_id=f"decisions.{decision_id}",
            text=f"decision {decision_id}: status={state.decision_status}, "
                 f"execution={state.execution_status}, owner={state.owner}",
            availability=AVAIL_SUPPORTED,
            source_refs=(SourceRef(
                subsystem="decisions", artifact_type="decision_record",
                artifact_id=decision_id,
                replay_id=f"decisions:{decision_id}:{self.as_of}",
                as_of=self.as_of),),
            transformation="direct")
