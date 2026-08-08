"""Preregistering what a rival should do — before finding out whether it did.

WHY THE ORDER IS THE WHOLE THING
--------------------------------
A response found first and explained afterwards is not evidence of anything.
Every competitor does something every quarter, so a search that begins with
"did they respond?" will always succeed, and the resulting story is
unfalsifiable in exactly the way that feels most convincing.

So the expectation is written down, with its window and its disconfirming
observation, and only then is later evidence allowed to score it.
`register` refuses an expectation whose window has already closed, and
`observe` refuses evidence dated before the expectation existed. Retroactive
game theory is not available through any argument to either.

THE MENU PROBLEM
----------------
"Magento may respond through pricing, product, bundling, migration
incentives, or partner strategy" cannot be wrong. A five-way menu is a
prediction only in grammar.

An expectation therefore names ONE response class, or a bounded set of at
most `MAX_RESPONSE_CLASSES` where the constraint genuinely does not
discriminate — and it must always name what it would take to be WRONG, which
is what a menu cannot supply.
"""
from __future__ import annotations

import collections
import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "cross_actor_expectation.v1"

# --- response classes -------------------------------------------------------
PRICE_RESPONSE = "PRICE_RESPONSE"
PRODUCT_RESPONSE = "PRODUCT_RESPONSE"
BUNDLE_RESPONSE = "BUNDLE_RESPONSE"
MIGRATION_INCENTIVE = "MIGRATION_INCENTIVE"
PARTNER_RESPONSE = "PARTNER_RESPONSE"
SEGMENT_RETREAT = "SEGMENT_RETREAT"
NO_RESPONSE = "NO_RESPONSE"
RESPONSE_CLASSES = (PRICE_RESPONSE, PRODUCT_RESPONSE, BUNDLE_RESPONSE,
                    MIGRATION_INCENTIVE, PARTNER_RESPONSE, SEGMENT_RETREAT,
                    NO_RESPONSE)

#: More than this and the expectation cannot be wrong.
MAX_RESPONSE_CLASSES = 2

# --- outcomes ---------------------------------------------------------------
CONFIRMED = "CONFIRMED"
CONTRADICTED = "CONTRADICTED"
ALTERNATIVE_RESPONSE = "ALTERNATIVE_RESPONSE"
NO_RESPONSE_YET = "NO_RESPONSE_YET"
AMBIGUOUS = "AMBIGUOUS"
OUTCOMES = (CONFIRMED, CONTRADICTED, ALTERNATIVE_RESPONSE, NO_RESPONSE_YET,
            AMBIGUOUS)

OPEN = "OPEN"
RESOLVED = "RESOLVED"


class ExpectationRejected(ValueError):
    """The engine was asked to preregister something it cannot be wrong about."""


def _date(value: object) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class CrossActorExpectation:
    expectation_id: str
    interaction_id: str
    trigger_actor: str
    counterparty: str
    trigger_action: str
    mechanism: str
    expected_response_class: Tuple[str, ...]
    resolution_window: str
    eligible_evidence: Tuple[str, ...]
    disconfirming_outcome: str
    created_at: str
    status: str = OPEN
    outcome: str = ""
    resolved_by: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "expectation_id": self.expectation_id,
            "interaction_id": self.interaction_id,
            "trigger_actor": self.trigger_actor,
            "counterparty": self.counterparty,
            "trigger_action": self.trigger_action,
            "mechanism": self.mechanism,
            "expected_response_class": list(self.expected_response_class),
            "resolution_window": self.resolution_window,
            "eligible_evidence": list(self.eligible_evidence),
            "disconfirming_outcome": self.disconfirming_outcome,
            "created_at": self.created_at, "status": self.status,
            "outcome": self.outcome, "resolved_by": list(self.resolved_by),
        }

    def is_open(self, as_of: str) -> bool:
        end = _date(self.resolution_window)
        today = _date(as_of)
        return bool(end and today and today <= end)


