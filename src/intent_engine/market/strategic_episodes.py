"""Which rivalry could actually teach us how one actor answers another.

OBSERVABILITY IS NOT VALIDITY
-----------------------------
"Magento competes with Shopify" can be perfectly true and completely useless
for learning response behaviour. Across six official surfaces — business
adobe.com, developer.adobe.com, experienceleague.adobe.com and three more —
Magento returned ZERO retrievable release-note documents. A rivalry with one
observable party cannot produce an interaction, because an interaction needs
an action from one side and a response from the other.

So a candidate carries two independent judgements that must never be merged:

    relationship_standing   is this rivalry real?
    response_observability  could we ever SEE the answer?

A pair can be VALID and NOT_OBSERVABLE. Ranking on validity alone sends the
next wave to watch a company that does not publish.

WHY THIS RANKS LEARNABILITY AND NOT IMPORTANCE
----------------------------------------------
Salesforce is a more important competitor to more people than any changelog
this engine can read. That is an argument about the market, not about which
episode will teach the engine how rivals respond. Selecting the case where
the phenomenon is visible is not confirmation bias: nothing about the
RESULT is chosen, only whether the result can be observed at all.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "strategic_episode_candidate.v1"

# --- standing ---------------------------------------------------------------
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
NOT_OBSERVABLE = "NOT_OBSERVABLE"
STANDINGS = (HIGH, MEDIUM, LOW, NOT_OBSERVABLE)

#: An interaction needs BOTH parties to have published something. One side's
#: silence is not a weak signal; it is the absence of the second half.
MIN_ACTIONS_PER_SIDE = 1

#: An established object on at least one side is what makes the contest
#: locatable. Without it a "response" is two companies acting near each other.
MIN_ESTABLISHED_EITHER_SIDE = 1


@dataclass(frozen=True)
class StrategicEpisodeCandidate:
    candidate_id: str
    actor_a: str
    actor_b: str
    relationship_id: str
    competitive_object: str
    relationship_standing: str
    action_history_a: int
    action_history_b: int
    established_object_count_a: int
    established_object_count_b: int
    partial_object_count: int
    temporal_overlap: bool
    source_maturity: str
    response_observability: str
    founder_relevance: str
    voi: float
    standing: str
    reason: str
    provenance: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "candidate_id": self.candidate_id,
            "actor_a": self.actor_a, "actor_b": self.actor_b,
            "relationship_id": self.relationship_id,
            "competitive_object": self.competitive_object,
            "relationship_standing": self.relationship_standing,
            "action_history_a": self.action_history_a,
            "action_history_b": self.action_history_b,
            "established_object_count_a": self.established_object_count_a,
            "established_object_count_b": self.established_object_count_b,
            "partial_object_count": self.partial_object_count,
            "temporal_overlap": self.temporal_overlap,
            "source_maturity": self.source_maturity,
            "response_observability": self.response_observability,
            "founder_relevance": self.founder_relevance,
            "voi": round(self.voi, 4),
            "standing": self.standing, "reason": self.reason,
            "provenance": list(self.provenance),
        }


def observability(actions_a: int, actions_b: int) -> Tuple[str, str]:
    """Could this pair ever show us a response?

    Deliberately blunt and deliberately symmetric. A trigger with no
    observable counterparty and a counterparty with no observable trigger
    are the same failure seen from two sides.
    """
    if actions_a >= MIN_ACTIONS_PER_SIDE and actions_b >= MIN_ACTIONS_PER_SIDE:
        return "BOTH_SIDES_PUBLISH", "both actors have observed actions"
    if actions_a or actions_b:
        silent = "b" if actions_a else "a"
        return "ONE_SIDE_SILENT", (
            f"actor_{silent} has no observed action, so a response from them "
            f"could never be seen")
    return "NEITHER_SIDE_PUBLISHES", "neither actor has an observed action"


def score(*, actor_a: str, actor_b: str, relationship_id: str,
          competitive_object: str, relationship_standing: str,
          actions_a: int, actions_b: int,
          established_a: int = 0, established_b: int = 0,
          partial: int = 0, temporal_overlap: bool = False,
          source_maturity: str = "PROVISIONAL",
          founder_relevance: str = "UNKNOWN",
          voi: float = 0.0) -> StrategicEpisodeCandidate:
    """Rank one pair on whether an episode could be LEARNED from it."""
    obs, why = observability(actions_a, actions_b)
    provenance: List[str] = [f"observability: {why}"]

    if obs != "BOTH_SIDES_PUBLISH":
        standing, reason = NOT_OBSERVABLE, why
    elif (established_a + established_b) < MIN_ESTABLISHED_EITHER_SIDE:
        standing = LOW
        reason = ("both actors publish, but neither has an action whose "
                  "competitive object is established, so any sequence would "
                  "be two companies acting near each other")
        provenance.append("no established object on either side")
    elif not temporal_overlap:
        standing = MEDIUM
        reason = ("both actors publish and an object is established, but "
                  "their observed actions do not overlap in time, so no "
                  "sequence can be ordered yet")
        provenance.append("histories do not overlap in time")
    else:
        standing = HIGH
        reason = ("both actors publish, an object is established, and their "
                  "histories overlap in time")
        provenance.append("overlapping histories with an established object")

    if source_maturity == "PROVISIONAL" and standing == HIGH:
        standing = MEDIUM
        reason += ("; held at MEDIUM because the source family behind it is "
                   "still PROVISIONAL")
        provenance.append("source maturity caps the standing")

    raw = f"{actor_a}|{actor_b}|{relationship_id}".lower()
    return StrategicEpisodeCandidate(
        candidate_id="epi_" + str(abs(hash(raw)))[:12],
        actor_a=actor_a, actor_b=actor_b, relationship_id=relationship_id,
        competitive_object=competitive_object,
        relationship_standing=relationship_standing,
        action_history_a=actions_a, action_history_b=actions_b,
        established_object_count_a=established_a,
        established_object_count_b=established_b,
        partial_object_count=partial, temporal_overlap=temporal_overlap,
        source_maturity=source_maturity, response_observability=obs,
        founder_relevance=founder_relevance, voi=voi,
        standing=standing, reason=reason, provenance=tuple(provenance))


_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2, NOT_OBSERVABLE: 3}


def rank(candidates: Sequence[StrategicEpisodeCandidate]
         ) -> Tuple[StrategicEpisodeCandidate, ...]:
    """Best learnable first. VOI breaks ties WITHIN a standing and never
    across one: a high-value question about an unobservable pair is still
    unobservable."""
    return tuple(sorted(
        candidates, key=lambda c: (_ORDER.get(c.standing, 9), -c.voi,
                                   c.actor_a, c.actor_b)))


def summarise(candidates: Sequence[StrategicEpisodeCandidate]) -> dict:
    by_standing = collections.Counter(c.standing for c in candidates)
    ranked = rank(candidates)
    best = next((c for c in ranked if c.standing in (HIGH, MEDIUM)), None)
    return {
        "contract": CONTRACT,
        "candidates": len(candidates),
        "by_standing": {s: by_standing.get(s, 0) for s in STANDINGS
                        if by_standing.get(s, 0)},
        "best_learnable": (best.as_dict() if best else None),
        "note": ("relationship validity and response observability are "
                 "separate judgements. A pair can be a real rivalry and "
                 "NOT_OBSERVABLE, and ranking on validity alone sends the "
                 "next wave to watch a company that does not publish."),
    }
