"""A source that is down must not read as an economy that went quiet.

THE FAILURE THIS MODULE IS BUILT AGAINST, MEASURED
--------------------------------------------------
The Bureau of Labor Statistics has returned `HTTP Error 503: Service
Unavailable` on every recorded cycle. One of six macro series families is
down and has been for the whole observed history.

That failure IS reported — `research.macro.failures` names it every cycle —
and it is reported nowhere else and remembered nowhere at all. There is no
state, so there is no streak, no `last_success`, no expected cadence and no
fallback. Every cycle rediscovers the outage and forgets it.

The consequence is not a missing number. It is that a belief fed by US
inflation stops receiving confirming evidence, and NOTHING IN THE ENGINE CAN
TELL THAT FROM THE ECONOMY GOING QUIET. One of those means the world changed;
the other means we went blind. They call for opposite responses and they
produce identical counts.

OBSERVABILITY FELL IS NOT ACTIVITY FELL
---------------------------------------
So the rule this module enforces is narrow and absolute: a degraded source
RAISES UNCERTAINTY and NEVER WEAKENS THE CLAIM. A thesis whose evidence
source went dark is not a weaker thesis. It is the same thesis, less
observable, and the honest sentence is "we have less visibility", not
"activity has fallen".

This is the same shape as `observability is not validity`, where a real
rivalry with a silent rival is unlearnable — and the engine's job is to say
which of the two it is looking at.

AN UNRECOGNISED FAILURE IS THE ONLY INFORMATION THERE IS
--------------------------------------------------------
The states below are a closed vocabulary, and a failure that matches none of
them is `UNCLASSIFIED` carrying its raw message. It is deliberately NOT
mapped onto the nearest neighbour: a 503 and a schema change need different
responses, and guessing between them destroys the one signal the outage
produced. `failure pages: suppress only when understood`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "source_health.v1"

# --- the states -------------------------------------------------------------
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNAVAILABLE = "UNAVAILABLE"
RATE_LIMITED = "RATE_LIMITED"
AUTH_EXPIRED = "AUTH_EXPIRED"
SCHEMA_CHANGED = "SCHEMA_CHANGED"
PARSER_BROKEN = "PARSER_BROKEN"
STALE = "STALE"
RETIRED = "RETIRED"
#: A failure whose message matches no known signature. Not an error state so
#: much as an honest one: the raw message is carried forward intact.
UNCLASSIFIED = "UNCLASSIFIED"

STATES = (HEALTHY, DEGRADED, UNAVAILABLE, RATE_LIMITED, AUTH_EXPIRED,
          SCHEMA_CHANGED, PARSER_BROKEN, STALE, RETIRED, UNCLASSIFIED)

#: States in which the source is not delivering what it is supposed to.
#: `STALE` is included: a feed answering with month-old figures is failing at
#: its job even though every call succeeds.
IMPAIRED = frozenset({DEGRADED, UNAVAILABLE, RATE_LIMITED, AUTH_EXPIRED,
                      SCHEMA_CHANGED, PARSER_BROKEN, STALE, UNCLASSIFIED})

#: Failure signatures, most specific first. Ordered rather than a dict
#: because "429 Too Many Requests" contains "Requests" and several patterns
#: would otherwise match the same message.
_SIGNATURES: Tuple[Tuple[str, str], ...] = (
    (r"\b429\b|too many requests|rate.?limit", RATE_LIMITED),
    (r"\b40[13]\b|unauthorized|forbidden|invalid.{0,10}(key|token|"
     r"credential)|expired.{0,10}token", AUTH_EXPIRED),
    (r"\b50[0-9]\b|service unavailable|bad gateway|gateway time.?out",
     UNAVAILABLE),
    (r"timed? ?out|timeout|connection (refused|reset|aborted)|"
     r"name or service not known|temporary failure in name resolution",
     UNAVAILABLE),
    (r"keyerror|missing (column|field|key)|unexpected (column|field|key)|"
     r"schema", SCHEMA_CHANGED),
    (r"parse|decode|malformed|not valid json|expecting value|"
     r"no such element|attributeerror.*nonetype", PARSER_BROKEN),
)

#: Consecutive failures before an intermittent source is called UNAVAILABLE
#: rather than DEGRADED. One 503 is a bad minute; three in a row is an
#: outage, and the difference decides whether a fallback is worth taking.
OUTAGE_STREAK = 3


@dataclass(frozen=True)
class SourceHealth:
    """One source family's standing, and the evidence for it."""
    source_family: str
    state: str
    detected_at: str = ""
    last_success: str = ""
    failure_streak: int = 0
    expected_cadence_days: Optional[int] = None
    schema_version: str = ""
    fallback_family: str = ""
    failure: str = ""
    affected: Tuple[str, ...] = ()
    resolution: str = ""

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"unknown source state {self.state!r}")
        if self.state in IMPAIRED and not self.failure:
            raise ValueError(
                f"a {self.state} source must carry the failure that "
                f"established it; a state with no evidence cannot be "
                f"disputed and cannot be resolved")

    @property
    def impaired(self) -> bool:
        return self.state in IMPAIRED

    def as_dict(self) -> dict:
        return {"record": "source_health", "contract": CONTRACT,
                "source_family": self.source_family, "state": self.state,
                "detected_at": self.detected_at,
                "last_success": self.last_success,
                "failure_streak": self.failure_streak,
                "expected_cadence_days": self.expected_cadence_days,
                "schema_version": self.schema_version,
                "fallback_family": self.fallback_family,
                "failure": self.failure, "affected": list(self.affected),
                "resolution": self.resolution}


