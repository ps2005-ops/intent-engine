"""Composes the Week 1 pipeline: raw input -> intent -> risk audit, with timing.

Uses the combined PremortemAnalyzer stage by default (one Claude call, ~7-8s) rather than
chaining the separate IntentClassifier + RiskAuditGenerator stages (two calls, ~20s+),
which blew the spec's <10s budget. Pass an `analyzer=` override to use a different
implementation (e.g. the two-stage version) for comparison or future domains with a
looser latency budget.
"""

import time
from typing import NamedTuple, Optional

from ..core.llm_client import LLMClient
from ..core.schemas import RiskAudit, StructuredIntent
from .analysis import PremortemAnalyzer
from .context_schema import BusinessContext
from .schemas import ScenarioSet


class PremortemResult(NamedTuple):
    intent: StructuredIntent
    risk_audit: RiskAudit
    scenario_set: ScenarioSet
    elapsed_seconds: float
    # T005 additive field (docs/TASK4_SPEC_PROPOSAL.md): None when the
    # mechanism section wasn't requested; [] when requested but nothing
    # matched (correct silence); populated list otherwise. Defaulted, so
    # every existing caller/unpacking site is unaffected.
    ranked_mechanisms: Optional[list] = None
    # T006 additive field (docs/TASK5_WIRING_SPEC_PROPOSAL.md, approved):
    # None when prediction recording wasn't requested; otherwise the list
    # of Prediction rows the bridge recorded (source="premortem").
    # Defaulted for the same caller-compatibility guarantee as T005.
    ledgered_predictions: Optional[list] = None
    # T010 Slice 1B additive field (V1_COMPLETION_ROADMAP.md Part E): None
    # when no DecisionService was provided; otherwise the (created or
    # idempotently reused) DecisionRecord this intake belongs to. Same
    # caller-compatibility guarantee as the two fields above.
    decision_record: Optional[object] = None


def run_premortem(
    decision_text: str,
    context: BusinessContext,
    client: Optional[LLMClient] = None,
    analyzer: Optional[PremortemAnalyzer] = None,
    mechanism_client: Optional[LLMClient] = None,
    bridge_client: Optional[LLMClient] = None,
    bridge_entity_id: Optional[str] = None,
    bridge_ledger_path=None,
    decision_service=None,
    decision_intake_key: Optional[str] = None,
    decision_actor_id: str = "founder",
) -> PremortemResult:
    """`mechanism_client` (T005): when provided, ONE additional isolated
    extraction call computes the structural-mechanisms read (see
    simulator/mechanism_section.py) -- the combined-call analyzer prompt is
    untouched either way (hard wall A3; LuckTest isolation pattern).
    Default None: zero new calls, zero behavior change.

    `bridge_client` (T006, docs/TASK5_WIRING_SPEC_PROPOSAL.md): when
    provided, ONE additional isolated drafting call derives 1-3 resolvable
    predictions from the produced RiskAudit's failure modes and records
    them to the append-only ledger with source="premortem" (recording is
    code -- the drafting schema has no record/include field). Same A3
    isolation: the combined analyzer prompt is untouched either way.
    Default None: zero new calls, nothing recorded, additive field stays
    None. `bridge_entity_id` is required with `bridge_client`.

    `decision_service` (T010 Slice 1B, V1_COMPLETION_ROADMAP.md Part E):
    when provided, this intake gets ONE event-sourced Decision Record
    (created idempotently on `decision_intake_key`, so reprocessing the
    same accepted intake reuses the existing record). The ordered flow
    appends events and a later failure never erases earlier facts:
    DecisionCreated -> analysis -> RecommendationIssued -> prediction rows
    stamped with the record's decision_id. A failed analysis appends
    AnalysisFailed; a failed bridge appends PredictionLoggingFailed; both
    re-raise, and a retry with the same intake key creates zero duplicate
    records, events, or ledger rows. Default None: zero behavior change."""
    analyzer = analyzer or PremortemAnalyzer(client=client)

    decision_record = None
    if decision_service is not None:
        import hashlib
        metadata = {"intake_sha256": hashlib.sha256(decision_text.encode()).hexdigest()}
        if bridge_entity_id:
            metadata["entity_id"] = bridge_entity_id
        decision_record = decision_service.create_decision(
            decision_actor_id, actor_type="human", actor_id=decision_actor_id,
            source="cli", idempotency_key=decision_intake_key, metadata=metadata)
        if bridge_entity_id:
            decision_service.add_entity(
                decision_record.decision_id, bridge_entity_id, "subject")

    start = time.monotonic()
    try:
        result = analyzer.run(decision_text, context)
    except Exception as exc:
        if decision_record is not None:
            # Typed failure event -- audit-only, never erases the record.
            # Payload carries the exception TYPE only: no raw intake or
            # provider text ever enters an event payload (locked decision 10).
            decision_service.record_event(
                decision_record.decision_id, "AnalysisFailed",
                actor_type="system", actor_id="premortem_pipeline",
                source="system", payload={"error_type": type(exc).__name__})
        raise

    if decision_record is not None:
        decision_service.record_event(
            decision_record.decision_id, "RecommendationIssued",
            actor_type="system", actor_id="premortem_pipeline", source="system",
            payload={"n_failure_modes": len(result.risk_audit.failure_modes)},
            idempotency_key=(f"reco:{decision_intake_key}"
                             if decision_intake_key else None))

    ranked_mechanisms = None
    if mechanism_client is not None:
        from .mechanism_section import compute_ranked_mechanisms
        ranked_mechanisms = compute_ranked_mechanisms(decision_text, client=mechanism_client)

    ledgered_predictions = None
    if bridge_client is not None:
        if not bridge_entity_id:
            raise ValueError("bridge_entity_id is required when bridge_client is provided")
        from ..core.premortem_prediction_bridge import derive_predictions_from_premortem
        from ..core.prediction_ledger import DEFAULT_LEDGER_PATH, list_predictions
        bridge_kwargs = {} if bridge_ledger_path is None else {"ledger_path": bridge_ledger_path}
        existing_rows = []
        if decision_record is not None:
            ledger = DEFAULT_LEDGER_PATH if bridge_ledger_path is None else bridge_ledger_path
            existing_rows = list_predictions(
                path=ledger, decision_id=decision_record.decision_id)
        if existing_rows:
            # Idempotent retry (bar b): this decision's rows already exist --
            # zero new ledger rows, zero drafting calls.
            ledgered_predictions = existing_rows
        else:
            try:
                ledgered_predictions = derive_predictions_from_premortem(
                    bridge_entity_id, result.risk_audit, client=bridge_client,
                    decision_id=(None if decision_record is None
                                 else decision_record.decision_id),
                    **bridge_kwargs)
            except Exception as exc:
                if decision_record is not None:
                    decision_service.record_event(
                        decision_record.decision_id, "PredictionLoggingFailed",
                        actor_type="system", actor_id="premortem_pipeline",
                        source="system",
                        payload={"error_type": type(exc).__name__})
                raise
    elapsed = time.monotonic() - start

    return PremortemResult(
        intent=result.intent,
        risk_audit=result.risk_audit,
        scenario_set=result.scenario_set,
        elapsed_seconds=elapsed,
        ranked_mechanisms=ranked_mechanisms,
        ledgered_predictions=ledgered_predictions,
        decision_record=decision_record,
    )
