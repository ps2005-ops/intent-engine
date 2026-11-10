"""Hypotheses — what the engine is actually testing when it takes a position.

WHY A DECISION IS NOT THE UNIT
------------------------------
Storing "BUY Shopify, confidence 0.74" cannot answer the question that matters
when it fails: **was the decision wrong, or was the reasoning wrong?** Three
losing BUYs whose hypotheses were all correct is a timing problem. Three
losing BUYs whose hypotheses were all refuted is a reasoning problem. They
need opposite responses and the decision record cannot tell them apart.

So a position is a *consequence* of a hypothesis, and the hypothesis is what
accumulates. Knowledge grows by refining hypotheses, not by counting trades.

SCOPE — DELIBERATELY THE SMALLEST USEFUL VERSION
------------------------------------------------
A full knowledge graph ("this held 17 times under high inflation for mid-cap
SaaS") needs hundreds of resolutions across regimes. This engine produces
roughly one gradable decision per cycle, so that capability would not be
exercised for years and is recorded in the dependency graph rather than built.

What IS built is what the next ten cycles will actually use: an explicit
hypothesis on every position, a quality axis separate from decision quality,
belief revision on resolution, and expected information gain — which is
immediately useful because sample size is the binding constraint and EIG says
which samples are worth taking.

WHY EIG MATTERS RIGHT NOW
-------------------------
`A-M5` needs ≥30 resolutions. Reaching thirty by testing one hypothesis thirty
times is worth 4.0 novelty-weighted; reaching it across several is worth 13.7 —
measured, not assumed. EIG is how the engine picks the second kind without
being told to.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence

# Outcome of testing a hypothesis, kept separate from whether the trade paid.
SUPPORTED, REFUTED, INCONCLUSIVE = "supported", "refuted", "inconclusive"

# Confidence never reaches 0 or 1. A hypothesis that cannot be moved by
# evidence has stopped being a hypothesis.
_MIN_CONFIDENCE, _MAX_CONFIDENCE = 0.05, 0.95


@dataclass(frozen=True)
class Revision:
    """One belief update. The engine must not merely accumulate outcomes; it
    must be able to say what changed its mind and by how much."""
    at: str
    confidence_before: float
    confidence_after: float
    reason: str
    evidence: str = ""

    def as_dict(self) -> dict:
        return {"at": self.at, "confidence_before": self.confidence_before,
                "confidence_after": self.confidence_after,
                "reason": self.reason, "evidence": self.evidence}


@dataclass(frozen=True)
class Hypothesis:
    """A claim about the world that a position is one consequence of."""
    hypothesis_id: str
    statement: str
    mechanism: str = ""          # WHY it would be true
    prediction: str = ""         # what should be observable, and by when
    confidence: float = 0.5
    tested: int = 0
    supported: int = 0
    refuted: int = 0
    retired: bool = False
    revisions: tuple = ()

    @property
    def support_rate(self) -> Optional[float]:
        scored = self.supported + self.refuted
        return round(self.supported / scored, 3) if scored else None

    def as_dict(self) -> dict:
        return {"hypothesis_id": self.hypothesis_id,
                "statement": self.statement, "mechanism": self.mechanism,
                "prediction": self.prediction, "confidence": self.confidence,
                "tested": self.tested, "supported": self.supported,
                "refuted": self.refuted, "support_rate": self.support_rate,
                "retired": self.retired,
                "revisions": [r.as_dict() for r in self.revisions]}


# The baseline signal's hypothesis, stated out loud. It was always there --
# every momentum trade asserts it -- and leaving it implicit is what made
# "was the trade wrong or was the idea wrong?" unanswerable.
BASELINE_HYPOTHESIS = Hypothesis(
    hypothesis_id="momentum_persists.v1",
    statement="A company's recent price direction persists over the next "
              "horizon.",
    mechanism="Stated as a null-ish baseline rather than a mechanism: this "
              "signal claims no causal story, which is precisely what makes "
              "it the bar a real hypothesis has to beat.",
    prediction="The direction of the trailing move continues over the "
               "horizon more often than not.",
    confidence=0.55)


def evaluate(hypothesis: Hypothesis, *, decision_correct: Optional[bool],
             predicted_observable_occurred: Optional[bool] = None) -> str:
    """Was the HYPOTHESIS supported — which is not "did the trade pay".

    When a hypothesis names its own observable, that observable decides. Only
    when it does not does the decision outcome stand in, and then the result is
    explicitly weaker: a trade can pay for reasons the hypothesis never
    claimed.
    """
    if predicted_observable_occurred is not None:
        return SUPPORTED if predicted_observable_occurred else REFUTED
    if decision_correct is None:
        return INCONCLUSIVE
    return SUPPORTED if decision_correct else REFUTED


def revise(hypothesis: Hypothesis, verdict: str, *, at: str,
           evidence: str = "", step: float = 0.05) -> Hypothesis:
    """Update belief, and record what changed it.

    A fixed step, not a Bayesian update. The likelihoods a proper update needs
    are exactly what this engine has not measured yet, and inventing them would
    put a precise-looking number on top of a guess — the failure the metric-
    integrity work exists to prevent. The step is the honest placeholder, and
    it is replaced when calibration data exists to derive one.
    """
    if verdict == INCONCLUSIVE:
        return replace(hypothesis, tested=hypothesis.tested + 1)

    before = hypothesis.confidence
    delta = step if verdict == SUPPORTED else -step
    after = round(min(max(before + delta, _MIN_CONFIDENCE),
                      _MAX_CONFIDENCE), 4)
    revision = Revision(
        at=at, confidence_before=before, confidence_after=after,
        reason=f"hypothesis {verdict} by the observed outcome",
        evidence=evidence)
    return replace(
        hypothesis,
        confidence=after,
        tested=hypothesis.tested + 1,
        supported=hypothesis.supported + (1 if verdict == SUPPORTED else 0),
        refuted=hypothesis.refuted + (1 if verdict == REFUTED else 0),
        revisions=hypothesis.revisions + (revision,))


def should_retire(hypothesis: Hypothesis, *, min_tests: int = 10) -> bool:
    """Retire only on evidence, never on a losing streak.

    `min_tests` guards the failure this is most likely to cause: killing a
    correct hypothesis after three unlucky outcomes. Retirement is a claim that
    the idea is wrong, and it needs the sample size any other claim would.
    """
    if hypothesis.tested < min_tests:
        return False
    rate = hypothesis.support_rate
    return rate is not None and rate < 0.35


def expected_information_gain(hypothesis: Hypothesis,
                              prior_tests: Sequence[Dict[str, Any]] = ()
                              ) -> float:
    """How much testing this teaches REGARDLESS of the outcome. 0.0–1.0.

    Two factors, both about how much is currently unknown:

      * **Uncertainty.** A hypothesis at 0.5 splits the world in half whichever
        way it resolves. One at 0.9 mostly confirms what is already believed,
        so a test buys little.
      * **Under-testing.** The first test of an idea buys far more than its
        fortieth, decaying as 1/(1+tested) for the same reason novelty decays.

    This is why a prediction can be worth making while being a coin flip. With
    sample size binding, it is the difference between reaching n=30 usefully
    and reaching it thirty times over on one idea.
    """
    if hypothesis.retired:
        return 0.0
    # peaks at 0.5, falls to 0 at either certainty
    uncertainty = 1.0 - abs(hypothesis.confidence - 0.5) * 2
    scarcity = 1.0 / (1 + hypothesis.tested)
    same_shape = sum(1 for t in prior_tests
                     if t.get("hypothesis_id") == hypothesis.hypothesis_id)
    crowding = 1.0 / (1 + same_shape)
    return round(max(uncertainty, 0.05) * scarcity * crowding, 4)


def rank_by_information(hypotheses: Sequence[Hypothesis],
                        prior_tests: Sequence[Dict[str, Any]] = ()
                        ) -> List[Hypothesis]:
    """Most-informative first. What to test when only n tests are affordable."""
    return sorted(hypotheses,
                  key=lambda h: expected_information_gain(h, prior_tests),
                  reverse=True)


@dataclass(frozen=True)
class HypothesisQuality:
    """The axis that decision quality cannot express.

    Four combinations, and the two mixed ones are the whole point:

      hypothesis supported + decision right  -> the reasoning worked
      hypothesis supported + decision wrong  -> TIMING or execution, not logic
      hypothesis refuted   + decision right  -> right for the wrong reason;
                                                the most dangerous outcome,
                                                because it rewards bad reasoning
      hypothesis refuted   + decision wrong  -> the idea was wrong
    """
    hypothesis_id: str
    verdict: str
    decision_correct: Optional[bool]
    diagnosis: str

    def as_dict(self) -> dict:
        return {"hypothesis_id": self.hypothesis_id, "verdict": self.verdict,
                "decision_correct": self.decision_correct,
                "diagnosis": self.diagnosis}


_DIAGNOSIS = {
    (SUPPORTED, True): "reasoning and decision both held",
    (SUPPORTED, False): "the reasoning held and the decision did not — a "
                        "timing or execution problem, not a reasoning one",
    (REFUTED, True): "right for the wrong reason — the decision paid while "
                     "the reasoning was refuted, which rewards bad reasoning "
                     "if counted as a success",
    (REFUTED, False): "the hypothesis was wrong, and the decision followed it",
}


def assess_hypothesis(hypothesis: Hypothesis, *,
                      decision_correct: Optional[bool],
                      predicted_observable_occurred: Optional[bool] = None
                      ) -> HypothesisQuality:
    verdict = evaluate(
        hypothesis, decision_correct=decision_correct,
        predicted_observable_occurred=predicted_observable_occurred)
    diagnosis = _DIAGNOSIS.get(
        (verdict, decision_correct),
        "inconclusive — no outcome to evaluate the hypothesis against")
    return HypothesisQuality(hypothesis_id=hypothesis.hypothesis_id,
                             verdict=verdict,
                             decision_correct=decision_correct,
                             diagnosis=diagnosis)