def classify(failure: str) -> str:
    """What KIND of failure this is, or UNCLASSIFIED with the message kept.

    Never guesses. A message matching no signature returns UNCLASSIFIED
    rather than the nearest neighbour, because a 503 and a schema change are
    different problems and the wrong guess destroys the only signal the
    outage produced.
    """
    text = str(failure or "").lower()
    if not text.strip():
        return HEALTHY
    for pattern, state in _SIGNATURES:
        if re.search(pattern, text):
            return state
    return UNCLASSIFIED


def assess(*, source_family: str, failure: str = "", as_of: str,
           prior: Optional[SourceHealth] = None,
           expected_cadence_days: Optional[int] = None,
           fallback_family: str = "",
           affected: Sequence[str] = ()) -> SourceHealth:
    """This cycle's standing for one source, given the last one.

    A success RESETS the streak and records `last_success`; it does not erase
    the history, which lives in the append-only log.
    """
    previous_streak = prior.failure_streak if prior else 0
    last_success = prior.last_success if prior else ""
    if not str(failure or "").strip():
        return SourceHealth(
            source_family=source_family, state=HEALTHY, detected_at=as_of,
            last_success=as_of, failure_streak=0,
            expected_cadence_days=expected_cadence_days,
            fallback_family=fallback_family, affected=tuple(affected))

    streak = previous_streak + 1
    state = classify(failure)
    # A transient class that keeps happening is an outage. The class itself
    # is preserved in the failure text; what changes is what we are entitled
    # to conclude about availability.
    if state == UNAVAILABLE and streak < OUTAGE_STREAK:
        state = DEGRADED
    return SourceHealth(
        source_family=source_family, state=state, detected_at=as_of,
        last_success=last_success, failure_streak=streak,
        expected_cadence_days=expected_cadence_days,
        fallback_family=fallback_family, failure=str(failure),
        affected=tuple(affected))


def from_collection(collected: dict, *, as_of: str,
                    prior: Dict[str, SourceHealth] = None,
                    attempted: Sequence[str] = ()) -> List[SourceHealth]:
    """Every attempted source family's standing, successes included.

    Successes are recorded, not just failures. A log that only keeps the
    outages cannot answer "when did this last work", which is the question
    that decides whether silence is new.
    """
    prior = prior or {}
    failures = dict(collected.get("failures") or {})
    families = list(attempted) or sorted(
        set(failures) | set(collected.get("series_succeeded_names") or ()))
    if not families:
        # `collect` reports the count of successes and the names of failures.
        # With nothing else to go on, the failures are the only families we
        # can name — and naming only those is stated rather than implied.
        families = sorted(failures)
    return [assess(source_family=family, failure=failures.get(family, ""),
                   as_of=as_of, prior=prior.get(family))
            for family in families]


