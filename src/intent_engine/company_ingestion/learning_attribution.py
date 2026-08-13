"""Did this evidence change anything, and was it worth the retrieval?

WHAT WAS MISSING, IN THE WORDS OF THE INSTRUMENT THAT REPORTED IT
-----------------------------------------------------------------
    "no per-row evidence→belief attribution exists on the founder path; the
     market branch owns the knowledge_effect ledger and the founder branch
     cannot import it"

That was true, and it left Wave-30 criterion 10 unavailable for a reason no
amount of retrieval could fix: there was no seam to attribute AT. This module
is that seam. It does not replace `market.knowledge_effect` — it mirrors its
vocabulary exactly, restated rather than imported for the same structural
reason `_high_activity_low_learning` restates the market detector, so the two
ledgers can be read side by side and a future merge is a rename and not a
reconciliation.

ABOUT IS NOT CHANGED
--------------------
The one rule this contract is built around. Evidence that MENTIONS a thesis is
not evidence that MOVED it, and the cheapest way to manufacture a learning
rate is to count citations. So a changing effect must show a before and an
after that differ, and one that cannot is rejected rather than downgraded — a
caller that means "the evidence was about this" already has NO_CHANGE, which
is stored exactly like a change.

WHY NO_CHANGE IS STORED
-----------------------
An effect log that keeps only the positives is a success log, and a success
log cannot price a research action. Retrieval that produced nothing is the
observation that makes a conversion rate mean something.

MISSING IS NOT ZERO, AND IT IS THE COMMON CASE HERE
----------------------------------------------------
On this cohort the reasoning backend is out of credit, so no knowledge state
is produced at all. Reporting 0% learning conversion would assert that
retrieval taught the system nothing — a claim about the evidence — when the
truth is that nothing downstream ran. Those are different facts and
`attribution_state` is what separates them.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

CONTRACT = "learning_attribution.v1"

# --- what may be changed (mirrors market.knowledge_effect) ------------------
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
INFORMATION_GAP = "INFORMATION_GAP"
RESEARCH_QUESTION = "RESEARCH_QUESTION"
FOUNDER_DECISION_COMPONENT = "FOUNDER_DECISION_COMPONENT"

TARGET_TYPES = (EVENT, BELIEF, EXPECTATION, CAUSAL_NODE, CAUSAL_EDGE,
                MECHANISM, HYPOTHESIS, THESIS, HIDDEN_STATE, RELATIONSHIP,
                FALSIFIER, INFORMATION_GAP, RESEARCH_QUESTION,
                FOUNDER_DECISION_COMPONENT)

# --- what happened to it ----------------------------------------------------
CREATED = "CREATED"
SUPPORTED = "SUPPORTED"
WEAKENED = "WEAKENED"
CONTRADICTED = "CONTRADICTED"
REVISED = "REVISED"
RESOLVED = "RESOLVED"
RETIRED = "RETIRED"
NO_CHANGE = "NO_CHANGE"

EFFECT_TYPES = (CREATED, SUPPORTED, WEAKENED, CONTRADICTED, REVISED, RESOLVED,
                RETIRED, NO_CHANGE)

#: Every one of these must be able to show a before and an after that differ.
CHANGING = frozenset(EFFECT_TYPES) - {NO_CHANGE}

# --- how well the attribution itself is known -------------------------------
DIRECT = "DIRECT"
RECONSTRUCTED = "RECONSTRUCTED"
UNKNOWN = "UNKNOWN"
STANDINGS = (DIRECT, RECONSTRUCTED, UNKNOWN)

# --- whether the question could be asked at all (§21) -----------------------
MEASURED = "MEASURED"
#: The reasoning backend never produced a knowledge state, so no evidence row
#: could have moved one. NOT a measurement of the evidence.
BLOCKED_EXTERNAL_CREDITS = "BLOCKED_EXTERNAL_CREDITS"
#: A knowledge layer ran but recorded no attributions — the seam exists and
#: was not exercised. Distinct from the above, and from a measured zero.
NOT_ATTEMPTED = "NOT_ATTEMPTED"
ATTRIBUTION_STATES = (MEASURED, BLOCKED_EXTERNAL_CREDITS, NOT_ATTEMPTED)

UNAVAILABLE = "UNAVAILABLE"


class EffectRejected(ValueError):
    """An attribution that claims more than a state change can support."""


class NotAChange(EffectRejected):
    """Raised when a changing effect cannot show that anything changed."""


@dataclass(frozen=True)
class KnowledgeEffect:
    """One evidence row, one knowledge object, one thing that happened."""

    evidence_id: str
    target_type: str
    target_id: str
    effect_type: str
    before_state: str = ""
    after_state: str = ""
    occurred_at: str = ""
    created_at: str = ""
    reason: str = ""
    standing: str = DIRECT

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
                "cannot price a retrieval, which is the only reason this "
                "record exists")
        if not self.reason.strip():
            raise EffectRejected(
                "an effect needs the reason it was written; an unexplained "
                "attribution cannot be audited and cannot be disputed")
        if self.effect_type in CHANGING:
            if not self.target_id:
                raise EffectRejected(
                    f"a {self.effect_type} effect needs the object it changed")
            if self.before_state == self.after_state:
                raise NotAChange(
                    f"{self.effect_type} on {self.target_id} reports the same "
                    f"state before and after ({self.before_state!r}); an "
                    "object the evidence was merely ABOUT has not been "
                    "changed by it, and the honest record is NO_CHANGE")

    @property
    def effect_id(self) -> str:
        raw = "|".join((self.evidence_id, self.target_type, self.target_id,
                        self.effect_type, self.before_state, self.after_state,
                        self.created_at[:10]))
        return "ke-" + hashlib.blake2b(raw.encode(), digest_size=8).hexdigest()

    def as_dict(self) -> dict:
        return {"record": "knowledge_effect", "contract": CONTRACT,
                "effect_id": self.effect_id, "evidence_id": self.evidence_id,
                "target_type": self.target_type, "target_id": self.target_id,
                "effect_type": self.effect_type,
                "before_state": self.before_state,
                "after_state": self.after_state,
                "occurred_at": self.occurred_at, "created_at": self.created_at,
                "reason": self.reason, "standing": self.standing}


# ---------------------------------------------------------------------------
# what the evidence behind a change actually was (§20)
# ---------------------------------------------------------------------------
def evidence_structure(evidence_ids: Sequence[str],
                       independence_rows: Sequence[dict]) -> dict:
    """The shape of the support behind one change — never a score.

    A belief strengthened by one company release and nine syndications of it
    must not read like one strengthened by a release, a regulator and a
    customer. Both are "ten documents". The difference is the origin count,
    so the origins are what this returns.

    No confidence number is produced. How much to believe a claim is a
    judgement that needs to see the claim; a number derived from these counts
    would launder a row count into an authority it has not earned.
    """
    wanted = {str(e) for e in evidence_ids}
    rows = [r for r in independence_rows
            if str(r.get("source_id") or "") in wanted]
    origins = sorted({str(r.get("origin_family") or "") for r in rows
                      if r.get("origin_family")})
    independent = sorted({str(r.get("origin_family") or "") for r in rows
                          if r.get("independence_bearing")
                          and r.get("origin_family")})
    return {
        "evidence_ids": sorted(wanted),
        "document_count": len(rows),
        "matched_document_count": len(rows),
        # Ids we were given that no independence row explains. Reported, not
        # dropped: a change resting on evidence we cannot trace is a weaker
        # thing than one resting on evidence we can, and silently equating
        # them is how lineage-unknown becomes lineage-independent.
        "unmatched_evidence_ids": sorted(
            wanted - {str(r.get("source_id") or "") for r in rows}),
        "origin_families": origins,
        "origin_count": len(origins),
        "independent_origins": independent,
        "independent_origin_count": len(independent),
        "source_roles": sorted({str(r.get("source_class") or "") for r in rows
                                if r.get("source_class")}),
        "lineages": dict(sorted(Counter(str(r.get("lineage") or "")
                                        for r in rows).items())),
    }


def _ratio(numerator: int, denominator: int):
    """A share, or UNAVAILABLE — never 0.0 standing in for an empty set."""
    if not denominator:
        return UNAVAILABLE
    return round(numerator / denominator, 4)


def conversion(*, evidence_rows: Sequence[dict],
               effects: Sequence[object] = (),
               independence_rows: Sequence[dict] = (),
               knowledge_layer_ran: bool = True,
               blocked_reason: str = "") -> dict:
    """Learning conversion for one company, over compatible populations.

    THE POPULATIONS ARE ROWS ON BOTH SIDES (§22). One evidence row can produce
    several effects, so a raw effect count in the numerator would let a single
    well-cited document report a conversion above 100% — the same shape as the
    stagnation defect this programme has already shipped once, where an
    aggregate counted 112 actions that were 32.
    """
    rows = list(evidence_rows)
    eligible = len(rows)
    payloads = [e.as_dict() if hasattr(e, "as_dict") else dict(e)
                for e in effects]

    if not knowledge_layer_ran:
        # THE COMMON CASE ON THIS COHORT, AND THE ONE MOST WORTH GETTING
        # RIGHT. No knowledge state was produced, so no row could have moved
        # one. Every count below is about US, not about the evidence.
        return {
            "contract": CONTRACT,
            "attribution_state": BLOCKED_EXTERNAL_CREDITS,
            "attribution_reason": blocked_reason or (
                "no knowledge state was produced, so no evidence row could "
                "have changed one; this is a fact about the reasoning "
                "backend and not a measurement of the evidence"),
            "evidence_rows": eligible,
            "eligible_evidence_rows": UNAVAILABLE,
            "effect_producing_evidence_rows": UNAVAILABLE,
            "independent_effect_producing_evidence_rows": UNAVAILABLE,
            "zero_effect_evidence_rows": UNAVAILABLE,
            "learning_conversion": UNAVAILABLE,
            "independent_learning_conversion": UNAVAILABLE,
            "knowledge_effects": 0,
            "effects_by_type": {},
            "changes": [],
        }

    independent_ids = {str(r.get("source_id") or "")
                       for r in independence_rows
                       if r.get("independence_bearing")}
    changing = [p for p in payloads
                if str(p.get("effect_type")) in CHANGING]
    # ROWS, not effects: the set of evidence ids that moved at least one
    # object. `len(changing)` is a different number and is reported beside it
    # rather than instead of it.
    producing = {str(p.get("evidence_id") or "") for p in changing}
    producing.discard("")
    row_ids = {str(r.get("source_id") or "") for r in rows}
    producing &= row_ids or producing

    changes = []
    by_target: Dict[tuple, List[str]] = {}
    for payload in changing:
        key = (payload.get("target_type"), payload.get("target_id"))
        by_target.setdefault(key, []).append(str(payload.get("evidence_id")))
    for (target_type, target_id), ids in sorted(
            by_target.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        changes.append({
            "target_type": target_type, "target_id": target_id,
            "support": evidence_structure(ids, independence_rows)})

    state = MEASURED if payloads else NOT_ATTEMPTED
    reason = "" if payloads else (
        "a knowledge state was produced and no attribution was recorded "
        "against it; the seam exists and was not exercised, which is not the "
        "same as evidence that changed nothing")
    return {
        "contract": CONTRACT,
        "attribution_state": state,
        "attribution_reason": reason,
        "evidence_rows": eligible,
        "eligible_evidence_rows": eligible,
        "effect_producing_evidence_rows": len(producing),
        "independent_effect_producing_evidence_rows":
            len(producing & independent_ids),
        "zero_effect_evidence_rows": eligible - len(producing),
        "learning_conversion": _ratio(len(producing), eligible),
        "independent_learning_conversion": _ratio(
            len(producing & independent_ids), len(row_ids & independent_ids)),
        "knowledge_effects": len(payloads),
        "effects_by_type": dict(sorted(Counter(
            str(p.get("effect_type")) for p in payloads).items())),
        "changes": changes,
    }
