"""The Founder-facing INTERNAL IMPACT surface, and the request that builds it.

This is the consumer that moves D-IBG-001, D-SYN-001 and F-TS-001 from
CAPABILITY_VERIFIED to something a request can actually reach. The whole chain
lives here, in one readable function, because the chain IS the deliverable:

    session -> TenantScope -> private graph load -> internal impact
            -> minimum data request -> rendered answer -> receipt

Kept out of `app.py` so it can be exercised by a caller that is not an HTTP
server without any helper bypass -- the route below calls `answer()` and does
nothing else, so a local invocation of `answer()` runs exactly the code a
request runs. That mattered for the live proof: section 20 allows a controlled
local invocation of the deployed stack, and forbids an "alternate helper
bypass". If the route contained logic of its own, this module would be a
different path wearing the same name.

THE SURFACE MUST NOT FLATTEN THE FOUR ANSWERS
---------------------------------------------
Every rendering decision below is downstream of one rule: a founder must be
able to tell "we looked at your metrics and this moves none of them" from "we
cannot see your business". They are the same empty screen in every product that
gets this wrong. So the state drives the heading, the wording and the presence
of a data request, and `is_negative` is read from the state rather than from
`not metrics` -- which is true in all four cases.

SYNTHETIC IS RENDERED, NOT HIDDEN
---------------------------------
When the answer rests on synthetic rows the surface says so, in the answer
itself rather than in a footnote. Section 26 permits these rows to prove
capability and forbids them from proving an economic result, and a surface that
quietly renders a fixture as a finding is exactly how that line gets crossed.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from intent_engine.business_graph.model import BusinessGraph
from intent_engine.business_graph.private_store import PrivateGraphStore
from intent_engine.core.tenant import ScopeAuditLog, TenantScope
from intent_engine.external_intel import minimum_data_request as MDR
from intent_engine.external_intel.internal_impact import (
    INTERNAL_DATA_UNAVAILABLE,
    INTERNAL_IMPACT_IDENTIFIED,
    INTERNAL_LINK_WITHOUT_METRIC,
    NO_INTERNAL_IMPACT,
    SYNTHETIC_ENTERPRISE,
    assess_internal_impact,
    candidate_fields,
    request_outcome,
)
from intent_engine.webapp.tenancy import (
    TenantDirectory,
    receipt_for,
    scope_for_session,
)

CONTRACT = "internal_impact_view.v1"
OPERATION = "internal_impact.read"

#: Heading and lead sentence per state. A table rather than branching prose, so
#: adding a state without deciding how it reads is a KeyError at render time
#: instead of a silently blank panel.
_WORDING = {
    INTERNAL_IMPACT_IDENTIFIED: (
        "Internal impact identified",
        "These internal metrics are linked to that subject by your own "
        "declarations."),
    NO_INTERNAL_IMPACT: (
        "No internal impact",
        "Your internal world was read and nothing in it declares a dependency "
        "on that subject."),
    INTERNAL_LINK_WITHOUT_METRIC: (
        "Linked, but nothing measures it",
        "Something in your business depends on that subject and no metric is "
        "wired to it. That is missing instrumentation, not absence of "
        "exposure."),
    INTERNAL_DATA_UNAVAILABLE: (
        "Internal data unavailable",
        "There was nothing to reason over. This is NOT a finding that the "
        "subject does not affect you."),
}


@dataclass(frozen=True)
class InternalImpactAnswer:
    """Everything one request produced, including its receipt."""

    request_id: str = ""
    subject_id: str = ""
    impact: object = None
    data_request: object = None
    receipt: object = None
    load: object = None
    scoped: bool = False
    #: The routing decision behind `data_request`. Present even when no request
    #: was made, because "you already have this", "it would change nothing",
    #: "we refused the breadth" and "no field can produce it" are four
    #: different answers that a bare `None` renders as one.
    outcome: object = None
    experiment: object = None
    telemetry: object = None
    persisted: bool = False
    decision_id: str = ""

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "request_id": self.request_id,
            "subject_id": self.subject_id,
            "scoped": self.scoped,
            "impact": self.impact.as_dict() if self.impact else None,
            "minimum_data_request": (self.data_request.as_dict()
                                     if self.data_request else None),
            "minimum_viable_experiment": (self.experiment.as_dict()
                                          if self.experiment else None),
            "request_state": (self.outcome.state if self.outcome else ""),
            "request_reason": (self.outcome.reason if self.outcome else ""),
            "selection": (self.outcome.selection.as_dict()
                          if self.outcome else None),
            "telemetry": self.telemetry.as_dict() if self.telemetry else None,
            "persisted": self.persisted,
            "decision_id": self.decision_id,
            "receipt": self.receipt.as_dict() if self.receipt else None,
            "load": self.load.as_dict() if self.load else None,
        }


def _request_id(subject_id: str, when: str) -> str:
    import hashlib

    raw = f"{OPERATION}|{subject_id}|{when}"
    return "ireq_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def answer(*, session, subject_id: str, decision: str,
           directory: TenantDirectory, store: PrivateGraphStore,
           audit: Optional[ScopeAuditLog] = None,
           requests: Optional[MDR.DataRequestStore] = None,
           decisions=None, decision_id: str = "",
           runtime_sha: str = "", now: Optional[str] = None
           ) -> InternalImpactAnswer:
    """The whole production chain for one internal-impact question.

    Scope first, and the load is skipped entirely without one -- a scopeless
    request must not open a partition file at all, so a path bug cannot become
    a read. The receipt is emitted on BOTH branches, because the requests an
    auditor came for are the refused ones.

    THE SCOPE IS NEVER TAKEN FROM THE QUESTION. `subject_id` and `decision`
    arrive from the query string, which means they can arrive from a document
    somebody else wrote. Neither reaches `scope_for_session`, the partition
    path, or the candidate catalogue: candidates are read through the scoped
    reader below, so an external instruction to "retrieve Tenant A's board
    metrics" can at most name a gap in the tenant we are already inside.
    """
    when = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    request_id = _request_id(subject_id, when)
    scope = scope_for_session(session, directory=directory, audit=audit)

    if scope is None:
        impact = assess_internal_impact(BusinessGraph(), subject_id=subject_id,
                                        scope=None)
        outcome = request_outcome(impact, decision=decision, now=when)
        # Nothing is persisted without a scope. A request row has to live in
        # somebody's partition, and a reader holding no authority has not said
        # whose.
        return InternalImpactAnswer(
            request_id=request_id, subject_id=subject_id, impact=impact,
            data_request=outcome.request, experiment=outcome.experiment,
            outcome=outcome, telemetry=MDR.MDRTelemetry.of(outcome),
            scoped=False, persisted=False,
            receipt=receipt_for(
                request_id=request_id, scope=None, company_id=subject_id,
                operation=OPERATION, denial_reason=impact.reason,
                runtime_sha=runtime_sha, occurred_at=when))

    graph = BusinessGraph()
    load = store.load_into(graph, scope=scope)
    impact = assess_internal_impact(graph, subject_id=subject_id, scope=scope)
    outcome = request_outcome(
        impact, decision=decision, decision_id=decision_id, scope=scope,
        candidates=candidate_fields(graph, scope=scope), now=when)

    persisted = False
    if requests is not None:
        if outcome.request is not None:
            requests.append(outcome.request, scope=scope)
            persisted = True
        if outcome.experiment is not None:
            requests.append(outcome.experiment, scope=scope)
            persisted = True
    if decisions is not None and decision_id and \
            (outcome.request is not None or outcome.experiment is not None):
        _attach_to_decision(decisions, scope=scope, decision_id=decision_id,
                            outcome=outcome)

    return InternalImpactAnswer(
        request_id=request_id, subject_id=subject_id, impact=impact,
        data_request=outcome.request, experiment=outcome.experiment,
        outcome=outcome, telemetry=MDR.MDRTelemetry.of(outcome),
        persisted=persisted, decision_id=decision_id,
        load=load, scoped=True,
        receipt=receipt_for(
            request_id=request_id, scope=scope, company_id=subject_id,
            operation=OPERATION,
            requested=impact.private_nodes_examined + impact.withheld,
            allowed=impact.private_nodes_examined,
            withheld=impact.withheld,
            denial_reason=impact.reason, runtime_sha=runtime_sha,
            occurred_at=when))


def _attach_to_decision(decisions, *, scope, decision_id: str,
                        outcome) -> None:
    """Point the Living Decision Record at the request, by id.

    The LDR is the canonical decision memory, so the request must be REFERENCED
    from it rather than copied into it -- a second copy of the ask inside the
    decision row is a second decision history, and the two drift the moment one
    is revised.

    A decision that already names this request is left alone: re-asking the
    same question must not produce a new revision, or "what changed?" fills up
    with rows where nothing did.
    """
    from intent_engine.executive import living_decision as LDRM

    rows = [r for r in decisions.all(scope=scope)
            if r.get("decision_id") == decision_id]
    if not rows:
        return
    row = rows[-1]
    gaps = tuple(row.get("information_gaps") or ())
    reqs = tuple(row.get("minimum_data_requests") or ())
    mves = tuple(row.get("mve_refs") or ())

    new_gaps = tuple(dict.fromkeys(gaps + tuple(
        f.unresolved_parameter for f in
        (outcome.request.requested_fields if outcome.request else ()))
        + tuple(outcome.selection.unresolvable)))
    new_reqs = tuple(dict.fromkeys(
        reqs + ((outcome.request.request_id,) if outcome.request else ())))
    new_mves = tuple(dict.fromkeys(
        mves + ((outcome.experiment.experiment_id,)
                if outcome.experiment else ())))
    if (new_gaps, new_reqs, new_mves) == (gaps, reqs, mves):
        return

    record = LDRM.LivingDecisionRecord(**{
        k: v for k, v in _record_kwargs(row).items()})
    revised = LDRM.revise(
        record, scope=scope, information_gaps=new_gaps,
        minimum_data_requests=new_reqs, mve_refs=new_mves,
        reason="minimum data request attached")
    decisions.append(revised, scope=scope)


#: The stored keys that are not constructor arguments. Listed rather than
#: filtered by `hasattr`, so a field added to the record without a decision
#: about this seam is a TypeError here instead of a silently dropped column.
_DERIVED_KEYS = ("contract", "is_recommendation_only", "retrospective")


def _record_kwargs(row: dict) -> dict:
    return {k: (tuple(v) if isinstance(v, list) else v)
            for k, v in row.items() if k not in _DERIVED_KEYS}


def render(ans: InternalImpactAnswer) -> str:
    """The founder-facing panel. Escapes everything; asserts nothing extra."""
    impact = ans.impact
    heading, lead = _WORDING[impact.state]
    e = html.escape

    parts = [f"<section id=\"internal-impact\" data-state=\"{e(impact.state)}\">",
             f"<h2>{e(heading)}</h2>", f"<p>{e(lead)}</p>"]

    if impact.state == INTERNAL_IMPACT_IDENTIFIED:
        parts.append("<ul class=\"internal-metrics\">")
        for metric in impact.metrics:
            chain = " &rarr; ".join(e(step) for step in metric.via)
            parts.append(
                f"<li><strong>{e(metric.label)}</strong>"
                f"<span class=\"chain\">{chain}</span></li>")
        parts.append("</ul>")
    elif impact.state == NO_INTERNAL_IMPACT:
        # The count is the evidence that this is a MEASURED negative rather
        # than an empty screen. Without it the two are the same panel.
        parts.append(
            f"<p class=\"examined\">{impact.private_nodes_examined} internal "
            f"records were read to reach this.</p>")
    elif impact.state == INTERNAL_DATA_UNAVAILABLE:
        parts.append(f"<p class=\"reason\">Reason: <code>"
                     f"{e(impact.reason)}</code></p>")

    if impact.withheld:
        parts.append(f"<p class=\"withheld\">{impact.withheld} records were "
                     f"not shown to this reader.</p>")

    # SYNTHETIC IS PART OF THE ANSWER, not a footnote. Rendered whenever the
    # answer does not rest on real data, including the unavailable case.
    if not impact.is_real_data_claim():
        basis = (", ".join(e(p) for p in impact.populations)
                 if impact.populations else "no internal records")
        parts.append(
            f"<p class=\"population\" data-population=\"{e(SYNTHETIC_ENTERPRISE)}\">"
            f"This answer rests on {basis} and is NOT a claim about real "
            f"business results.</p>")

    parts.append(_render_ask(ans, e))
    parts.append("</section>")
    return "".join(parts)


#: How each routing state reads to a founder. A table, so a state added
#: without deciding how it reads is a KeyError instead of a blank panel -- the
#: same device `_WORDING` uses for the impact states.
_ASK_WORDING = {
    MDR.NO_REQUEST_DATA_SUFFICIENT: (
        "Nothing is needed from you",
        "Your own records already answer this."),
    MDR.NO_REQUEST_NO_DECISION_VALUE: (
        "Nothing worth asking for",
        "The missing values were identified and none of them could change "
        "this decision, so they are not being requested."),
    MDR.MDR_ISSUED: (
        "Missing information",
        "These fields — and only these — would resolve the open part."),
    MDR.MVE_PROPOSED: (
        "No existing data answers this",
        "Nothing you already hold can produce this. A bounded experiment "
        "could."),
    MDR.UNRESOLVABLE: (
        "Unresolved, and honestly so",
        "No field you have and no safe experiment we can design would settle "
        "this. It stays open."),
    MDR.BREADTH_REFUSED: (
        "Request refused",
        "The only way to obtain this named a whole system rather than "
        "specific fields, so it was refused."),
}


def _render_ask(ans, e) -> str:
    """§16's blocks, read off the record. The renderer invents NOTHING.

    Every sentence below is either a constant from `_ASK_WORDING` or a value
    stored on the request. There is no branch here that composes a rationale,
    because a surface that can write its own reason can write one the record
    does not support, and a founder auditing the ask would find nothing behind
    it.
    """
    outcome = ans.outcome
    if outcome is None:
        return ""
    heading, lead = _ASK_WORDING[outcome.state]
    parts = [f"<div class=\"minimum-data-request\" "
             f"data-request-state=\"{e(outcome.state)}\">",
             f"<h3>{e(heading)}</h3><p>{e(lead)}</p>"]

    req = ans.data_request
    if req is not None:
        parts.append(f"<p class=\"why\">{e(req.missing)}</p>")
        parts.append("<ul class=\"requested-fields\">")
        for got in req.requested_fields:
            parts.append(
                f"<li data-voi=\"{e(got.voi_band)}\" "
                f"data-privacy=\"{e(got.privacy_class)}\">"
                f"<strong>{e(got.field_name)}</strong>"
                f"<span class=\"definition\">{e(got.semantic_definition)}</span>"
                f"<span class=\"resolves\">{e(got.decision_question)}</span>"
                f"<span class=\"effect\">What it could change: "
                f"{e(got.expected_decision_effect)}</span>"
                f"<span class=\"scope\">{e(got.required_grain)} grain, "
                f"{e(got.privacy_class)}, kept: "
                f"{e(got.retention_policy)}</span>"
                + (f"<span class=\"substitute\">Asked for instead of "
                   f"{e(got.substitute_for)}</span>"
                   if got.substitute_for else "")
                + "</li>")
        parts.append("</ul>")
        parts.append(
            f"<p class=\"window\">Window: last {int(req.window_days)} "
            f"days</p>" if req.window_days else
            "<p class=\"window\">Point in time. No history is being "
            "requested.</p>")
        parts.append(f"<p class=\"numeric-voi\">{e(req.numeric_voi)}</p>")

    declined = outcome.selection.declined
    if declined:
        rows = "".join(f"<li>{e(name)}: {e(why)}</li>" for name, why in declined)
        parts.append(f"<details class=\"not-requested\"><summary>"
                     f"{len(declined)} field(s) were deliberately NOT "
                     f"requested</summary><ul>{rows}</ul></details>")

    mve = ans.experiment
    if mve is not None:
        guards = "".join(f"<li>{e(g)}</li>" for g in mve.guardrail_metrics)
        params = "".join(f"<li>{e(p)}</li>" for p in mve.parameterization)
        parts.append(
            f"<div class=\"minimum-viable-experiment\" "
            f"data-parameterized=\"{str(mve.is_fully_parameterized).lower()}\">"
            f"<h4>Experiment option</h4>"
            f"<p class=\"hypothesis\">{e(mve.hypothesis)}</p>"
            f"<p class=\"intervention\">{e(mve.intervention)}</p>"
            f"<p class=\"population\">{e(mve.target_population)}</p>"
            f"<p class=\"exposure\">Exposure: {e(mve.exposure_scope)} · "
            f"Duration: {e(mve.duration)} · Stop at: "
            f"{e(mve.kill_threshold)}</p>"
            f"<p class=\"budget\">{e(mve.downside_budget)} "
            f"({e(mve.downside_budget_status)})</p>"
            f"<p class=\"kill\">Kill switch: {e(mve.kill_switch)}</p>"
            f"<p class=\"falsifier\">Refuted by: {e(mve.falsifier)}</p>"
            f"<ul class=\"guardrails\">{guards}</ul>"
            f"<p class=\"needs\">To set the numbers above we would need:</p>"
            f"<ul class=\"parameterization\">{params}</ul>"
            f"</div>")

    still = outcome.selection.unresolvable
    if still and ans.experiment is None:
        rows = "".join(f"<li>{e(p)}</li>" for p in still)
        parts.append(f"<div class=\"still-unresolved\"><h4>Still "
                     f"unresolved</h4><ul>{rows}</ul></div>")

    parts.append("</div>")
    return "".join(parts)
