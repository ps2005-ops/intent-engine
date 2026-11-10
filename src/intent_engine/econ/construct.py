"""The life and death of a candidate psychological construct (Section 42).

WHY A CONSTRUCT HAS A LIFECYCLE AND NOT A CONFIG FLAG
-----------------------------------------------------
Section 7 permits frameworks -- Hawkins, IPEC, emotional-guidance taxonomies,
behavioural-economic constructs -- to PROPOSE dimensions. It forbids treating
any of them as physical truth. The difference between those two things is not
a matter of tone; it is whether there exists a code path that deletes the
dimension. This module is that path.

A construct here is a scientific object with a state, and the only way to
advance it is to survive `incremental.py`. The states are not decorative:

    CANDIDATE   somebody proposed it. No proxy, no measurement, no standing.
    OBSERVED    a proxy exists and has produced a real posterior.
    TESTED      it has faced the base-vs-augmented comparison once.
    REPLICATED  and again, on a sample that did not select it.
    PROMOTED    robust incremental value; may enter the causal graph.
    WEAKENED    it once passed and has stopped passing.
    RETIRED     it does not earn its place. It is removed.

THE ASYMMETRY IS DELIBERATE
---------------------------
Promotion requires two independent passes in different regimes. Retirement
requires one clear failure. That is not fairness, it is the correct cost
asymmetry: a promoted construct enters the causal graph and starts informing
decisions, while a retired one costs only the effort of having tested it.

WHAT "REMOVE IT" MEANS
----------------------
`RETIRED` is terminal and `active_dimensions()` excludes it. A retired
construct may not be silently resurrected by a later cycle that happens to
find a positive delta; `revive()` exists, requires an explicit reason, and
sends it back to CANDIDATE rather than to PROMOTED.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .incremental import (
    IMPROVEMENT, INSUFFICIENT_SAMPLE, NOT_ROBUST, NO_IMPROVEMENT, Comparison,
)
from .vocabulary import (
    CANDIDATE, COLLECTIVE_DIMENSIONS, COLLECTIVE_STATES, OBSERVED_C, PROMOTED,
    REPLICATED, RETIRED, TESTED, WEAKENED, EconError, require,
)

CONTRACT = "econ_construct.v1"

#: Independent passes required before a construct may enter the causal graph.
#: Two, in different regimes -- a relationship that only holds in expansions
#: is a regime artefact, and the whole point of the holdout design is to be
#: able to notice that.
PASSES_FOR_PROMOTION = 2

#: Legal transitions. A construct cannot jump from CANDIDATE to PROMOTED
#: because someone liked the theory.
_ALLOWED = {
    CANDIDATE: {OBSERVED_C, RETIRED},
    OBSERVED_C: {TESTED, RETIRED, CANDIDATE},
    TESTED: {REPLICATED, WEAKENED, RETIRED, OBSERVED_C},
    REPLICATED: {PROMOTED, WEAKENED, RETIRED},
    PROMOTED: {WEAKENED, RETIRED},
    WEAKENED: {REPLICATED, RETIRED, TESTED},
    RETIRED: {CANDIDATE},          # only via revive(), with a stated reason
}


class ConstructRefused(EconError):
    """An illegal transition, or a promotion with nothing behind it."""


@dataclass(frozen=True)
class Trial:
    """One comparison, recorded against the construct that it tested."""

    at: str
    regime: str
    horizon_days: int
    population: str
    n_paired: int
    delta: float
    verdict: str
    survived_fdr: bool
    comparison_name: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == IMPROVEMENT and self.survived_fdr

    def as_dict(self) -> dict:
        return {"at": self.at, "regime": self.regime,
                "horizon_days": self.horizon_days,
                "population": self.population, "n_paired": self.n_paired,
                "delta": self.delta, "verdict": self.verdict,
                "survived_fdr": self.survived_fdr, "passed": self.passed,
                "comparison_name": self.comparison_name}


def trial_from(c: Comparison, *, at: str) -> Trial:
    return Trial(at=at, regime=c.regime, horizon_days=c.horizon_days,
                 population=c.population, n_paired=c.n_paired, delta=c.delta,
                 verdict=c.verdict, survived_fdr=bool(c.survives_fdr),
                 comparison_name=c.name)


@dataclass(frozen=True)
class Construct:
    """One candidate dimension, with everything that has happened to it."""

    dimension: str
    state: str = CANDIDATE
    #: Which framework or reading proposed it. Recorded so that a framework
    #: whose every construct retires can itself be retired (Section 7).
    proposed_by: str = ""
    proxy: str = ""
    trials: Tuple[Trial, ...] = ()
    history: Tuple[dict, ...] = ()
    retired_reason: str = ""

    def __post_init__(self) -> None:
        require(self.dimension in COLLECTIVE_DIMENSIONS,
                f"{self.dimension!r} is not a declared dimension")
        require(self.state in COLLECTIVE_STATES,
                f"unknown construct state {self.state!r}")

    @property
    def passes(self) -> int:
        return sum(1 for t in self.trials if t.passed)

    @property
    def regimes_passed(self) -> List[str]:
        return sorted({t.regime for t in self.trials if t.passed})

    @property
    def failures(self) -> int:
        return sum(1 for t in self.trials
                   if t.verdict in (NO_IMPROVEMENT, NOT_ROBUST))

    @property
    def best_delta(self) -> Optional[float]:
        passed = [t.delta for t in self.trials if t.passed]
        return max(passed) if passed else None

    @property
    def active(self) -> bool:
        return self.state != RETIRED

    @property
    def usable_in_causal_graph(self) -> bool:
        """Only a PROMOTED construct may become a node in Section 16's graph.

        This is the join between the two halves of the architecture: a
        psychological edge cannot exist unless the construct at its end has
        paid for itself in forecast skill.
        """
        return self.state == PROMOTED

    def as_dict(self) -> dict:
        return {"dimension": self.dimension, "state": self.state,
                "proposed_by": self.proposed_by, "proxy": self.proxy,
                "passes": self.passes, "failures": self.failures,
                "regimes_passed": self.regimes_passed,
                "best_delta": self.best_delta, "active": self.active,
                "usable_in_causal_graph": self.usable_in_causal_graph,
                "retired_reason": self.retired_reason,
                "trials": [t.as_dict() for t in self.trials]}


def propose(dimension: str, *, proposed_by: str, proxy: str = ""
            ) -> Construct:
    require(bool(proposed_by),
            "a construct records who proposed it, so that a framework whose "
            "constructs all retire can itself be retired (Section 7)")
    return Construct(dimension=dimension, state=CANDIDATE,
                     proposed_by=proposed_by, proxy=proxy)


def _move(c: Construct, to: str, *, at: str, why: str) -> Construct:
    if to not in _ALLOWED[c.state]:
        raise ConstructRefused(
            f"{c.dimension}: {c.state} -> {to} is not a legal transition. "
            f"From {c.state} the only moves are {sorted(_ALLOWED[c.state])}. "
            "A construct that could jump straight to PROMOTED would make the "
            "whole pipeline decorative.")
    return replace(c, state=to,
                   history=c.history + ({"at": at, "from": c.state, "to": to,
                                         "why": why},))


def observe(c: Construct, *, proxy: str, at: str) -> Construct:
    """A real proxy has produced a real posterior for this construct."""
    require(bool(proxy), "OBSERVED means a named proxy measured it")
    return replace(_move(c, OBSERVED_C, at=at,
                         why=f"proxy {proxy!r} produced a posterior"),
                   proxy=proxy)


def record(c: Construct, trial: Trial) -> Construct:
    """Record a trial and move the construct to wherever it now belongs.

    The state is DERIVED from the record, not asserted alongside it. A caller
    cannot record a failure and separately claim the construct passed.
    """
    trials = c.trials + (trial,)
    nxt = replace(c, trials=trials)
    at = trial.at

    if trial.verdict == INSUFFICIENT_SAMPLE:
        return replace(nxt, history=c.history + (
            {"at": at, "from": c.state, "to": c.state,
             "why": f"trial on n={trial.n_paired} was below the floor; "
                    "state unchanged because nothing was learned"},))

    if trial.passed:
        passing_regimes = {t.regime for t in trials if t.passed}
        if c.state in (CANDIDATE, OBSERVED_C):
            return _move(nxt, TESTED, at=at,
                         why=f"passed in regime {trial.regime} "
                             f"(delta {trial.delta:+.4f})")
        if c.state in (TESTED, WEAKENED):
            if len(passing_regimes) >= PASSES_FOR_PROMOTION:
                return _move(nxt, REPLICATED, at=at,
                             why=f"passed in {len(passing_regimes)} distinct "
                                 f"regimes {sorted(passing_regimes)}")
            return replace(nxt, history=c.history + (
                {"at": at, "from": c.state, "to": c.state,
                 "why": f"passed again but in regime {trial.regime}, already "
                        "counted; replication requires a DIFFERENT regime"},))
        return nxt

    # A failure.
    if c.state in (PROMOTED, REPLICATED, TESTED):
        return _move(nxt, WEAKENED, at=at,
                     why=f"{trial.verdict} in regime {trial.regime} "
                         f"(delta {trial.delta:+.4f})")
    return replace(nxt, history=c.history + (
        {"at": at, "from": c.state, "to": c.state,
         "why": f"{trial.verdict}; construct has not yet earned a state to "
                "lose"},))


def promote(c: Construct, *, at: str) -> Construct:
    """Enter the causal graph. Refused unless the record actually supports it."""
    if c.state != REPLICATED:
        raise ConstructRefused(
            f"{c.dimension} is {c.state}; only a REPLICATED construct may be "
            "promoted. Promotion is what lets a psychological variable into "
            "the causal graph, and the graph is what founder surfaces read.")
    regimes = c.regimes_passed
    if len(regimes) < PASSES_FOR_PROMOTION:
        raise ConstructRefused(
            f"{c.dimension} passed in regimes {regimes}; promotion requires "
            f"{PASSES_FOR_PROMOTION} distinct regimes. A relationship that "
            "holds only in one regime is a regime artefact.")
    return _move(c, PROMOTED, at=at,
                 why=f"robust incremental value in {regimes}; "
                     f"best delta {c.best_delta:+.4f}")


def retire(c: Construct, *, at: str, reason: str) -> Construct:
    """Remove a construct that does not earn its place.

    Section 42's requirement, in one function: the engine must be able to
    conclude that fear adds no useful incremental predictive value, and act
    on it.
    """
    require(bool(reason), "a retirement states why")
    return replace(_move(c, RETIRED, at=at, why=reason), retired_reason=reason)


def revive(c: Construct, *, at: str, reason: str) -> Construct:
    """Bring a retired construct back — as a CANDIDATE, never as promoted."""
    require(c.state == RETIRED, "only a retired construct is revived")
    require(bool(reason), "a revival states what changed")
    return replace(_move(c, CANDIDATE, at=at, why=f"revived: {reason}"),
                   retired_reason="")


# =============================================================================
# THE REGISTER
# =============================================================================

def active_dimensions(constructs: Sequence[Construct]) -> List[str]:
    return sorted(c.dimension for c in constructs if c.active)


def promoted_dimensions(constructs: Sequence[Construct]) -> List[str]:
    return sorted(c.dimension for c in constructs if c.usable_in_causal_graph)


def retired_dimensions(constructs: Sequence[Construct]) -> List[str]:
    return sorted(c.dimension for c in constructs if c.state == RETIRED)


def apply_report(constructs: Sequence[Construct],
                 comparisons: Sequence[Comparison], *, at: str,
                 retire_after_failures: int = 2) -> List[Construct]:
    """Fold a whole comparison family into the register, in one pass.

    `retire_after_failures` is the only place a construct dies automatically.
    Two clear failures, having never passed, is enough: the alternative is a
    register that accumulates constructs nobody will ever delete, which is
    how a taxonomy becomes a permanent assumption.
    """
    by_dim: Dict[str, Construct] = {c.dimension: c for c in constructs}
    for comp in comparisons:
        cur = by_dim.get(comp.dimension)
        if cur is None or not cur.active:
            continue
        cur = record(cur, trial_from(comp, at=at))
        if (cur.passes == 0 and cur.failures >= retire_after_failures
                and cur.state != RETIRED):
            cur = retire(cur, at=at, reason=(
                f"{cur.failures} comparisons, none showing robust "
                f"incremental value over the base economic model"))
        elif cur.state == REPLICATED:
            cur = promote(cur, at=at)
        by_dim[comp.dimension] = cur
    return [by_dim[d] for d in sorted(by_dim)]


def summarise(constructs: Sequence[Construct]) -> dict:
    by_state = {s: [] for s in COLLECTIVE_STATES}
    for c in constructs:
        by_state[c.state].append(c.dimension)
    return {"contract": CONTRACT, "total": len(constructs),
            "by_state": {s: sorted(v) for s, v in by_state.items() if v},
            "promoted": promoted_dimensions(constructs),
            "retired": retired_dimensions(constructs),
            "active": active_dimensions(constructs),
            "usable_in_causal_graph": promoted_dimensions(constructs),
            "detail": [c.as_dict() for c in constructs]}
