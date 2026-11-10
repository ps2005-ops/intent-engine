"""Real causal episodes, built from tests the engine already ran.

WHY THIS IS NOT A NEW SCHEMA
----------------------------
`causal.py` has existed for a long time with a complete `CausalEdge` — cause,
effect, mechanism, lag, competing explanations, falsifiable status — and it
has held **zero edges**. It was reported as a built subsystem for weeks. The
missing piece was never the model; it was a source of episodes good enough to
justify an edge.

That source now exists and did not before. `observation_binding` produced the
engine's first informative reconciliations, and each one has exactly the shape
a causal episode needs:

    evidence E1 at t1   ->  opened belief B
    expectation X preregistered at t1, BEFORE the outcome
    evidence E2 at t2   ->  reconciliation CONFIRMED or CONTRADICTED

The preregistration is what makes these worth anything. A pair of observations
that happen to agree is a coincidence; a pair where the second was committed
to in advance, in a direction that could have come back wrong, is a test. Two
of the ten came back CONTRADICTED, which is the proof that they could.

WHY NO EDGE IS EVER `OBSERVED`
------------------------------
Causation is not observed. Events are observed; the link between them is
always inferred, and this module has no instrument that could do otherwise.
An edge here is HYPOTHESIZED on creation and can be promoted to SUPPORTED
only by repeated independent tests — never by one, and never by the passage
of time.

Every episode also carries what would have to be true for the link to be
wrong. The common-cause alternative is attached to every single edge, because
it is always live: a sector-wide demand shift moves the company's earnings and
its next guidance figure without either causing the other, and no amount of
within-company evidence can rule that out.
"""
from __future__ import annotations

import collections
import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import causal as C

CONTRACT = "causal_episode.v1"

#: Alive on every episode this construction can produce, so it is attached
#: automatically rather than left to whoever writes the next one.
COMMON_CAUSE = (
    "a sector-wide or macro demand shift moved both observations "
    "independently, and neither caused the other")
REPORTING_ARTEFACT = (
    "both observations come from the company's own reporting cadence, so "
    "the sequence may reflect when it discloses rather than what changed")

#: How a belief family's proposition becomes a cause->effect pair. Only
#: families whose expectation names a LATER, SEPARATELY OBSERVABLE event can
#: form an episode -- otherwise the "effect" is a restatement of the cause.
_LINKS: Dict[str, Tuple[str, str, str]] = {
    "demand_strengthening": (
        "observed demand strengthening",
        "the next reported revenue or guidance figure",
        "demand that is genuinely strengthening should show up again in the "
        "next reported period, because order intake precedes recognised "
        "revenue"),
    "demand_weakening": (
        "observed demand weakening",
        "the next reported revenue or guidance figure",
        "demand that is genuinely weakening should show up again in the next "
        "reported period, for the same reason in reverse"),
    "pricing_power": (
        "observed pricing action holding",
        "subsequent pricing or margin evidence",
        "a company able to hold price should not need to discount in the "
        "following period"),
    "market_share_seeking": (
        "observed price reduction",
        "subsequent volume or share evidence",
        "a price cut taken to buy share should be followed by volume, or the "
        "cut bought nothing"),
}


@dataclass(frozen=True)
class Episode:
    """One preregistered test, and what it did to a causal claim."""
    episode_id: str
    subject: str
    family: str
    timeline: Tuple[dict, ...]
    mechanism: str
    alternative_explanations: Tuple[str, ...]
    expectation: str
    expected_direction: str
    observed_direction: str
    outcome: str
    edge_id: str
    edge_status: str
    evidence_ids: Tuple[str, ...]
    what_was_learned: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "episode_id": self.episode_id,
            "subject": self.subject, "mechanism_family": self.family,
            "timeline": list(self.timeline), "mechanism": self.mechanism,
            "alternative_explanations": list(self.alternative_explanations),
            "expectation": self.expectation,
            "expected_direction": self.expected_direction,
            "observed_direction": self.observed_direction,
            "outcome": self.outcome, "edge_id": self.edge_id,
            "edge_status": self.edge_status,
            "evidence_ids": list(self.evidence_ids),
            "what_was_learned": self.what_was_learned,
        }


def _learned(outcome: str, family: str, subject: str) -> str:
    if outcome == "CONTRADICTED":
        return (f"The preregistered direction for {family} did not hold for "
                f"{subject}. The link is weakened, not refuted: one company "
                f"failing a mechanism is evidence against its universality, "
                f"not proof it never operates.")
    if outcome == "CONFIRMED":
        return (f"The preregistered direction held for {subject}. The link "
                f"survives one test it could have failed, which is worth "
                f"more than agreement found after the fact and much less "
                f"than a repeated result.")
    return (f"The observation was partially consistent for {subject}; "
            f"direction held and magnitude did not, so the mechanism's "
            f"strength is less established than its sign.")


