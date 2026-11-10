"""Behavioural observations -> construct posteriors. The measurement layer.

A PROXY IS A HYPOTHESIS, NOT A DEFINITION
-----------------------------------------
"Rising delinquency means financial anxiety" is a claim about the world that
could be wrong, and this module is careful never to let it read as a
definition. Each `Proxy` carries a `rationale` (why this observation should
load on this construct), a `sign`, a `noise` (how good the instrument is) and
a `contested` flag for the cases where the mapping is genuinely ambiguous.
The ambiguity is recorded rather than resolved by fiat, because a resolved-by
-fiat mapping is what makes a latent variable unfalsifiable.

THE SAVING-RATE PROBLEM
-----------------------
A rising saving rate is consistent with rising financial anxiety
(precautionary saving) AND with rising perceived control (people who feel in
command save more). Both are defensible. So `saving_rate` is marked contested
and given a wide noise, which is the honest encoding of "this observation
does not discriminate between the two constructs" -- rather than picking one
and letting the posterior claim a precision it does not have.

NORMALISATION
-------------
Every construct is defined on 0-1. Raw observations are not, so each proxy
declares the range it expects and clamps outside it. The clamp is reported:
a series that keeps pinning the top of its declared range is a proxy whose
range is wrong, and silently saturating it would hide that.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from .bayes import Observation
from .vocabulary import BEHAVIORAL, COLLECTIVE_DIMENSIONS, NODE_KINDS, require

CONTRACT = "econ_proxies.v1"

POSITIVE, NEGATIVE = "+", "-"


@dataclass(frozen=True)
class Proxy:
    """One behavioural observation kind, claimed to load on one construct."""

    kind: str
    dimension: str
    sign: str
    #: The raw range this observation is expected to occupy, used to place it
    #: on the construct's 0-1 scale. Stated per-proxy because "high" for a
    #: delinquency rate and "high" for a confidence index are different numbers.
    low: float
    high: float
    noise: float
    rationale: str
    #: True when the observation is consistent with more than one construct.
    #: A contested proxy may still be used; it may not be used alone.
    contested: bool = False

    def __post_init__(self) -> None:
        require(self.kind in NODE_KINDS[BEHAVIORAL],
                f"{self.kind!r} is not a declared BEHAVIORAL kind")
        require(self.dimension in COLLECTIVE_DIMENSIONS,
                f"{self.dimension!r} is not a declared collective dimension")
        require(self.sign in (POSITIVE, NEGATIVE),
                f"unknown sign {self.sign!r}")
        require(self.high > self.low, f"{self.kind}: empty range")
        require(self.noise > 0, f"{self.kind}: an instrument has noise")
        require(bool(self.rationale),
                f"{self.kind}->{self.dimension} states why this observation "
                "should load on this construct; an unexplained loading is an "
                "assumption wearing a number")

    def place(self, value: float) -> Tuple[float, bool]:
        """Put a raw reading on 0-1. Returns (placed, was_clamped)."""
        frac = (value - self.low) / (self.high - self.low)
        clamped = frac < 0.0 or frac > 1.0
        frac = min(1.0, max(0.0, frac))
        return (frac if self.sign == POSITIVE else 1.0 - frac), clamped

    def as_dict(self) -> dict:
        return {"kind": self.kind, "dimension": self.dimension,
                "sign": self.sign, "range": [self.low, self.high],
                "noise": self.noise, "rationale": self.rationale,
                "contested": self.contested}


def _p(kind, dimension, sign, low, high, noise, rationale, contested=False):
    return Proxy(kind=kind, dimension=dimension, sign=sign, low=low,
                 high=high, noise=noise, rationale=rationale,
                 contested=contested)


#: The declared proxy set. Every entry is a hypothesis that Section 18 may
#: kill. Noise values are deliberately conservative -- a survey of a few
#: thousand people asked a vague question is not a precise instrument, and
#: encoding it as one is how a posterior gets a confidence it never earned.
REGISTRY: Tuple[Proxy, ...] = (
    # --- financial anxiety ---------------------------------------------------
    _p("survey_confidence", "financial_anxiety", NEGATIVE, 40, 120, 0.12,
       "consumer confidence indices fall when households report worry about "
       "their own finances; inverted because high confidence is low anxiety"),
    _p("delinquency", "financial_anxiety", POSITIVE, 1.0, 8.0, 0.10,
       "households miss payments when they have run out of buffer; a "
       "behavioural record rather than a stated feeling"),
    _p("revolving_balance", "financial_anxiety", POSITIVE, -5.0, 15.0, 0.15,
       "revolving credit growth outpacing income growth indicates borrowing "
       "to cover ordinary consumption", contested=True),
    _p("defensive_spending", "financial_anxiety", POSITIVE, 0.0, 1.0, 0.12,
       "the share of the basket in staples rises when households protect "
       "against a worse month ahead"),
    _p("saving_rate", "financial_anxiety", POSITIVE, 2.0, 12.0, 0.22,
       "precautionary saving rises with anxiety -- but a high saving rate is "
       "equally consistent with perceived control, so this cannot "
       "discriminate on its own", contested=True),

    # --- perceived control ---------------------------------------------------
    _p("household_expectation", "perceived_control", POSITIVE, -30, 40, 0.13,
       "households who expect their own situation to improve report more "
       "command over it than those expecting only the economy to improve"),
    _p("job_switching", "perceived_control", POSITIVE, 1.0, 3.5, 0.11,
       "voluntarily leaving a job is a costly signal that a worker believes "
       "they can secure another"),
    _p("quits", "perceived_control", POSITIVE, 1.2, 3.2, 0.10,
       "the quits rate is the cleanest revealed-preference reading of "
       "workers' confidence in their own options"),
    _p("business_formation", "perceived_control", POSITIVE, 200, 500, 0.16,
       "new business applications commit personal capital to a belief that "
       "effort will produce a result"),

    # --- trust ---------------------------------------------------------------
    _p("trust_index", "institutional_trust", POSITIVE, 0.0, 1.0, 0.14,
       "published trust indices are the direct instrument, with all the "
       "framing sensitivity that survey instruments carry"),
    _p("survey_trust", "institutional_trust", POSITIVE, 0.0, 100.0, 0.15,
       "confidence-in-institutions survey batteries"),

    # --- risk appetite -------------------------------------------------------
    _p("retail_speculation", "risk_appetite", POSITIVE, 0.0, 1.0, 0.13,
       "the share of retail activity in the most speculative instruments "
       "available to households"),
    _p("risk_taking_proxy", "risk_appetite", POSITIVE, 0.0, 1.0, 0.14,
       "aggregate household allocation to volatile assets"),
    _p("credit_application", "risk_appetite", POSITIVE, 0.0, 1.0, 0.18,
       "applying for credit commits to a future obligation -- though it also "
       "rises under distress, which is the opposite state", contested=True),

    # --- time horizon / future orientation -----------------------------------
    _p("big_ticket_intent", "time_horizon", POSITIVE, 0.0, 1.0, 0.12,
       "intent to buy a durable good is a commitment to a horizon longer "
       "than the purchase itself"),
    _p("discretionary_intent", "future_orientation", POSITIVE, 0.0, 1.0, 0.13,
       "discretionary purchase intent is deferred first when the future "
       "feels short"),
    _p("trade_down", "future_orientation", NEGATIVE, 0.0, 1.0, 0.12,
       "substituting cheaper alternatives is the first observable act of a "
       "shortened horizon"),

    # --- newly instrumented, after the second probe round --------------------
    # Every loading below rests on a series this engine has actually called.
    # They are added because instruments were FOUND, not because the constructs
    # needed rescuing: four constructs are still retired below for having none.
    _p("debt_service_burden", "financial_anxiety", POSITIVE, 8.0, 14.0, 0.09,
       "the share of disposable income committed to debt service is the "
       "cleanest non-survey measure of how much room a household has left; "
       "unlike a sentiment index it cannot be moved by the news"),
    _p("underemployment", "perceived_security", NEGATIVE, 6.0, 18.0, 0.10,
       "U-6 counts people working part-time because they could not find "
       "full-time work — involuntary underemployment is the direct "
       "observable of insecurity, distinct from anxiety about it"),
    _p("employment_ratio", "perceived_security", POSITIVE, 55.0, 65.0, 0.12,
       "the share of the working-age population actually employed; a "
       "structural floor under a household's sense of its own position"),
    _p("underemployment", "perceived_control", NEGATIVE, 6.0, 18.0, 0.14,
       "involuntary part-time work is the absence of the outside option "
       "that makes a worker feel in command; weaker here than for security "
       "because it conflates 'cannot find' with 'chose not to look'",
       contested=True),
    _p("risk_taking_proxy", "risk_appetite", POSITIVE, 20.0, 55.0, 0.11,
       "household equity holdings as a share of financial assets is revealed "
       "allocation, not stated intent"),
    _p("big_ticket_intent", "time_horizon", POSITIVE, 0.0, 1.0, 0.11,
       "durable-goods orders and new-home sales commit a household to a "
       "horizon longer than the purchase; both are placed on a common scale "
       "by the proxy's declared range"),
    _p("survey_expectation", "future_orientation", POSITIVE, 95.0, 105.0, 0.13,
       "the OECD consumer confidence indicator is normalised around 100 and "
       "leads its own national surveys; used for orientation toward the "
       "future rather than for present anxiety"),

    # --- attention / language ------------------------------------------------
    _p("search_interest", "stress", POSITIVE, 0.0, 100.0, 0.20,
       "search volume for distress terms; a weak instrument because search "
       "behaviour is driven by news cycles as much as by experience",
       contested=True),
    _p("public_language", "anger", POSITIVE, 0.0, 1.0, 0.25,
       "aggregate sentiment of public text; the weakest instrument here, "
       "and marked as such rather than given a flattering noise",
       contested=True),
)

BY_KIND: Dict[str, List[Proxy]] = {}
for _proxy in REGISTRY:
    BY_KIND.setdefault(_proxy.kind, []).append(_proxy)

BY_DIMENSION: Dict[str, List[Proxy]] = {}
for _proxy in REGISTRY:
    BY_DIMENSION.setdefault(_proxy.dimension, []).append(_proxy)


def covered_dimensions() -> List[str]:
    return sorted(BY_DIMENSION)


def indistinguishable_pairs() -> List[tuple]:
    """Constructs whose instrument sets are identical.

    Section 3's wall, one level deeper than spelling. Two constructs measured
    by exactly the same series are not two constructs -- they are one
    construct with two names, and the incremental-value test would credit
    whichever happened to be tested first while the other rode along.

    Reported rather than raised, because the correct remedy depends on which
    it is: find a discriminating instrument, or retire one of them.
    """
    out = []
    dims = sorted(BY_DIMENSION)
    for i, a in enumerate(dims):
        ka = {p.kind for p in BY_DIMENSION[a]}
        for b in dims[i + 1:]:
            kb = {p.kind for p in BY_DIMENSION[b]}
            if ka == kb:
                out.append((a, b, sorted(ka)))
    return out


def uncovered_dimensions() -> List[str]:
    """Constructs nobody can currently measure.

    Reported, not hidden. A dimension with no proxy is permanently stuck at
    CANDIDATE, and a register that did not say so would look like a research
    programme in progress rather than one that cannot start.
    """
    return sorted(set(COLLECTIVE_DIMENSIONS) - set(BY_DIMENSION))


@dataclass(frozen=True)
class Reading:
    """One behavioural node, mapped onto one construct."""

    node_id: str
    kind: str
    dimension: str
    raw_value: float
    placed: float
    clamped: bool
    proxy: Proxy
    as_of: str
    publisher: str = ""

    def observation(self) -> Observation:
        # A clamped reading is at the edge of its declared range, which means
        # the range is probably wrong. Widen the noise rather than pretending
        # the saturated value is precise.
        noise = self.proxy.noise * (1.6 if self.clamped else 1.0)
        return Observation(node_id=self.node_id, value=self.placed,
                           noise=min(0.49, noise), as_of=self.as_of,
                           publisher=self.publisher)


def read_nodes(nodes: Iterable) -> List[Reading]:
    """Map BEHAVIORAL evidence nodes onto constructs.

    Nodes of other classes are IGNORED, not refused: a cycle hands this
    function everything it collected, and a MACRO node arriving here is
    normal rather than an error. A behavioural node with no value is skipped
    and reported by `summarise`, because a kind with no number cannot be
    placed on a scale.
    """
    out: List[Reading] = []
    for n in nodes:
        if getattr(n, "node_class", None) != BEHAVIORAL:
            continue
        value = getattr(n, "value", None)
        if value is None:
            continue
        for proxy in BY_KIND.get(getattr(n, "kind", ""), ()):
            placed, clamped = proxy.place(float(value))
            out.append(Reading(
                node_id=n.node_id, kind=n.kind, dimension=proxy.dimension,
                raw_value=float(value), placed=round(placed, 4),
                clamped=clamped, proxy=proxy,
                as_of=getattr(n, "occurred_at", "") or getattr(n, "available_at", ""),
                publisher=getattr(getattr(n, "provenance", None),
                                  "publisher", "")))
    return out


def group_by_dimension(readings: Sequence[Reading]
                       ) -> Dict[str, List[Reading]]:
    grouped: Dict[str, List[Reading]] = {}
    for r in readings:
        grouped.setdefault(r.dimension, []).append(r)
    return grouped


def sole_contested(readings: Sequence[Reading]) -> bool:
    """Every reading behind this construct is a contested proxy.

    A construct supported only by ambiguous instruments should not produce a
    narrow posterior. Callers widen uncertainty when this is true rather than
    refusing outright -- the reading is weak, not absent, and those are
    different states.
    """
    return bool(readings) and all(r.proxy.contested for r in readings)


def summarise(readings: Sequence[Reading]) -> dict:
    grouped = group_by_dimension(readings)
    return {"contract": CONTRACT, "readings": len(readings),
            "dimensions_touched": sorted(grouped),
            "clamped": sum(1 for r in readings if r.clamped),
            "contested_only": sorted(d for d, rs in grouped.items()
                                     if sole_contested(rs)),
            "proxies_declared": len(REGISTRY),
            "dimensions_covered": covered_dimensions(),
            "dimensions_with_no_proxy": uncovered_dimensions()}
