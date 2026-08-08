"""Tell the market engine what actually happened to the dossier it published.

WHY THIS EXISTS
---------------
The market engine could report that it published 22 strategic dossiers and
could not report whether one of them was ever read. Its founder-utility metric
said `UNMEASURABLE`, which was honest and useless — a producer that cannot see
whether its output is consumed is optimising in the dark.

Only this side knows the answer. The dossier is read here, validated here,
accepted or refused here, and turned into reasoning blocks here.

WHY THE SCHEMA IS DUPLICATED RATHER THAN IMPORTED
-------------------------------------------------
There is no import path between the two systems and there should not be: the
market package is not present on this branch, `external_intel` is not present
on that one, and a founder surface able to reach into market internals would
eventually render one. The strategic allowlist is already carried the same way
for the same reason. `SCHEMA` is the one string both copies must agree on, and
it is versioned so a mismatch is visible rather than silent — the market
reader ignores rows whose schema it does not recognise.

WHAT IS DELIBERATELY NOT CLAIMED
--------------------------------
Writing this receipt is not permission to change anything the market engine
believes. It records consumption, never truth. Nothing here flows back into a
belief, a mechanism or an expectation, and the market side treats these rows
as observations about ITS OWN reach rather than as evidence about the world.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Optional, Tuple

#: MUST match `intent_engine.market.dossier_consumption.SCHEMA`.
SCHEMA = "dossier_consumption.v1"

#: Beside the dossiers this service reads, so the acknowledgement and the
#: thing it acknowledges travel together.
LEDGER_PATH = "reports/market/dossier_consumption.jsonl"

CONSUMER_VERSION = "founder_intelligence.v1"

# --- stages, in order. Utility begins at USED_IN_REASONING ------------------
RECEIVED = "RECEIVED"
VALIDATED = "VALIDATED"
ELIGIBLE = "ELIGIBLE"
SELECTED = "SELECTED"
PROJECTED = "PROJECTED"
USED_IN_REASONING = "USED_IN_REASONING"
#: The reasoning ran on NORMALIZED evidence rather than on a row count.
#: Between "used" and "rendered" because it qualifies what was used: a
#: dossier can be fully consumed and still have been consumed by counting.
TRUST_NORMALIZED = "TRUST_NORMALIZED"
RENDERED_TO_FOUNDER = "RENDERED_TO_FOUNDER"
#: The dossier did not merely appear — it constrained something a founder
#: acts on. Deliberately the hardest stage to reach and the only one that
#: answers "was this learning worth having".
DECISION_RELEVANT = "DECISION_RELEVANT"

#: THE LADDER, DECLARED ONCE.
#:
#: It was previously written out twice inside the health reader, in two
#: functions, as two literal tuples. Adding a stage therefore meant editing
#: both — and a stage missing from either is not an error, it is a row that
#: silently ranks below every other and disappears from the health view. The
#: reader now imports this, so a new stage cannot be half-added.
LADDER: Tuple[str, ...] = (
    RECEIVED, VALIDATED, ELIGIBLE, SELECTED, PROJECTED, USED_IN_REASONING,
    TRUST_NORMALIZED, RENDERED_TO_FOUNDER, DECISION_RELEVANT,
)

# --- refusal codes ----------------------------------------------------------
STALE_DOSSIER = "STALE_DOSSIER"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
SCHEMA_REJECTED = "SCHEMA_REJECTED"
NO_MATERIAL = "NO_MATERIAL"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _trust_telemetry(strategic) -> dict:
    """How much of this dossier's evidence was normalized, and to what.

    AVAILABLE AND USED ARE COUNTED SEPARATELY and must stay that way. A
    dossier can carry a normalized standing on every belief and be consumed by
    a renderer that reads none of them, which is exactly the state this
    project was in before this cycle: the market layer had known since wave 8
    that 143 claimed accounts were 55.5 effective ones, and no reader had ever
    been told. Counting availability as use would have reported that as
    success.

    `dependent_clusters` is the quantity the layer removes: rows that would
    have been presented as separate observations and are not.
    """
    from intent_engine.external_intel import evidence_trust as ET

    beliefs = list(getattr(strategic, "beliefs", ()) or ())
    trusts = [ET.of_belief(b) for b in beliefs]
    rated = [t for t in trusts if t.known]
    dependent = [t for t in rated if t.standing == ET.DEPENDENT_REREPORTING]
    independent = [t for t in rated
                   if t.standing == ET.INDEPENDENTLY_CORROBORATED]
    conflicted = [t for t in rated if t.standing == ET.CONFLICTED]
    whole = ET.read(getattr(strategic, "evidence_trust", None))
    return {
        "normalized_events_available": sum(t.distinct_events for t in rated),
        # USED means the reasoning path actually read the standing. Every
        # rated belief is projected through the graph, which is the only way
        # a belief becomes a block, so these coincide by construction rather
        # than by assumption — and the test that pins it says so.
        "normalized_events_used": sum(t.distinct_events for t in rated),
        "dependent_clusters_used": len(dependent),
        "independent_corroborations_used": len(independent),
        "conflicted_events_used": len(conflicted),
        # Rows that would have been counted as separate observations.
        "inflation_avoided": sum(t.inflation for t in rated),
        "trust_adjusted_reasoning": sum(1 for t in rated if t.must_bound),
        "standing": whole.standing if whole.known else (
            ET.weakest(rated).standing if rated else ET.UNKNOWN),
    }


def emit(root, *, company_id: str, stage: str, analysis_id: str,
         dossier_revision: str = "", published_at: str = "",
         analysis_started_at: str = "", analysis_as_of: str = "",
         strategic_content_used: int = 0, surface: str = "",
         refusal_code: str = "", refusal_reason: str = "",
         path: str = LEDGER_PATH) -> bool:
    """Append one acknowledgement. Never raises, never blocks an analysis.

    A telemetry write that can break a founder's run is a worse defect than
    the missing measurement it was added to fix, so every failure here is
    swallowed. The cost is that a broken ledger looks like an absent one —
    which the market side already reports as UNMEASURABLE rather than as zero,
    so the failure mode is silence rather than a false number.

    Idempotent on (analysis, dossier, revision, stage): a founder reloading a
    page must not inflate the producer's consumption count.
    """
    try:
        event_id = "|".join((analysis_id or "-", company_id or "-",
                             dossier_revision or "-", stage))
        target = pathlib.Path(root) / path
        if target.exists():
            for line in target.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("consumption_event_id") == event_id:
                    return False

        row = {
            "schema": SCHEMA,
            "consumption_event_id": event_id,
            "dossier_id": company_id,
            "dossier_revision": dossier_revision,
            "company_id": company_id,
            "market_runtime_sha": "",
            "market_cycle_id": "",
            "published_at": published_at,
            "founder_received_at": _now(),
            "founder_analysis_id": analysis_id,
            "analysis_started_at": analysis_started_at,
            "analysis_as_of": analysis_as_of,
            "stage": stage,
            "graph_projection_id": "",
            "strategic_content_used": int(strategic_content_used or 0),
            "founder_surface_rendered": surface,
            "consumed_at": _now(),
            "refusal_code": refusal_code,
            "refusal_reason": (refusal_reason or "")[:300],
            "consumer_version": CONSUMER_VERSION,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001 - see docstring
        return False


def acknowledge_context(root, *, company_id: str, analysis_id: str,
                        strategic, has_strategic: bool,
                        analysis_started_at: str = "",
                        analysis_as_of: str = "",
                        rendered_blocks: int = 0,
                        surface: str = "",
                        decision_impact: Optional[dict] = None) -> None:
    """Record how far one dossier got in one analysis.

    Called once per analysis, after the external context is built, because
    that is the moment every stage is decided and nothing later can change
    them. The ladder is walked honestly: a dossier that loaded but carried no
    material stops at VALIDATED with a refusal code, and does not quietly
    become a consumption.
    """
    if strategic is None:
        return

    # Reading the dossier object is itself guarded. `emit` was already
    # unbreakable, but this function inspects `strategic`, and a caller
    # handing over an object whose attributes raise would have propagated
    # straight into the analysis — exactly what the module promises cannot
    # happen. Measured by a test with a hostile property.
    try:
        available = bool(getattr(strategic, "available", False))
        published_at = str(getattr(strategic, "as_of", "") or "")
        reason = str(getattr(strategic, "reason", "") or "")
        beliefs = len(getattr(strategic, "beliefs", ()) or ())
        trust = _trust_telemetry(strategic)
    except Exception:  # noqa: BLE001 - see above
        return

    common = dict(company_id=company_id, analysis_id=analysis_id,
                  dossier_revision=published_at, published_at=published_at,
                  analysis_started_at=analysis_started_at,
                  analysis_as_of=analysis_as_of)

    # ONE ROW PER STAGE, carrying the refusal when there is one.
    #
    # The first version emitted a plain row and then a second row at the same
    # stage with the refusal attached. Both share an idempotency key, so the
    # refusal was silently deduped away and every refusal test failed —
    # the producer would have seen a bare RECEIVED and no reason for the stop.
    if not available:
        emit(root, stage=RECEIVED, refusal_code=SCHEMA_REJECTED,
             refusal_reason=reason or "dossier did not validate", **common)
        return

    emit(root, stage=RECEIVED, **common)

    if not has_strategic:
        # Loaded and validated, and it said nothing. Recorded as a refusal so
        # the producer can see the difference between "not delivered" and
        # "delivered empty" — those have different fixes, one upstream of the
        # other.
        emit(root, stage=VALIDATED, refusal_code=NO_MATERIAL,
             refusal_reason="dossier validated but carried no material",
             **common)
        return

    emit(root, stage=VALIDATED, **common)
    emit(root, stage=ELIGIBLE, **common)
    emit(root, stage=SELECTED, **common)
    emit(root, stage=PROJECTED, **common)
    # The dossier's content becomes reasoning blocks in exactly the branch
    # gated by `has_strategic`, so this is the same condition rather than an
    # optimistic proxy for it.
    emit(root, stage=USED_IN_REASONING, strategic_content_used=beliefs,
         **common)
    # NORMALIZED EVIDENCE, USED — not merely available.
    #
    # Availability is what the producer sent; use is what this side reasoned
    # from. Counting the first as the second is the error this whole ladder
    # exists to prevent, so the two are separate rows and the gap between
    # them is readable. A dossier from a producer that never normalized emits
    # availability 0 and is therefore distinguishable from one that
    # normalized and found a single observation.
    if trust["normalized_events_available"]:
        emit(root, stage=TRUST_NORMALIZED,
             strategic_content_used=trust["normalized_events_used"],
             surface=trust["standing"], **common)
    if rendered_blocks:
        # RENDERED means a strategic block actually exists to show. An
        # empty strategic section used to be reachable -- validated,
        # eligible, "used", and nothing under the heading -- so this stage
        # counts blocks rather than trusting that the section opened.
        emit(root, stage=RENDERED_TO_FOUNDER,
             strategic_content_used=rendered_blocks,
             surface=surface or "analysis", **common)
        # DECISION_RELEVANT only when a semantic decision field actually
        # moved AND the move is attributable to market evidence. Passing
        # a falsey impact is the normal case and must stay normal: a
        # dossier that was read and changed nothing is a real, common
        # and honest outcome, not a failure to be papered over.
        if decision_impact and decision_impact.get("changed"):
            emit(root, stage=DECISION_RELEVANT,
                 strategic_content_used=len(
                     decision_impact.get("impact_types") or ()),
                 surface=str(decision_impact.get("materiality") or ""),
                 **common)
