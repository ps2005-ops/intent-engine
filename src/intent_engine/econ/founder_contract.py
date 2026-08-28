"""§4-§8/§13/§17: what a founder surface is allowed to be told about the economy.

WHY A SECOND CONTRACT WHEN `econ_context.v1` ALREADY EXISTS
-----------------------------------------------------------
`econ_context.v1` carries READINGS: conditions, directions, dates. A reading is
not a decision, and a product that renders readings is a macro dashboard. What
the founder engine owes its reader is the DECISION consequence — whether the
economic state changes what this company should do, and, just as often, that it
does not.

That verdict cannot be recomputed per surface. Sixty offline comparisons put
40% of the mass in a material delta and 60% in a deliberate abstention, and a
brief that recomputes materiality from prose while the full analysis reads the
structured fields is how the two came to disagree before. So the verdict is
computed once, into this object, and every surface renders THIS.

WHAT IS DELIBERATELY EXCLUDED, AND ENFORCED RATHER THAN DOCUMENTED
------------------------------------------------------------------
    * unsupported collective-human constructs. Zero are PROMOTED; the register
      is FROZEN_CANDIDATE. `refuse_human_constructs` is called from
      `__post_init__`, so a caller cannot pass one in by mistake.
    * rehearsal expectations. REHEARSAL exists to prove the forward machinery
      can score itself on history. It is not a track record and may never
      contribute to a customer-facing accuracy figure — §14. The guard is on
      the CONTRACT, not on the renderer, because a renderer guard protects one
      surface and there are five.
    * tenant-private evidence. The shared state is public by construction and
      this object is built from it.
    * internal debugging artifacts. `provenance` carries source, observation,
      as_of and evidence type; it does not carry the engine's diary.

STALENESS IS A DECISION INPUT, NOT A BADGE
------------------------------------------
§17. A state old enough to be STALE cannot support a HIGH-confidence delta, so
`freshness` is consulted where confidence is set rather than printed beside it.
`DecisionDamage(kind="STALE_STATE")` already existed offline for exactly this;
this is the same rule on the product path.

FAILURE SEMANTICS SURVIVE (§5)
------------------------------
Seven states, and the two that matter most are the two that look like nothing:
NO_MATERIAL_ECONOMIC_DELTA means the engine read the economy and decided it
does not bear on this decision, and BLOCKED_DATA means it could not read it at
all. Collapsing either into a missing section is the defect this vocabulary
exists to prevent — a reader cannot act on a blank.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "founder_economic_context.v1"

# --- §5 failure semantics ----------------------------------------------------
COMPLETE = "COMPLETE"
NO_MATERIAL_ECONOMIC_DELTA = "NO_MATERIAL_ECONOMIC_DELTA"
NO_NEW_DATA = "NO_NEW_DATA"
BLOCKED_DATA = "BLOCKED_DATA"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
FAILED = "FAILED"
STATUSES = (COMPLETE, NO_MATERIAL_ECONOMIC_DELTA, NO_NEW_DATA, BLOCKED_DATA,
            BLOCKED_EXTERNAL, INSUFFICIENT_EVIDENCE, FAILED)

#: The states in which the surface has something economic to say. Everything
#: else renders the reason, never an empty heading.
SPEAKING = (COMPLETE,)

# --- §17 freshness -----------------------------------------------------------
CURRENT, DELAYED, STALE, BLOCKED = "CURRENT", "DELAYED", "STALE", "BLOCKED"
FRESHNESS = (CURRENT, DELAYED, STALE, BLOCKED)

#: Declared here rather than at the call site. A threshold that lives in the
#: consumer is a threshold each consumer picks differently.
DELAYED_AFTER_DAYS = 45
STALE_AFTER_DAYS = 120

# --- §12 standing, as a reader meets it --------------------------------------
OBSERVED = "OBSERVED"
SUPPORTED = "SUPPORTED"
CANDIDATE = "CANDIDATE"
UNCERTAIN = "UNCERTAIN"
STANDINGS = (OBSERVED, SUPPORTED, CANDIDATE, UNCERTAIN)

#: §12/§26.4. A CANDIDATE relation has not beaten anything out of sample. It
#: may be shown as something the engine is watching and never as a finding, so
#: the renderer's verb is fixed here rather than chosen per surface.
STANDING_VERB = {
    OBSERVED: "is observed",
    SUPPORTED: "is supported by evidence",
    CANDIDATE: "is being tracked and is not yet supported",
    UNCERTAIN: "is uncertain",
}

# --- §13 calibration ---------------------------------------------------------
PRE_CALIBRATION = "PRE_CALIBRATION"
CALIBRATING = "CALIBRATING"
CALIBRATED = "CALIBRATED"
CALIBRATION_STATES = (PRE_CALIBRATION, CALIBRATING, CALIBRATED)

#: §14. A ledger source that may never reach a customer-facing figure. The
#: real ledger writes `source: "V2"`; the rehearsal writes this.
REHEARSAL = "REHEARSAL"

#: §8. Which evidence classes may support a material decision delta. A class
#: not listed cannot, however interesting the reading is — the failure being
#: guarded is a private or model-internal figure arriving as a public fact.
ALLOWED_EVIDENCE_CLASSES = ("published_series", "regulatory_filing",
                            "company_document", "shared_economic_state")


class ContextViolation(EconError):
    """Something tried to put material into a founder surface that may not go
    there."""


# =============================================================================
# the parts
# =============================================================================
@dataclass(frozen=True)
class Exposure:
    """One economic condition this company is evidenced to be exposed to.

    `measured` False is kept rather than dropped: "this company is exposed to
    real yields and the shared state does not measure them" is an information
    priority, and dropping it makes the company look less exposed than it is.
    """

    quantity: str
    measured: bool
    channel: str = ""
    mechanism: str = ""
    business_variable: str = ""
    direction: str = ""
    value: Optional[float] = None
    unit: str = ""
    as_of: str = ""
    prior_value: Optional[float] = None
    prior_as_of: str = ""
    publisher: str = ""
    node_id: str = ""
    reason: str = ""

    def as_dict(self) -> dict:
        return {"quantity": self.quantity, "measured": self.measured,
                "channel": self.channel, "mechanism": self.mechanism,
                "business_variable": self.business_variable,
                "direction": self.direction, "value": self.value,
                "unit": self.unit, "as_of": self.as_of,
                "prior_value": self.prior_value,
                "prior_as_of": self.prior_as_of,
                "publisher": self.publisher, "node_id": self.node_id,
                "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict) -> "Exposure":
        return cls(quantity=str(d.get("quantity", "")),
                   measured=bool(d.get("measured")),
                   channel=str(d.get("channel", "")),
                   mechanism=str(d.get("mechanism", "")),
                   business_variable=str(d.get("business_variable", "")),
                   direction=str(d.get("direction", "")),
                   value=d.get("value"), unit=str(d.get("unit", "")),
                   as_of=str(d.get("as_of", "")),
                   prior_value=d.get("prior_value"),
                   prior_as_of=str(d.get("prior_as_of", "")),
                   publisher=str(d.get("publisher", "")),
                   node_id=str(d.get("node_id", "")),
                   reason=str(d.get("reason", "")))


@dataclass(frozen=True)
class Relation:
    """One economic relation, carrying the standing that decides its verb."""

    statement: str
    standing: str
    mechanism: str = ""
    falsifier: str = ""
    evidence: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.standing in STANDINGS,
                f"unknown standing {self.standing!r}")

    @property
    def may_be_stated_as_fact(self) -> bool:
        """§12/§26.4. Only an OBSERVED or SUPPORTED relation may be."""
        return self.standing in (OBSERVED, SUPPORTED)

    def as_dict(self) -> dict:
        return {"statement": self.statement, "standing": self.standing,
                "mechanism": self.mechanism, "falsifier": self.falsifier,
                "evidence": list(self.evidence),
                "may_be_stated_as_fact": self.may_be_stated_as_fact}

    @classmethod
    def from_dict(cls, d: dict) -> "Relation":
        return cls(statement=str(d.get("statement", "")),
                   standing=str(d.get("standing", UNCERTAIN)),
                   mechanism=str(d.get("mechanism", "")),
                   falsifier=str(d.get("falsifier", "")),
                   evidence=tuple(d.get("evidence") or ()))


@dataclass(frozen=True)
class FieldChange:
    """One structured decision field the economic state moved, and why.

    `field`, `before` and `after` are structured values from
    `founder_ab`'s vocabulary. There is no prose field here at all, which is
    what makes §26.15 -- a wording-only difference counted as material --
    unrepresentable rather than merely refused.
    """

    field: str
    before: Any
    after: Any
    trigger: str
    mechanism: str
    provenance: Tuple[str, ...]
    why_material: str = ""

    def __post_init__(self) -> None:
        require(bool(self.field), "a field change names its field")

    @property
    def attributable(self) -> bool:
        return bool(self.provenance) and bool(self.mechanism.strip())

    def as_dict(self) -> dict:
        return {"field": self.field, "before": self.before,
                "after": self.after, "trigger": self.trigger,
                "mechanism": self.mechanism,
                "provenance": list(self.provenance),
                "why_material": self.why_material,
                "attributable": self.attributable}

    @classmethod
    def from_dict(cls, d: dict) -> "FieldChange":
        return cls(field=str(d.get("field", "")), before=d.get("before"),
                   after=d.get("after"), trigger=str(d.get("trigger", "")),
                   mechanism=str(d.get("mechanism", "")),
                   provenance=tuple(d.get("provenance") or ()),
                   why_material=str(d.get("why_material", "")))


@dataclass(frozen=True)
class ForwardExpectation:
    """One open forward prediction, as an operator surface may show it.

    `source` is carried so §14 can be enforced HERE. A rehearsal expectation
    proves the machinery and is not a prediction anybody made about the
    future; letting one into this list is how a rehearsal score becomes a
    customer-facing track record.
    """

    expectation_id: str
    quantity: str
    expected_direction: str
    horizon_days: int
    expires_at: str
    resolution_rule: str
    outcome: str = "OPEN"
    source: str = ""
    mechanism: str = ""
    falsifier: str = ""

    def as_dict(self) -> dict:
        return {"expectation_id": self.expectation_id,
                "quantity": self.quantity,
                "expected_direction": self.expected_direction,
                "horizon_days": self.horizon_days,
                "expires_at": self.expires_at,
                "resolution_rule": self.resolution_rule,
                "outcome": self.outcome, "source": self.source,
                "mechanism": self.mechanism, "falsifier": self.falsifier}

    @classmethod
    def from_dict(cls, d: dict) -> "ForwardExpectation":
        return cls(expectation_id=str(d.get("expectation_id", "")),
                   quantity=str(d.get("quantity", "")),
                   expected_direction=str(d.get("expected_direction", "")),
                   horizon_days=int(d.get("horizon_days") or 0),
                   expires_at=str(d.get("expires_at", "")),
                   resolution_rule=str(d.get("resolution_rule", "")),
                   outcome=str(d.get("outcome", "OPEN")),
                   source=str(d.get("source", "")),
                   mechanism=str(d.get("mechanism", "")),
                   falsifier=str(d.get("falsifier", "")))


@dataclass(frozen=True)
class Provenance:
    """Where one visible economic claim came from. §12's minimum."""

    claim: str
    source: str
    observation: str
    as_of: str
    evidence_type: str
    derived_from: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.evidence_type in ALLOWED_EVIDENCE_CLASSES,
                f"{self.evidence_type!r} is not an evidence class a founder "
                f"surface may cite; known: {ALLOWED_EVIDENCE_CLASSES}")

    def as_dict(self) -> dict:
        return {"claim": self.claim, "source": self.source,
                "observation": self.observation, "as_of": self.as_of,
                "evidence_type": self.evidence_type,
                "derived_from": list(self.derived_from)}

    @classmethod
    def from_dict(cls, d: dict) -> "Provenance":
        return cls(claim=str(d.get("claim", "")),
                   source=str(d.get("source", "")),
                   observation=str(d.get("observation", "")),
                   as_of=str(d.get("as_of", "")),
                   evidence_type=str(d.get("evidence_type", "")),
                   derived_from=tuple(d.get("derived_from") or ()))