def observability(healths: Sequence[SourceHealth]) -> dict:
    """What the engine can currently SEE — never what it currently believes.

    This is the whole point of the module and the one number a caller may act
    on. It is deliberately not called "confidence": confidence is a property
    of a claim, and nothing here has read a claim.
    """
    total = len(healths)
    if not total:
        return {"contract": CONTRACT, "sources": 0,
                "observability": None,
                "reason": "no source was attempted, so visibility is "
                          "unmeasured rather than complete"}
    impaired = [h for h in healths if h.impaired]
    healthy = total - len(impaired)
    return {
        "contract": CONTRACT,
        "sources": total,
        "healthy": healthy,
        "impaired": len(impaired),
        "observability": round(healthy / total, 4),
        "by_state": {state: sum(1 for h in healths if h.state == state)
                     for state in STATES
                     if any(h.state == state for h in healths)},
        "impaired_families": sorted(h.source_family for h in impaired),
        "unclassified": sorted(h.source_family for h in healths
                               if h.state == UNCLASSIFIED),
        "reason": (
            f"{healthy} of {total} source families are delivering. "
            f"Reduced visibility is NOT reduced activity: a belief fed by an "
            f"impaired source stops receiving confirming evidence, and that "
            f"is the engine going blind rather than the economy going quiet"
            if impaired else
            f"all {total} source families are delivering"),
    }


class UncertaintyRaised(ValueError):
    """Raised when a caller tries to weaken a claim from a source outage."""


def apply_to_claim(*, standing: str, confidence: Optional[float],
                   healths: Sequence[SourceHealth],
                   sources_used: Sequence[str]) -> dict:
    """A source outage's effect on a claim: uncertainty up, claim untouched.

    The standing and the confidence come back EXACTLY as they went in. That
    is not an oversight and it is the reason this function exists rather than
    the caller doing the arithmetic inline: the tempting move is to shade the
    confidence down a little because the evidence stopped arriving, and that
    silently converts "we stopped looking" into "we believe it less".
    """
    impaired = {h.source_family: h for h in healths if h.impaired}
    hit = [name for name in sources_used if name in impaired]
    return {
        "contract": CONTRACT,
        # Untouched, by rule.
        "standing": standing,
        "confidence": confidence,
        "observability_reduced": bool(hit),
        "impaired_sources": sorted(hit),
        "uncertainty": ("RAISED" if hit else "UNCHANGED"),
        "reason": (
            f"{len(hit)} of {len(sources_used)} sources feeding this claim "
            f"are impaired ({', '.join(sorted(hit))}). The claim is "
            f"unchanged and LESS OBSERVABLE; absence of new confirming "
            f"evidence from a dark source is not evidence against it"
            if hit else
            "every source feeding this claim is delivering"),
    }


@dataclass(frozen=True)
class Fallback:
    """A substitution, recorded as a substitution."""
    question: str
    unavailable_family: str
    substitute_family: str
    reason: str
    temporally_valid: bool = True

    def as_dict(self) -> dict:
        return {"record": "source_fallback", "contract": CONTRACT,
                "question": self.question,
                "unavailable_family": self.unavailable_family,
                "substitute_family": self.substitute_family,
                "reason": self.reason,
                "temporally_valid": self.temporally_valid}


def route(healths: Sequence[SourceHealth], *, question: str,
          preferred: str, alternatives: Sequence[str] = ()) -> Optional[Fallback]:
    """Pick a substitute for an impaired source, and SAY that it is one.

    Returns None when the preferred source is fine — a fallback record for a
    substitution that did not happen would make the provenance log lie in the
    safe direction, which is still lying.
    """
    state = {h.source_family: h for h in healths}
    if preferred not in state or not state[preferred].impaired:
        return None
    for candidate in alternatives:
        health = state.get(candidate)
        if health is None or not health.impaired:
            return Fallback(
                question=question, unavailable_family=preferred,
                substitute_family=candidate,
                reason=(f"{preferred} is {state[preferred].state} "
                        f"({state[preferred].failure[:80]})"))
    return None


def summarise(healths: Sequence[SourceHealth],
              fallbacks: Sequence[Fallback] = ()) -> dict:
    return {
        **observability(healths),
        "fallbacks": [f.as_dict() for f in fallbacks],
        "sources_detail": [h.as_dict() for h in healths],
        "note": ("a degraded source raises uncertainty and never weakens a "
                 "claim; an unrecognised failure is UNCLASSIFIED with its "
                 "message kept, never mapped onto the nearest known one"),
    }
