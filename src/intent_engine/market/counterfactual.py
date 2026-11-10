"""Was the DECISION good — which is not "did the outcome pay".

THE DISTINCTION THIS MODULE EXISTS TO HOLD
------------------------------------------
A rejected company that later doubled did not necessarily reveal a mistake. It
may have revealed a correct refusal under genuine uncertainty, and a system
that cannot tell those apart will loosen its gates after every missed winner
until it has no gates left. That is the failure mode: regret learning, done
naively, is a machine for talking yourself out of discipline.

So every evaluation here answers a narrower and answerable question: given
only what was knowable AT THE DECISION TIME, was this decision well made?

NO-TRADE IS AN ACTION
---------------------
It has a counterfactual, it has regret, and it is evaluated exactly like any
other choice. An engine that only scores the trades it took is blind to its
false negatives, and false negatives are the dominant error of a conservative
system — the funnel measured 26 of 28 companies exiting at no-trade.

HINDSIGHT LEAKAGE IS STRUCTURALLY BLOCKED
-----------------------------------------
`evaluate` takes the full evidence set and filters it through
`micro_evidence.visible_subset` at the decision timestamp itself, rather than
trusting the caller to have filtered. Evidence that arrived later is available
for scoring the OUTCOME and is refused for scoring the DECISION. The two
questions have different evidence sets, and conflating them is what makes a
backtest flatter itself.

REGRET IS ATTRIBUTED, NOT JUST COUNTED
--------------------------------------
A number that says "regret: 0.14" tells nobody what to change. Every regret
record carries a cause — execution, ranking, threshold, missing data, horizon,
model, or unavoidable uncertainty — and only the middle four are actionable.
UNAVOIDABLE is a real and common verdict, and it is what stops the system
drifting.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import micro_evidence as ME

CONTRACT_VERSION = "counterfactual.v1"

# --- regret attribution ---------------------------------------------------
EXECUTION = "EXECUTION"
RANKING = "RANKING"
THRESHOLD = "THRESHOLD"
MISSING_DATA = "MISSING_DATA"
HORIZON = "HORIZON"
MODEL = "MODEL"
UNAVOIDABLE = "UNAVOIDABLE_UNCERTAINTY"

REGRET_CAUSES = frozenset({EXECUTION, RANKING, THRESHOLD, MISSING_DATA,
                           HORIZON, MODEL, UNAVOIDABLE})

# Causes a policy review may act on. UNAVOIDABLE and EXECUTION are excluded
# deliberately: the first is the price of deciding under uncertainty, and the
# second is not a calibration problem.
ACTIONABLE_CAUSES = frozenset({RANKING, THRESHOLD, MISSING_DATA, HORIZON,
                               MODEL})

# --- decision verdicts ----------------------------------------------------
WELL_MADE = "WELL_MADE"
FALSE_NEGATIVE = "FALSE_NEGATIVE"
FALSE_POSITIVE = "FALSE_POSITIVE"
CORRECT_REFUSAL = "CORRECT_REFUSAL"
UNRESOLVED = "UNRESOLVED"


class HindsightLeak(RuntimeError):
    """Evidence from after the decision was used to judge the decision."""


@dataclass(frozen=True)
class Counterfactual:
    """One decision, its alternatives, and what it cost — or did not."""
    record_id: str
    subject: str
    decided_at: str
    chosen_action: str
    rejected_alternatives: Tuple[str, ...]
    rank: Optional[int]
    threshold_distance: Optional[float]
    decision_evidence_ids: Tuple[str, ...]
    evidence_quality_at_decision: float
    later_outcome: Optional[float] = None
    counterfactual_outcome: Optional[float] = None
    outcome_resolved_at: str = ""
    verdict: str = UNRESOLVED
    regret: Optional[float] = None
    regret_cause: str = ""
    rationale: str = ""

    @property
    def actionable(self) -> bool:
        return self.regret_cause in ACTIONABLE_CAUSES

    def as_dict(self) -> dict:
        return {"record_id": self.record_id, "subject": self.subject,
                "decided_at": self.decided_at,
                "chosen_action": self.chosen_action,
                "rejected_alternatives": list(self.rejected_alternatives),
                "rank": self.rank,
                "threshold_distance": self.threshold_distance,
                "decision_evidence_ids": list(self.decision_evidence_ids),
                "evidence_quality_at_decision":
                    self.evidence_quality_at_decision,
                "later_outcome": self.later_outcome,
                "counterfactual_outcome": self.counterfactual_outcome,
                "outcome_resolved_at": self.outcome_resolved_at,
                "verdict": self.verdict, "regret": self.regret,
                "regret_cause": self.regret_cause,
                "actionable": self.actionable, "rationale": self.rationale}


def record_decision(*, subject: str, decided_at: str, chosen_action: str,
                    all_evidence: Sequence[ME.MicroEvidence],
                    rejected_alternatives: Sequence[str] = (),
                    rank: Optional[int] = None,
                    threshold_distance: Optional[float] = None
                    ) -> Counterfactual:
    """Freeze what was knowable when the decision was made.

    The evidence set is filtered HERE, at decision time, rather than at
    scoring time. Doing it later means trusting whoever calls the scorer to
    have remembered — and that is precisely the memory lapse that produces a
    backtest with a suspiciously good record.
    """
    visible = ME.visible_subset(all_evidence, decided_at)
    quality = (round(sum(e.reliability * e.relevance * e.independence
                         for e in visible) / len(visible), 4)
               if visible else 0.0)
    rid = "cf_" + hashlib.sha256(
        f"{subject}|{decided_at[:10]}|{chosen_action}".encode()
    ).hexdigest()[:14]
    return Counterfactual(
        record_id=rid, subject=subject, decided_at=decided_at[:10],
        chosen_action=chosen_action,
        rejected_alternatives=tuple(rejected_alternatives), rank=rank,
        threshold_distance=threshold_distance,
        decision_evidence_ids=tuple(e.evidence_id for e in visible),
        evidence_quality_at_decision=quality)


# A gap smaller than this is not a decision error. Without a floor, risk
# adjustment can only ever shrink a positive alternative toward zero and
# never below it, so every profitable rejected candidate would score as some
# regret however heavily it was discounted — which is the "every missed
# winner is regret" failure arriving by a side door.
MATERIALITY = 0.02


def resolve(cf: Counterfactual, *, resolved_at: str,
            chosen_outcome: float, counterfactual_outcome: float,
            all_evidence: Sequence[ME.MicroEvidence] = (),
            risk_adjustment: float = 1.0,
            materiality: float = MATERIALITY) -> Counterfactual:
    """Score the decision once the outcome is known.

    `risk_adjustment` divides the counterfactual gain to compare like with
    like: an alternative that would have paid more while carrying far more
    risk is not straightforwardly the better decision, and scoring raw return
    would keep recommending it.

    `materiality` is what makes that adjustment able to change a verdict.
    Division alone shrinks a positive alternative toward zero but never past
    it, so without a floor every profitable rejected candidate scores as
    regret no matter how heavily discounted.

    The verdict distinguishes a MISTAKE from a MISS. A rejected candidate
    that later rose, decided on thin evidence with an honest gate, is a
    CORRECT_REFUSAL — the information to choose otherwise did not exist.
    """
    if all_evidence:
        _assert_no_leak(cf, all_evidence)

    adjusted_cf = counterfactual_outcome / max(risk_adjustment, 1e-6)
    gap = adjusted_cf - chosen_outcome

    if gap <= materiality:
        verdict = (CORRECT_REFUSAL if cf.chosen_action == "NO_TRADE"
                   else WELL_MADE)
        return _finalise(cf, resolved_at, chosen_outcome,
                         counterfactual_outcome, verdict, 0.0, UNAVOIDABLE,
                         f"on a risk-adjusted basis the alternative was "
                         f"ahead by {gap:.4f}, inside the {materiality} "
                         f"materiality floor, so the choice was not a "
                         f"decision error")

    cause, rationale = _attribute(cf, gap)
    verdict = (FALSE_NEGATIVE if cf.chosen_action == "NO_TRADE"
               else FALSE_POSITIVE)
    if cause == UNAVOIDABLE:
        verdict = CORRECT_REFUSAL if cf.chosen_action == "NO_TRADE" \
            else WELL_MADE
    return _finalise(cf, resolved_at, chosen_outcome, counterfactual_outcome,
                     verdict, round(gap, 6), cause, rationale)


def _attribute(cf: Counterfactual, gap: float) -> Tuple[str, str]:
    """Why the gap opened. Order matters: the cheapest fix is checked first.

    Evidence quality is checked BEFORE thresholds. A candidate rejected on
    thin evidence is a data problem, and loosening a threshold to catch it
    would be treating a symptom by removing the discipline.
    """
    if cf.evidence_quality_at_decision < 0.25:
        return (UNAVOIDABLE,
                f"evidence quality at decision time was "
                f"{cf.evidence_quality_at_decision:.2f}; the information "
                f"needed to choose otherwise did not exist, so this is the "
                f"price of deciding under uncertainty, not a miscalibration")
    if cf.evidence_quality_at_decision < 0.45:
        return (MISSING_DATA,
                f"the decision ran on evidence of quality "
                f"{cf.evidence_quality_at_decision:.2f}; better inputs, not "
                f"a looser gate, are what would have changed it")
    if cf.threshold_distance is not None and abs(cf.threshold_distance) <= 0.1:
        return (THRESHOLD,
                f"missed its gate by {cf.threshold_distance:.3f}, close "
                f"enough that the threshold itself is worth reviewing — "
                f"after repeated instances, not this one")
    if cf.rank is not None and cf.rank > 1:
        return (RANKING,
                f"ranked {cf.rank}; the candidate was seen and ordered "
                f"below others that did not do better")
    return (MODEL,
            "the decision had adequate evidence, cleared no threshold "
            "narrowly, and was not a ranking artefact, which points at the "
            "model rather than the policy")


def _finalise(cf, resolved_at, chosen, alt, verdict, regret, cause,
              rationale) -> Counterfactual:
    from dataclasses import replace
    return replace(cf, later_outcome=chosen, counterfactual_outcome=alt,
                   outcome_resolved_at=resolved_at[:10], verdict=verdict,
                   regret=regret, regret_cause=cause, rationale=rationale)


def _assert_no_leak(cf: Counterfactual,
                    all_evidence: Sequence[ME.MicroEvidence]) -> None:
    """The decision's evidence set must contain nothing from after it."""
    by_id = {e.evidence_id: e for e in all_evidence}
    for eid in cf.decision_evidence_ids:
        item = by_id.get(eid)
        if item is not None and not item.visible_at(cf.decided_at):
            raise HindsightLeak(
                f"{cf.subject}: evidence {eid} became available "
                f"{item.available_at}, after the {cf.decided_at} decision it "
                f"is being used to judge")


