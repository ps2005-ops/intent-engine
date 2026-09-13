"""What a piece of evidence actually changed, or that it changed nothing.

THE GAP THIS CLOSES
-------------------
The ledger holds 316 pieces of evidence and, on every one of them,
`affected_causal_nodes`, `affected_hypotheses`, `affected_hidden_states` and
`numeric_values` are empty. The engine knows that evidence EXISTS. It does not
know what any of it DID. Everything downstream inherits that hole:

  - the research reward has four positive terms and can measure one of them,
    so "go where the answers are" is optimal and the audit reports HACKABLE;
  - a discovered cluster cannot be scored by whether it led anywhere;
  - a thesis cannot answer "what changed your mind";
  - a research policy can learn to retrieve and cannot learn to be useful.

WHY THE FIELDS ON MicroEvidence WERE NEVER GOING TO WORK
--------------------------------------------------------
They are on the wrong object, at the wrong time. Evidence is translated from a
document BEFORE any belief exists for it to affect; at that moment there is
nothing true to write in `affected_hypotheses`. Filling them in later from text
similarity would be a guess wearing a provenance field.

An effect is a fact about a STATE CHANGE, so it is recorded where the state
changes and it is its own append-only record. `micro_evidence`'s fields stay
where they are, unused by this module and unread by the reward.

NO_CHANGE IS THE POINT
----------------------
Most accepted evidence changes nothing, and that is the single most valuable
thing this layer can say. Without it, "we accepted 300 rows" and "we learned
300 things" are the same number, and a research policy optimising against that
number learns to fetch more documents. An effect log that only records changes
is a success log, and a success log cannot price an action.

MARKED AFFECTED IS NOT AFFECTED
-------------------------------
The easiest way to fake this layer is to write an effect for every object the
evidence is merely ABOUT. So a state-changing effect must state a `before` and
an `after` and they must differ; if they do not, the honest record is
NO_CHANGE, and `KnowledgeEffect` raises rather than accepting a change that
changed nothing.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "knowledge_effect.v1"

# --- what kind of thing was affected -----------------------------------------
EVENT = "EVENT"
BELIEF = "BELIEF"
EXPECTATION = "EXPECTATION"
CAUSAL_NODE = "CAUSAL_NODE"
CAUSAL_EDGE = "CAUSAL_EDGE"
MECHANISM = "MECHANISM"
HYPOTHESIS = "HYPOTHESIS"
THESIS = "THESIS"
HIDDEN_STATE = "HIDDEN_STATE"
RELATIONSHIP = "RELATIONSHIP"
FALSIFIER = "FALSIFIER"
COUNTERFACTUAL = "COUNTERFACTUAL"
ECONOMIC_STATE = "ECONOMIC_STATE"
COMPANY_EXPOSURE = "COMPANY_EXPOSURE"
RESEARCH_QUESTION = "RESEARCH_QUESTION"
FOUNDER_DECISION_COMPONENT = "FOUNDER_DECISION_COMPONENT"

TARGET_TYPES = (EVENT, BELIEF, EXPECTATION, CAUSAL_NODE, CAUSAL_EDGE,
                MECHANISM, HYPOTHESIS, THESIS, HIDDEN_STATE, RELATIONSHIP,
                FALSIFIER, COUNTERFACTUAL, ECONOMIC_STATE, COMPANY_EXPOSURE,
                RESEARCH_QUESTION, FOUNDER_DECISION_COMPONENT)

# --- what happened to it -------------------------------------------------------
CREATED = "CREATED"
SUPPORTED = "SUPPORTED"
WEAKENED = "WEAKENED"
CONTRADICTED = "CONTRADICTED"
REVISED = "REVISED"
RESOLVED = "RESOLVED"
DISCRIMINATED = "DISCRIMINATED"
INVALIDATED = "INVALIDATED"
NO_CHANGE = "NO_CHANGE"

EFFECT_TYPES = (CREATED, SUPPORTED, WEAKENED, CONTRADICTED, REVISED, RESOLVED,
                DISCRIMINATED, INVALIDATED, NO_CHANGE)

#: Effects that assert the knowledge state is different than it was. Every one
#: of these must be able to show a before and an after that differ.
CHANGING = frozenset(EFFECT_TYPES) - {NO_CHANGE}

#: Effects that separate live explanations rather than adding weight to the
#: one already ahead. This is the term a confirmation-seeking research policy
#: cannot farm, and it is why DISCRIMINATED is its own type rather than a
#: flavour of SUPPORTED.
DISCRIMINATING = frozenset({DISCRIMINATED, CONTRADICTED, RESOLVED,
                            INVALIDATED})

# --- how well the attribution itself is known ----------------------------------
#
# DIRECT is written at the seam by the code that made the change. RECONSTRUCTED
# is derived after the fact from append-only records that make the derivation
# deterministic. UNKNOWN is for history that predates the contract and cannot
# be recovered — recorded rather than dropped, so a rate computed over the log
# can report its own denominator honestly.
DIRECT = "DIRECT"
RECONSTRUCTED = "RECONSTRUCTED"
UNKNOWN = "UNKNOWN"
STANDINGS = (DIRECT, RECONSTRUCTED, UNKNOWN)

#: Only these may be used to price a research action. A reconstructed log is
#: built from evidence that survived, so it is missing every action that
#: returned nothing and every rate over it is biased toward success.
PRICEABLE = frozenset({DIRECT})


class EffectRejected(ValueError):
    """An attribution that claims more than a state change can support."""


class NotAChange(EffectRejected):
    """Raised when a changing effect cannot show that anything changed."""


@dataclass(frozen=True)
class KnowledgeEffect:
    """One evidence item, one knowledge object, one thing that happened."""

    evidence_id: str
    target_type: str
    target_id: str
    effect_type: str
    #: The object's state before and after, as short strings. Free text on
    #: purpose: the states belong to a dozen different contracts and forcing
    #: them into one vocabulary would either be enormous or be a lie.
    before_state: str = ""
    after_state: str = ""
    #: When the underlying fact happened, and when the effect was written.
    #: Kept apart for the same reason everywhere else in this engine does:
    #: collapsing them dates a March event to the August sweep that read it.
    occurred_at: str = ""
    created_at: str = ""
    reason: str = ""
    standing: str = DIRECT
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.target_type not in TARGET_TYPES:
            raise EffectRejected(f"unknown target type {self.target_type!r}")
        if self.effect_type not in EFFECT_TYPES:
            raise EffectRejected(f"unknown effect type {self.effect_type!r}")
        if self.standing not in STANDINGS:
            raise EffectRejected(f"unknown standing {self.standing!r}")
        if not self.evidence_id:
            raise EffectRejected(
                "an effect needs the evidence that caused it; without one it "
                "cannot price a research action, which is the only reason "
                "this record exists")
        if not self.reason.strip():
            raise EffectRejected(
                "an effect needs the reason it was written; an unexplained "
                "attribution cannot be audited and cannot be disputed")
        if self.effect_type in CHANGING:
            if not self.target_id:
                raise EffectRejected(
                    f"a {self.effect_type} effect needs the object it "
                    "changed")
            if self.before_state == self.after_state:
                raise NotAChange(
                    f"{self.effect_type} on {self.target_id} reports the "
                    f"same state before and after ({self.before_state!r}); "
                    "an object the evidence was merely ABOUT has not been "
                    "changed by it, and the honest record is NO_CHANGE")
        elif self.before_state and self.after_state and \
                self.before_state != self.after_state:
            raise EffectRejected(
                "NO_CHANGE reports two different states; if the state moved, "
                "say which way it moved")

    @property
    def effect_id(self) -> str:
        raw = "|".join((self.evidence_id, self.target_type, self.target_id,
                        self.effect_type, self.created_at))
        return "ke_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def changed(self) -> bool:
        return self.effect_type in CHANGING

    @property
    def discriminating(self) -> bool:
        return self.effect_type in DISCRIMINATING

    @property
    def priceable(self) -> bool:
        """Whether this may be used to price a research action."""
        return self.standing in PRICEABLE

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(record="knowledge_effect", contract=CONTRACT,
                 effect_id=self.effect_id, changed=self.changed,
                 discriminating=self.discriminating,
                 priceable=self.priceable)
        return d


_FIELDS = tuple(f.name for f in dataclasses.fields(KnowledgeEffect))


def from_dict(row: dict) -> KnowledgeEffect:
    return KnowledgeEffect(**{k: row[k] for k in _FIELDS if k in row})


def no_change(evidence_id: str, *, reason: str, occurred_at: str = "",
              created_at: str = "", target_type: str = BELIEF,
              standing: str = DIRECT) -> KnowledgeEffect:
    """Evidence was processed and moved nothing.

    Deliberately as easy to write as a change. The whole layer fails if
    recording a null result is more work than recording a positive one,
    because then the log fills with successes and stops being able to price
    anything.
    """
    return KnowledgeEffect(
        evidence_id=evidence_id, target_type=target_type, target_id="",
        effect_type=NO_CHANGE, occurred_at=occurred_at,
        created_at=created_at, reason=reason, standing=standing)


#: How a reconciliation outcome maps onto what the resolving evidence DID.
#:
#: This is where discrimination finally comes from. Creating a belief adds a
#: claim; RESOLVING one settles a question that was open, and only the second
#: separates live explanations. Until an expectation is reconciled, every
#: effect in the log is CREATED, the discriminating term is zero everywhere,
#: and the research reward degenerates into "go where the answers are" —
#: which is exactly what the first audit reported.
_OUTCOME_TO_EFFECT = {
    "CONFIRMED": SUPPORTED,
    "PARTIALLY_CONFIRMED": SUPPORTED,
    "CONTRADICTED": CONTRADICTED,
    "UNINFORMATIVE": NO_CHANGE,
    "UNMEASURABLE": NO_CHANGE,
    "TOO_EARLY": NO_CHANGE,
}


def from_reconciliation(reconciliation, *, created_at: str = "",
                        standing: str = DIRECT) -> List["KnowledgeEffect"]:
    """The effects a resolved expectation attributes to its evidence.

    Two effects per resolving item, deliberately. The EXPECTATION is RESOLVED
    — the window is closed and the question is answered — and the BELIEF
    behind it is SUPPORTED or CONTRADICTED. They are different facts: an
    expectation that resolves against its belief is the most informative thing
    that can happen to this engine, and folding it into one record would make
    it indistinguishable from a confirmation.

    An outcome that settles nothing produces NO_CHANGE rather than nothing at
    all, because "we waited and the window closed empty" is a real, priced
    result for whatever action went looking.
    """
    outcome = str(getattr(reconciliation, "outcome", ""))
    mapped = _OUTCOME_TO_EFFECT.get(outcome, NO_CHANGE)
    ids = tuple(getattr(reconciliation, "evidence_ids", ()) or ())
    at = str(getattr(reconciliation, "evaluated_at", ""))[:10]
    rationale = str(getattr(reconciliation, "rationale", "")) or outcome
    out: List[KnowledgeEffect] = []
    for eid in ids:
        if mapped == NO_CHANGE:
            out.append(no_change(
                eid, reason=f"{outcome}: {rationale}"[:240],
                target_type=EXPECTATION, occurred_at=at,
                created_at=created_at or at, standing=standing))
            continue
        out.append(KnowledgeEffect(
            evidence_id=eid, target_type=EXPECTATION,
            target_id=str(getattr(reconciliation, "expectation_id", "")),
            effect_type=RESOLVED, before_state="open",
            after_state=outcome, occurred_at=at,
            created_at=created_at or at,
            reason=f"closed a preregistered window: {rationale}"[:240],
            standing=standing, provenance="expectation.reconcile"))
        out.append(KnowledgeEffect(
            evidence_id=eid, target_type=BELIEF,
            target_id=str(getattr(reconciliation, "hypothesis_id", "")),
            effect_type=mapped, before_state="untested",
            after_state=outcome, occurred_at=at,
            created_at=created_at or at,
            reason=f"a preregistered expectation resolved {outcome}",
            standing=standing, provenance="expectation.reconcile"))
    return out


def summarise(effects: Sequence[KnowledgeEffect], *,
              evidence_total: Optional[int] = None) -> dict:
    """What the evidence did, with its denominator.

    `evidence_total` is separate from the number of effects because evidence
    with NO effect record at all is a different failure from evidence with a
    NO_CHANGE record: the first means nobody looked, the second means somebody
    looked and nothing moved. A layer that cannot tell those apart cannot tell
    whether it is working.
    """
    by_effect: Dict[str, int] = {}
    by_target: Dict[str, int] = {}
    by_standing: Dict[str, int] = {}
    for e in effects:
        by_effect[e.effect_type] = by_effect.get(e.effect_type, 0) + 1
        by_target[e.target_type] = by_target.get(e.target_type, 0) + 1
        by_standing[e.standing] = by_standing.get(e.standing, 0) + 1
    attributed = {e.evidence_id for e in effects}
    changed = {e.evidence_id for e in effects if e.changed}
    return {
        "contract": CONTRACT,
        "effects": len(effects),
        "by_effect": by_effect,
        "by_target": by_target,
        "by_standing": by_standing,
        "evidence_attributed": len(attributed),
        "evidence_that_changed_something": len(changed),
        "evidence_that_changed_nothing": len(attributed - changed),
        "evidence_total": evidence_total,
        "evidence_unattributed": (None if evidence_total is None
                                  else max(0, evidence_total
                                           - len(attributed))),
        "discriminating": sum(1 for e in effects if e.discriminating),
        "priceable": sum(1 for e in effects if e.priceable),
        "note": ("evidence with no effect record was never examined; "
                 "evidence with a NO_CHANGE record was examined and moved "
                 "nothing, and the two must not be added together"),
    }


def by_evidence(effects: Sequence[KnowledgeEffect]
                ) -> Dict[str, List[KnowledgeEffect]]:
    out: Dict[str, List[KnowledgeEffect]] = {}
    for e in effects:
        out.setdefault(e.evidence_id, []).append(e)
    return out


def by_target(effects: Sequence[KnowledgeEffect], *, target_type: str = "",
              target_id: str = "") -> List[KnowledgeEffect]:
    """Every effect on one object, oldest first — a change history.

    This is what lets a thesis answer "what changed your mind": the question
    is a query over this log, not a sentence somebody writes.
    """
    rows = [e for e in effects
            if (not target_type or e.target_type == target_type)
            and (not target_id or e.target_id == target_id)]
    rows.sort(key=lambda e: (e.occurred_at or "", e.created_at or ""))
    return rows
