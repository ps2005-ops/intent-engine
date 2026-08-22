"""Decision Quality — the capability every other metric is a proxy for.

WHY THIS GRADES REFUSALS, WHICH RESOLUTION WOULD NOT HAVE
---------------------------------------------------------
Resolution was the standing #1 bottleneck. Trying to falsify that ranking did
not overturn it — it exposed that its SCOPE was wrong:

    BUY / SELL        1 of 11 decisions   ( 9%)   <- what resolution grades
    WATCH / NO_TRADE 10 of 11 decisions   (91%)   <- ungraded, forever

"Refuses when the evidence is insufficient" is an explicit component of
Decision Quality, and it was not measured at all. A resolution layer that
graded only positions would have measured 9% of the engine's decisions and
declared the loop closed.

So every decision is graded here, including the refusals. A refusal is a
decision. It is the decision this engine makes 91% of the time.

OUTCOME BIAS IS THE TRAP, AND IT IS AVOIDED DELIBERATELY
--------------------------------------------------------
The naive way to grade a refusal is "did the price go up? then refusing was
wrong." That is outcome bias, and adopting it would actively destroy Decision
Quality: it teaches the engine to take positions on insufficient evidence
whenever the coin happens to land well, which is precisely the behaviour the
gates exist to prevent.

So refusals are graded on two INDEPENDENT axes that are never collapsed:

  * `justified` — was the stated reason a legitimate one, given what was known
    at the time? This is answerable without knowing the outcome, and it is the
    axis that reflects decision quality.

  * `forgone` — what move was given up? This is answerable only afterwards,
    and it reflects opportunity cost, not correctness.

A justified refusal that missed a large move is a GOOD decision with a bad
outcome. Recorded as exactly that. What matters is the pattern: if justified
refusals systematically forgo large favourable moves, the gates may be too
strict — and that is a claim about the gates, established over many decisions,
never about any single one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

# Confidence in a METRIC, not in a prediction. Every number this module reports
# carries one, because treating a value derived from one sample as equal to one
# derived from three hundred is how a system talks itself into false certainty.
HIGH, MEDIUM, LOW, UNMEASURABLE = "high", "medium", "low", "unmeasurable"

# Sample sizes at which a rate becomes worth reading. Deliberately conservative:
# `A-M5` gates accuracy claims at 30, and nothing here should imply an accuracy
# claim below it.
_MEDIUM_N = 10
_HIGH_N = 30

# A move large enough that forgoing it is worth recording. Below this, "we
# missed it" is noise dressed as regret.
MATERIAL_MOVE = 0.05

# Gates that are legitimate reasons to refuse. A refusal citing one of these
# was justified on what was known at the time, whatever happened next. Listed
# explicitly rather than accepting any non-empty gate, so that a future gate
# added carelessly cannot silently launder a bad refusal into a good one.
_JUSTIFIED_GATES = frozenset({
    "not_tradable",           # structurally impossible, never a miss
    "no_strategic_reading",   # nothing was retrieved
    "view_withheld",          # read, and honestly declined
    "no_dated_evidence",      # nothing datable, so no "recent" to trade
    "no_outside_source",      # only the company's own account of itself
    "no_market_evidence",     # no view on direction or what is priced in
})


def _confidence(n: int) -> str:
    if n <= 0:
        return UNMEASURABLE
    if n >= _HIGH_N:
        return HIGH
    if n >= _MEDIUM_N:
        return MEDIUM
    return LOW


@dataclass(frozen=True)
class GradedDecision:
    company_id: str
    classification: str
    is_refusal: bool
    # positions
    correct: Optional[bool] = None
    # refusals
    justified: Optional[bool] = None
    forgone_move: Optional[float] = None
    material_miss: Optional[bool] = None
    gate: str = ""
    realised_move: Optional[float] = None
    note: str = ""

    def as_dict(self) -> dict:
        return {"company_id": self.company_id,
                "classification": self.classification,
                "is_refusal": self.is_refusal, "correct": self.correct,
                "justified": self.justified, "forgone_move": self.forgone_move,
                "material_miss": self.material_miss, "gate": self.gate,
                "realised_move": self.realised_move, "note": self.note}


def realised_move(entry_price: Optional[float],
                  exit_price: Optional[float]) -> Optional[float]:
    """Fractional move between the decision and its horizon, or None.

    None when either price is missing. Not zero — a missing price means we do
    not know what happened, and scoring that as "no move" would quietly count
    every data gap as a correct refusal.
    """
    if not entry_price or exit_price is None:
        return None
    return (exit_price - entry_price) / entry_price


def grade(decision: Dict[str, Any], *, entry_price: Optional[float] = None,
          exit_price: Optional[float] = None) -> GradedDecision:
    """Grade one decision — position or refusal."""
    classification = decision.get("classification") or ""
    company = decision.get("company_id") or ""
    gate = (decision.get("blocked_by") or [""])[0] if decision.get(
        "blocked_by") else ""
    move = realised_move(entry_price, exit_price)
    is_refusal = classification in ("WATCH", "NO_TRADE", "HOLD")

    if move is None:
        return GradedDecision(
            company_id=company, classification=classification,
            is_refusal=is_refusal, gate=gate,
            note="no price at the horizon; ungraded rather than assumed flat")

    if not is_refusal:
        direction = decision.get("direction") or ""
        correct = (move > 0) if direction == "up" else (move < 0)
        return GradedDecision(
            company_id=company, classification=classification,
            is_refusal=False, correct=correct, realised_move=round(move, 4),
            gate=gate)

    # A refusal. Justification is decided by the REASON, not the outcome.
    justified = gate in _JUSTIFIED_GATES
    # `not_tradable` cannot forgo anything: there was no instrument to hold.
    forgone = None if gate == "not_tradable" else abs(move)
    material = (forgone is not None and forgone >= MATERIAL_MOVE)
    return GradedDecision(
        company_id=company, classification=classification, is_refusal=True,
        justified=justified, forgone_move=(None if forgone is None
                                           else round(forgone, 4)),
        material_miss=material, gate=gate, realised_move=round(move, 4),
        note=("justified refusal that forwent a material move — opportunity "
              "cost, not an error" if (justified and material) else ""))


def assess(decisions: Sequence[Dict[str, Any]],
           prices: Optional[Dict[str, Sequence[Optional[float]]]] = None
           ) -> dict:
    """Decision Quality across a set of decisions, with a confidence per metric.

    Every rate is reported with the sample size it rests on. A rate over three
    decisions and a rate over three hundred are not the same measurement, and
    presenting them identically is how a system talks itself into certainty it
    has not earned.
    """
    prices = prices or {}
    graded: List[GradedDecision] = []
    for decision in decisions or ():
        entry, exit_ = prices.get(decision.get("company_id"), (None, None))
        graded.append(grade(decision, entry_price=entry, exit_price=exit_))

    scored = [g for g in graded if g.realised_move is not None]
    positions = [g for g in scored if not g.is_refusal]
    refusals = [g for g in scored if g.is_refusal]
    correct_positions = [g for g in positions if g.correct]
    justified_refusals = [g for g in refusals if g.justified]
    misses = [g for g in refusals if g.material_miss]

    def _rate(numerator: Sequence, denominator: Sequence):
        n = len(denominator)
        return {"value": (round(len(numerator) / n, 3) if n else None),
                "n": n, "confidence": _confidence(n)}

    return {
        "decisions": len(graded),
        "graded": len(scored),
        "ungraded_no_price": len(graded) - len(scored),
        # coverage of the grading itself -- the number that exposed the
        # original plan as measuring 9% of decisions
        "share_of_decisions_graded": (round(len(scored) / len(graded), 3)
                                      if graded else None),
        "position_accuracy": _rate(correct_positions, positions),
        "refusal_justification_rate": _rate(justified_refusals, refusals),
        # opportunity cost, kept SEPARATE from correctness on purpose
        "material_miss_rate": _rate(misses, refusals),
        "unjustified_refusals": [g.company_id for g in refusals
                                 if not g.justified],
        "graded_decisions": [g.as_dict() for g in graded],
        "note": ("A justified refusal that forwent a material move is a good "
                 "decision with a bad outcome. Grading it as an error would "
                 "teach the engine to take positions on insufficient evidence "
                 "whenever the coin lands well."),
    }