# --------------------------------------------------------------------------
# near-miss learning (§18)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class NearMiss:
    """A candidate that failed a gate, and by how much."""
    subject: str
    at: str
    gate: str
    threshold: float
    observed: float
    rank: Optional[int] = None
    evidence_quality: float = 0.0
    later_outcome: Optional[float] = None

    @property
    def distance(self) -> float:
        return round(self.observed - self.threshold, 6)

    @property
    def is_near(self) -> bool:
        """Within 10% of the threshold, scaled by the threshold's size."""
        scale = max(abs(self.threshold), 1e-6)
        return abs(self.distance) / scale <= 0.10

    def as_dict(self) -> dict:
        return {"subject": self.subject, "at": self.at, "gate": self.gate,
                "threshold": self.threshold, "observed": self.observed,
                "distance": self.distance, "is_near": self.is_near,
                "rank": self.rank, "evidence_quality": self.evidence_quality,
                "later_outcome": self.later_outcome}


def analyse_near_misses(misses: Sequence[NearMiss], *,
                        min_instances: int = 8) -> dict:
    """Look for threshold cliffs — and refuse to recommend on thin evidence.

    `min_instances` is the guard against the failure this whole module is
    built to avoid. Three near misses that later rose is a pattern the eye
    invents; recommending a threshold change on that is how a system talks
    itself out of a gate that was working. Below the floor the output is
    explicitly INSUFFICIENT_EVIDENCE, never a recommendation.
    """
    by_gate: Dict[str, List[NearMiss]] = {}
    for m in misses:
        by_gate.setdefault(m.gate, []).append(m)

    findings = []
    for gate, group in sorted(by_gate.items()):
        near = [m for m in group if m.is_near]
        resolved = [m for m in near if m.later_outcome is not None]
        would_have_paid = [m for m in resolved if m.later_outcome > 0]
        finding = {
            "gate": gate, "instances": len(group), "near_misses": len(near),
            "resolved": len(resolved),
            "near_misses_that_later_rose": len(would_have_paid),
            "median_distance": _median([m.distance for m in near]),
        }
        if len(resolved) < min_instances:
            finding["recommendation"] = "INSUFFICIENT_EVIDENCE"
            finding["note"] = (
                f"{len(resolved)} resolved near misses against a floor of "
                f"{min_instances}; a threshold change on this many is "
                f"pattern-matching on noise")
        elif len(would_have_paid) / len(resolved) >= 0.7:
            finding["recommendation"] = "REVIEW_THRESHOLD"
            finding["note"] = (
                f"{len(would_have_paid)}/{len(resolved)} resolved near misses "
                f"later rose, which is a stable enough cluster to justify a "
                f"HUMAN review of this gate — not an automatic change")
        else:
            finding["recommendation"] = "GATE_HOLDING"
            finding["note"] = (
                f"only {len(would_have_paid)}/{len(resolved)} later rose; the "
                f"gate is rejecting noise, which is its job")
        findings.append(finding)
    return {"gates_analysed": len(findings), "findings": findings}