def build(rows: Sequence[dict], *, limit: int = 0) -> Tuple[Episode, ...]:
    """Construct episodes from the ledger's real reconciliations.

    Reads only what is already recorded. Nothing here fabricates a link: an
    episode exists when, and only when, a belief was declared on dated
    evidence, an expectation was preregistered before the outcome, and a later
    observation scored it.
    """
    expectations = {r.get("expectation_id"): r for r in rows
                    if r.get("record") == "expectation"}
    evidence = {r.get("evidence_id"): r for r in rows
                if r.get("record") == "evidence"}

    out: List[Episode] = []
    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        outcome = str(row.get("outcome") or "")
        if outcome not in ("CONFIRMED", "CONTRADICTED",
                           "PARTIALLY_CONFIRMED"):
            continue
        exp = expectations.get(row.get("expectation_id")) or {}
        family = str(exp.get("metric") or "")
        link = _LINKS.get(family)
        if not link:
            # No separately observable effect, so no episode. Silence here is
            # correct: inventing one would make the "effect" a paraphrase of
            # the cause.
            continue
        cause, effect, mechanism = link
        subject = str(row.get("subject") or exp.get("subject") or "")

        opened = tuple(exp.get("evidence_basis") or ())
        closed = tuple(row.get("evidence_ids") or ())
        timeline = []
        for eid in opened:
            item = evidence.get(eid) or {}
            timeline.append({"at": item.get("observed_at", ""),
                             "role": "opened the belief",
                             "evidence_id": eid,
                             "fact": str(item.get("fact") or "")[:200]})
        timeline.append({"at": exp.get("preregistered_at", ""),
                         "role": "expectation preregistered",
                         "expectation_id": exp.get("expectation_id", ""),
                         "fact": str(exp.get("expected_event") or "")})
        for eid in closed:
            item = evidence.get(eid) or {}
            timeline.append({"at": item.get("observed_at", ""),
                             "role": "tested the expectation",
                             "evidence_id": eid,
                             "fact": str(item.get("fact") or "")[:200]})

        proposed = C.edge(
            cause=f"{subject}: {cause}", effect=f"{subject}: {effect}",
            direction=(C.POSITIVE if outcome != "CONTRADICTED"
                       else C.NEGATIVE),
            mechanism=mechanism,
            competing_explanations=(COMMON_CAUSE, REPORTING_ARTEFACT),
            evidence_ids=tuple(opened) + tuple(closed))

        out.append(Episode(
            episode_id=f"ep_{proposed.edge_id[5:]}_{subject}"[:64],
            subject=subject, family=family, timeline=tuple(timeline),
            mechanism=mechanism,
            alternative_explanations=(COMMON_CAUSE, REPORTING_ARTEFACT),
            expectation=str(exp.get("expected_event") or ""),
            expected_direction=str(exp.get("expected_direction") or ""),
            observed_direction=str(row.get("observed_direction") or ""),
            outcome=outcome, edge_id=proposed.edge_id,
            # HYPOTHESIZED, always. One test does not promote an edge, and
            # `causal.edge` has no argument that would let it.
            edge_status=proposed.status,
            evidence_ids=proposed.evidence_ids,
            what_was_learned=_learned(outcome, family, subject)))
        if limit and len(out) >= limit:
            break
    return tuple(out)


def summarise(episodes: Sequence[Episode]) -> dict:
    """The operator view of the causal graph's real, populated state."""
    by_outcome = collections.Counter(e.outcome for e in episodes)
    by_family = collections.Counter(e.family for e in episodes)
    edges = {e.edge_id for e in episodes}
    return {
        "contract": CONTRACT,
        "episodes": len(episodes),
        "distinct_edges": len(edges),
        "distinct_subjects": len({e.subject for e in episodes}),
        "by_outcome": dict(by_outcome),
        "by_family": dict(by_family),
        # Every edge is hypothesised. Nothing here has earned promotion, and
        # saying so is the point -- a causal graph whose edges all claim
        # SUPPORTED after one test each is a graph nobody should read.
        "observed_edges": 0,
        "inferred_edges": 0,
        "hypothesized_edges": len(edges),
        "edges_tested": len(episodes),
        "edges_contradicted": by_outcome.get("CONTRADICTED", 0),
        "promotion_note": (
            "no edge is promoted by a single test, and none is ever OBSERVED: "
            "events are observed, the link between them is inferred"),
    }
