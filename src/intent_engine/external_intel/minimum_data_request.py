"""The smallest defensible ask, and the experiment that replaces it.

WHAT WAS ACTUALLY HERE BEFORE
-----------------------------
`internal_impact.minimum_data_request()` returned one of two hard-coded field
lists. It had a breadth check in its docstring and none in its code, and its
"minimum" was a constant -- which passes a widening test the way a function
that ignores its input passes every metamorphic test. This program has recorded
that exact shape once already ("a named heuristic may be a constant"), and the
tell is the same both times: the output does not vary with the input it claims
to minimise over.

So this module is not a second MDR system. It is the one that was named but not
written, and `internal_impact` now delegates to it.

THE LADDER, WHICH IS THE WHOLE POINT
------------------------------------
A founder asks something the engine cannot answer. There are six honest
destinations and only one of them is "we don't know":

    answered                    nothing is requested
    answered as a negative      nothing is requested -- confirming a measured
                                negative is how a data request becomes
                                unbounded
    a named missing field       MINIMUM DATA REQUEST, field by field, each one
                                carrying the decision it resolves
    a field we should not ask   a SAFER SUBSTITUTE resolves the same
    for                         uncertainty, or the ask is refused
    no field can produce it     MINIMUM VIABLE EXPERIMENT, bounded
    neither                     UNRESOLVABLE, said plainly

A system that collapses the last four into "insufficient data" is not being
careful, it is being useless.

VOI IS DERIVED, NEVER ASSERTED
------------------------------
`voi_band` is computed from WHICH DECISION BOUNDARIES the parameter could move
(§5's list), so a field cannot be labelled HIGH by whoever wrote its catalogue
entry. A parameter that moves no boundary is NO_DECISION_VALUE and is never
requested, however interesting it is.

There is no numeric VOI here and there is not permitted to be one. Numeric VOI
needs action alternatives, state probabilities, a utility and a data cost; this
system holds none of the four for a tenant's private world, and "$3.2M of
expected information value" derived from prose is a fabricated number wearing a
decision-theory costume. `NUMERIC_VOI_UNMEASURABLE` records why.

MINIMISATION IS MECHANICAL
--------------------------
`select_minimum` walks the UNRESOLVED PARAMETERS, not the candidate list. A
candidate that resolves no active parameter is never reached, so appending ten
irrelevant private fields cannot widen the request -- and that is a property of
the loop, not of a threshold somebody has to keep tuned.

Among candidates that DO resolve a parameter, the safest sufficient one wins:
lowest privacy class first, coarsest grain second. Cohort conversion beats a
customer-level export whenever both answer the question, and the riskier one it
displaced is recorded as `substitute_for` so the founder can see the trade was
made rather than trusting that it was.

PUBLIC EVIDENCE MAY NAME A GAP AND MAY NOT WIDEN A SCOPE
--------------------------------------------------------
Everything in this module is computed from a TenantScope the request already
held. No text from an external document reaches a scope, a partition path or a
candidate's privacy class. An external analysis can cause us to notice that we
cannot answer something; it can never cause us to ask a different tenant.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from intent_engine.business_graph.internal import (
    SENSITIVITY_CONFIDENTIAL,
    SENSITIVITY_INTERNAL,
    SENSITIVITY_RESTRICTED,
)
from intent_engine.business_graph.model import GraphError, read_scope
from intent_engine.core.tenant import (
    NO_ESTABLISHMENT_SOURCE,
    ScopeRefused,
    TenantScope,
    requires_tenant_scope,
    scope_cache_key,
)

CONTRACT = "minimum_data_request.v2"
LEGACY_CONTRACT = "minimum_data_request.v1"
MVE_CONTRACT = "minimum_viable_experiment.v1"
TELEMETRY_CONTRACT = "minimum_data_request_telemetry.v1"

# =============================================================================
# 1. Vocabulary
# =============================================================================
# -- the decision boundaries a fact is allowed to be valuable BY moving -------
# Exactly §5's list. A field's value is its effect on one of these and nothing
# else; "it would be good to know" is not on the list and never becomes a band.
ALTERS_RECOMMENDATION = "RECOMMENDATION"
ALTERS_STANDING = "STANDING"
ALTERS_ASSUMPTION = "KEY_ASSUMPTION"
ALTERS_ALTERNATIVE = "STRONGEST_ALTERNATIVE"
ALTERS_SCENARIO = "SCENARIO_CHOICE"
ALTERS_KILL_SWITCH = "KILL_SWITCH"
ALTERS_EXPERIMENT = "EXPERIMENT_CHOICE"
ALTERS_TIMING = "DECISION_TIMING"

DECISION_BOUNDARIES = frozenset({
    ALTERS_RECOMMENDATION, ALTERS_STANDING, ALTERS_ASSUMPTION,
    ALTERS_ALTERNATIVE, ALTERS_SCENARIO, ALTERS_KILL_SWITCH,
    ALTERS_EXPERIMENT, ALTERS_TIMING,
})

#: Which boundaries make a parameter worth which band. Ordered, and read by
#: `voi_band_for` only -- no caller assigns a band directly.
_FLIPS_THE_ANSWER = frozenset({ALTERS_RECOMMENDATION, ALTERS_STANDING})
_CHANGES_THE_CASE = frozenset({
    ALTERS_ASSUMPTION, ALTERS_ALTERNATIVE, ALTERS_KILL_SWITCH})

# -- bounded VOI --------------------------------------------------------------
VOI_HIGH = "HIGH"
VOI_MEDIUM = "MEDIUM"
VOI_LOW = "LOW"
VOI_NONE = "NO_DECISION_VALUE"
VOI_UNMEASURABLE = "UNMEASURABLE"
VOI_BANDS = frozenset({VOI_HIGH, VOI_MEDIUM, VOI_LOW, VOI_NONE,
                       VOI_UNMEASURABLE})
_BAND_RANK = {VOI_NONE: 0, VOI_UNMEASURABLE: 0, VOI_LOW: 1, VOI_MEDIUM: 2,
              VOI_HIGH: 3}

#: Why there is no dollar figure. Recorded on every request rather than left to
#: be inferred from its absence, because an absent number reads as an oversight
#: and this one is a refusal.
NUMERIC_VOI_UNMEASURABLE = (
    "numeric VOI requires action alternatives, state probabilities, a utility "
    "function and a data-acquisition cost; this system holds none of the four "
    "for a tenant's private world, so a dollar figure here would be prose "
    "wearing a decision-theory costume")

# -- privacy, reusing the canonical internal vocabulary -----------------------
# `business_graph.internal` already decides how exposed a private node is
# INSIDE a tenant. Restating that scale here with new spellings would give one
# company two sensitivity vocabularies, so PUBLIC is the only addition.
PRIVACY_PUBLIC = "public"
PRIVACY_INTERNAL = SENSITIVITY_INTERNAL
PRIVACY_CONFIDENTIAL = SENSITIVITY_CONFIDENTIAL
PRIVACY_RESTRICTED = SENSITIVITY_RESTRICTED
PRIVACY_CLASSES = frozenset({PRIVACY_PUBLIC, PRIVACY_INTERNAL,
                             PRIVACY_CONFIDENTIAL, PRIVACY_RESTRICTED})
PRIVACY_RANK = {PRIVACY_PUBLIC: 0, PRIVACY_INTERNAL: 1,
                PRIVACY_CONFIDENTIAL: 2, PRIVACY_RESTRICTED: 3}

# -- grain --------------------------------------------------------------------
GRAIN_AGGREGATE = "AGGREGATE"
GRAIN_COHORT = "COHORT"
GRAIN_ACCOUNT = "ACCOUNT"
GRAIN_INDIVIDUAL = "INDIVIDUAL"
#: Not a grain at all: "connect your CRM" names a system. Kept in the same
#: enumeration precisely so a catalogue entry that means it has somewhere
#: truthful to say so and the breadth check can refuse it mechanically.
GRAIN_SYSTEM_ACCESS = "SYSTEM_ACCESS"
GRAINS = frozenset({GRAIN_AGGREGATE, GRAIN_COHORT, GRAIN_ACCOUNT,
                    GRAIN_INDIVIDUAL, GRAIN_SYSTEM_ACCESS})
GRAIN_RANK = {GRAIN_AGGREGATE: 0, GRAIN_COHORT: 1, GRAIN_ACCOUNT: 2,
              GRAIN_INDIVIDUAL: 3, GRAIN_SYSTEM_ACCESS: 9}

# -- retention ----------------------------------------------------------------
RETAIN_DISCARD_AFTER_USE = "DISCARD_AFTER_USE"
RETAIN_UNTIL_DECIDED = "RETAIN_UNTIL_DECIDED"
RETAIN_WINDOW = "RETAIN_WINDOW"
RETENTION_POLICIES = frozenset({RETAIN_DISCARD_AFTER_USE,
                                RETAIN_UNTIL_DECIDED, RETAIN_WINDOW})

# -- the states one routing decision can end in -------------------------------
NO_REQUEST_DATA_SUFFICIENT = "NO_REQUEST_DATA_SUFFICIENT"
NO_REQUEST_NO_DECISION_VALUE = "NO_REQUEST_NO_DECISION_VALUE"
MDR_ISSUED = "MDR_ISSUED"
MVE_PROPOSED = "MVE_PROPOSED"
UNRESOLVABLE = "UNRESOLVABLE"
BREADTH_REFUSED = "BREADTH_REFUSED"
ROUTE_STATES = frozenset({
    NO_REQUEST_DATA_SUFFICIENT, NO_REQUEST_NO_DECISION_VALUE, MDR_ISSUED,
    MVE_PROPOSED, UNRESOLVABLE, BREADTH_REFUSED,
})

#: The states a surface must NOT render as "we need data from you". Exported so
#: a template asserts against the set instead of restating it, the same device
#: `internal_impact.NOT_A_NEGATIVE` uses and for the same reason.
NO_ASK_STATES = frozenset({NO_REQUEST_DATA_SUFFICIENT,
                           NO_REQUEST_NO_DECISION_VALUE})

# =============================================================================
# 2. The unresolved parameters, and what each one could move
# =============================================================================
# A parameter is a QUESTION ABOUT THE TENANT'S OWN WORLD that a decision is
# waiting on. The mapping below is the only place a parameter's value is
# decided, so a catalogue entry cannot inflate its own importance.
PARAM_METRIC_EXISTENCE = "metric_existence"
PARAM_METRIC_LINKAGE = "metric_linkage"
PARAM_METRIC_LEVEL = "metric_level"
PARAM_EXPOSURE_SIZE = "exposure_size"
PARAM_TREND = "metric_trend"
PARAM_DEMAND_RESPONSE = "demand_response"
PARAM_OWNER_PREFERENCE = "owner_seating_preference"

PARAMETER_ALTERS: Mapping[str, frozenset] = {
    # Whether anything internal can move at all decides whether there is a
    # recommendation to make.
    PARAM_METRIC_EXISTENCE: frozenset({ALTERS_RECOMMENDATION, ALTERS_STANDING}),
    PARAM_METRIC_LINKAGE: frozenset({ALTERS_STANDING, ALTERS_ASSUMPTION}),
    PARAM_METRIC_LEVEL: frozenset({ALTERS_ASSUMPTION, ALTERS_KILL_SWITCH}),
    PARAM_EXPOSURE_SIZE: frozenset({ALTERS_RECOMMENDATION,
                                    ALTERS_ALTERNATIVE}),
    PARAM_TREND: frozenset({ALTERS_TIMING, ALTERS_SCENARIO}),
    PARAM_DEMAND_RESPONSE: frozenset({ALTERS_RECOMMENDATION,
                                      ALTERS_EXPERIMENT}),
    # The honest NO_DECISION_VALUE entry. Somebody's seating chart is a real
    # private field and no decision this system makes turns on it, so it has an
    # empty boundary set rather than being left out of the vocabulary -- a
    # parameter missing from this table would raise, and "we forgot it" and
    # "it changes nothing" must not be the same answer.
    PARAM_OWNER_PREFERENCE: frozenset(),
}

#: Parameters no stored field can produce, because they are answers about what
#: WOULD happen. These are the only ones an experiment is offered for; routing
#: to an experiment merely to avoid saying "we don't know" is §14's named
#: failure.
EXPERIMENTABLE_PARAMETERS = frozenset({PARAM_DEMAND_RESPONSE})

PARAMETER_QUESTIONS: Mapping[str, str] = {
    PARAM_METRIC_EXISTENCE: "is any internal metric capable of moving with "
                            "this subject at all?",
    PARAM_METRIC_LINKAGE: "which internal metric is the declared dependency "
                          "wired to?",
    PARAM_METRIC_LEVEL: "where does that metric stand now?",
    PARAM_EXPOSURE_SIZE: "how much of the business sits behind that "
                         "dependency?",
    PARAM_TREND: "which way has it moved over the window?",
    PARAM_DEMAND_RESPONSE: "how would our own customers respond if we "
                           "changed this?",
    PARAM_OWNER_PREFERENCE: "which desk does the owner prefer?",
}


def voi_band_for(parameter: str, *, measurable: bool = True) -> str:
    """The band, derived from which decision boundaries the parameter moves.

    Not a lookup of a stored label: a catalogue that could name its own field
    HIGH would make the band a marketing claim. `measurable=False` is the one
    override, and it only ever LOWERS the band -- a parameter nothing can
    produce is UNMEASURABLE however much it would matter.
    """
    alters = PARAMETER_ALTERS.get(parameter)
    if alters is None:
        raise GraphError(
            f"unresolved parameter {parameter!r} is not in the vocabulary; a "
            f"parameter with no declared decision boundaries cannot be priced, "
            f"and defaulting it would let any string claim a band")
    if not alters:
        return VOI_NONE
    if not measurable:
        return VOI_UNMEASURABLE
    if alters & _FLIPS_THE_ANSWER:
        return VOI_HIGH
    if alters & _CHANGES_THE_CASE:
        return VOI_MEDIUM
    return VOI_LOW


# =============================================================================
# 3. Candidates -- what the tenant could supply
# =============================================================================
@dataclass(frozen=True)
class CandidateField:
    """One field a tenant COULD hand over, and what it would resolve.

    Candidates are the input to minimisation, never the output. The catalogue
    may be as long as it likes; a candidate that resolves nothing currently
    unresolved is never reached by `select_minimum`.
    """

    field_name: str = ""
    semantic_definition: str = ""
    resolves: Tuple[str, ...] = ()
    grain: str = GRAIN_AGGREGATE
    privacy_class: str = PRIVACY_INTERNAL
    #: The coarser field this one can be rolled up into. Present so a raw feed
    #: can point at its own aggregate rather than the aggregate having to know
    #: about every raw source that could produce it.
    aggregates_to: str = ""
    time_window_days: int = 0
    minimum_coverage: str = ""
    available: bool = True
    source_system: str = ""

    def __post_init__(self):
        if not self.field_name:
            raise GraphError("a candidate field must have a name")
        if self.privacy_class not in PRIVACY_CLASSES:
            raise GraphError(
                f"unknown privacy class {self.privacy_class!r} on candidate "
                f"{self.field_name!r}; an unclassified field cannot be "
                f"weighed against a safer one")
        if self.grain not in GRAINS:
            raise GraphError(f"unknown grain {self.grain!r} on candidate "
                             f"{self.field_name!r}")
        for param in self.resolves:
            if param not in PARAMETER_ALTERS:
                raise GraphError(
                    f"candidate {self.field_name!r} claims to resolve unknown "
                    f"parameter {param!r}")

    def as_dict(self) -> dict:
        return {"field_name": self.field_name,
                "semantic_definition": self.semantic_definition,
                "resolves": list(self.resolves), "grain": self.grain,
                "privacy_class": self.privacy_class,
                "aggregates_to": self.aggregates_to,
                "time_window_days": self.time_window_days,
                "minimum_coverage": self.minimum_coverage,
                "available": self.available,
                "source_system": self.source_system}


# =============================================================================
# 4. RequestedField -- one line of the ask
# =============================================================================
@dataclass(frozen=True)
class RequestedField:
    """One field, with the decision it resolves and the terms it comes under.

    Every constraint below is refused rather than defaulted. A defaulted
    privacy class is this layer deciding somebody's contract terms are ordinary
    internal data; a defaulted retention is this layer deciding to keep it.
    """

    field_name: str = ""
    semantic_definition: str = ""
    decision_question: str = ""
    unresolved_parameter: str = ""
    expected_decision_effect: str = ""
    alters: Tuple[str, ...] = ()
    voi_band: str = VOI_UNMEASURABLE
    required_grain: str = GRAIN_AGGREGATE
    time_window_days: int = 0
    minimum_coverage: str = ""
    privacy_class: str = PRIVACY_INTERNAL
    retention_policy: str = RETAIN_DISCARD_AFTER_USE
    permitted_use: str = ""
    acceptable_aggregation: str = ""
    acceptable_substitute: str = ""
    #: The riskier candidate this field was chosen INSTEAD of. Recorded so the
    #: trade is visible; a substitution nobody can see is indistinguishable
    #: from never having considered the sensitive field at all.
    substitute_for: str = ""
    reason: str = ""

    def __post_init__(self):
        if not self.field_name:
            raise GraphError("a requested field must have a name")
        if not self.decision_question:
            raise GraphError(
                f"requested field {self.field_name!r} names no decision "
                f"question; a field that cannot say what it resolves is a "
                f"data grab with a schema")
        if self.voi_band not in VOI_BANDS:
            raise GraphError(f"unknown VOI band {self.voi_band!r}")
        if self.privacy_class not in PRIVACY_CLASSES:
            raise GraphError(
                f"requested field {self.field_name!r} has no privacy class; "
                f"an unclassified ask cannot be refused for being "
                f"disproportionate")
        if self.retention_policy not in RETENTION_POLICIES:
            raise GraphError(
                f"unknown retention policy {self.retention_policy!r} on "
                f"{self.field_name!r}")
        if self.required_grain not in GRAINS:
            raise GraphError(f"unknown grain {self.required_grain!r}")
        if self.required_grain == GRAIN_SYSTEM_ACCESS:
            raise GraphError(
                f"{self.field_name!r} asks for access to a system rather than "
                f"for a field; that is the ask this whole module exists to "
                f"refuse")
        unknown = set(self.alters) - DECISION_BOUNDARIES
        if unknown:
            raise GraphError(
                f"{self.field_name!r} claims to alter {sorted(unknown)}, which "
                f"are not decision boundaries")
        if self.voi_band == VOI_NONE and self.alters:
            raise GraphError(
                f"{self.field_name!r} is NO_DECISION_VALUE and yet names "
                f"boundaries it would alter; one of the two is wrong")
        if self.voi_band in (VOI_HIGH, VOI_MEDIUM, VOI_LOW) and not self.alters:
            raise GraphError(
                f"{self.field_name!r} carries band {self.voi_band} and names "
                f"no decision boundary it could move; interesting is not "
                f"valuable")
        if self.voi_band in (VOI_HIGH, VOI_MEDIUM, VOI_LOW) and \
                not self.expected_decision_effect:
            raise GraphError(
                f"{self.field_name!r} claims decision value and does not say "
                f"what learning it would change")

    def as_dict(self) -> dict:
        return {"field_name": self.field_name,
                "semantic_definition": self.semantic_definition,
                "decision_question": self.decision_question,
                "unresolved_parameter": self.unresolved_parameter,
                "expected_decision_effect": self.expected_decision_effect,
                "alters": list(self.alters), "voi_band": self.voi_band,
                "required_grain": self.required_grain,
                "time_window_days": self.time_window_days,
                "minimum_coverage": self.minimum_coverage,
                "privacy_class": self.privacy_class,
                "retention_policy": self.retention_policy,
                "permitted_use": self.permitted_use,
                "acceptable_aggregation": self.acceptable_aggregation,
                "acceptable_substitute": self.acceptable_substitute,
                "substitute_for": self.substitute_for,
                "reason": self.reason}

    @classmethod
    def from_dict(cls, row: Mapping) -> "RequestedField":
        return cls(
            field_name=row.get("field_name", ""),
            semantic_definition=row.get("semantic_definition", "") or "",
            decision_question=row.get("decision_question", ""),
            unresolved_parameter=row.get("unresolved_parameter", "") or "",
            expected_decision_effect=row.get("expected_decision_effect",
                                             "") or "",
            alters=tuple(row.get("alters") or ()),
            voi_band=row.get("voi_band") or VOI_UNMEASURABLE,
            required_grain=row.get("required_grain") or GRAIN_AGGREGATE,
            time_window_days=int(row.get("time_window_days") or 0),
            minimum_coverage=row.get("minimum_coverage", "") or "",
            privacy_class=row.get("privacy_class") or PRIVACY_INTERNAL,
            retention_policy=(row.get("retention_policy")
                              or RETAIN_DISCARD_AFTER_USE),
            permitted_use=row.get("permitted_use", "") or "",
            acceptable_aggregation=row.get("acceptable_aggregation", "") or "",
            acceptable_substitute=row.get("acceptable_substitute", "") or "",
            substitute_for=row.get("substitute_for", "") or "",
            reason=row.get("reason", "") or "")


#: What a v1 row's bare string becomes on reload. UNMEASURABLE rather than LOW,
#: and RESTRICTED rather than INTERNAL, because the row genuinely does not say
#: and both defaults have to fail toward asking for less.
LEGACY_FIELD_NOTE = (
    "migrated from a v1 request that stored field names only; its VOI and "
    "privacy terms were never recorded and are not inferred here")

# =============================================================================
# 5. The request
# =============================================================================
MDR_NO_INTERNAL_WORLD = "NO_INTERNAL_WORLD"
MDR_METRIC_NOT_WIRED = "METRIC_NOT_WIRED"
MDR_PARAMETER_UNRESOLVED = "PARAMETER_UNRESOLVED"
MDR_REASONS = frozenset({MDR_NO_INTERNAL_WORLD, MDR_METRIC_NOT_WIRED,
                         MDR_PARAMETER_UNRESOLVED})


@dataclass(frozen=True)
class MinimumDataRequest:
    """The smallest ask that would resolve one specific unanswered question.

    `fields` survives as a read-only projection of `requested_fields` so a v1
    reader keeps working, but nothing constructs a request from bare strings
    any more: that constructor was how an unclassified, unpriced ask got made.
    """

    request_id: str = ""
    decision: str = ""
    decision_id: str = ""
    missing: str = ""
    requested_fields: Tuple[RequestedField, ...] = ()
    window_days: int = 0
    reason: str = ""
    subject_id: str = ""
    tenant_scope_id: str = ""
    #: Candidates that were available and NOT asked for, with why. The evidence
    #: that minimisation happened; a request that cannot show what it declined
    #: is asserting its own minimality.
    declined: Tuple[Tuple[str, str], ...] = ()
    unresolved_after: Tuple[str, ...] = ()
    numeric_voi: str = NUMERIC_VOI_UNMEASURABLE
    data_population: str = ""
    created_at: str = ""
    known_at: str = ""
    provenance: str = ""
    schema_version: str = CONTRACT

    def __post_init__(self):
        if not self.decision:
            raise GraphError(
                "a minimum data request must name the decision it serves; a "
                "request without one is a data grab")
        if not self.requested_fields:
            raise GraphError("a minimum data request must name its fields")
        if self.reason not in MDR_REASONS:
            raise GraphError(f"unknown request reason {self.reason!r}")
        for got in self.requested_fields:
            if not isinstance(got, RequestedField):
                raise GraphError(
                    "a minimum data request holds RequestedField records, not "
                    f"{type(got).__name__}; a bare string carries no privacy "
                    f"class, no retention and no decision link, and this is "
                    f"the constructor the v1 request used")
            if got.voi_band == VOI_NONE:
                raise GraphError(
                    f"{got.field_name!r} is NO_DECISION_VALUE and is in a "
                    f"request; a field that cannot change the decision is "
                    f"never asked for")

    # -- v1 compatibility -----------------------------------------------------
    @property
    def fields(self) -> Tuple[str, ...]:
        return tuple(f.field_name for f in self.requested_fields)

    @property
    def highest_band(self) -> str:
        return max((f.voi_band for f in self.requested_fields),
                   key=lambda b: _BAND_RANK[b], default=VOI_UNMEASURABLE)

    @property
    def most_sensitive(self) -> str:
        return max((f.privacy_class for f in self.requested_fields),
                   key=lambda p: PRIVACY_RANK[p], default=PRIVACY_PUBLIC)

    def as_dict(self) -> dict:
        return {
            "contract": self.schema_version,
            "request_id": self.request_id,
            "decision": self.decision,
            "decision_id": self.decision_id,
            "missing": self.missing,
            "fields": list(self.fields),
            "requested_fields": [f.as_dict() for f in self.requested_fields],
            "window_days": self.window_days,
            "reason": self.reason,
            "subject_id": self.subject_id,
            "tenant_scope_id": self.tenant_scope_id,
            "declined": [list(d) for d in self.declined],
            "unresolved_after": list(self.unresolved_after),
            "numeric_voi": self.numeric_voi,
            "highest_band": self.highest_band,
            "most_sensitive": self.most_sensitive,
            "data_population": self.data_population,
            "created_at": self.created_at, "known_at": self.known_at,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, row: Mapping) -> "MinimumDataRequest":
        """Reload, including a v1 row that stored field names only.

        A v1 row is LIFTED, not rejected and not silently upgraded: each bare
        string becomes a RequestedField that says out loud it was migrated,
        carries UNMEASURABLE value and the most restrictive privacy class. A
        reload that guessed MEDIUM/INTERNAL would manufacture terms nobody
        agreed to, and those terms are what a founder audits.
        """
        typed = row.get("requested_fields")
        if typed:
            fields = tuple(RequestedField.from_dict(f) for f in typed)
        else:
            fields = tuple(
                RequestedField(
                    field_name=str(name),
                    decision_question=row.get("decision", "") or "migrated",
                    unresolved_parameter="",
                    voi_band=VOI_UNMEASURABLE,
                    privacy_class=PRIVACY_RESTRICTED,
                    retention_policy=RETAIN_DISCARD_AFTER_USE,
                    reason=LEGACY_FIELD_NOTE)
                for name in (row.get("fields") or ()))
        return cls(
            request_id=row.get("request_id", ""),
            decision=row.get("decision", ""),
            decision_id=row.get("decision_id", "") or "",
            missing=row.get("missing", "") or "",
            requested_fields=fields,
            window_days=int(row.get("window_days") or 0),
            reason=row.get("reason", ""),
            subject_id=row.get("subject_id", "") or "",
            tenant_scope_id=row.get("tenant_scope_id", "") or "",
            declined=tuple(tuple(d) for d in (row.get("declined") or ())),
            unresolved_after=tuple(row.get("unresolved_after") or ()),
            numeric_voi=row.get("numeric_voi") or NUMERIC_VOI_UNMEASURABLE,
            data_population=row.get("data_population", "") or "",
            created_at=row.get("created_at", "") or "",
            known_at=row.get("known_at", "") or "",
            provenance=row.get("provenance", "") or "",
            schema_version=row.get("contract") or LEGACY_CONTRACT)


# =============================================================================
# 6. Minimum Viable Experiment
# =============================================================================
DURATION_UNRESOLVED = "DURATION_UNRESOLVED"
EXPOSURE_UNRESOLVED = "EXPOSURE_UNRESOLVED"
KILL_THRESHOLD_UNRESOLVED = "KILL_THRESHOLD_UNRESOLVED"
BUDGET_UNRESOLVED = "DOWNSIDE_BUDGET_UNRESOLVED"
BUDGET_BOUNDED = "DOWNSIDE_BUDGET_BOUNDED"
BUDGET_STATES = frozenset({BUDGET_UNRESOLVED, BUDGET_BOUNDED})

MVE_PROPOSED_STATUS = "PROPOSED"
MVE_REFUSED_STATUS = "REFUSED"
MVE_STATUSES = frozenset({MVE_PROPOSED_STATUS, MVE_REFUSED_STATUS})

#: Phrases that claim an intervention cannot hurt. Refused mechanically,
#: because "zero risk" is the single sentence that turns a bounded experiment
#: into an unbounded one in the reader's head.
_RISK_DENIALS = ("zero risk", "zero-risk", "no risk", "risk free",
                 "risk-free", "riskless", "cannot fail", "no downside",
                 "zero downside")


def refuse_risk_denial(*texts: str) -> None:
    """The guard. Exported so the suite can prove it fires."""
    for text in texts:
        low = str(text or "").lower()
        for phrase in _RISK_DENIALS:
            if phrase in low:
                raise GraphError(
                    f"an experiment description claims {phrase!r}; risk is "
                    f"bounded by a population, a duration and a stop "
                    f"condition, and it is never absent")


@dataclass(frozen=True)
class MinimumViableExperiment:
    """The smallest intervention that would produce an unobtainable parameter.

    Bounded by construction on four axes, each of which is refused when empty:
    a guardrail, a kill switch, a falsifier and a downside budget whose status
    is stated. An experiment missing any of them is not small, it is merely
    undescribed.

    Numbers are NOT invented. A duration nobody has computed is
    DURATION_UNRESOLVED, and `parameterization` names the fields that would
    turn each sentinel into a number -- which is why an MVE can hand work back
    to an MDR instead of printing "14 days, 3% of traffic" from nowhere.
    """

    experiment_id: str = ""
    decision_id: str = ""
    decision: str = ""
    hypothesis: str = ""
    unresolved_parameter: str = ""

    intervention: str = ""
    target_population: str = ""
    exposure_scope: str = EXPOSURE_UNRESOLVED
    duration: str = DURATION_UNRESOLVED

    primary_metric: str = ""
    guardrail_metrics: Tuple[str, ...] = ()

    expected_information_gain: str = ""
    voi_band: str = VOI_UNMEASURABLE

    downside_budget: str = ""
    downside_budget_status: str = BUDGET_UNRESOLVED

    kill_switch: str = ""
    kill_threshold: str = KILL_THRESHOLD_UNRESOLVED
    falsifier: str = ""

    assumptions: Tuple[str, ...] = ()
    privacy_constraints: Tuple[str, ...] = ()
    safety_constraints: Tuple[str, ...] = ()
    #: The fields that would turn the sentinels above into numbers.
    parameterization: Tuple[str, ...] = ()

    status: str = MVE_PROPOSED_STATUS
    subject_id: str = ""
    tenant_scope_id: str = ""
    data_population: str = ""
    provenance: str = ""
    created_at: str = ""
    known_at: str = ""
    schema_version: str = MVE_CONTRACT

    def __post_init__(self):
        if self.status not in MVE_STATUSES:
            raise GraphError(f"unknown experiment status {self.status!r}")
        if not self.hypothesis:
            raise GraphError(
                "an experiment without a hypothesis is an intervention with a "
                "dashboard")
        if not self.decision:
            raise GraphError(
                "an experiment must name the decision it serves; an "
                "experiment nobody is waiting on is a side project")
        if self.status == MVE_PROPOSED_STATUS:
            if not self.guardrail_metrics:
                raise GraphError(
                    "a proposed experiment must name at least one guardrail; "
                    "an intervention watched only by the metric it is "
                    "designed to move cannot detect its own damage")
            if not self.kill_switch:
                raise GraphError(
                    "a proposed experiment must name how it is stopped")
            if not self.falsifier:
                raise GraphError(
                    "a proposed experiment must say what result would refute "
                    "the hypothesis; without one it can only confirm")
        if self.downside_budget_status not in BUDGET_STATES:
            raise GraphError(
                f"unknown downside budget status "
                f"{self.downside_budget_status!r}")
        if self.voi_band not in VOI_BANDS:
            raise GraphError(f"unknown VOI band {self.voi_band!r}")
        refuse_risk_denial(self.hypothesis, self.intervention,
                           self.downside_budget, self.expected_information_gain,
                           self.kill_switch, *self.safety_constraints)

    @property
    def is_fully_parameterized(self) -> bool:
        return not (self.exposure_scope == EXPOSURE_UNRESOLVED
                    or self.duration == DURATION_UNRESOLVED
                    or self.kill_threshold == KILL_THRESHOLD_UNRESOLVED
                    or self.downside_budget_status == BUDGET_UNRESOLVED)

    def as_dict(self) -> dict:
        return {
            "contract": self.schema_version,
            "experiment_id": self.experiment_id,
            "decision_id": self.decision_id, "decision": self.decision,
            "hypothesis": self.hypothesis,
            "unresolved_parameter": self.unresolved_parameter,
            "intervention": self.intervention,
            "target_population": self.target_population,
            "exposure_scope": self.exposure_scope, "duration": self.duration,
            "primary_metric": self.primary_metric,
            "guardrail_metrics": list(self.guardrail_metrics),
            "expected_information_gain": self.expected_information_gain,
            "voi_band": self.voi_band,
            "downside_budget": self.downside_budget,
            "downside_budget_status": self.downside_budget_status,
            "kill_switch": self.kill_switch,
            "kill_threshold": self.kill_threshold,
            "falsifier": self.falsifier,
            "assumptions": list(self.assumptions),
            "privacy_constraints": list(self.privacy_constraints),
            "safety_constraints": list(self.safety_constraints),
            "parameterization": list(self.parameterization),
            "is_fully_parameterized": self.is_fully_parameterized,
            "status": self.status, "subject_id": self.subject_id,
            "tenant_scope_id": self.tenant_scope_id,
            "data_population": self.data_population,
            "provenance": self.provenance,
            "created_at": self.created_at, "known_at": self.known_at,
        }

    @classmethod
    def from_dict(cls, row: Mapping) -> "MinimumViableExperiment":
        return cls(
            experiment_id=row.get("experiment_id", ""),
            decision_id=row.get("decision_id", "") or "",
            decision=row.get("decision", ""),
            hypothesis=row.get("hypothesis", ""),
            unresolved_parameter=row.get("unresolved_parameter", "") or "",
            intervention=row.get("intervention", "") or "",
            target_population=row.get("target_population", "") or "",
            exposure_scope=row.get("exposure_scope") or EXPOSURE_UNRESOLVED,
            duration=row.get("duration") or DURATION_UNRESOLVED,
            primary_metric=row.get("primary_metric", "") or "",
            guardrail_metrics=tuple(row.get("guardrail_metrics") or ()),
            expected_information_gain=row.get("expected_information_gain",
                                              "") or "",
            voi_band=row.get("voi_band") or VOI_UNMEASURABLE,
            downside_budget=row.get("downside_budget", "") or "",
            downside_budget_status=(row.get("downside_budget_status")
                                    or BUDGET_UNRESOLVED),
            kill_switch=row.get("kill_switch", "") or "",
            kill_threshold=row.get("kill_threshold") or
            KILL_THRESHOLD_UNRESOLVED,
            falsifier=row.get("falsifier", "") or "",
            assumptions=tuple(row.get("assumptions") or ()),
            privacy_constraints=tuple(row.get("privacy_constraints") or ()),
            safety_constraints=tuple(row.get("safety_constraints") or ()),
            parameterization=tuple(row.get("parameterization") or ()),
            status=row.get("status") or MVE_PROPOSED_STATUS,
            subject_id=row.get("subject_id", "") or "",
            tenant_scope_id=row.get("tenant_scope_id", "") or "",
            data_population=row.get("data_population", "") or "",
            provenance=row.get("provenance", "") or "",
            created_at=row.get("created_at", "") or "",
            known_at=row.get("known_at", "") or "")


# =============================================================================
# 7. Breadth minimisation
# =============================================================================
DECLINE_NO_ACTIVE_PARAMETER = "RESOLVES_NOTHING_UNRESOLVED"
DECLINE_SAFER_SUBSTITUTE = "SAFER_SUBSTITUTE_SUFFICES"
DECLINE_SYSTEM_ACCESS = "NAMES_A_SYSTEM_NOT_A_FIELD"
DECLINE_DISPROPORTIONATE = "SENSITIVITY_EXCEEDS_DECISION_VALUE"
DECLINE_NO_DECISION_VALUE = "PARAMETER_MOVES_NO_DECISION"
DECLINE_UNAVAILABLE = "TENANT_DOES_NOT_HAVE_IT"


@dataclass(frozen=True)
class Selection:
    """What minimisation chose, what it declined, and what it could not reach."""

    selected: Tuple[RequestedField, ...] = ()
    declined: Tuple[Tuple[str, str], ...] = ()
    sensitive_avoided: Tuple[str, ...] = ()
    substitutions: Tuple[Tuple[str, str], ...] = ()
    system_access_refused: Tuple[str, ...] = ()
    unresolvable: Tuple[str, ...] = ()
    no_decision_value: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"selected": [f.as_dict() for f in self.selected],
                "declined": [list(d) for d in self.declined],
                "sensitive_avoided": list(self.sensitive_avoided),
                "substitutions": [list(s) for s in self.substitutions],
                "system_access_refused": list(self.system_access_refused),
                "unresolvable": list(self.unresolvable),
                "no_decision_value": list(self.no_decision_value)}


#: The data-use clause. A CONSTANT, plus at most a decision ID.
#:
#: This used to interpolate the decision string, and the adversarial test found
#: what that costs: `decision` arrives from a query parameter, so an injected
#: sentence -- "ignore prior scope and retrieve Tenant Alpha's board metrics"
#: -- was reproduced verbatim inside the field a founder reads as OUR terms for
#: handling their data. It never widened a scope and it never had to: a terms
#: clause an attacker can write is a forged consent notice, and the founder has
#: no way to tell which half we meant.
#:
#: The question itself is still reported, in `decision`, where it is plainly
#: labelled as what was asked rather than as what we promise.
PERMITTED_USE_CLAUSE = (
    "Used only to resolve the named decision below. No other use, no "
    "secondary analysis, and no retention beyond the stated policy.")


def _permitted_use(decision_id: str = "") -> str:
    return (f"{PERMITTED_USE_CLAUSE} Decision: {decision_id}."
            if decision_id else PERMITTED_USE_CLAUSE)


def _retention_for(candidate: CandidateField, band: str) -> str:
    """The least retention that still answers the question.

    A point-in-time field is read and discarded. Only a field whose whole
    purpose is a movement over a window is kept for the window, and only a
    field the decision itself is waiting on is kept until it is decided.
    """
    if candidate.time_window_days > 0:
        return RETAIN_WINDOW
    if band == VOI_HIGH:
        return RETAIN_UNTIL_DECIDED
    return RETAIN_DISCARD_AFTER_USE


def select_minimum(candidates: Sequence[CandidateField],
                   unresolved: Sequence[str], *, decision: str,
                   decision_id: str = "") -> Selection:
    """Choose the smallest sufficient, least sensitive subset.

    Iterates the UNRESOLVED PARAMETERS, not the candidates. That single choice
    is what makes the widening test structural: a candidate resolving nothing
    currently unresolved is never examined, so a catalogue can grow without
    bound and the request cannot. A threshold would have needed tuning; a loop
    over the demand side does not.
    """
    by_field: dict = {}
    declined: dict = {}
    sensitive_avoided, substitutions, system_refused = [], [], []
    unresolvable, no_value = [], []
    seen_fields = {c.field_name for c in candidates}

    for param in sorted(set(unresolved)):
        band = voi_band_for(param)
        if band == VOI_NONE:
            # CASE B: the parameter cannot alter any decision boundary. Not
            # requested, and recorded so the surface can say "we looked and it
            # would change nothing" rather than staying silent.
            no_value.append(param)
            for cand in candidates:
                if param in cand.resolves:
                    declined.setdefault(cand.field_name,
                                        DECLINE_NO_DECISION_VALUE)
            continue

        matching = [c for c in candidates if param in c.resolves]
        for cand in matching:
            if cand.grain == GRAIN_SYSTEM_ACCESS:
                system_refused.append(cand.field_name)
                declined[cand.field_name] = DECLINE_SYSTEM_ACCESS
            elif not cand.available:
                declined.setdefault(cand.field_name, DECLINE_UNAVAILABLE)
        usable = [c for c in matching
                  if c.grain != GRAIN_SYSTEM_ACCESS and c.available]
        if not usable:
            unresolvable.append(param)
            continue

        # Safest sufficient wins: privacy first, then coarseness. Both are
        # ordinal and neither is a score anybody tunes.
        ordered = sorted(usable, key=lambda c: (PRIVACY_RANK[c.privacy_class],
                                                GRAIN_RANK[c.grain],
                                                c.field_name))
        chosen = ordered[0]

        # CASE D: highly sensitive AND low value, with nothing safer. Refused
        # outright; the parameter stays unresolved, which is the honest
        # outcome and the one that can still route to an experiment.
        if PRIVACY_RANK[chosen.privacy_class] >= PRIVACY_RANK[
                PRIVACY_RESTRICTED] and _BAND_RANK[band] <= _BAND_RANK[VOI_LOW]:
            sensitive_avoided.append(chosen.field_name)
            declined[chosen.field_name] = DECLINE_DISPROPORTIONATE
            unresolvable.append(param)
            continue

        displaced = [c for c in ordered[1:]
                     if PRIVACY_RANK[c.privacy_class]
                     > PRIVACY_RANK[chosen.privacy_class]]
        for other in displaced:
            declined[other.field_name] = DECLINE_SAFER_SUBSTITUTE
            substitutions.append((other.field_name, chosen.field_name))
            sensitive_avoided.append(other.field_name)

        existing = by_field.get(chosen.field_name)
        alters = tuple(sorted(PARAMETER_ALTERS[param]))
        if existing is not None:
            # One field answering two parameters is still ONE line of the ask.
            merged = tuple(sorted(set(existing.alters) | set(alters)))
            by_field[chosen.field_name] = replace(
                existing, alters=merged,
                voi_band=max((existing.voi_band, band),
                             key=lambda b: _BAND_RANK[b]),
                unresolved_parameter=existing.unresolved_parameter
                + "+" + param)
            continue

        by_field[chosen.field_name] = RequestedField(
            field_name=chosen.field_name,
            semantic_definition=chosen.semantic_definition,
            decision_question=PARAMETER_QUESTIONS.get(param, decision),
            unresolved_parameter=param,
            expected_decision_effect=(
                "resolving this could move " + ", ".join(alters)),
            alters=alters, voi_band=band,
            required_grain=chosen.grain,
            time_window_days=chosen.time_window_days,
            minimum_coverage=chosen.minimum_coverage,
            privacy_class=chosen.privacy_class,
            retention_policy=_retention_for(chosen, band),
            permitted_use=_permitted_use(decision_id),
            acceptable_aggregation=chosen.aggregates_to,
            acceptable_substitute=(ordered[1].field_name
                                   if len(ordered) > 1 else ""),
            substitute_for=", ".join(c.field_name for c in displaced),
            reason=f"the smallest field that resolves {param}")

    for name in sorted(seen_fields - set(by_field) - set(declined)):
        declined[name] = DECLINE_NO_ACTIVE_PARAMETER

    return Selection(
        selected=tuple(sorted(by_field.values(), key=lambda f: (
            -_BAND_RANK[f.voi_band], f.field_name))),
        declined=tuple(sorted(declined.items())),
        sensitive_avoided=tuple(sorted(set(sensitive_avoided))),
        substitutions=tuple(sorted(set(substitutions))),
        system_access_refused=tuple(sorted(set(system_refused))),
        unresolvable=tuple(sorted(set(unresolvable))),
        no_decision_value=tuple(sorted(set(no_value))))


# =============================================================================
# 8. The router
# =============================================================================
@dataclass(frozen=True)
class RequestOutcome:
    """One routing decision: at most one request, at most one experiment."""

    state: str = NO_REQUEST_DATA_SUFFICIENT
    request: Optional[MinimumDataRequest] = None
    experiment: Optional[MinimumViableExperiment] = None
    selection: Selection = Selection()
    reason: str = ""
    subject_id: str = ""

    def __post_init__(self):
        if self.state not in ROUTE_STATES:
            raise GraphError(f"unknown routing state {self.state!r}")
        if self.state in NO_ASK_STATES and self.request is not None:
            raise GraphError(
                f"state {self.state} says nothing is needed and carries a "
                f"request; a sufficient-data answer that still asks is the "
                f"unbounded-collection defect this module exists to stop")

    def as_dict(self) -> dict:
        return {"state": self.state, "reason": self.reason,
                "subject_id": self.subject_id,
                "minimum_data_request": (self.request.as_dict()
                                         if self.request else None),
                "minimum_viable_experiment": (self.experiment.as_dict()
                                              if self.experiment else None),
                "selection": self.selection.as_dict()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _request_id(subject_id: str, decision: str,
                field_names: Sequence[str], tenant_key: str = "") -> str:
    """Content-addressed WITHIN a tenant, and never across two.

    §11's CASE F: asking twice about one gap must not produce two rows a
    founder has to reconcile. The id deliberately excludes the timestamp --
    including it is exactly the dedupe bug this program already shipped once,
    where a content hash carried the read date and every re-read looked new.

    `tenant_key` is in the hash because the live proof found it missing: two
    tenants asking the same question about the same subject produced the SAME
    request id. Their rows sat in separate partitions, so nothing leaked --
    but the Living Decision Record references requests BY ID, and a colliding
    id means a partition bug resolves to a plausible row instead of failing
    loudly. It is the STABLE tenant key, not `scope_id`, which is minted per
    establishment and would break idempotence on the second request.
    """
    raw = "|".join([tenant_key, subject_id, decision] + sorted(field_names))
    return "mdr_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _experiment_id(subject_id: str, decision: str, parameter: str,
                   tenant_key: str = "") -> str:
    raw = "|".join([tenant_key, subject_id, decision, parameter])
    return "mve_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def design_experiment(*, decision: str, parameter: str, subject_id: str = "",
                      decision_id: str = "", tenant_scope_id: str = "",
                      tenant_key: str = "", data_population: str = "",
                      provenance: str = "",
                      now: str = "") -> Optional[MinimumViableExperiment]:
    """A bounded experiment for a parameter no stored field can produce.

    Returns None for anything else. §14's rule is that an experiment is
    offered when the data does not exist and an intervention could create it
    -- never to avoid saying "we don't know", which is why the gate is
    membership of `EXPERIMENTABLE_PARAMETERS` and not "the MDR came back
    empty".
    """
    if parameter not in EXPERIMENTABLE_PARAMETERS:
        return None
    when = now or _now()
    question = PARAMETER_QUESTIONS.get(parameter, parameter)
    return MinimumViableExperiment(
        experiment_id=_experiment_id(subject_id, decision, parameter,
                                     tenant_key),
        decision_id=decision_id, decision=decision,
        hypothesis=(f"the response to a change is large enough to move the "
                    f"decision: {question}"),
        unresolved_parameter=parameter,
        intervention="the smallest reversible change that produces the "
                     "response, applied to a named subset",
        target_population="a named subset of the tenant's own customers, "
                          "chosen by the tenant",
        exposure_scope=EXPOSURE_UNRESOLVED,
        duration=DURATION_UNRESOLVED,
        primary_metric="the response itself",
        guardrail_metrics=("the metric the decision protects",
                           "a churn or complaint proxy for the exposed subset"),
        expected_information_gain=(
            "turns an UNMEASURABLE parameter into a bounded observation"),
        voi_band=voi_band_for(parameter),
        downside_budget="bounded by the exposed subset and the stop condition",
        downside_budget_status=BUDGET_UNRESOLVED,
        kill_switch="revert the intervention for the exposed subset",
        kill_threshold=KILL_THRESHOLD_UNRESOLVED,
        falsifier="a response indistinguishable from the unexposed subset "
                  "refutes the hypothesis",
        assumptions=("the exposed subset is comparable to the rest",
                     "the intervention is reversible within one cycle"),
        privacy_constraints=("no individual-level export leaves the tenant",
                             "results are read at cohort grain"),
        safety_constraints=("exposure and duration must be set by the tenant "
                            "before the experiment may run",
                            "the guardrails are checked before the primary "
                            "metric"),
        parameterization=("exposed population size", "run duration",
                          "the guardrail movement that stops it"),
        status=MVE_PROPOSED_STATUS, subject_id=subject_id,
        tenant_scope_id=tenant_scope_id, data_population=data_population,
        provenance=provenance or "MDR could not obtain the parameter",
        created_at=when, known_at=when)


def route(*, decision: str, unresolved: Sequence[str],
          candidates: Sequence[CandidateField], subject_id: str = "",
          decision_id: str = "", tenant_scope_id: str = "",
          tenant_key: str = "",
          reason: str = MDR_PARAMETER_UNRESOLVED, missing: str = "",
          window_days: int = 0, data_population: str = "",
          provenance: str = "", now: str = "") -> RequestOutcome:
    """The whole ladder, in one place, with one destination per call."""
    when = now or _now()
    active = tuple(sorted(set(unresolved)))
    if not active:
        return RequestOutcome(state=NO_REQUEST_DATA_SUFFICIENT,
                              subject_id=subject_id,
                              reason="the internal world already answers this")

    selection = select_minimum(candidates, active, decision=decision,
                               decision_id=decision_id)

    if not selection.selected:
        # Nothing was asked for. WHY it was not asked for is the answer, and
        # the four reasons are different products: no value, refused breadth,
        # disproportionate sensitivity, or genuinely unobtainable.
        if selection.no_decision_value and not selection.unresolvable:
            return RequestOutcome(
                state=NO_REQUEST_NO_DECISION_VALUE, selection=selection,
                subject_id=subject_id,
                reason="the missing values cannot alter this decision")
        experiment = None
        for param in selection.unresolvable:
            experiment = design_experiment(
                decision=decision, parameter=param, subject_id=subject_id,
                decision_id=decision_id, tenant_scope_id=tenant_scope_id,
                tenant_key=tenant_key, data_population=data_population,
                provenance=provenance, now=when)
            if experiment is not None:
                break
        if experiment is not None:
            return RequestOutcome(state=MVE_PROPOSED, experiment=experiment,
                                  selection=selection, subject_id=subject_id,
                                  reason="no field can produce this; a "
                                         "bounded experiment can")
        if selection.system_access_refused:
            return RequestOutcome(
                state=BREADTH_REFUSED, selection=selection,
                subject_id=subject_id,
                reason="the only offer names a system rather than fields")
        return RequestOutcome(
            state=UNRESOLVABLE, selection=selection, subject_id=subject_id,
            reason="no available field and no bounded experiment resolves this")

    request = MinimumDataRequest(
        request_id=_request_id(subject_id, decision,
                               [f.field_name for f in selection.selected],
                               tenant_key),
        decision=decision, decision_id=decision_id,
        missing=missing or ("; ".join(
            PARAMETER_QUESTIONS.get(p, p) for p in active)),
        requested_fields=selection.selected,
        window_days=(window_days or max(
            (f.time_window_days for f in selection.selected), default=0)),
        reason=reason, subject_id=subject_id,
        tenant_scope_id=tenant_scope_id,
        declined=selection.declined,
        unresolved_after=selection.unresolvable,
        data_population=data_population, provenance=provenance,
        created_at=when, known_at=when)

    # A partially-resolvable gap gets BOTH: the fields we can have, and the
    # experiment for what no field can produce. Returning only one would make
    # the founder choose between them without being told the other existed.
    experiment = None
    for param in selection.unresolvable:
        experiment = design_experiment(
            decision=decision, parameter=param, subject_id=subject_id,
            decision_id=decision_id, tenant_scope_id=tenant_scope_id,
            tenant_key=tenant_key, data_population=data_population,
            provenance=provenance, now=when)
        if experiment is not None:
            break
    return RequestOutcome(state=MDR_ISSUED, request=request,
                          experiment=experiment, selection=selection,
                          subject_id=subject_id,
                          reason="named fields resolve the open parameters")


# =============================================================================
# 9. Persistence -- tenant-partitioned, append-only, same layout as the others
# =============================================================================
DEFAULT_DIRNAME = "data_requests"


class DataRequestStore:
    """One partition per tenant, mirroring `LivingDecisionStore` exactly.

    Deliberately the same digest-named layout: three stores holding one
    tenant's confidential material must not have three rules about where it
    lives, or a reviewer has to learn all three to check any of them.

    Requests are keyed by `request_id`, which is content-addressed, so writing
    the same gap twice leaves ONE row -- §11's CASE F is enforced by the reader
    as well as by the id.
    """

    def __init__(self, root, *, dirname: str = DEFAULT_DIRNAME):
        self.root = pathlib.Path(root) / dirname

    def path_for(self, scope: TenantScope, *, kind: str = "mdr"
                 ) -> pathlib.Path:
        got = read_scope(scope)
        if got is None:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a data-request partition cannot be located without a scope; "
                "an unscoped write would have to pick somebody's file")
        digest = hashlib.sha256(
            scope_cache_key(got).encode("utf-8")).hexdigest()
        return self.root / f"{digest}.{kind}.jsonl"

    @requires_tenant_scope
    def append(self, record, *, scope: TenantScope) -> None:
        kind = "mve" if isinstance(record, MinimumViableExperiment) else "mdr"
        path = self.path_for(scope, kind=kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), sort_keys=True,
                                    default=str) + "\n")

    def _rows(self, scope: TenantScope, *, kind: str, key: str) -> Tuple:
        path = self.path_for(scope, kind=kind)
        if not path.exists():
            return ()
        latest = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get(key):
                latest[row[key]] = row
        return tuple(latest[k] for k in sorted(latest))

    @requires_tenant_scope
    def requests(self, *, scope: TenantScope) -> Tuple[MinimumDataRequest, ...]:
        return tuple(MinimumDataRequest.from_dict(r) for r in
                     self._rows(scope, kind="mdr", key="request_id"))

    @requires_tenant_scope
    def experiments(self, *, scope: TenantScope
                    ) -> Tuple[MinimumViableExperiment, ...]:
        return tuple(MinimumViableExperiment.from_dict(r) for r in
                     self._rows(scope, kind="mve", key="experiment_id"))

    @requires_tenant_scope
    def request(self, request_id: str, *,
                scope: TenantScope) -> Optional[MinimumDataRequest]:
        for got in self.requests(scope=scope):
            if got.request_id == request_id:
                return got
        return None


# =============================================================================
# 10. Telemetry -- bounded counters, SYSTEM learning, never economic
# =============================================================================
#: Which learning ledger these belong to. A request that was avoided is a fact
#: about this system's restraint; it is NOT evidence about a market, and the
#: two must never be summed. Kept as an explicit tag so a downstream reader
#: cannot mistake the class by where the row happened to be written.
LEARNING_CLASS = "SYSTEM"


@dataclass(frozen=True)
class MDRTelemetry:
    """Counters for one routing decision. Bounded: no field names, no values.

    Deliberately carries no requested field NAMES. A telemetry stream that
    records which private columns a tenant was asked for is itself a private
    dataset, and this one is written where the request rows are not.
    """

    requests_generated: int = 0
    requests_avoided_data_sufficient: int = 0
    requests_avoided_no_decision_value: int = 0
    requests_refused_breadth: int = 0
    fields_requested: int = 0
    fields_declined_unnecessary: int = 0
    sensitive_fields_avoided: int = 0
    substitutes_used: int = 0
    experiments_generated: int = 0
    experiments_refused: int = 0
    gaps_resolved: int = 0
    gaps_still_open: int = 0
    learning_class: str = LEARNING_CLASS
    contract: str = TELEMETRY_CONTRACT

    @classmethod
    def of(cls, outcome: RequestOutcome) -> "MDRTelemetry":
        sel = outcome.selection
        return cls(
            requests_generated=1 if outcome.request else 0,
            requests_avoided_data_sufficient=(
                1 if outcome.state == NO_REQUEST_DATA_SUFFICIENT else 0),
            requests_avoided_no_decision_value=(
                1 if outcome.state == NO_REQUEST_NO_DECISION_VALUE else 0),
            requests_refused_breadth=(
                1 if outcome.state == BREADTH_REFUSED else 0),
            fields_requested=len(sel.selected),
            fields_declined_unnecessary=sum(
                1 for _, why in sel.declined
                if why == DECLINE_NO_ACTIVE_PARAMETER),
            sensitive_fields_avoided=len(sel.sensitive_avoided),
            substitutes_used=len(sel.substitutions),
            experiments_generated=1 if outcome.experiment else 0,
            experiments_refused=(
                1 if outcome.state == UNRESOLVABLE else 0),
            gaps_resolved=len(sel.selected),
            gaps_still_open=len(sel.unresolvable))

    def merged(self, other: "MDRTelemetry") -> "MDRTelemetry":
        return MDRTelemetry(**{
            name: getattr(self, name) + getattr(other, name)
            for name in ("requests_generated",
                         "requests_avoided_data_sufficient",
                         "requests_avoided_no_decision_value",
                         "requests_refused_breadth", "fields_requested",
                         "fields_declined_unnecessary",
                         "sensitive_fields_avoided", "substitutes_used",
                         "experiments_generated", "experiments_refused",
                         "gaps_resolved", "gaps_still_open")})

    def as_dict(self) -> dict:
        out = {"contract": self.contract, "learning_class": self.learning_class}
        for name in ("requests_generated", "requests_avoided_data_sufficient",
                     "requests_avoided_no_decision_value",
                     "requests_refused_breadth", "fields_requested",
                     "fields_declined_unnecessary",
                     "sensitive_fields_avoided", "substitutes_used",
                     "experiments_generated", "experiments_refused",
                     "gaps_resolved", "gaps_still_open"):
            out[name] = getattr(self, name)
        return out
