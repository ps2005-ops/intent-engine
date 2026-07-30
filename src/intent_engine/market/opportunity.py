"""Classify a company into exactly one opportunity outcome, and say why.

WHAT THIS IS FOR
----------------
The hosted daily cycle was a complete pipeline with no reasoning in it:
`predict_fn` returned None unconditionally, so every run produced no
prediction, no order, no outcome and nothing to learn from. This is the
reasoning that fills it — and the record it leaves behind is the training data
the rest of the loop needs to exist at all.

Every company analysed on a given day gets exactly one `Opportunity`, and
every one is stored, including the rejections. A NO_TRADE is not a failed
analysis; it is a dated, reasoned statement that the evidence did not support
a position, and it is the row that later tells us whether our reasons for
standing aside were good ones.

WHY IT REFUSES TO PRODUCE BUY/SELL FROM STRATEGY ALONE
------------------------------------------------------
The temptation here is to read a strategic thesis ("this company is moving
upmarket") and emit a direction. That is a fabrication, and it is the exact
failure this codebase spends most of its guards preventing. A strategic
reading says what a company appears to be doing and why. It contains no
statement about what is already priced in, and a company can be executing
perfectly while its stock falls for a year.

So the market evidence needed to reach BUY or SELL is a SEPARATE input from
the strategic reading — `MarketEvidence` below — and no such adapter is wired
yet. The consequence is stated rather than hidden: until one is, this returns
WATCH and NO_TRADE, with `blocked_by` naming the missing input on every single
record. That is a real answer. A daily cycle that honestly produces 25 WATCH
records with reasons is worth more than one that produces 25 confident
directions from evidence that cannot support them, because the first can be
audited later and the second cannot be distinguished from noise.

CALIBRATION IS RECORDED, NOT APPLIED
------------------------------------
`CompanyLearningState` is read and attached, so every opportunity carries what
was known about our accuracy on that company at the time. It deliberately does
NOT adjust the classification. There are zero resolved predictions today, so
there is nothing to calibrate against; wiring the feedback now would build a
path that silently activates later, unreviewed. `A-M5` (COMPANY_OS.md) gates
accuracy claims behind >=30 live-resolved predictions per source plus a human
calibration review, and the honest order is: produce the records, resolve
them, then open that path deliberately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Exactly one of these, always. "NO_TRADE" and "WATCH" are outcomes, not
# failures — the mission is explicit that rejected opportunities are training
# data, so nothing here returns None or raises to mean "nothing to say".
CLASSIFICATIONS = ("BUY", "SELL", "HOLD", "WATCH", "NO_TRADE")

# Gate names. Stable strings, because they are persisted on every record and
# become the thing we group by when asking "what stopped us trading this
# month?" — the ranked-backlog question the daily system review has to answer.
NOT_TRADABLE = "not_tradable"
# Nothing was retrieved. A RETRIEVAL problem, and actionable: a broken site, a
# blocked crawl, a company that publishes nothing.
NO_STRATEGIC_READING = "no_strategic_reading"
# Evidence WAS read and the strategic layer declined to form a view from it.
# Not a problem at all — it is the honest gate doing its job — and it must not
# share a name with the case above. They were one gate, which made the
# `blocked_by` distribution undiagnosable: "we could not fetch anything" and
# "we fetched plenty and correctly declined" looked identical, and they need
# opposite responses. The whole value of that distribution is telling them
# apart.
VIEW_WITHHELD = "view_withheld"
NO_DATED_EVIDENCE = "no_dated_evidence"
NO_OUTSIDE_SOURCE = "no_outside_source"
NO_MARKET_EVIDENCE = "no_market_evidence"


@dataclass(frozen=True)
class MarketEvidence:
    """What a strategic reading structurally cannot tell you.

    Kept as an explicit input with an explicit empty state, so "we have no
    market evidence" is a value the reasoner can act on and record, rather
    than an absence someone later mistakes for neutrality.
    """
    direction: str = ""            # "up" | "down" | "" (none)
    probability: Optional[float] = None
    horizon_days: Optional[int] = None
    upside_pct: Optional[float] = None
    downside_pct: Optional[float] = None
    catalysts: tuple = ()          # dated, checkable events
    source: str = ""               # what produced this, for provenance

    @property
    def is_empty(self) -> bool:
        return not (self.direction and self.probability is not None)

    @property
    def risk_reward(self) -> Optional[float]:
        if not self.upside_pct or not self.downside_pct:
            return None
        if self.downside_pct == 0:
            return None
        return round(abs(self.upside_pct / self.downside_pct), 2)


@dataclass(frozen=True)
class Opportunity:
    """One dated, reasoned decision about one company. Always stored."""
    company_id: str
    as_of: str
    classification: str
    rationale: str
    # what the strategic layer actually established
    thesis: str = ""
    alternatives: tuple = ()
    uncertainty: tuple = ()
    invalidation: tuple = ()
    monitoring: tuple = ()
    catalysts: tuple = ()
    # the market view, when there is one
    direction: str = ""
    probability: Optional[float] = None
    horizon_days: Optional[int] = None
    upside_pct: Optional[float] = None
    downside_pct: Optional[float] = None
    risk_reward: Optional[float] = None
    # WHICH signal produced the market view. Recorded on every opportunity so a
    # later calibration review can segment by source and hold each one to its
    # own record -- the difference between "the engine is 55% accurate" and
    # "baseline_momentum.v1 is 55% accurate and the thing that replaced it is
    # 61%". Without it the first real signal and the placeholder it beat are
    # averaged together and neither can be judged.
    market_source: str = ""
    # WHICH claim about the world this position is a consequence of. Distinct
    # from `market_source`: that is the machinery, this is the assertion. They
    # are 1:1 today because there is one signal, and they separate the moment a
    # second signal tests the same hypothesis -- at which point "was the trade
    # wrong or the idea wrong?" needs both to be answerable.
    hypothesis_id: str = ""
    # provenance and self-knowledge
    evidence_count: int = 0
    dated_evidence_count: int = 0
    independent_source: bool = False
    regime: str = "unknown"
    quality: float = 0.0
    blocked_by: tuple = ()
    calibration: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_tradable_decision(self) -> bool:
        return self.classification in ("BUY", "SELL")

    def as_dict(self) -> dict:
        return {
            "company_id": self.company_id, "as_of": self.as_of,
            "classification": self.classification, "rationale": self.rationale,
            "thesis": self.thesis, "alternatives": list(self.alternatives),
            "uncertainty": list(self.uncertainty),
            "invalidation": list(self.invalidation),
            "monitoring": list(self.monitoring),
            "catalysts": list(self.catalysts),
            "direction": self.direction, "probability": self.probability,
            "horizon_days": self.horizon_days,
            "upside_pct": self.upside_pct, "downside_pct": self.downside_pct,
            "risk_reward": self.risk_reward,
            "market_source": self.market_source,
            "hypothesis_id": self.hypothesis_id,
            "evidence_count": self.evidence_count,
            "dated_evidence_count": self.dated_evidence_count,
            "independent_source": self.independent_source,
            "regime": self.regime, "quality": self.quality,
            "blocked_by": list(self.blocked_by),
            "calibration": dict(self.calibration),
        }

    def to_signal(self) -> Optional[dict]:
        """The shape `predictions.generation.build_prediction` consumes, or
        None when this opportunity is not a position. Only BUY/SELL become
        predictions; everything else is recorded and stops here."""
        if not self.is_tradable_decision or self.probability is None:
            return None
        return {"direction": self.direction, "probability": self.probability,
                "horizon_days": self.horizon_days or 21,
                "claim_text": self.thesis or self.rationale}


# --- evidence readings -------------------------------------------------------
# These read the strategic report the SAME way its own renderers do, so the
# opportunity and the report a human opens cannot disagree about what was found.

_INDEPENDENT_CLASSES = ("independent_reporting", "customer_voice",
                        "competitor_statement", "analyst_coverage")


def _observations(report: dict) -> List[dict]:
    return [o for o in (report.get("observations") or []) if isinstance(o, dict)]


def _dated(observations: List[dict]) -> List[dict]:
    return [o for o in observations if (o.get("date") or "").strip()]


def _has_independent(report: dict, observations: List[dict]) -> bool:
    coverage = report.get("source_class_coverage") or {}
    if any(coverage.get(c) for c in _INDEPENDENT_CLASSES):
        return True
    return any(o.get("source_class") in _INDEPENDENT_CLASSES
               for o in observations)


def _thesis_text(report: dict) -> str:
    thesis = report.get("thesis") or {}
    if thesis.get("view_withheld"):
        return ""
    return (thesis.get("view") or "").strip()


def _first_sentences(values, limit: int) -> tuple:
    out: List[str] = []
    for value in values or ():
        text = (value if isinstance(value, str)
                else (value or {}).get("question")
                or (value or {}).get("statement")
                or (value or {}).get("text") or "")
        text = " ".join(str(text).split())
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


def _alternatives(report: dict) -> tuple:
    out: List[str] = []
    for hypothesis in report.get("hypotheses") or ():
        for alt in (hypothesis or {}).get("alternative_explanations") or ():
            text = " ".join(str(alt).split())
            if text and text not in out:
                out.append(text)
    return tuple(out[:4])


def _invalidation(report: dict) -> tuple:
    """What would show the reading is wrong. The strategic layer already
    produces these as falsification questions — reusing them is the point;
    inventing a second vocabulary for the same idea is how two systems start
    disagreeing about the same company."""
    out: List[str] = []
    for hypothesis in report.get("hypotheses") or ():
        for q in (hypothesis or {}).get("falsification_questions") or ():
            text = " ".join(str(q).split())
            if text and text not in out:
                out.append(text)
    return tuple(out[:4])


def _quality(*, evidence: int, dated: int, independent: bool,
             alternatives: int, has_thesis: bool) -> float:
    """A bounded, explainable 0-1 rank — not a model output.

    Deliberately rewards the things that make a later post-mortem possible
    (dated evidence, an outside source, a stated alternative) rather than how
    confident the reading sounds. Ranking by confidence is how a system learns
    to sound sure.
    """
    score = 0.0
    score += min(evidence, 10) / 10 * 0.25       # breadth
    score += min(dated, 5) / 5 * 0.30            # checkable in time
    score += 0.25 if independent else 0.0        # not just self-published
    score += min(alternatives, 3) / 3 * 0.10     # considered otherwise
    score += 0.10 if has_thesis else 0.0         # says something at all
    return round(min(score, 1.0), 3)


# --- the decision ------------------------------------------------------------
def classify(company, report: Optional[dict], *, as_of: str,
             market: Optional[MarketEvidence] = None,
             regime: str = "unknown",
             calibration: Optional[dict] = None,
             hypothesis_id: str = "") -> Opportunity:
    """Exactly one classification, with every gate that stopped it named.

    The order of the gates is the order a careful analyst would apply them,
    and each returns rather than accumulating, so the rationale names the
    FIRST reason this is not a position — the one worth acting on.
    """
    market = market or MarketEvidence()
    calibration = dict(calibration or {})
    company_id = getattr(company, "company_id", "") or ""
    instrument = getattr(company, "tradable_instrument", None)

    report = report or {}
    observations = _observations(report)
    dated = _dated(observations)
    independent = _has_independent(report, observations)
    thesis = _thesis_text(report)
    alternatives = _alternatives(report)
    invalidation = _invalidation(report)
    uncertainty = _first_sentences(report.get("evidence_gaps"), 4)
    monitoring = _first_sentences(report.get("questions"), 4)

    quality = _quality(evidence=len(observations), dated=len(dated),
                       independent=independent, alternatives=len(alternatives),
                       has_thesis=bool(thesis))

    def _out(classification: str, rationale: str, blocked: tuple = ()) -> Opportunity:
        return Opportunity(
            company_id=company_id, as_of=as_of,
            classification=classification, rationale=rationale,
            thesis=thesis, alternatives=alternatives, uncertainty=uncertainty,
            invalidation=invalidation, monitoring=monitoring,
            catalysts=tuple(market.catalysts),
            direction=market.direction if classification in ("BUY", "SELL") else "",
            probability=market.probability if classification in ("BUY", "SELL") else None,
            horizon_days=market.horizon_days if classification in ("BUY", "SELL") else None,
            upside_pct=market.upside_pct, downside_pct=market.downside_pct,
            risk_reward=market.risk_reward, market_source=market.source,
            hypothesis_id=hypothesis_id,
            evidence_count=len(observations), dated_evidence_count=len(dated),
            independent_source=independent, regime=regime, quality=quality,
            blocked_by=blocked, calibration=calibration)

    # 1. A private company cannot be a position. This is not a shortcoming of
    #    the analysis and the reasoning above is still worth keeping: it is how
    #    the engine learns about companies it can never trade, which is most of
    #    them. The universe enforces this invariant too; stating it here means
    #    the RECORD says why, not just the schema.
    if not instrument:
        return _out("NO_TRADE",
                    "There is no instrument to express a view in — this "
                    "company is not publicly tradable, so the analysis is kept "
                    "as company knowledge rather than a position.",
                    (NOT_TRADABLE,))

    # 2. No view. Two very different situations, told apart because they need
    #    opposite responses: nothing was retrieved (fix the retrieval), or
    #    plenty was retrieved and the strategic gate correctly declined to read
    #    a strategy from it (nothing to fix). Collapsing them was hiding which
    #    of the two the daily cycle was actually hitting.
    if not thesis:
        if not observations:
            return _out("NO_TRADE",
                        "Nothing could be retrieved about this company, so "
                        "there is no reading to take a position on.",
                        (NO_STRATEGIC_READING,))
        return _out("NO_TRADE",
                    f"{len(observations)} source(s) were read, and what the "
                    f"company publishes is not enough to read a strategy "
                    f"from — so no view is put forward and no position "
                    f"follows from one.",
                    (VIEW_WITHHELD,))

    # 3. Nothing dated. Without a date there is no "recent", so there is no
    #    change to trade and no way to say later whether we were early or wrong.
    if not dated:
        return _out("WATCH",
                    "The reading rests on undated material, so nothing here "
                    "can be called a recent change — there is no event to be "
                    "early or late to.",
                    (NO_DATED_EVIDENCE,))

    # 4. Everything is the company's own account of itself. A position taken
    #    purely on what a company says about itself is a position on its
    #    marketing.
    if not independent:
        return _out("WATCH",
                    "Every source is the company's own, so this reading has "
                    "not been checked against an outside account and is not "
                    "yet worth a position.",
                    (NO_OUTSIDE_SOURCE,))

    # 5. The strategic reading is sound and checkable — and still says nothing
    #    about direction. This is the honest end of the current pipeline.
    if market.is_empty:
        return _out("WATCH",
                    "The strategic reading is well-evidenced but says nothing "
                    "about direction or what is already priced in. A market "
                    "signal is required before this can become a position.",
                    (NO_MARKET_EVIDENCE,))

    # 6. There is a market view. Direction decides the side; an unusable
    #    risk/reward is a HOLD rather than a forced trade, because "not at this
    #    price" is a real answer and the mission is explicit that trade count
    #    is never the thing being optimised.
    if market.risk_reward is not None and market.risk_reward < 1.0:
        return _out("HOLD",
                    f"The view is directional but the payoff is unfavourable "
                    f"(risk/reward {market.risk_reward}): the downside is "
                    f"larger than the upside it is being taken for.")

    if market.direction == "up":
        return _out("BUY",
                    f"A dated, independently-corroborated reading supports "
                    f"upside, with {len(invalidation) or 'no'} stated way(s) "
                    f"to find out it is wrong.")
    if market.direction == "down":
        return _out("SELL",
                    f"A dated, independently-corroborated reading supports "
                    f"downside, with {len(invalidation) or 'no'} stated way(s) "
                    f"to find out it is wrong.")

    # A direction we do not recognise is not a coin flip.
    return _out("HOLD",
                f"The market input named a direction ({market.direction!r}) "
                f"this reasoner does not act on.")
