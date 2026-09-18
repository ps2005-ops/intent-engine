"""Can this product's reasoning change when the evidence changes?

WHAT THIS IS, AND WHAT IT IS EMPHATICALLY NOT
---------------------------------------------
The frozen 40-company qualification ended `CALIBRATION_STATUS =
PRE_CALIBRATION` with every real learning counter at zero, and that is still
true: no expectation this product preregistered has yet been resolved by an
event that happened afterwards. Nothing here changes that, and nothing here
may be reported as though it did.

What this module does is REHEARSE the loop on the record as it stood on a
past date:

    T0   hide everything filed after the cutoff
         read the company
         form a belief, and PREREGISTER what it implies should be observable
    T1   advance the cutoff
         observe only what had arrived by then
         reconcile the expectation against it
         read the company again
         measure whether the DECISION moved, and say why

Every artifact carries `label = HISTORICAL_REHEARSAL`. §22 is enforced in
code, not in prose: `as_dict()` refuses to emit a row without it, because a
rehearsal row that reaches a calibration count is indistinguishable from a
forward result once it is in a table.

WHY A REHEARSAL IS WORTH ANYTHING AT ALL
----------------------------------------
Because the alternative claim -- "the architecture exists" -- is the one the
40 companies specifically refused to accept. A ledger with methods nobody
calls is not a learning loop; the recorded lesson is `a write path is not a
write`. Running the real decision path twice over two honest vintages and
showing what moved is the weakest claim that is still a claim about
BEHAVIOUR rather than about code.

THE HONEST OUTCOMES
-------------------
§24: if the evidence does not support a reversal, do not manufacture one. A
rehearsal that ends `NO_MATERIAL_CHANGE` is a result. A rehearsal where the
decision holds but the information priority moves is a result. The claim is
"reasoning CAN revise when evidence changes", never "reasoning always
changes its mind".
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
from typing import Optional, Tuple

CONTRACT = "learning_rehearsal.v1"

#: §22, enforced. Never remove, never parameterise, never make it a default
#: a caller can override: the whole separation rests on this literal.
HISTORICAL_REHEARSAL = "HISTORICAL_REHEARSAL"

#: LearningDecisionDelta change types (§25).
REVERSED = "REVERSED"
WEAKENED = "WEAKENED"
REINFORCED = "REINFORCED"
ABSTAINED = "ABSTAINED"
NEW_OPTION = "NEW_OPTION"
INFORMATION_PRIORITY_CHANGED = "INFORMATION_PRIORITY_CHANGED"
NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
#: ADDED RATHER THAN OVERLOADING `REVERSED`. A decision whose ARCHETYPE is
#: unchanged but whose measure moved -- "customer count" to "managed
#: endpoints" after a later filing said so -- has not been reversed. Calling
#: it REVERSED would inflate the one count a reader trusts most, and the
#: recorded lesson is that counts inflate before they inform. REVERSED is
#: now reserved for a decision that became a DIFFERENT decision.
MEASURE_REVISED = "MEASURE_REVISED"

#: Expectation reconciliation outcomes (§21).
MATCHED = "MATCHED"
PARTIALLY_MATCHED = "PARTIALLY_MATCHED"
CONTRADICTED = "CONTRADICTED"
UNRESOLVED = "UNRESOLVED"


def _stamp(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _as_date(value):
    text = str(value or "")[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class RehearsedBelief:
    """What was believed at T0, from T0 evidence only (§19)."""
    belief_id: str = ""
    company: str = ""
    as_of: str = ""
    statement: str = ""
    mechanism: str = ""
    supporting_evidence: Tuple[str, ...] = ()
    confidence_state: str = "HELD"
    assumptions: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    label: str = HISTORICAL_REHEARSAL

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["label"] = HISTORICAL_REHEARSAL
        return out


@dataclasses.dataclass(frozen=True)
class RehearsedExpectation:
    """What T0's belief said should become observable (§20).

    Created from T0 evidence ONLY. The cutoff is carried so a reader can
    check that it precedes every observation used to resolve it -- §20's
    "no hindsight expectation creation" is a property anybody can verify
    from the record rather than a promise in a docstring.
    """
    expectation_id: str = ""
    belief_id: str = ""
    company: str = ""
    created_at: str = ""            #: the T0 cutoff. Never "now".
    expected_observation: str = ""
    expected_direction: str = ""
    expected_window: str = ""
    measurement_source: str = ""
    falsifier: str = ""
    confidence_state: str = "OPEN"
    label: str = HISTORICAL_REHEARSAL

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["label"] = HISTORICAL_REHEARSAL
        return out


@dataclasses.dataclass(frozen=True)
class Reconciliation:
    """What actually arrived by T1, against what T0 expected (§21)."""
    expectation_id: str = ""
    observation: str = ""
    observation_date: str = ""
    source: str = ""
    outcome: str = UNRESOLVED
    reason: str = ""
    belief_effect: str = ""
    label: str = HISTORICAL_REHEARSAL

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["label"] = HISTORICAL_REHEARSAL
        return out


@dataclasses.dataclass(frozen=True)
class LearningDecisionDelta:
    """Did the decision move, and what moved it (§25)."""
    company: str = ""
    before_belief: str = ""
    after_belief: str = ""
    before_decision: str = ""
    after_decision: str = ""
    before_priority: str = ""
    after_priority: str = ""
    changed: bool = False
    change_type: str = NO_MATERIAL_CHANGE
    evidence_that_caused_change: Tuple[str, ...] = ()
    provenance: str = ""
    label: str = HISTORICAL_REHEARSAL

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["evidence_that_caused_change"] = list(
            self.evidence_that_caused_change)
        out["label"] = HISTORICAL_REHEARSAL
        return out


@dataclasses.dataclass(frozen=True)
class Rehearsal:
    """One company, two vintages, and what moved between them."""
    company: str = ""
    t0: str = ""
    t1: str = ""
    documents_at_t0: int = 0
    documents_at_t1: int = 0
    belief: Optional[RehearsedBelief] = None
    expectation: Optional[RehearsedExpectation] = None
    reconciliation: Optional[Reconciliation] = None
    delta: Optional[LearningDecisionDelta] = None
    refused: str = ""               #: why no rehearsal was possible
    label: str = HISTORICAL_REHEARSAL
    contract: str = CONTRACT

    @property
    def available(self) -> bool:
        return not self.refused and self.delta is not None

    def as_dict(self) -> dict:
        return {
            "contract": self.contract,
            "label": HISTORICAL_REHEARSAL,
            "company": self.company, "t0": self.t0, "t1": self.t1,
            "documents_at_t0": self.documents_at_t0,
            "documents_at_t1": self.documents_at_t1,
            "belief": self.belief.as_dict() if self.belief else None,
            "expectation": (self.expectation.as_dict()
                            if self.expectation else None),
            "reconciliation": (self.reconciliation.as_dict()
                               if self.reconciliation else None),
            "delta": self.delta.as_dict() if self.delta else None,
            "refused": self.refused,
            "available": self.available,
        }


def _dated(documents):
    """(date, text, label) for every document carrying a usable date."""
    rows = []
    for doc in documents or ():
        if not isinstance(doc, dict):
            continue
        when = _as_date(doc.get("filed") or doc.get("date")
                        or doc.get("published_at") or doc.get("as_of"))
        if when is None:
            continue
        text = str(doc.get("text") or doc.get("body")
                   or doc.get("excerpt") or "")
        label = str(doc.get("form") or doc.get("title")
                    or doc.get("kind") or "document")
        rows.append((when, text, label, str(doc.get("url") or "")))
    rows.sort(key=lambda r: r[0])
    return rows


def choose_cutoffs(documents, *, min_each: int = 1):
    """Two dates with real evidence on both sides, or a reason there are not.

    THE SPLIT IS THE EXPERIMENT. A T0 with nothing before it rehearses
    nothing, and a T1 with nothing new is the same reading twice -- so both
    sides are required to carry documents, and a corpus that cannot supply
    them is REFUSED rather than split anyway.
    """
    rows = _dated(documents)
    if len(rows) < 2 * min_each:
        return None, None, (f"only {len(rows)} dated document(s) were read, "
                            f"which cannot be split into a before and an "
                            f"after")
    dates = sorted({r[0] for r in rows})
    if len(dates) < 2:
        return None, None, ("every dated document carries the same date, so "
                            "there is no earlier state to rehearse from")
    # The cut that leaves the most evidence on the thinner side, so neither
    # vintage is a single document standing in for a company.
    best, best_score = None, -1
    for candidate in dates[:-1]:
        before = sum(1 for r in rows if r[0] <= candidate)
        after = len(rows) - before
        score = min(before, after)
        if score > best_score:
            best, best_score = candidate, score
    if best is None or best_score < min_each:
        return None, None, ("no cut leaves evidence on both sides, so an "
                            "earlier state cannot be separated from a later "
                            "one")
    return best.isoformat(), dates[-1].isoformat(), ""


def _text_before(documents, cutoff: str) -> Tuple[str, int]:
    """Every document filed on or before the cutoff. THE ONLY WAY IN.

    A rehearsal whose T0 reading can see a T1 document is not a rehearsal.
    The filter is arithmetic on dates and has no escape hatch.
    """
    edge = _as_date(cutoff)
    if edge is None:
        return "", 0
    kept = [r for r in _dated(documents) if r[0] <= edge]
    return " ".join(r[1] for r in kept)[:400_000], len(kept)


def _new_between(documents, t0: str, t1: str):
    """What arrived after T0 and by T1 -- the only thing that may resolve."""
    start, end = _as_date(t0), _as_date(t1)
    if start is None or end is None:
        return ()
    return tuple(r for r in _dated(documents) if start < r[0] <= end)


def rehearse(*, company: str, documents=(), read):
    """Run the real decision path over two honest vintages.

    `read(text)` is the caller's reading function -- in production, the same
    `analysis_selection.select` every surface uses. It is injected rather
    than imported so this module cannot be accused of rehearsing a DIFFERENT
    reasoner from the live one, and so a test can prove the wall holds
    without a network.

    NEVER RAISES. A rehearsal that cannot run is `refused` with a reason.
    """
    name = str(company or "")
    try:
        t0, t1, why_not = choose_cutoffs(documents)
        if why_not:
            return Rehearsal(company=name, refused=why_not)

        text0, n0 = _text_before(documents, t0)
        text1, n1 = _text_before(documents, t1)
        before = read(text0)
        after = read(text1)
        a0 = str(getattr(before, "archetype", "") or "")
        a1 = str(getattr(after, "archetype", "") or "")

        q0 = str(getattr(before, "decision_question", "") or "")
        q1 = str(getattr(after, "decision_question", "") or "")
        p0 = _first_priority(before)
        p1 = _first_priority(after)
        basis0 = getattr(before, "question_basis", {}) or {}
        basis1 = getattr(after, "question_basis", {}) or {}

        belief = RehearsedBelief(
            belief_id=_stamp(name, t0, q0), company=name, as_of=t0,
            statement=(q0 or "no reading could be formed from the record as "
                       "it stood"),
            mechanism=str(basis0.get("why") or ""),
            supporting_evidence=(f"{n0} document(s) filed on or before {t0}",),
            confidence_state=("HELD" if q0 else "NONE"),
            assumptions=tuple(basis0.get("slots_from_class_prior") or ()),
            falsifiers=("a later filing states a different unit of revenue, "
                        "buyer, or dependency",))

        expectation = RehearsedExpectation(
            expectation_id=_stamp(name, t0, "exp"), belief_id=belief.belief_id,
            company=name, created_at=t0,
            expected_observation=(
                "later filings continue to describe this business in the "
                "terms this reading rests on"),
            expected_direction="UNCHANGED",
            expected_window=f"{t0} to {t1}",
            measurement_source="this company's own later filings",
            falsifier=("a document filed after the cutoff states a different "
                       "unit of revenue, buyer or dependency"))

        arrived = _new_between(documents, t0, t1)
        recon = _reconcile(expectation, arrived, basis0, basis1)
        delta = _delta(name, belief, q0, q1, p0, p1, recon, arrived,
                       basis0, basis1, t0, t1, a0, a1)
        return Rehearsal(company=name, t0=t0, t1=t1, documents_at_t0=n0,
                         documents_at_t1=n1, belief=belief,
                         expectation=expectation, reconciliation=recon,
                         delta=delta)
    except Exception as exc:                                 # noqa: BLE001
        return Rehearsal(company=name,
                         refused=(f"the rehearsal could not be run "
                                  f"({type(exc).__name__}); it is reported as "
                                  f"unavailable rather than omitted"))


def _first_priority(reading) -> str:
    rows = getattr(reading, "information_priorities", ()) or ()
    return str(getattr(rows[0], "question", "")) if rows else ""


def _reconcile(expectation, arrived, basis0, basis1) -> Reconciliation:
    """Did what arrived match what T0 said should arrive?"""
    if not arrived:
        return Reconciliation(
            expectation_id=expectation.expectation_id, outcome=UNRESOLVED,
            reason=("nothing was filed between the two cutoffs, so the "
                    "expectation is still open"),
            belief_effect="none")
    when, _text, label, url = arrived[-1]
    unit0 = str(basis0.get("billing_unit") or "")
    unit1 = str(basis1.get("billing_unit") or "")
    buyer0 = str(basis0.get("buyer") or "")
    buyer1 = str(basis1.get("buyer") or "")
    moved = [f"{a!r} -> {b!r}" for a, b, k in
             ((unit0, unit1, "unit"), (buyer0, buyer1, "buyer")) if a != b]
    if moved:
        return Reconciliation(
            expectation_id=expectation.expectation_id,
            observation=f"{len(arrived)} later document(s); {'; '.join(moved)}",
            observation_date=when.isoformat(), source=f"{label} {url}".strip(),
            outcome=CONTRADICTED,
            reason=("a later filing describes this business in different "
                    "terms from the ones the earlier reading rested on"),
            belief_effect="BELIEF_REVISED")
    return Reconciliation(
        expectation_id=expectation.expectation_id,
        observation=f"{len(arrived)} later document(s), same description",
        observation_date=when.isoformat(), source=f"{label} {url}".strip(),
        outcome=MATCHED,
        reason=("later filings continue to describe this business in the "
                "terms the earlier reading rested on"),
        belief_effect="BELIEF_REINFORCED")


def _delta(name, belief, q0, q1, p0, p1, recon, arrived, basis0, basis1,
           t0, t1, a0="", a1="") -> LearningDecisionDelta:
    """What moved, classified honestly (§25).

    §24 IS ENFORCED HERE. There is no branch that produces a reversal the
    evidence did not produce: every outcome below is read off a comparison
    of two real readings, and `NO_MATERIAL_CHANGE` is a legitimate end state
    that the caller may not override.
    """
    caused = tuple(f"{r[2]} filed {r[0].isoformat()}" for r in arrived[-3:])
    prov = (f"two readings of the same company by the same reasoner, over "
            f"documents filed on or before {t0} and on or before {t1}")
    if not q0 and q1:
        return LearningDecisionDelta(
            company=name, before_belief=belief.statement, after_belief=q1,
            before_decision=q0, after_decision=q1, before_priority=p0,
            after_priority=p1, changed=True, change_type=NEW_OPTION,
            evidence_that_caused_change=caused, provenance=prov)
    if q0 and not q1:
        return LearningDecisionDelta(
            company=name, before_belief=belief.statement, after_belief="",
            before_decision=q0, after_decision=q1, before_priority=p0,
            after_priority=p1, changed=True, change_type=ABSTAINED,
            evidence_that_caused_change=caused, provenance=prov)
    if q0 != q1:
        # A DIFFERENT DECISION is REVERSED. The SAME decision, measured in
        # terms a later filing supplied, is MEASURE_REVISED -- which is the
        # commoner and more truthful outcome, and the one this product will
        # mostly produce.
        if a0 and a1 and a0 != a1:
            kind = REVERSED
        elif recon.outcome == CONTRADICTED:
            kind = MEASURE_REVISED
        else:
            kind = WEAKENED
        return LearningDecisionDelta(
            company=name, before_belief=q0, after_belief=q1,
            before_decision=q0, after_decision=q1, before_priority=p0,
            after_priority=p1, changed=True, change_type=kind,
            evidence_that_caused_change=caused, provenance=prov)
    if p0 != p1:
        return LearningDecisionDelta(
            company=name, before_belief=q0, after_belief=q1,
            before_decision=q0, after_decision=q1, before_priority=p0,
            after_priority=p1, changed=True,
            change_type=INFORMATION_PRIORITY_CHANGED,
            evidence_that_caused_change=caused, provenance=prov)
    if recon.outcome == MATCHED and arrived:
        return LearningDecisionDelta(
            company=name, before_belief=q0, after_belief=q1,
            before_decision=q0, after_decision=q1, before_priority=p0,
            after_priority=p1, changed=False, change_type=REINFORCED,
            evidence_that_caused_change=caused, provenance=prov)
    return LearningDecisionDelta(
        company=name, before_belief=q0, after_belief=q1, before_decision=q0,
        after_decision=q1, before_priority=p0, after_priority=p1,
        changed=False, change_type=NO_MATERIAL_CHANGE,
        evidence_that_caused_change=caused, provenance=prov)
