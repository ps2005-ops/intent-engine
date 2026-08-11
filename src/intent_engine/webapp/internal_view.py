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
from intent_engine.external_intel.internal_impact import (
    INTERNAL_DATA_UNAVAILABLE,
    INTERNAL_IMPACT_IDENTIFIED,
    INTERNAL_LINK_WITHOUT_METRIC,
    NO_INTERNAL_IMPACT,
    SYNTHETIC_ENTERPRISE,
    assess_internal_impact,
    minimum_data_request,
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

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "request_id": self.request_id,
            "subject_id": self.subject_id,
            "scoped": self.scoped,
            "impact": self.impact.as_dict() if self.impact else None,
            "minimum_data_request": (self.data_request.as_dict()
                                     if self.data_request else None),
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
           runtime_sha: str = "", now: Optional[str] = None
           ) -> InternalImpactAnswer:
    """The whole production chain for one internal-impact question.

    Scope first, and the load is skipped entirely without one -- a scopeless
    request must not open a partition file at all, so a path bug cannot become
    a read. The receipt is emitted on BOTH branches, because the requests an
    auditor came for are the refused ones.
    """
    when = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    request_id = _request_id(subject_id, when)
    scope = scope_for_session(session, directory=directory, audit=audit)

    if scope is None:
        impact = assess_internal_impact(BusinessGraph(), subject_id=subject_id,
                                        scope=None)
        return InternalImpactAnswer(
            request_id=request_id, subject_id=subject_id, impact=impact,
            data_request=minimum_data_request(impact, decision=decision),
            scoped=False,
            receipt=receipt_for(
                request_id=request_id, scope=None, company_id=subject_id,
                operation=OPERATION, denial_reason=impact.reason,
                runtime_sha=runtime_sha, occurred_at=when))

    graph = BusinessGraph()
    load = store.load_into(graph, scope=scope)
    impact = assess_internal_impact(graph, subject_id=subject_id, scope=scope)
    return InternalImpactAnswer(
        request_id=request_id, subject_id=subject_id, impact=impact,
        data_request=minimum_data_request(impact, decision=decision),
        load=load, scoped=True,
        receipt=receipt_for(
            request_id=request_id, scope=scope, company_id=subject_id,
            operation=OPERATION,
            requested=impact.private_nodes_examined + impact.withheld,
            allowed=impact.private_nodes_examined,
            withheld=impact.withheld,
            denial_reason=impact.reason, runtime_sha=runtime_sha,
            occurred_at=when))


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

    if ans.data_request is not None:
        req = ans.data_request
        fields = "".join(f"<li>{e(f)}</li>" for f in req.fields)
        parts.append(
            f"<div class=\"minimum-data-request\">"
            f"<h3>Smallest thing that would answer this</h3>"
            f"<p>{e(req.missing)}</p><ul>{fields}</ul>"
            f"<p class=\"window\">Window: last {int(req.window_days)} days</p>"
            f"</div>")

    parts.append("</section>")
    return "".join(parts)