# =============================================================================
# §8 THE DECISION-DAMAGE WALL
# =============================================================================
#: Why one candidate change was refused. Each is a different repair, so they
#: are named rather than folded into "rejected".
NOT_MATERIAL = "NOT_MATERIAL"
NOT_ATTRIBUTABLE = "NOT_ATTRIBUTABLE"
NOT_COMPANY_SPECIFIC = "NOT_COMPANY_SPECIFIC"
NOT_EVIDENCE_SUPPORTED = "NOT_EVIDENCE_SUPPORTED"
DUPLICATIVE = "DUPLICATIVE"
DISALLOWED_EVIDENCE_CLASS = "DISALLOWED_EVIDENCE_CLASS"
STALE_STATE = "STALE_STATE"
REFUSALS = (NOT_MATERIAL, NOT_ATTRIBUTABLE, NOT_COMPANY_SPECIFIC,
            NOT_EVIDENCE_SUPPORTED, DUPLICATIVE, DISALLOWED_EVIDENCE_CLASS,
            STALE_STATE)

_REFUSAL_REASON = {
    NOT_MATERIAL: ("the field did not move, so there is nothing to show"),
    NOT_ATTRIBUTABLE: ("the field moved with no trigger, mechanism or "
                       "provenance behind it; §13 does not credit a change "
                       "that cannot say what caused it"),
    NOT_COMPANY_SPECIFIC: ("the change rests on no channel into this company, "
                           "so it is the generic macro paragraph rather than "
                           "a reading of this business"),
    NOT_EVIDENCE_SUPPORTED: ("no economic node backs the trigger; a reading "
                             "with no evidence node cannot be checked"),
    DUPLICATIVE: ("this field was already changed by the same trigger; "
                  "counting it twice inflates the delta"),
    DISALLOWED_EVIDENCE_CLASS: ("the supporting evidence is not of a class a "
                                "founder surface may cite"),
    STALE_STATE: ("the economic state is old enough that a confident change "
                  "based on it would be asserting more than is known"),
}


