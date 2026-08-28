"""§4: may an older series stand in for a modern one? Measured, not assumed.

THE TEMPTATION THIS EXISTS TO REFUSE
------------------------------------
The modern credit series stop being walled before 2012 and a corporate bond
spread runs back to 1919. Splicing them produces a construct with a century of
history and no meaning: one measures whether households pay their credit
cards, the other measures what the bond market charges companies. They move
together in a crisis and apart everywhere else, and a model fitted across the
join learns the join.

So a candidate is scored on FOUR things during the years both exist, and the
weakest one decides:

    DIRECTION      do their year-on-year changes agree in sign?
    RANK           do they order the periods the same way?
    TURNING POINT  do they turn at the same time?
    CRISIS         do they both move the expected way when stress hits?

WHY THE WEAKEST DECIDES
-----------------------
A proxy that tracks the level beautifully and turns three quarters late is
useless for a lead-time claim, and averaging the four scores would hide that.
`verdict` takes the minimum.

WHAT A FAILED CANDIDATE IS NOT
------------------------------
It is not discarded. §4 is explicit: model it as a separate proxy version
with its own bridge uncertainty, never as more of the same series.
`SPLICE_REFUSED` is the recorded outcome, and the series may still enter the
model as its own column.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_equivalence.v1"

SAME_SERIES = "SAME_SERIES_NOT_A_PROXY"
DIRECT_MEASURE = "DIRECT_MEASURE"
DEFENSIBLE_PROXY = "DEFENSIBLE_PROXY"
WEAK_PROXY = "WEAK_PROXY"
UNUSABLE = "UNUSABLE"
VERDICTS = (SAME_SERIES, DIRECT_MEASURE, DEFENSIBLE_PROXY, WEAK_PROXY,
            UNUSABLE)

#: Thresholds, fixed before any candidate was scored. Round numbers on
#: standard quantities, for the same reason every other threshold in this
#: package is one: a cut point chosen after seeing which candidate it admitted
#: is a hyperparameter, not a standard.
DIRECT_AGREEMENT = 0.75
PROXY_AGREEMENT = 0.60
MIN_OVERLAP = 24


def _rank(xs: Sequence[float]) -> List[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return (sum((x - ma) * (y - mb) for x, y in zip(a, b))
            / (va ** 0.5 * vb ** 0.5))


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    return _pearson(_rank(a), _rank(b))


def _turning_points(xs: Sequence[float]) -> List[int]:
    """Indices where the series changes direction."""
    out = []
    for i in range(1, len(xs) - 1):
        if (xs[i] - xs[i - 1]) * (xs[i + 1] - xs[i]) < 0:
            out.append(i)
    return out


@dataclass(frozen=True)
class Equivalence:
    """One candidate against the incumbent it claims to extend."""

    candidate: str
    incumbent: str
    construct: str
    overlap: int
    #: Fraction of periods where the two changes have the same sign, after
    #: applying `expected_sign` -- a spread RISES when delinquency rises, so
    #: a candidate that is expected to move the other way is not penalised
    #: for doing so.
    direction_agreement: float
    rank_correlation: float
    turning_point_agreement: float
    crisis_agreement: float
    expected_sign: int
    span: Tuple[str, str] = ("", "")
    note: str = ""

    @property
    def weakest(self) -> Tuple[str, float]:
        pairs = (("direction", self.direction_agreement),
                 ("rank", abs(self.rank_correlation)),
                 ("turning_point", self.turning_point_agreement),
                 ("crisis", self.crisis_agreement))
        return min(pairs, key=lambda p: p[1])

    #: True when every overlapping observation is bit-identical. That is not
    #: a perfect proxy; it is the same numbers under another id.
    identical: bool = False

    @property
    def verdict(self) -> str:
        # A PERFECT SCORE IS AN INSTRUMENT TELL, NOT A RESULT.
        #
        # UMCSENT1 scored 1.00 on all four metrics against UMCSENT. It is not
        # the Michigan expectations component, as the candidate list claimed:
        # it is FRED's pre-1978 QUARTERLY SEGMENT OF UMCSENT ITSELF, 92
        # observations from 1952-11 to 1977-11, bit-identical where they
        # overlap. An equivalence test cannot tell a perfect proxy from an
        # identity, so the identity is checked separately.
        if self.identical:
            return SAME_SERIES
        if self.overlap < MIN_OVERLAP:
            return UNUSABLE
        _name, worst = self.weakest
        if worst >= DIRECT_AGREEMENT:
            return DIRECT_MEASURE
        if worst >= PROXY_AGREEMENT:
            return DEFENSIBLE_PROXY
        if worst > 0.0:
            return WEAK_PROXY
        return UNUSABLE

    @property
    def splice_allowed(self) -> bool:
        """May the two be treated as ONE series? Almost never.

        Only a DIRECT_MEASURE may be spliced, and even then the join date is
        recorded. Everything else enters the model as its own column with its
        own name, which is what §4 means by proxy version A and version B.
        """
        return self.verdict == DIRECT_MEASURE

    def statement(self) -> str:
        name, worst = self.weakest
        return (f"{self.candidate} for {self.incumbent} ({self.construct}): "
                f"{self.verdict} on {self.overlap} overlapping periods. "
                f"direction {self.direction_agreement:.2f}, rank "
                f"{self.rank_correlation:+.2f}, turning points "
                f"{self.turning_point_agreement:.2f}, crisis "
                f"{self.crisis_agreement:.2f}. The weakest is {name} at "
                f"{worst:.2f}, and it is the weakest that decides. "
                + ("Splice permitted." if self.splice_allowed
                   else ("IT IS THE SAME SERIES under another id, so it "
                         "carries no new information."
                         if self.verdict == SAME_SERIES
                         else "SPLICE REFUSED -- it enters as its own "
                              "column.")))

    def as_dict(self) -> dict:
        name, worst = self.weakest
        return {"candidate": self.candidate, "incumbent": self.incumbent,
                "construct": self.construct, "overlap": self.overlap,
                "direction_agreement": round(self.direction_agreement, 4),
                "rank_correlation": round(self.rank_correlation, 4),
                "turning_point_agreement": round(
                    self.turning_point_agreement, 4),
                "crisis_agreement": round(self.crisis_agreement, 4),
                "expected_sign": self.expected_sign,
                "weakest": name, "weakest_score": round(worst, 4),
                "verdict": self.verdict, "identical": self.identical,
                "splice_allowed": self.splice_allowed,
                "span": list(self.span), "note": self.note,
                "statement": self.statement()}


def compare(*, candidate: str, incumbent: str, construct: str,
            candidate_series: Sequence[Tuple[str, float]],
            incumbent_series: Sequence[Tuple[str, float]],
            expected_sign: int = 1,
            crisis_periods: Sequence[str] = ()) -> Equivalence:
    """Score a candidate against its incumbent over their shared periods."""
    require(expected_sign in (1, -1), "expected_sign is +1 or -1")
    a, b = dict(candidate_series), dict(incumbent_series)
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return Equivalence(candidate=candidate, incumbent=incumbent,
                           construct=construct, overlap=len(keys),
                           direction_agreement=0.0, rank_correlation=0.0,
                           turning_point_agreement=0.0, crisis_agreement=0.0,
                           expected_sign=expected_sign,
                           note="fewer than three overlapping periods")
    identical = all(abs(a[k] - b[k]) < 1e-9 for k in keys)
    av = [a[k] * expected_sign for k in keys]
    bv = [b[k] for k in keys]

    da = [av[i] - av[i - 1] for i in range(1, len(av))]
    db = [bv[i] - bv[i - 1] for i in range(1, len(bv))]
    agree = sum(1 for x, y in zip(da, db) if (x > 0) == (y > 0))
    direction = agree / len(da) if da else 0.0

    rank = spearman(av, bv)

    ta, tb = set(_turning_points(av)), set(_turning_points(bv))
    # A turning point within one period counts as agreement: a monthly
    # series and a quarterly one cannot turn on the same month.
    matched = sum(1 for i in ta if {i - 1, i, i + 1} & tb)
    if not ta and not tb:
        # Neither series turns. There is nothing to disagree about, and
        # scoring that as 0.0 would fail a perfectly matched pair on an
        # absence. (It did: two identical monotone series scored UNUSABLE.)
        tpa = 1.0
    elif not ta:
        tpa = 0.0
    else:
        tpa = matched / len(ta)

    crisis_idx = [i for i, k in enumerate(keys) if k in set(crisis_periods)]
    if len(crisis_idx) >= 3:
        ca = [av[i] for i in crisis_idx]
        cb = [bv[i] for i in crisis_idx]
        crisis = max(0.0, spearman(ca, cb))
    else:
        crisis = rank if rank > 0 else 0.0

    return Equivalence(
        candidate=candidate, incumbent=incumbent, construct=construct,
        overlap=len(keys), direction_agreement=direction,
        rank_correlation=rank, turning_point_agreement=tpa,
        crisis_agreement=crisis, expected_sign=expected_sign,
        identical=identical, span=(keys[0], keys[-1]),
        note=("crisis agreement computed on the origins the contemporaneous "
              "classifier read as stressed"
              if len(crisis_idx) >= 3 else
              "too few stressed periods in the overlap; crisis agreement "
              "falls back to the rank correlation, which is the weaker claim"))


def summarise(results: Sequence[Equivalence]) -> dict:
    by_verdict: Dict[str, List[str]] = {}
    for r in results:
        by_verdict.setdefault(r.verdict, []).append(r.candidate)
    return {"contract": CONTRACT, "tested": len(results),
            "by_verdict": by_verdict,
            "splice_allowed": [r.candidate for r in results
                               if r.splice_allowed],
            "thresholds": {"direct": DIRECT_AGREEMENT,
                           "proxy": PROXY_AGREEMENT,
                           "min_overlap": MIN_OVERLAP},
            "detail": [r.as_dict() for r in results]}