def register(*, interaction_id: str, trigger_actor: str, counterparty: str,
             trigger_action: str, mechanism: str,
             expected_response_class: Sequence[str], resolution_window: str,
             disconfirming_outcome: str, created_at: str,
             eligible_evidence: Sequence[str] = ()) -> CrossActorExpectation:
    """Write the prediction down. Refuses anything that cannot be wrong."""
    classes = tuple(dict.fromkeys(
        c for c in expected_response_class if c in RESPONSE_CLASSES))
    if not classes:
        raise ExpectationRejected(
            "name a response class from the closed vocabulary; 'they will "
            "react somehow' is not a preregistration")
    if len(classes) > MAX_RESPONSE_CLASSES:
        raise ExpectationRejected(
            f"{len(classes)} response classes is a menu, not a prediction: "
            f"a set that broad cannot come back wrong. At most "
            f"{MAX_RESPONSE_CLASSES}, and only where the constraint "
            f"genuinely does not discriminate")
    if not disconfirming_outcome.strip():
        raise ExpectationRejected(
            "state the observation that would make this wrong")
    if not mechanism.strip():
        raise ExpectationRejected(
            "state why the counterparty would respond at all; without a "
            "mechanism this is a coincidence with a date attached")
    window = _date(resolution_window)
    created = _date(created_at)
    if not window or not created:
        raise ExpectationRejected("both dates must be real dates")
    if window <= created:
        raise ExpectationRejected(
            "the window closes on or before the expectation is written, so "
            "there is no future in which it could resolve")
    raw = f"{interaction_id}|{counterparty}|{'|'.join(classes)}"
    return CrossActorExpectation(
        expectation_id="cax_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        interaction_id=interaction_id, trigger_actor=trigger_actor,
        counterparty=counterparty, trigger_action=trigger_action,
        mechanism=mechanism, expected_response_class=classes,
        resolution_window=resolution_window[:10],
        eligible_evidence=tuple(eligible_evidence),
        disconfirming_outcome=disconfirming_outcome.strip(),
        created_at=created_at[:10])


def observe(expectation: CrossActorExpectation, *, response_class: str,
            observed_at: str, evidence_ids: Sequence[str],
            as_of: str) -> CrossActorExpectation:
    """Score a later response against what was written down beforehand.

    Evidence dated before the expectation existed is refused outright. That
    is the only structural defence against a story assembled backwards, and
    it costs nothing that a real response would have needed.
    """
    when = _date(observed_at)
    created = _date(expectation.created_at)
    if when and created and when < created:
        raise ExpectationRejected(
            f"the response is dated {observed_at[:10]} and the expectation "
            f"was written on {expectation.created_at}: evidence that "
            f"predates the prediction cannot test it")
    if expectation.status == RESOLVED:
        return expectation

    if response_class == NO_RESPONSE:
        outcome = (NO_RESPONSE_YET if expectation.is_open(as_of)
                   else CONTRADICTED)
    elif response_class in expectation.expected_response_class:
        outcome = CONFIRMED
    elif response_class in RESPONSE_CLASSES:
        outcome = ALTERNATIVE_RESPONSE
    else:
        outcome = AMBIGUOUS
    return CrossActorExpectation(**{
        **expectation.__dict__,
        "status": OPEN if outcome == NO_RESPONSE_YET else RESOLVED,
        "outcome": outcome, "resolved_by": tuple(evidence_ids)})


def summarise(expectations: Sequence[CrossActorExpectation], *,
              as_of: str = "") -> dict:
    by_outcome = collections.Counter(e.outcome for e in expectations
                                     if e.outcome)
    return {
        "contract": CONTRACT,
        "expectations": len(expectations),
        "open": sum(1 for e in expectations if e.status == OPEN),
        "resolved": sum(1 for e in expectations if e.status == RESOLVED),
        "by_outcome": dict(by_outcome),
        "counterparties": sorted({e.counterparty for e in expectations}),
        "note": ("an unresolved expectation is a success: it was written "
                 "down before the answer was known, which is the only "
                 "state from which a response can teach anything"),
    }
