"""How an actor has answered before — and why one answer is not a habit.

THE ERROR THIS IS BUILT AGAINST
-------------------------------
"Cloudflare cut prices when Fastly did, so Cloudflare responds to Fastly on
price." One episode. That sentence has the grammar of a behavioural trait and
the evidence of an anecdote, and once it is written down every later analysis
inherits it.

So one observation is a CANDIDATE and nothing else. A pattern needs repeated
COMPARABLE episodes — same trigger type, same actor, comparable context —
before it may be called anything stronger, and the count is carried on the
record so a reader never has to trust the label.

WHY DELAY IS PART OF THE PATTERN
--------------------------------
"They respond" is not usable. "They respond within a quarter" is: it tells a
reader when to stop waiting, and it is the part that can be wrong. A pattern
with no delay is a pattern that can absorb any observation whenever it
arrives, which makes it unfalsifiable.

WHY NON-RESPONSE IS A RESPONSE TYPE
-----------------------------------
An actor that did NOT answer is evidence about that actor, and a memory that
only records the times somebody moved will conclude that everybody always
moves. `NO_OBSERVED_RESPONSE` is a first-class response type.
"""
from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "actor_response_pattern.v1"

# --- standing ---------------------------------------------------------------
CANDIDATE = "CANDIDATE"          # one episode
EMERGING = "EMERGING"            # repeated, not yet across contexts
PATTERN = "PATTERN"              # repeated across comparable contexts
CONTRADICTED = "CONTRADICTED"    # the actor did the opposite
STANDINGS = (CANDIDATE, EMERGING, PATTERN, CONTRADICTED)

MIN_EPISODES_EMERGING = 2
MIN_EPISODES_PATTERN = 3

# --- response types ---------------------------------------------------------
MATCHED = "MATCHED"                          # did the same thing
COUNTERED = "COUNTERED"                      # did the opposite
DIFFERENTIATED = "DIFFERENTIATED"            # moved on another dimension
WITHDREW = "WITHDREW"
NO_OBSERVED_RESPONSE = "NO_OBSERVED_RESPONSE"
RESPONSE_TYPES = (MATCHED, COUNTERED, DIFFERENTIATED, WITHDREW,
                  NO_OBSERVED_RESPONSE)


class PatternRejected(ValueError):
    """A trait was claimed from evidence that cannot carry one."""


@dataclass(frozen=True)
class ActorResponsePattern:
    pattern_id: str
    actor: str
    trigger_type: str
    historical_context: str
    response_type: str
    delay_days: Optional[int]
    outcome: str
    evidence: Tuple[str, ...]
    scope: str
    repeat_count: int
    standing: str
    contexts: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "pattern_id": self.pattern_id,
            "actor": self.actor, "trigger_type": self.trigger_type,
            "historical_context": self.historical_context,
            "response_type": self.response_type,
            "delay_days": self.delay_days, "outcome": self.outcome,
            "evidence": list(self.evidence), "scope": self.scope,
            "repeat_count": self.repeat_count, "standing": self.standing,
            "contexts": list(self.contexts),
            "caution": ("one episode is a CANDIDATE, never a trait; "
                        f"this has {self.repeat_count}"),
        }


def observe(*, actor: str, trigger_type: str, response_type: str,
            delay_days: Optional[int], outcome: str, evidence: Sequence[str],
            context: str, scope: str = "") -> ActorResponsePattern:
    """Record ONE episode. Always CANDIDATE — there is no other opening."""
    if response_type not in RESPONSE_TYPES:
        raise PatternRejected(f"unknown response type {response_type!r}")
    if not trigger_type.strip():
        raise PatternRejected("a response with no trigger is just an action")
    if response_type != NO_OBSERVED_RESPONSE and delay_days is None:
        raise PatternRejected(
            "a response with no delay can absorb any observation whenever it "
            "arrives, which makes the pattern unfalsifiable")
    if not evidence:
        raise PatternRejected("a response with no evidence is a recollection")
    raw = f"{actor}|{trigger_type}|{response_type}".lower()
    return ActorResponsePattern(
        pattern_id="arp_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        actor=actor, trigger_type=trigger_type,
        historical_context=context, response_type=response_type,
        delay_days=delay_days, outcome=outcome, evidence=tuple(evidence),
        scope=scope or f"{actor} responding to {trigger_type}",
        repeat_count=1, standing=CANDIDATE, contexts=(context,))


def merge(held: ActorResponsePattern,
          episode: ActorResponsePattern) -> ActorResponsePattern:
    """Fold a comparable episode in, and promote only on the count.

    A DIFFERENT response type to the same trigger does not raise the count —
    it contradicts. An actor that matched once and countered once has no
    pattern, and saying so is the whole point of keeping the count.
    """
    if (held.actor, held.trigger_type) != (episode.actor,
                                           episode.trigger_type):
        raise PatternRejected("these episodes are not comparable")
    if held.response_type != episode.response_type:
        return ActorResponsePattern(**{
            **held.__dict__, "standing": CONTRADICTED,
            "evidence": tuple(dict.fromkeys(held.evidence
                                            + episode.evidence)),
            "contexts": tuple(dict.fromkeys(held.contexts
                                            + episode.contexts))})
    count = held.repeat_count + 1
    contexts = tuple(dict.fromkeys(held.contexts + episode.contexts))
    if count >= MIN_EPISODES_PATTERN and len(contexts) >= 2:
        standing = PATTERN
    elif count >= MIN_EPISODES_EMERGING:
        standing = EMERGING
    else:
        standing = CANDIDATE
    delays = [d for d in (held.delay_days, episode.delay_days)
              if d is not None]
    return ActorResponsePattern(**{
        **held.__dict__, "repeat_count": count, "standing": standing,
        "contexts": contexts,
        "delay_days": (sum(delays) // len(delays)) if delays else None,
        "evidence": tuple(dict.fromkeys(held.evidence + episode.evidence))})


def summarise(patterns: Sequence[ActorResponsePattern]) -> dict:
    by_standing = collections.Counter(p.standing for p in patterns)
    return {
        "contract": CONTRACT,
        "patterns": len(patterns),
        "by_standing": {s: by_standing.get(s, 0) for s in STANDINGS},
        "by_response_type": dict(collections.Counter(p.response_type
                                                     for p in patterns)),
        "actors": sorted({p.actor for p in patterns}),
        "usable_patterns": by_standing.get(PATTERN, 0),
        "note": ("one episode is a CANDIDATE. Promotion needs repeated "
                 "comparable episodes across more than one context, and a "
                 "different response to the same trigger CONTRADICTS rather "
                 "than accumulates"),
    }
