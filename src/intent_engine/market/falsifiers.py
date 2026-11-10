"""What would change the engine's mind, written down where it survives.

WHY THIS IS NOT OPTIONAL
------------------------
A system that learns indefinitely must remember what would make it wrong. A
falsifier that lives only in generated prose is re-invented every run, so the
engine can never notice that the disconfirming observation ARRIVED — the
thing it was waiting for goes past unrecognised.

WHY A FALSIFIER IS NOT A RESEARCH QUERY
---------------------------------------
    falsifier         "the next reported backlog declines materially"
    research query    "retrieve the next reported backlog figure"

The first is a condition on the world. The second is neutral and is what
actually gets asked. Turning a falsifier into "find evidence this belief is
wrong" produces a search for confirmation of the opposite, which is the same
disease with the sign flipped.

THE ENGINE OWNS VALIDATION
--------------------------
An LLM may PROPOSE a falsifier. It may not decide that one is admissible: a
falsifier that no observation could settle, or that names no window, is a
rhetorical gesture and is refused here.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

CONTRACT = "falsifier.v1"

# --- standing ---------------------------------------------------------------
OPEN = "OPEN"
RESOLVED_FALSIFIED = "RESOLVED_FALSIFIED"
RESOLVED_SURVIVED = "RESOLVED_SURVIVED"
EXPIRED = "EXPIRED"
STANDINGS = (OPEN, RESOLVED_FALSIFIED, RESOLVED_SURVIVED, EXPIRED)

# --- validation -------------------------------------------------------------
VALID = "VALID"
REFUSED_UNOBSERVABLE = "REFUSED_UNOBSERVABLE"
REFUSED_NO_WINDOW = "REFUSED_NO_WINDOW"
REFUSED_NOT_DISCRIMINATING = "REFUSED_NOT_DISCRIMINATING"

#: Wording that describes a feeling rather than an observation. A falsifier
#: has to name something a source could report.
_UNOBSERVABLE = re.compile(
    r"\b(?:seems?|feels?|appears?\s+weak|loses?\s+momentum|sentiment|"
    r"the\s+story\s+changes|vibes?|narrative\s+shifts?)\b", re.I)

#: A falsifier that would be satisfied by ordinary noise discriminates
#: nothing.
_NOT_DISCRIMINATING = re.compile(
    r"\b(?:anything\s+changes|any\s+news|something\s+happens|"
    r"the\s+number\s+moves)\b", re.I)


class FalsifierRejected(ValueError):
    pass


@dataclass(frozen=True)
class Falsifier:
    falsifier_id: str
    subject: str
    hypothesis_id: str
    observation_needed: str
    eligible_sources: Tuple[str, ...]
    resolution_window: str
    standing: str = OPEN
    validation_status: str = VALID
    created_at: str = ""
    resolved_at: str = ""
    resolution: str = ""
    provenance: Dict[str, str] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.standing == OPEN

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "falsifier_id": self.falsifier_id,
            "subject": self.subject, "hypothesis_id": self.hypothesis_id,
            "observation_needed": self.observation_needed,
            "eligible_sources": list(self.eligible_sources),
            "resolution_window": self.resolution_window,
            "standing": self.standing,
            "validation_status": self.validation_status,
            "created_at": self.created_at, "resolved_at": self.resolved_at,
            "resolution": self.resolution, "provenance": dict(self.provenance),
        }


def validate(observation_needed: str, *, resolution_window: str,
             eligible_sources: Sequence[str]) -> str:
    """Is this a condition on the world that a source could report?"""
    text = " ".join((observation_needed or "").split())
    if not text:
        return REFUSED_UNOBSERVABLE
    if _UNOBSERVABLE.search(text):
        return REFUSED_UNOBSERVABLE
    if _NOT_DISCRIMINATING.search(text):
        return REFUSED_NOT_DISCRIMINATING
    if not resolution_window.strip() or not tuple(eligible_sources):
        return REFUSED_NO_WINDOW
    return VALID


def propose(*, subject: str, hypothesis_id: str, observation_needed: str,
            eligible_sources: Sequence[str], resolution_window: str,
            created_at: str, provenance: Optional[Dict[str, str]] = None
            ) -> Falsifier:
    """Admit a falsifier, or refuse it with the term it is missing."""
    status = validate(observation_needed,
                      resolution_window=resolution_window,
                      eligible_sources=eligible_sources)
    if status != VALID:
        raise FalsifierRejected(
            f"{status}: {observation_needed!r} — a falsifier must name an "
            f"observation a source could report, inside a window, or it is a "
            f"rhetorical gesture the engine can never notice arriving")
    raw = f"{subject}|{hypothesis_id}|{observation_needed}".lower()
    return Falsifier(
        falsifier_id="fls_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        subject=subject.strip(), hypothesis_id=hypothesis_id.strip(),
        observation_needed=" ".join(observation_needed.split()),
        eligible_sources=tuple(eligible_sources),
        resolution_window=resolution_window[:10], standing=OPEN,
        validation_status=VALID, created_at=created_at[:10],
        provenance=dict(provenance or {}))


def research_question(falsifier: Falsifier) -> str:
    """The NEUTRAL question that would settle it.

    Never "find evidence the belief is wrong" — that is a search for
    confirmation of the opposite. The question asks for the OBSERVATION,
    and the observation is allowed to come back either way.
    """
    return (f"Retrieve the next reported observation bearing on "
            f"{falsifier.subject}: {falsifier.observation_needed}")


def resolve(falsifier: Falsifier, *, falsified: bool, observed_at: str,
            resolution: str) -> Falsifier:
    if not falsifier.is_open:
        return falsifier
    return Falsifier(**{
        **falsifier.__dict__,
        "standing": RESOLVED_FALSIFIED if falsified else RESOLVED_SURVIVED,
        "resolved_at": observed_at[:10], "resolution": resolution})


def expire(falsifier: Falsifier, *, as_of: str) -> Falsifier:
    """A window that closed with no observation. NOT the same as surviving:
    nobody looked, or nobody reported."""
    if not falsifier.is_open or as_of[:10] <= falsifier.resolution_window:
        return falsifier
    return Falsifier(**{**falsifier.__dict__, "standing": EXPIRED,
                        "resolved_at": as_of[:10],
                        "resolution": "the window closed with no eligible "
                                      "observation; this is not survival"})


def summarise(falsifiers: Sequence[Falsifier]) -> dict:
    import collections
    by_standing = collections.Counter(f.standing for f in falsifiers)
    return {
        "contract": CONTRACT,
        "falsifiers": len(falsifiers),
        "open": sum(1 for f in falsifiers if f.is_open),
        "by_standing": {s: by_standing.get(s, 0) for s in STANDINGS
                        if by_standing.get(s, 0)},
        "note": ("EXPIRED is not RESOLVED_SURVIVED: a window that closed "
                 "with nobody reporting is an absence of evidence, and "
                 "counting it as survival would let a belief harden on "
                 "silence"),
    }
