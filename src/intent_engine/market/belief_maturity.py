"""How far a belief has actually earned its keep — and what has gone stale.

WHY THIS IS DERIVED, NOT STORED
-------------------------------
`beliefs.py` already owns a lifecycle (ACTIVE / UNDER_REVIEW / RETIRED) and a
`decay` function, and that lifecycle is persisted. Adding four more states to
it would mean rewriting stored history, and this project has learned twice
over that mutating an append-only record to make a number look better is how
the record stops being evidence.

So maturity is a VIEW: recomputed from the ledger every time, owning nothing.
Run it twice on the same ledger and it says the same thing; run it after the
ledger grows and it says the newer thing. It cannot disagree with its inputs
because it has none of its own.

STALE IS NOT CONTRADICTED
-------------------------
The distinction this module exists to hold:

    CONTRADICTED  later evidence argued against the belief. The engine was
                  wrong, or the world changed, and either way it LEARNED
                  something.

    STALE         no evidence has argued either way for long enough that
                  relying on it is now a choice rather than a finding. The
                  engine learned nothing; time simply passed.

Collapsing them would let an untested year-old belief and a refuted one carry
the same warning, and they call for opposite responses: one needs a test, the
other has already had one.

WHAT CANNOT PROMOTE A BELIEF
----------------------------
A high prior. Duplicate evidence. The same wire story from a second outlet.
Age. Each of those was available to the previous implementation of every
metric in this system and each has, at some point, made something look
stronger than it was. Promotion here requires INFORMATIVE reconciliations
from INDEPENDENT subjects — the same bar mechanism calibration uses, for the
same reason.
"""
from __future__ import annotations

import collections
import datetime as _dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "belief_maturity.v1"

# --- maturity states --------------------------------------------------------
CANDIDATE = "CANDIDATE"                      # declared, never tested
SUPPORTED = "SUPPORTED"                      # one informative confirmation
REPEATEDLY_SUPPORTED = "REPEATEDLY_SUPPORTED"  # several, independent
CONTESTED = "CONTESTED"                      # confirmed and contradicted
WEAKENING = "WEAKENING"                      # contradicted, not yet retired
STALE = "STALE"                              # nothing has argued either way
RETIRED = "RETIRED"

STATES = (CANDIDATE, SUPPORTED, REPEATEDLY_SUPPORTED, CONTESTED, WEAKENING,
          STALE, RETIRED)

#: Repeated support means repeated across SUBJECTS, not repeated in a row.
#: Three confirmations for one company is one company agreeing with itself.
MIN_INDEPENDENT_FOR_REPEATED = 2

#: Past this, an untested belief is a standing assumption rather than a
#: finding. Chosen to match the shortest expectation window in use (120 days)
#: so a belief goes stale only after its own test had a chance to resolve.
STALE_AFTER_DAYS = 120

INFORMATIVE = frozenset({"CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED"})


def _date(value: object) -> Optional[_dt.date]:
    text = str(value or "")[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class Maturity:
    """One belief's standing, and the reason for it."""
    belief_id: str
    subject: str
    proposition: str
    state: str
    confirmations: int
    contradictions: int
    independent_subjects: int
    age_days: Optional[int]
    days_since_informative_test: Optional[int]
    last_supporting_evidence: str
    reason: str
    what_would_revalidate: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "belief_id": self.belief_id,
            "subject": self.subject, "proposition": self.proposition,
            "maturity": self.state, "confirmations": self.confirmations,
            "contradictions": self.contradictions,
            "independent_subjects": self.independent_subjects,
            "age_days": self.age_days,
            "days_since_informative_test": self.days_since_informative_test,
            "last_supporting_evidence": self.last_supporting_evidence,
            "reason": self.reason,
            "what_would_revalidate": self.what_would_revalidate,
        }