def admit(change: FieldChange, *, freshness: str,
          evidence_classes: Sequence[str] = (),
          already_triggered_by: Sequence[str] = ()) -> Tuple[bool, str]:
    """§8: may this change reach a customer-facing recommendation?

    Six conditions, checked in the order that makes the REFUSAL most useful:
    attribution before evidence class, because "no mechanism" and "wrong
    evidence class" are different repairs and the first is the commoner one.

    Productization is where a useful offline signal becomes a bad
    recommendation, and the reason is always the same: offline, an
    unattributed delta is a row in a table marked MATERIAL_BUT_UNATTRIBUTED
    and nobody acts on it. On a page it is a sentence telling a founder to do
    something. So the wall is here, between the comparator and the surface.
    """
    if not change.mechanism.strip() or not change.provenance:
        return False, NOT_ATTRIBUTABLE
    if not change.trigger.strip():
        return False, NOT_EVIDENCE_SUPPORTED
    classes = tuple(evidence_classes)
    if classes and any(c not in ALLOWED_EVIDENCE_CLASSES for c in classes):
        return False, DISALLOWED_EVIDENCE_CLASS
    if change.trigger in tuple(already_triggered_by):
        return False, DUPLICATIVE
    if freshness == STALE:
        return False, STALE_STATE
    return True, ""