def summarise(records: Sequence[Counterfactual]) -> dict:
    """Regret by cause, and how much of it is actually actionable."""
    resolved = [c for c in records if c.verdict != UNRESOLVED]
    by_cause: Dict[str, int] = {}
    by_verdict: Dict[str, int] = {}
    for c in resolved:
        if c.regret_cause:
            by_cause[c.regret_cause] = by_cause.get(c.regret_cause, 0) + 1
        by_verdict[c.verdict] = by_verdict.get(c.verdict, 0) + 1
    regrets = [c.regret for c in resolved if c.regret]
    no_trade = [c for c in resolved if c.chosen_action == "NO_TRADE"]
    return {
        "decisions_recorded": len(records), "resolved": len(resolved),
        "unresolved": len(records) - len(resolved),
        "by_verdict": by_verdict, "by_cause": by_cause,
        "cumulative_regret": round(sum(regrets), 6) if regrets else 0.0,
        "actionable_regret_records": sum(1 for c in resolved if c.actionable),
        "no_trade_decisions_scored": len(no_trade),
        "no_trade_regret": round(
            sum(c.regret or 0.0 for c in no_trade), 6),
        "correct_refusals": sum(1 for c in no_trade
                                if c.verdict == CORRECT_REFUSAL),
        "false_negatives": sum(1 for c in resolved
                               if c.verdict == FALSE_NEGATIVE),
    }


def _median(values: Sequence[float]) -> Optional[float]:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    return round(clean[mid] if len(clean) % 2
                 else (clean[mid - 1] + clean[mid]) / 2, 6)