def classify(rows: Sequence[dict], *, as_of: str) -> Tuple[Maturity, ...]:
    """Derive every belief's maturity from the real ledger."""
    today = _date(as_of)
    beliefs = [r for r in rows if r.get("record") == "belief"]
    expectations = {r.get("expectation_id"): r for r in rows
                    if r.get("record") == "expectation"}

    by_belief: Dict[str, List[dict]] = collections.defaultdict(list)
    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        if row.get("outcome") not in INFORMATIVE:
            continue
        key = row.get("hypothesis_id") or ""
        if key:
            by_belief[key].append(row)

    expected_of: Dict[str, str] = {}
    for exp in expectations.values():
        if exp.get("hypothesis_id"):
            expected_of[exp["hypothesis_id"]] = str(
                exp.get("expected_event") or "")

    out: List[Maturity] = []
    for belief in beliefs:
        bid = str(belief.get("belief_id") or "")
        tests = by_belief.get(bid, [])
        confirmations = sum(1 for t in tests
                            if t.get("outcome") != "CONTRADICTED")
        contradictions = sum(1 for t in tests
                             if t.get("outcome") == "CONTRADICTED")
        subjects = {str(t.get("subject") or "") for t in tests}
        declared = _date(belief.get("last_updated"))
        age = (today - declared).days if today and declared else None

        last_test = max((_date(t.get("evaluated_at")) for t in tests
                         if _date(t.get("evaluated_at"))), default=None)
        since_test = (today - last_test).days if today and last_test else None

        state, reason = _state_of(
            confirmations=confirmations, contradictions=contradictions,
            independent=len(subjects), age=age,
            since_test=since_test,
            retired=belief.get("lifecycle_state") == "RETIRED")

        expected = expected_of.get(bid) or "a later observation of the "\
                                           "same kind"
        out.append(Maturity(
            belief_id=bid, subject=str(belief.get("subject") or ""),
            proposition=str(belief.get("proposition") or ""),
            state=state, confirmations=confirmations,
            contradictions=contradictions, independent_subjects=len(subjects),
            age_days=age, days_since_informative_test=since_test,
            last_supporting_evidence=str(
                (belief.get("supporting_evidence_ids") or
                 belief.get("applied_evidence_ids") or [""])[0]),
            reason=reason,
            what_would_revalidate=expected))
    return tuple(out)


def _state_of(*, confirmations: int, contradictions: int, independent: int,
              age: Optional[int], since_test: Optional[int],
              retired: bool) -> Tuple[str, str]:
    """The state, and why. Order matters and encodes what outranks what."""
    if retired:
        return RETIRED, "the belief has been retired"

    tested = confirmations + contradictions
    if tested:
        # A tested belief is never STALE, however old. Something argued about
        # it, and that is the opposite of nothing having happened.
        if confirmations and contradictions:
            return CONTESTED, (
                f"{confirmations} confirmation(s) and {contradictions} "
                f"contradiction(s); the evidence disagrees with itself")
        if contradictions:
            return WEAKENING, (
                f"{contradictions} contradiction(s) and no confirmation; "
                f"later evidence argued against it")
        if independent >= MIN_INDEPENDENT_FOR_REPEATED:
            return REPEATEDLY_SUPPORTED, (
                f"{confirmations} confirmation(s) across {independent} "
                f"independent subjects")
        return SUPPORTED, (
            f"{confirmations} confirmation(s), but from {independent} "
            f"subject(s) — one subject agreeing with itself is one "
            f"observation repeated")

    if age is not None and age >= STALE_AFTER_DAYS:
        return STALE, (
            f"declared {age} days ago and never tested either way; relying "
            f"on it is now a choice rather than a finding")
    return CANDIDATE, (
        "declared on its opening evidence and not yet tested; its "
        "expectation window has not resolved")


def summarise(maturities: Sequence[Maturity]) -> dict:
    counts = collections.Counter(m.state for m in maturities)
    stale = [m for m in maturities if m.state == STALE]
    weakening = [m for m in maturities if m.state in (WEAKENING, CONTESTED)]
    return {
        "contract": CONTRACT,
        "beliefs": len(maturities),
        "by_maturity": {s: counts.get(s, 0) for s in STATES},
        # The two questions an operator actually has.
        "no_longer_fresh": [m.as_dict() for m in stale[:10]],
        "argued_against": [m.as_dict() for m in weakening[:10]],
        "note": ("STALE means time passed and nothing argued either way; "
                 "WEAKENING means later evidence argued against it. They "
                 "call for opposite responses and are never merged"),
    }