def refusal_reason(code: str) -> str:
    return _REFUSAL_REASON.get(code, "")


# =============================================================================
# §17 freshness, computed rather than asserted
# =============================================================================
def _days_between(earlier: str, later: str) -> Optional[int]:
    import datetime as _dt
    try:
        a = _dt.date.fromisoformat(earlier[:10])
        b = _dt.date.fromisoformat(later[:10])
    except (ValueError, TypeError):
        return None
    return (b - a).days


def freshness_of(state_as_of: str, *, at: str,
                 available: bool = True) -> Tuple[str, int]:
    """(freshness, age_days). BLOCKED when there is no state to age."""
    if not available or not state_as_of:
        return BLOCKED, -1
    age = _days_between(state_as_of, at)
    if age is None:
        return BLOCKED, -1
    if age < 0:
        # A state dated after the run's own cutoff is not fresh, it is a
        # hindsight leak. Refusing it here rather than rendering it is the
        # same rule the forward ledger enforces with `information_cutoff`.
        return BLOCKED, age
    if age >= STALE_AFTER_DAYS:
        return STALE, age
    if age >= DELAYED_AFTER_DAYS:
        return DELAYED, age
    return CURRENT, age


# =============================================================================
# §4 THE PRODUCT CONTRACT
# =============================================================================
def refuse_human_constructs(names: Sequence[str], *, where: str) -> None:
    """§4/§14. Zero collective constructs are PROMOTED; none may appear here.

    Called from `__post_init__` rather than offered as a helper, because a
    guard a caller must remember to call is a guard that holds until somebody
    adds a fifth surface.
    """
    from .vocabulary import COLLECTIVE_DIMENSIONS
    lowered = {str(n).strip().lower() for n in names}
    hit = sorted(lowered & set(COLLECTIVE_DIMENSIONS))
    if hit:
        raise ContextViolation(
            f"{where}: {hit} are collective-human constructs. The register is "
            "FROZEN_CANDIDATE and zero constructs have been promoted, so none "
            "of them may inform a founder's decision. Showing one would be "
            "presenting an untested latent estimate about people as an "
            "economic finding.")


