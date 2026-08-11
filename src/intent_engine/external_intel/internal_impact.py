"""Which of the tenant's OWN metrics an external thesis reaches.

WHY THIS MODULE EXISTS AT ALL
-----------------------------
`business_graph.internal` can store a company's private world, persist it,
reload it and refuse the wrong reader. None of that is worth anything until
something ASKS IT A QUESTION. This program has now recorded five separate
capabilities that were built, tested, adversarially proven and had zero
production callers, and each one was reported as finished because its suite was
green. A graph nobody queries is the same defect with a nicer schema.

So this is the first consumer, and the question it answers is the one a founder
actually asks when an external analysis lands:

    "That's a claim about the outside world. What does it touch in MINE?"

THE ANSWER VOCABULARY, AND THE DISTINCTION THAT MATTERS MOST
------------------------------------------------------------
    INTERNAL_IMPACT_IDENTIFIED    named metrics, each with the path that
                                  reached it
    NO_INTERNAL_IMPACT            the private world is visible, was examined,
                                  and declares no dependency on this subject.
                                  A MEASURED NEGATIVE.
    INTERNAL_LINK_WITHOUT_METRIC  something internal depends on this subject,
                                  and no metric is wired to it. An information
                                  GAP.
    INTERNAL_DATA_UNAVAILABLE     there was nothing to reason over.

The line between the last two and `NO_INTERNAL_IMPACT` is the whole point.
"We looked at your 40 internal metrics and this thesis moves none of them" and
"we cannot see your business" are OPPOSITE answers, and a system that renders
both as "no impact" tells a founder their exposure is zero when what it means
is that it is unmeasured. This program has shipped that exact collapse before,
in the other direction, and spent a release removing it. So the empty case is
never reachable from the negative case: they are computed on different
branches, before any metric search runs.

HOW AN EXTERNAL THESIS BINDS TO AN INTERNAL NODE
------------------------------------------------
By an EXPLICIT DECLARED ATTRIBUTE (`external_subject`), compared EXACTLY, and
by nothing else.

Not by keyword overlap, not by label similarity, not by alias. That restraint
is the expensive lesson in this codebase: a substring match once let the alias
"Linear" satisfy "Linear Minerals Corp.", and a keyword rule elsewhere invented
a competitive exposure out of boilerplate. A fabricated internal exposure is
worse than a missing one, because a founder cannot audit an inference they were
never shown the basis for. If the tenant did not declare that this initiative
depends on this subject, this module does not know it, and says so.

POPULATION AWARENESS IS NOT DECORATION
--------------------------------------
A synthetic enterprise may prove capability, persistence, security and
plumbing. It may NOT prove a real economic result. Every answer therefore
carries the populations that produced it, and `is_real_data_claim()` is False
the moment a synthetic row contributed. A surface that renders this without
consulting that flag is reporting a fixture as a finding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from intent_engine.business_graph.internal import (
    ACTION_AFFECTS_METRIC,
    DECISION_AUTHORIZES_ACTION,
    EXPERIMENT_TESTS_ASSUMPTION,
    INITIATIVE,
    INITIATIVE_AFFECTS_METRIC,
    INTERNAL_ASSUMPTION,
    INTERNAL_METRIC,
    PRIVATE_ACTION,
    PRIVATE_DECISION,
    PRIVATE_NODE_KINDS,
)
from intent_engine.business_graph.model import (
    EMPTY_NO_ROWS,
    EMPTY_PRIVATE_WITHHELD,
    EMPTY_UNTAGGED_REFUSED,
    BusinessGraph,
    GraphError,
    read_scope,
)
from intent_engine.core.tenant import TenantScope

CONTRACT = "internal_impact.v1"

# -- the answer states --------------------------------------------------------
INTERNAL_IMPACT_IDENTIFIED = "INTERNAL_IMPACT_IDENTIFIED"
NO_INTERNAL_IMPACT = "NO_INTERNAL_IMPACT"
INTERNAL_LINK_WITHOUT_METRIC = "INTERNAL_LINK_WITHOUT_METRIC"
INTERNAL_DATA_UNAVAILABLE = "INTERNAL_DATA_UNAVAILABLE"

ANSWER_STATES = frozenset({
    INTERNAL_IMPACT_IDENTIFIED, NO_INTERNAL_IMPACT,
    INTERNAL_LINK_WITHOUT_METRIC, INTERNAL_DATA_UNAVAILABLE,
})

#: The states that must never be read as "this thesis does not affect you".
#: Exported so a surface can assert against the set rather than restate it and
#: drift; `test_internal_impact.py` pins the membership, not the length.
NOT_A_NEGATIVE = frozenset({
    INTERNAL_LINK_WITHOUT_METRIC, INTERNAL_DATA_UNAVAILABLE})

# -- why nothing was available ------------------------------------------------
SCOPELESS_READ = "SCOPELESS_READ"
NO_PRIVATE_ROWS = "NO_PRIVATE_ROWS"
ALL_PRIVATE_WITHHELD = "ALL_PRIVATE_WITHHELD"
ALL_ROWS_REFUSED = "ALL_ROWS_REFUSED"
UNAVAILABLE_REASONS = frozenset({
    SCOPELESS_READ, NO_PRIVATE_ROWS, ALL_PRIVATE_WITHHELD, ALL_ROWS_REFUSED})

#: The attribute a tenant sets to say "this part of my business depends on that
#: part of the outside world". The ONLY bridge; see the module docstring.
EXTERNAL_SUBJECT_KEY = "external_subject"

#: Population tag, mirroring the V5 constitution's synthetic-enterprise rule.
POPULATION_KEY = "data_population"
SYNTHETIC_ENTERPRISE = "SYNTHETIC_ENTERPRISE"
REAL_ENTERPRISE = "REAL_ENTERPRISE"
POPULATIONS = frozenset({SYNTHETIC_ENTERPRISE, REAL_ENTERPRISE})

#: How a linked node reaches a metric. Every entry is a real edge kind in
#: `business_graph.internal`; there is no path here the graph cannot store.
_METRIC_ROUTES = {
    INITIATIVE: ((INITIATIVE_AFFECTS_METRIC,),),
    PRIVATE_ACTION: ((ACTION_AFFECTS_METRIC,),),
    PRIVATE_DECISION: ((DECISION_AUTHORIZES_ACTION, ACTION_AFFECTS_METRIC),),
}


@dataclass(frozen=True)
class AffectedMetric:
    """One internal metric, and the declared chain that reached it.

    `path` is not a nicety. An impact a founder cannot trace back to the node
    THEY declared is an assertion, and this module is not permitted to make
    assertions about somebody's business.
    """

    metric_id: str = ""
    label: str = ""
    via: Tuple[str, ...] = ()
    declared_by: str = ""
    population: str = ""

    def as_dict(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "label": self.label,
            "via": list(self.via),
            "declared_by": self.declared_by,
            "population": self.population,
        }


@dataclass(frozen=True)
class InternalImpact:
    """What the private graph says about one external thesis.

    Frozen, and every field populated on every branch including the empty ones.
    A result object whose counters appear only when non-zero cannot report that
    nothing happened -- the same reason `private_inventory` keys every kind at
    zero.
    """

    state: str = INTERNAL_DATA_UNAVAILABLE
    subject_id: str = ""
    metrics: Tuple[AffectedMetric, ...] = ()
    declared_links: Tuple[str, ...] = ()
    reason: str = ""
    private_nodes_examined: int = 0
    withheld: int = 0
    refused: int = 0
    populations: Tuple[str, ...] = ()
    scope_state: str = ""

    def __post_init__(self):
        if self.state not in ANSWER_STATES:
            raise GraphError(f"unknown internal-impact state {self.state!r}")
        if self.state == INTERNAL_DATA_UNAVAILABLE:
            if self.reason not in UNAVAILABLE_REASONS:
                raise GraphError(
                    "INTERNAL_DATA_UNAVAILABLE must name which prerequisite is "
                    f"missing; got reason {self.reason!r}")
        elif self.reason:
            raise GraphError(
                f"state {self.state} carries an unavailability reason "
                f"{self.reason!r}; only INTERNAL_DATA_UNAVAILABLE may")

    @property
    def is_negative(self) -> bool:
        """True ONLY for a measured negative.

        The property exists so a surface asks this question instead of testing
        `not impact.metrics`, which is True for all four states and is how the
        collapse this module was built to prevent gets reintroduced by a
        template.
        """
        return self.state == NO_INTERNAL_IMPACT

    def is_real_data_claim(self) -> bool:
        """False if any synthetic row contributed, and False when nothing did.

        Absence of evidence is not a real-data claim either, so an empty answer
        is not permitted to pass this gate on the technicality that no synthetic
        row was involved.
        """
        if self.state == INTERNAL_DATA_UNAVAILABLE:
            return False
        return SYNTHETIC_ENTERPRISE not in self.populations

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "state": self.state,
            "subject_id": self.subject_id,
            "metrics": [m.as_dict() for m in self.metrics],
            "declared_links": list(self.declared_links),
            "reason": self.reason,
            "private_nodes_examined": self.private_nodes_examined,
            "withheld": self.withheld,
            "refused": self.refused,
            "populations": list(self.populations),
            "scope_state": self.scope_state,
            "is_real_data_claim": self.is_real_data_claim(),
        }


def _population_of(node) -> str:
    """A row that does not say which population it belongs to is SYNTHETIC.

    Defaulting the other way would let an untagged fixture be reported as a real
    economic result, which is the one thing section 26 forbids. Failing safe
    here costs a truthful answer its `is_real_data_claim` flag until somebody
    tags the row; failing the other way costs a founder a decision.
    """
    value = (getattr(node, "attrs", None) or {}).get(POPULATION_KEY)
    return value if value in POPULATIONS else SYNTHETIC_ENTERPRISE


def _declares(node, subject_id: str) -> bool:
    """Exact, whole-value match on a declared attribute. Never a substring.

    `startswith`/`in` here is precisely how "Linear" once matched
    "Linear Minerals Corp.", and how a keyword rule invented a competitive
    exposure out of a filing's boilerplate.
    """
    declared = (getattr(node, "attrs", None) or {}).get(EXTERNAL_SUBJECT_KEY)
    return isinstance(declared, str) and declared != "" and declared == subject_id


def _walk_to_metrics(graph: BusinessGraph, node, *,
                     scope: TenantScope) -> Tuple[Tuple[str, ...], ...]:
    """Every declared chain from one linked node to a metric.

    Traverses through the SCOPED readers, never `_all_nodes`, so a chain stops
    at the tenant boundary exactly where a direct read would.
    """
    if node.kind == INTERNAL_METRIC:
        return ((node.node_id,),)
    routes = _METRIC_ROUTES.get(node.kind, ())
    found = []
    for route in routes:
        frontier = [(node.node_id,)]
        for edge_kind in route:
            nxt = []
            for path in frontier:
                for edge in graph.out_edges(path[-1], edge_kind, scope=scope):
                    nxt.append(path + (edge.dst,))
            frontier = nxt
        found.extend(frontier)
    return tuple(found)


def assess_internal_impact(graph: BusinessGraph, *, subject_id: str,
                           scope: Optional[TenantScope] = None
                           ) -> InternalImpact:
    """Answer "what does this external subject touch inside my business?"

    `scope=None` is legal and answers honestly: a scopeless reader sees the
    public world, and the public world contains no private metrics, so the
    answer is INTERNAL_DATA_UNAVAILABLE with reason SCOPELESS_READ. It is NOT
    `NO_INTERNAL_IMPACT`, because a reader holding no authority has not
    established that there is no impact -- only that it may not look.
    """
    if not isinstance(subject_id, str) or not subject_id:
        raise GraphError(
            "an internal-impact assessment needs the external subject it is "
            "about; an empty subject would match every undeclared node")
    scope = read_scope(scope)
    read = graph.read(scope=scope)
    empty_state = read.empty_state()
    private = [n for n in read.nodes if n.kind in PRIVATE_NODE_KINDS]

    common = dict(subject_id=subject_id, withheld=read.withheld_private,
                  refused=len(read.refused), scope_state=read.scope_state,
                  private_nodes_examined=len(private))

    # -- the unavailable branch, decided BEFORE any search ------------------
    # Reached without looking for a metric, so an empty private world can never
    # fall through into the measured negative below.
    if not private:
        if scope is None:
            reason = SCOPELESS_READ
        elif empty_state == EMPTY_PRIVATE_WITHHELD or read.withheld_private:
            reason = ALL_PRIVATE_WITHHELD
        elif empty_state == EMPTY_UNTAGGED_REFUSED or read.refused:
            reason = ALL_ROWS_REFUSED
        else:
            reason = NO_PRIVATE_ROWS
        return InternalImpact(state=INTERNAL_DATA_UNAVAILABLE, reason=reason,
                              **common)

    linked = [n for n in private if _declares(n, subject_id)]
    if not linked:
        # A real measured negative: the rows were visible and examined.
        return InternalImpact(state=NO_INTERNAL_IMPACT, **common)

    by_id = {n.node_id: n for n in read.nodes}
    metrics, seen = [], set()
    for node in sorted(linked, key=lambda n: n.node_id):
        for path in _walk_to_metrics(graph, node, scope=scope):
            metric = by_id.get(path[-1])
            if metric is None or metric.kind != INTERNAL_METRIC:
                continue
            key = (metric.node_id, node.node_id)
            if key in seen:
                continue
            seen.add(key)
            metrics.append(AffectedMetric(
                metric_id=metric.node_id, label=metric.label,
                via=path, declared_by=node.node_id,
                population=_population_of(metric)))

    contributors = list(linked) + [by_id[m.metric_id] for m in metrics
                                   if m.metric_id in by_id]
    populations = tuple(sorted({_population_of(n) for n in contributors}))
    declared = tuple(sorted(n.node_id for n in linked))

    if not metrics:
        # Something depends on this subject and no metric is wired to it. An
        # information gap, and the natural input to a Minimum Data Request.
        return InternalImpact(
            state=INTERNAL_LINK_WITHOUT_METRIC, declared_links=declared,
            populations=populations, **common)

    return InternalImpact(
        state=INTERNAL_IMPACT_IDENTIFIED,
        metrics=tuple(sorted(metrics, key=lambda m: (m.metric_id,
                                                     m.declared_by))),
        declared_links=declared, populations=populations, **common)


# =============================================================================
# Minimum Data Request -- the bounded foundation
# =============================================================================
#: What a request is FOR. A request that cannot name the decision it serves is
#: a data grab, and this is the seam where "give us CRM access" gets born.
MDR_CONTRACT = "minimum_data_request.v1"

MDR_NO_INTERNAL_WORLD = "NO_INTERNAL_WORLD"
MDR_METRIC_NOT_WIRED = "METRIC_NOT_WIRED"
MDR_REASONS = frozenset({MDR_NO_INTERNAL_WORLD, MDR_METRIC_NOT_WIRED})


@dataclass(frozen=True)
class MinimumDataRequest:
    """The smallest ask that would resolve one specific unanswered question.

    BOUNDED BY CONSTRUCTION: `fields` and `window_days` are required and the
    constructor refuses a request that names no decision. The alternative --
    asking for a system rather than for the columns that resolve an uncertainty
    -- is both a worse security posture and an admission that we do not know
    what we would do with the data.
    """

    request_id: str = ""
    decision: str = ""
    missing: str = ""
    fields: Tuple[str, ...] = ()
    window_days: int = 0
    reason: str = ""
    subject_id: str = ""

    def __post_init__(self):
        if not self.decision:
            raise GraphError(
                "a minimum data request must name the decision it serves; a "
                "request without one is a data grab")
        if not self.fields:
            raise GraphError("a minimum data request must name its fields")
        if self.reason not in MDR_REASONS:
            raise GraphError(f"unknown request reason {self.reason!r}")

    def as_dict(self) -> dict:
        return {
            "contract": MDR_CONTRACT,
            "request_id": self.request_id,
            "decision": self.decision,
            "missing": self.missing,
            "fields": list(self.fields),
            "window_days": self.window_days,
            "reason": self.reason,
            "subject_id": self.subject_id,
        }


def minimum_data_request(impact: InternalImpact, *, decision: str
                         ) -> Optional[MinimumDataRequest]:
    """The request that would turn this non-answer into an answer, or None.

    None for both ANSWERED states, and the reason differs: an identified impact
    needs nothing, and a MEASURED NEGATIVE needs nothing either -- asking for
    more data to confirm a negative we already measured is how a data request
    becomes unbounded.
    """
    if impact.state not in NOT_A_NEGATIVE:
        return None
    if impact.state == INTERNAL_DATA_UNAVAILABLE:
        return MinimumDataRequest(
            request_id=f"mdr-{impact.subject_id}-world",
            decision=decision,
            missing="any internal metric this thesis could move",
            fields=("metric name", "owning initiative",
                    "the external subject it depends on"),
            window_days=90, reason=MDR_NO_INTERNAL_WORLD,
            subject_id=impact.subject_id)
    return MinimumDataRequest(
        request_id=f"mdr-{impact.subject_id}-metric",
        decision=decision,
        missing=("a metric wired to " + ", ".join(impact.declared_links)),
        fields=("metric name", "current value", "the initiative that moves it"),
        window_days=90, reason=MDR_METRIC_NOT_WIRED,
        subject_id=impact.subject_id)
