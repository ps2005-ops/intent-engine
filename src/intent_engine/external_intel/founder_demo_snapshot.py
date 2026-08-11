"""Emit `founder_demo_snapshot.v1` from canonical founder state.

WHICH SIDE OF THE SEAM THIS IS ON
----------------------------------
This module is a PRODUCER, not part of the neutral join. It may import
founder internals freely — that is its job. `intent_engine.demo_dossier` may
not import *this*, and does not: the dependency runs one way, producer →
serialized contract → neutral assembler, and the structural guard enforces it.

AUTHORIZATION HAPPENS HERE, NOT DOWNSTREAM
-------------------------------------------
§10: the dossier is not an authorization boundary. Every tenant-partitioned
read is performed here, under a scope, and what crosses is a sanitized
reference plus a state. If no scope was established, the private blocks read
UNAVAILABLE with the reason — they never read as an empty AVAILABLE list,
because "you are not allowed to see this" and "there is nothing here" are
different sentences and only one of them is about the company.

EVERY DEFAULT IS AN ABSENCE, NEVER A ZERO
------------------------------------------
`internal_impact_state` defaults to `INTERNAL_DATA_UNAVAILABLE` and not to
`NO_INTERNAL_IMPACT`; `decision_impact_state` to `IMPACT_UNAVAILABLE` and not
to `NONE`. A producer whose defaults are measured zeros manufactures findings
on every run where a subsystem was merely quiet, and `internal_impact` already
exports `NOT_A_NEGATIVE` precisely so this cannot be argued about.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Optional, Sequence

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.contracts import FOUNDER_CONTRACT
from intent_engine.external_intel import internal_impact as II

#: What a private block says when nobody is authorized to read it. Distinct
#: from NOT_ATTEMPTED (nobody looked) and from an AVAILABLE empty set.
_NO_SCOPE = "no tenant scope was established for this analysis"


def _ref(state: str, ids: Sequence[str] = (), note: str = "",
         count: Optional[int] = None) -> dict:
    ids = [str(i) for i in ids]
    return {"state": state, "ids": ids[:64],
            "count": len(ids) if count is None else int(count), "note": note}


def _unavailable_ref(note: str) -> dict:
    return _ref("UNAVAILABLE", (), note)


def _snapshot_id(run_id: str, company_id: str, cutoff: str) -> str:
    """Stable across identical inputs, distinct across any change.

    Includes the cutoff: the same run re-serialized over a different evidence
    window is not the same snapshot, and a snapshot id that ignored the window
    would let the assembler dedupe two genuinely different observations.
    """
    blob = f"{company_id}|{run_id}|{cutoff}".encode("utf-8")
    return f"fs-{hashlib.sha256(blob).hexdigest()[:20]}"


def _runtime_sha() -> str:
    try:
        from intent_engine._version import version_info
        info = version_info()
        return str(info.get("git_sha") or info.get("app_version") or "")
    except Exception:  # noqa: BLE001 - a snapshot must not fail a run
        return ""


def _coverage_state(report: Any, context: Any) -> str:
    """Read the canonical coverage state; never invent one."""
    for source in (report, context):
        state = (source or {}).get("coverage_state") \
            if isinstance(source, dict) else getattr(source, "coverage_state",
                                                     None)
        if isinstance(state, str) and state:
            return state
        obj = getattr(source, "coverage", None)
        if obj is not None and getattr(obj, "state", None):
            return str(obj.state)
    return V.FIELD_UNAVAILABLE


def _recommendation(report: Any) -> tuple:
    """The recommendation's REFERENCE and standing — not its text.

    The dossier references; it does not restate a conclusion. Copying the
    recommendation prose in would make this a second place a founder could
    read an answer, and the two would drift the first time one was revised.
    """
    if not isinstance(report, dict):
        return "", V.FIELD_UNAVAILABLE
    rec = report.get("recommendation") or report.get("decision") or {}
    if isinstance(rec, dict):
        ref = str(rec.get("id") or rec.get("recommendation_id") or "")
        standing = str(rec.get("standing") or rec.get("ceiling")
                       or V.FIELD_UNAVAILABLE)
        return ref, (standing or V.FIELD_UNAVAILABLE)
    return "", V.FIELD_UNAVAILABLE


def build_payload(*, run_id: str, company_id: str, canonical_name: str = "",
                  domain: str = "", ticker: str = "", report: Any = None,
                  context: Any = None, scope: Any = None,
                  living_decisions: Sequence[Any] = (),
                  mdrs: Sequence[Any] = (), mves: Sequence[Any] = (),
                  internal_impact_state: str = "",
                  decision_impact_state: str = "",
                  evidence_ids: Sequence[str] = (),
                  data_population: str = "",
                  evidence_cutoff: str = "", known_at: str = "",
                  generated_at: str = "") -> dict:
    """Build the serialized snapshot. Returns a plain dict, on purpose.

    A dict is what crosses the seam. Returning a founder object would tempt
    the assembler into reaching through it into founder internals, which is
    the import boundary this whole design exists to keep structural.
    """
    today = date.today().isoformat()
    generated_at = generated_at or today
    known_at = known_at or generated_at
    cutoff = evidence_cutoff or known_at

    scoped = scope is not None
    tenant_id = str(getattr(scope, "tenant_id", "") or "") if scoped else ""
    tenant_state = (str(getattr(scope, "state", "") or "SCOPED") if scoped
                    else "SCOPELESS_PUBLIC_ONLY")

    def _private(rows: Sequence[Any], label: str) -> dict:
        if not scoped:
            return _unavailable_ref(f"{label}: {_NO_SCOPE}")
        return _ref("AVAILABLE",
                    [str(getattr(r, "id", None) or (r.get("id") if
                                                    isinstance(r, dict)
                                                    else "") or "")
                     for r in rows], "")

    population = data_population if data_population in V.POPULATIONS else ""
    impact = (decision_impact_state if decision_impact_state in V.IMPACT_STATES
              else V.IMPACT_UNAVAILABLE)
    internal = (internal_impact_state
                if internal_impact_state in II.ANSWER_STATES
                else II.INTERNAL_DATA_UNAVAILABLE)

    return {
        "contract_version": FOUNDER_CONTRACT,
        "snapshot_id": _snapshot_id(run_id, company_id, cutoff),
        "company_id": company_id,
        "canonical_name": canonical_name or company_id,
        "domain": domain, "ticker": ticker,
        "analysis_id": run_id, "run_id": run_id,
        "runtime_sha": _runtime_sha(),
        "generated_at": generated_at, "known_at": known_at,
        "evidence_cutoff": cutoff,
        # THREE STATES, NOT TWO. A sparse real company found this: `ghost_co`
        # completes an analysis and reaches no strategic report, and folding
        # that into the same UNAVAILABLE as "no analysis ever ran" is the
        # missing-vs-zero defect this whole contract exists to refuse —
        # committed here, in the producer, where the distinction is still
        # knowable. A completed run that concluded little is a MEASURED
        # outcome about the company; an absent run is a fact about us.
        "availability": _availability(report, run_id),
        "unavailable_reason": _availability_reason(report, run_id),
        "tenant_id": tenant_id, "tenant_state": tenant_state,
        "data_population": population,
        "coverage_state": _coverage_state(report, context),
        "ceo_answer_coverage": _ceo_coverage(report),
        "recommendation_ref": _recommendation(report)[0],
        "recommendation_standing": _recommendation(report)[1],
        "what_changed_ref": str((report or {}).get("what_changed_ref") or "")
        if isinstance(report, dict) else "",
        "what_changed_your_mind_ref": str(
            (report or {}).get("what_changed_your_mind_ref") or "")
        if isinstance(report, dict) else "",
        "decision_impact_state": impact,
        "living_decision_refs": _private(living_decisions, "living decisions"),
        "mdr_refs": _private(mdrs, "minimum data requests"),
        "mve_refs": _private(mves, "minimum viable experiments"),
        "internal_impact_state": internal,
        "internal_graph_availability": (V.AVAILABLE if scoped
                                        else V.UNAVAILABLE),
        "evidence_reference_ids": (_ref("AVAILABLE", evidence_ids)
                                   if evidence_ids else
                                   _ref("NOT_ATTEMPTED", (),
                                        "no evidence ids were collected")),
        # NOT BUILT IN THIS VERTICAL, and never faked from a source count.
        # `len(evidence_ids)` is a row count; independent support is a
        # different number and this program has already shipped the version
        # that confused them (§26).
        "evidence_independence_state": V.INDEPENDENCE_UNAVAILABLE,
        # A backend cannot see its own rendering. Permanently UNMEASURED
        # from here (§27); only an exercised UI proof may say otherwise.
        "product_surfaces": {name: V.UNMEASURED
                             for name in V.PRODUCT_SURFACES},
        "provenance_summary": {"state": V.AVAILABLE,
                               "value": _runtime_sha(),
                               "as_of": generated_at,
                               "note": "runtime provenance of the analysis"},
    }


def _availability(report: Any, run_id: str) -> str:
    """AVAILABLE, DEGRADED or UNAVAILABLE — never two of the three merged."""
    if report is not None:
        return V.AVAILABLE
    if run_id:
        return V.DEGRADED
    return V.UNAVAILABLE


def _availability_reason(report: Any, run_id: str) -> str:
    if report is not None:
        return ""
    if run_id:
        return ("the analysis completed and reached no strategic report for "
                "this company; this is a bounded result, not a missing run")
    return "no analysis has been composed for this run"


def _ceo_coverage(report: Any) -> dict:
    """How much of the CEO question set this analysis answered.

    A report that carries no answers block reads UNAVAILABLE. Zero answered
    out of zero asked is not the same as a question set nobody ran.
    """
    if not isinstance(report, dict):
        return {"state": V.UNAVAILABLE, "note": "no report was composed"}
    answers = report.get("ceo_answers")
    if not isinstance(answers, (list, tuple)):
        return {"state": V.UNAVAILABLE,
                "note": "this analysis carries no CEO answer block"}
    return {"state": V.AVAILABLE, "value": len(answers),
            "note": f"{len(answers)} CEO answers present"}