@dataclass(frozen=True)
class FounderEconomicContext:
    """What one company's analysis is told about the economy, and no more.

    Built once per run and rendered by every surface, which is what makes
    §21 -- brief and full may not contradict -- a property of the object
    rather than a check between two renderers.
    """

    company_id: str
    as_of: str
    status: str
    #: A plain sentence naming what the economy is doing. Never the reason
    #: for a recommendation on its own; the mechanism is what connects them.
    economic_state_summary: str = ""
    relevant_dimensions: Tuple[str, ...] = ()
    company_exposures: Tuple[Exposure, ...] = ()
    supported_relations: Tuple[Relation, ...] = ()
    candidate_relations: Tuple[Relation, ...] = ()
    causal_bleeds: Tuple[str, ...] = ()
    material_decision_delta: Tuple[FieldChange, ...] = ()
    abstention_status: str = ""
    abstention_reason: str = ""
    uncertainty: Dict[str, Any] = field(default_factory=dict)
    falsifiers: Tuple[str, ...] = ()
    information_priorities: Tuple[str, ...] = ()
    forward_expectations: Tuple[ForwardExpectation, ...] = ()
    provenance: Tuple[Provenance, ...] = ()
    calibration_status: str = PRE_CALIBRATION
    freshness: str = BLOCKED
    age_days: int = -1
    #: The date this context was computed AT -- the run's own evidence cutoff.
    #: Carried so the object can check its own freshness rather than trusting
    #: the producer that built it; see `__post_init__`.
    computed_at: str = ""
    #: Every candidate change the §8 wall refused, with its code. Returned
    #: rather than dropped for the same reason `founder_view.withheld` is:
    #: a surface that showed nothing would be indistinguishable from one with
    #: nothing to say.
    refused: Tuple[dict, ...] = ()
    #: Why the state is unavailable, when it is. Empty otherwise.
    reason: str = ""

    def __post_init__(self) -> None:
        require(self.status in STATUSES, f"unknown status {self.status!r}")
        require(self.calibration_status in CALIBRATION_STATES,
                f"unknown calibration {self.calibration_status!r}")
        require(self.freshness in FRESHNESS,
                f"unknown freshness {self.freshness!r}")
        refuse_human_constructs(self.relevant_dimensions,
                                where=f"{self.company_id} relevant_dimensions")
        refuse_human_constructs([e.quantity for e in self.company_exposures],
                                where=f"{self.company_id} company_exposures")
        # §14, ON THE CONTRACT. A rehearsal expectation reaching a surface is
        # the "the model is 80% accurate" claim being manufactured out of
        # history, and it is refused at construction so no renderer has to
        # remember.
        rehearsed = [e.expectation_id for e in self.forward_expectations
                     if str(e.source).upper() == REHEARSAL]
        if rehearsed:
            raise ContextViolation(
                f"{self.company_id}: {len(rehearsed)} rehearsal "
                f"expectation(s) ({rehearsed[:3]}) reached the founder "
                "contract. REHEARSAL exists to prove the forward machinery "
                "can score itself on history; it is not a prediction anyone "
                "made about the future and may never contribute to a "
                "customer-facing accuracy figure.")
        # §13. A calibration claim needs resolved predictions behind it, and
        # nothing is resolved yet.
        if self.calibration_status != PRE_CALIBRATION:
            resolved = [e for e in self.forward_expectations
                        if e.outcome not in ("", "OPEN")]
            if not resolved:
                raise ContextViolation(
                    f"{self.company_id}: calibration is claimed as "
                    f"{self.calibration_status} with no resolved expectation. "
                    "A calibration figure with an empty denominator is the "
                    "accuracy claim this programme exists to not make.")
        # §17. A CONTEXT CHECKS ITS OWN FRESHNESS.
        #
        # Break proof 8 mutated the producer to compute the age against the
        # state's own date instead of the run's, so a 601-day-old reading
        # arrived labelled CURRENT and every downstream guard -- the
        # admission wall, the damage detector, the rule below -- was handed a
        # freshness that was simply false. Each of them was working
        # correctly on the input it was given.
        #
        # So the object recomputes from the two dates it carries. A producer
        # that says CURRENT about a state its own dates make STALE is refused
        # here, which is the only place that has both dates and no reason to
        # prefer either answer.
        if self.computed_at and self.as_of:
            expected, expected_age = freshness_of(self.as_of,
                                                  at=self.computed_at)
            if expected != self.freshness:
                raise ContextViolation(
                    f"{self.company_id}: this context is labelled "
                    f"{self.freshness} but its own dates -- a state of "
                    f"{self.as_of} read at {self.computed_at}, "
                    f"{expected_age} days -- make it {expected}. A freshness "
                    "that disagrees with the dates behind it is not a label, "
                    "it is a wrong input to every guard downstream of it.")
        # §17. Staleness cannot coexist with a material delta: the wall in
        # `admit` refuses one, so a context carrying both was assembled
        # around the wall rather than through it.
        if self.freshness == STALE and self.material_decision_delta:
            raise ContextViolation(
                f"{self.company_id}: a {self.age_days}-day-old economic state "
                "produced a material decision delta. §17 forbids a stale "
                "state creating a high-confidence change; `admit` refuses "
                "one, so this context did not come through it.")
        # §5. The two states are answers to different questions and a surface
        # renders them differently, so they may not both be true.
        if self.status == COMPLETE:
            require(bool(self.material_decision_delta),
                    f"{self.company_id}: status COMPLETE with no material "
                    "change. The abstention states exist for this; COMPLETE "
                    "with nothing in it renders as a heading with no content.")
        if self.status == NO_MATERIAL_ECONOMIC_DELTA:
            require(not self.material_decision_delta,
                    f"{self.company_id}: status NO_MATERIAL_ECONOMIC_DELTA "
                    f"with {len(self.material_decision_delta)} material "
                    "change(s). One of the two is wrong and a reader cannot "
                    "tell which.")

    # --- what surfaces ask it -------------------------------------------
    @property
    def available(self) -> bool:
        """Whether an economic state was read at all. NOT whether it spoke."""
        return self.status not in (BLOCKED_DATA, BLOCKED_EXTERNAL, FAILED)

    @property
    def speaks(self) -> bool:
        return self.status in SPEAKING and bool(self.material_decision_delta)

    @property
    def abstains(self) -> bool:
        return self.status == NO_MATERIAL_ECONOMIC_DELTA

    @property
    def attributable(self) -> bool:
        changes = self.material_decision_delta
        return bool(changes) and all(c.attributable for c in changes)

    def headline(self) -> str:
        """The one sentence every surface leads with. §7/§41.

        Computed, so brief and full cannot word the same verdict differently
        and cannot disagree about which verdict it is.
        """
        if self.status == BLOCKED_DATA:
            return ("No shared economic state is available to this "
                    "deployment, so this analysis rests entirely on the "
                    "company's own evidence.")
        if self.status == BLOCKED_EXTERNAL:
            return ("The shared economic state could not be read for this "
                    "analysis. What follows is the company's own evidence "
                    "only.")
        if self.status == INSUFFICIENT_EVIDENCE:
            return ("This company has no evidenced exposure to any condition "
                    "the shared economic state measures, so no economic "
                    "reading is asserted for it.")
        if self.status == NO_NEW_DATA:
            return ("The economic state has not moved since the last reading, "
                    "so nothing about it changes the recommendation.")
        if self.status == FAILED:
            return ("The economic reading failed for this analysis and is "
                    "reported as failed rather than omitted.")
        if self.status == NO_MATERIAL_ECONOMIC_DELTA:
            return ("Current economic conditions do not materially change the "
                    "strategic recommendation for this company.")
        n = len(self.material_decision_delta)
        fields = ", ".join(sorted({c.field.replace('_', ' ')
                                   for c in self.material_decision_delta}))
        return (f"The current economic state changes {n} element"
                f"{'' if n == 1 else 's'} of this recommendation: {fields}.")

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "company_id": self.company_id,
            "as_of": self.as_of, "status": self.status,
            "economic_state_summary": self.economic_state_summary,
            "relevant_dimensions": list(self.relevant_dimensions),
            "company_exposures": [e.as_dict() for e in self.company_exposures],
            "supported_relations": [r.as_dict()
                                    for r in self.supported_relations],
            "candidate_relations": [r.as_dict()
                                    for r in self.candidate_relations],
            "causal_bleeds": list(self.causal_bleeds),
            "material_decision_delta": [c.as_dict() for c
                                        in self.material_decision_delta],
            "abstention_status": self.abstention_status,
            "abstention_reason": self.abstention_reason,
            "uncertainty": dict(self.uncertainty),
            "falsifiers": list(self.falsifiers),
            "information_priorities": list(self.information_priorities),
            "forward_expectations": [e.as_dict()
                                     for e in self.forward_expectations],
            "provenance": [p.as_dict() for p in self.provenance],
            "calibration_status": self.calibration_status,
            "freshness": self.freshness, "age_days": self.age_days,
            "computed_at": self.computed_at,
            "refused": [dict(r) for r in self.refused],
            "reason": self.reason,
            # Computed, and serialised, so a consumer reading the stored form
            # gets the SAME verdict rather than recomputing it from parts.
            "headline": self.headline(), "speaks": self.speaks,
            "abstains": self.abstains, "attributable": self.attributable,
            "available": self.available,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FounderEconomicContext":
        """§16. Reload must reproduce the object, not a lookalike.

        Every derived field above is RECOMPUTED from the parts on the way back
        in rather than read from the payload: a stored `headline` that
        disagreed with the stored delta would be a surface rendering a verdict
        nothing in the object supports.
        """
        require(str(d.get("contract", CONTRACT)) == CONTRACT,
                f"expected {CONTRACT}, got {d.get('contract')!r}")
        return cls(
            company_id=str(d.get("company_id", "")),
            as_of=str(d.get("as_of", "")),
            status=str(d.get("status", BLOCKED_DATA)),
            economic_state_summary=str(d.get("economic_state_summary", "")),
            relevant_dimensions=tuple(d.get("relevant_dimensions") or ()),
            company_exposures=tuple(
                Exposure.from_dict(x)
                for x in (d.get("company_exposures") or ())),
            supported_relations=tuple(
                Relation.from_dict(x)
                for x in (d.get("supported_relations") or ())),
            candidate_relations=tuple(
                Relation.from_dict(x)
                for x in (d.get("candidate_relations") or ())),
            causal_bleeds=tuple(d.get("causal_bleeds") or ()),
            material_decision_delta=tuple(
                FieldChange.from_dict(x)
                for x in (d.get("material_decision_delta") or ())),
            abstention_status=str(d.get("abstention_status", "")),
            abstention_reason=str(d.get("abstention_reason", "")),
            uncertainty=dict(d.get("uncertainty") or {}),
            falsifiers=tuple(d.get("falsifiers") or ()),
            information_priorities=tuple(d.get("information_priorities") or ()),
            forward_expectations=tuple(
                ForwardExpectation.from_dict(x)
                for x in (d.get("forward_expectations") or ())),
            provenance=tuple(Provenance.from_dict(x)
                             for x in (d.get("provenance") or ())),
            calibration_status=str(d.get("calibration_status",
                                         PRE_CALIBRATION)),
            freshness=str(d.get("freshness", BLOCKED)),
            age_days=int(d.get("age_days", -1)),
            computed_at=str(d.get("computed_at", "")),
            refused=tuple(dict(r) for r in (d.get("refused") or ())),
            reason=str(d.get("reason", "")))


def blocked(company_id: str, *, reason: str, as_of: str = "",
            status: str = BLOCKED_DATA) -> FounderEconomicContext:
    """§18. Founder still works; the economic section says what is missing."""
    require(status in (BLOCKED_DATA, BLOCKED_EXTERNAL, FAILED,
                       INSUFFICIENT_EVIDENCE),
            f"{status!r} is not an unavailable state")
    return FounderEconomicContext(company_id=company_id, as_of=as_of,
                                  status=status, reason=reason,
                                  freshness=BLOCKED, age_days=-1)
