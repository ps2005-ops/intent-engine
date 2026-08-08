"""What the engine would have expected if it had been wrong — kept, and reused.

WHY THIS IS NOT `counterfactual.py`
-----------------------------------
`counterfactual.py` asks whether a DECISION was well made given what was
knowable. This asks a different question about the same episodes: given the
outcome, which of two explanations does it discriminate, and what should the
engine do differently the next time it sees this shape.

The first is about the past. This is memory: an episode is only worth keeping
if a later, ANALOGOUS episode can be recognised and handled differently. So
every record here carries `future_use_scope`, and a lesson that cannot state
where it applies is not stored.

WHY THE ALTERNATIVE HAS TO BE PREDICTIVE
----------------------------------------
"It might have been a one-off" is not an alternative explanation; it is a
hedge. An alternative earns its place only if it predicts something DIFFERENT
from the leading explanation, because otherwise no observation could ever
separate them and the pair is decoration.

So both explanations must state what they expect next, and the two statements
must differ. A record whose two expectations are the same is refused.

BUILT FROM RESOLVED EPISODES ONLY
---------------------------------
Every episode here is a belief that was declared on dated evidence, committed
to a direction in advance, and then scored by a later observation. Nothing is
constructed to illustrate a point. The engine has five such episodes and this
module reads them; when it has fifty it will read those.

THE TWO REAL LESSONS THIS FOUND
-------------------------------
Both came out of the ledger rather than being written into it:

1. Cloudflare held `demand_strengthening` AND `demand_weakening` at once. The
   weakening belief was opened by "Revenue Rises 36% as Restructuring Widens
   GAAP Loss" — a sentence whose DEMAND content is up and whose MARGIN content
   is down. The later observation separated them, and what it taught is about
   the classifier, not about Cloudflare: a cost signal sharing a sentence with
   a revenue signal must not open a demand belief.

2. Duolingo's `demand_weakening` was opened by "Stock Falls on Q2 2026
   Earnings" and contradicted by "Beats, Raises Outlook — But Stock Drops".
   The share price fell both times and demand did not. A price move is a
   market's opinion about a company, not an observation of it.
"""
from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "counterfactual_episode.v1"

STRENGTHENED = "STRENGTHENED"
WEAKENED = "WEAKENED"
UNRESOLVED = "UNRESOLVED"

#: Where a lesson may be applied next. Deliberately coarse — a lesson scoped
#: to one company is nearly worthless, and one scoped to "everything" is
#: nearly always wrong.
THIS_COMPANY = "THIS_COMPANY"
THIS_MECHANISM = "THIS_MECHANISM"          # the belief family, any company
THIS_CLASSIFIER = "THIS_CLASSIFIER"        # how evidence becomes an event
ANY_SUBJECT = "ANY_SUBJECT"
SCOPES = (THIS_COMPANY, THIS_MECHANISM, THIS_CLASSIFIER, ANY_SUBJECT)


class EpisodeRejected(ValueError):
    """The episode was asked to hold a counterfactual that predicts nothing."""


@dataclass(frozen=True)
class CounterfactualEpisode:
    episode_id: str
    subject: str
    observed_outcome: str
    leading_explanation: str
    strongest_alternative: str
    expected_outcome_under_leading: str
    expected_outcome_under_alternative: str
    discriminating_evidence: str
    resolution: str
    lesson: str
    future_use_scope: str
    provenance: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "episode_id": self.episode_id,
            "subject": self.subject,
            "observed_outcome": self.observed_outcome,
            "leading_explanation": self.leading_explanation,
            "strongest_alternative": self.strongest_alternative,
            "expected_outcome_under_leading":
                self.expected_outcome_under_leading,
            "expected_outcome_under_alternative":
                self.expected_outcome_under_alternative,
            "discriminating_evidence": self.discriminating_evidence,
            "resolution": self.resolution, "lesson": self.lesson,
            "future_use_scope": self.future_use_scope,
            "provenance": dict(self.provenance),
        }

    def applies_to(self, *, subject: str, family: str) -> bool:
        """Whether this memory should be consulted for a new episode."""
        scope = self.future_use_scope
        if scope == ANY_SUBJECT:
            return True
        if scope == THIS_COMPANY:
            return subject == self.subject
        if scope == THIS_MECHANISM:
            return family == self.provenance.get("family", "")
        if scope == THIS_CLASSIFIER:
            return True          # the classifier runs on every subject
        return False


def episode(*, subject: str, observed_outcome: str, leading: str,
            alternative: str, expected_under_leading: str,
            expected_under_alternative: str, discriminating_evidence: str,
            resolution: str, lesson: str, scope: str,
            provenance: Optional[Dict[str, str]] = None
            ) -> CounterfactualEpisode:
    """Admit one episode, or refuse it for predicting nothing.

    The two refusals are the whole contract. An alternative that expects the
    same thing as the leading explanation cannot be separated from it by any
    observation, and a lesson with no scope cannot be retrieved.
    """
    if not alternative.strip():
        raise EpisodeRejected(
            "an episode with no alternative is a story, not a test")
    left = " ".join(expected_under_leading.lower().split())
    right = " ".join(expected_under_alternative.lower().split())
    if not left or not right:
        raise EpisodeRejected(
            "both explanations must state what they expect next; an "
            "explanation that predicts nothing cannot be wrong")
    if left == right:
        raise EpisodeRejected(
            "the two explanations expect the same thing, so no observation "
            "could ever separate them — this pair is decoration")
    if scope not in SCOPES:
        raise EpisodeRejected(f"unknown scope {scope!r}")
    if not lesson.strip():
        raise EpisodeRejected("an episode with no lesson is not memory")
    raw = f"{subject}|{leading}|{alternative}"
    return CounterfactualEpisode(
        episode_id="cf_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        subject=subject, observed_outcome=observed_outcome,
        leading_explanation=leading, strongest_alternative=alternative,
        expected_outcome_under_leading=expected_under_leading,
        expected_outcome_under_alternative=expected_under_alternative,
        discriminating_evidence=discriminating_evidence,
        resolution=resolution, lesson=lesson, future_use_scope=scope,
        provenance=dict(provenance or {}))


# --- reading real episodes out of the ledger --------------------------------
#
# The alternative for each family is the reading the SAME evidence would
# support if the mechanism did not operate. Written per family because "it was
# a one-off" is not an alternative — it predicts nothing.
_ALTERNATIVES: Dict[str, Tuple[str, str, str]] = {
    "demand_strengthening": (
        "the reported figure rose on price, currency or an easy base period, "
        "with underlying volume flat",
        "the next period's revenue rises again, on volume the company "
        "attributes to demand",
        "the next period's revenue is flat once price and currency are "
        "stripped out, or the company attributes growth to price"),
    "demand_weakening": (
        "the evidence that opened this belief reported a COST or MARGIN "
        "movement, not a demand movement, and the two shared a sentence",
        "the next reported revenue or guidance figure falls",
        "the next reported revenue figure rises while margin or headcount "
        "falls — the cost story continues and the demand story never was"),
    "margin_protection": (
        "margin held because of an input-cost or mix change rather than "
        "because the company took cost out",
        "further cost reductions are announced, and margin holds as revenue "
        "is flat",
        "margin moves with input prices while the company's own cost base is "
        "unchanged"),
    "pricing_power": (
        "the price move was a mix change rather than a posture",
        "further price increases, or margin holding as volumes soften",
        "the price level reverts once mix normalises, with no discount "
        "programme announced"),
}

#: When a MARKET REACTION opened the belief, the strongest alternative is not
#: about the mechanism at all — it is that the observation was never about the
#: company. Selecting the alternative from the OPENING EVIDENCE rather than
#: from the family alone is what keeps the stored pair honest: an alternative
#: that does not fit the episode it is attached to teaches the wrong lesson.
_PRICE_ALTERNATIVE = (
    "the evidence that opened this belief reported a SHARE-PRICE movement, "
    "which is the market's opinion about the company rather than an "
    "observation of it",
    "the next reported revenue or guidance figure falls, matching the price",
    "the next reported revenue or guidance figure rises while the share "
    "price falls — the price was reacting to expectations, not to demand")


def _alternative_for(family: str, opened: Sequence[str]):
    opening = " ".join(opened).lower()
    if any(word in opening for word in _PRICE_WORDS):
        return _PRICE_ALTERNATIVE
    return _ALTERNATIVES.get(family)


#: What the outcome of a reconciliation says about the belief. `CONTRADICTED`
#: is the informative one: the engine committed to a direction and the world
#: came back the other way, which is the only shape that can teach anything
#: an agreement could not.
_RESOLUTION = {
    "CONFIRMED": STRENGTHENED,
    "PARTIALLY_CONFIRMED": STRENGTHENED,
    "CONTRADICTED": WEAKENED,
}


def build(rows: Sequence[dict]) -> Tuple[CounterfactualEpisode, ...]:
    """Construct episodes from the ledger's real, resolved reconciliations."""
    evidence = {r.get("evidence_id"): r for r in rows
                if r.get("record") == "evidence"}
    expectations = {r.get("expectation_id"): r for r in rows
                    if r.get("record") == "expectation"}
    beliefs = {r.get("belief_id"): r for r in rows
               if r.get("record") == "belief"}

    out: List[CounterfactualEpisode] = []
    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        resolution = _RESOLUTION.get(str(row.get("outcome") or ""))
        if not resolution:
            continue
        exp = expectations.get(row.get("expectation_id")) or {}
        family = str(exp.get("metric") or "")
        opened_facts = [str((evidence.get(e) or {}).get("fact") or "")
                        for e in (exp.get("evidence_basis") or ())]
        alternative = _alternative_for(family, opened_facts)
        if not alternative:
            # No stated alternative for this family means no episode. Silence
            # is correct: a fabricated alternative would be the decoration
            # `episode` exists to refuse.
            continue
        belief = beliefs.get(row.get("hypothesis_id")) or {}
        subject = str(row.get("subject") or exp.get("subject") or "")
        opened = opened_facts
        closed = [str((evidence.get(e) or {}).get("fact") or "")
                  for e in (row.get("evidence_ids") or ())]
        alt_claim, expect_leading, expect_alt = alternative

        observed = (f"{row.get('observed_direction') or '?'} — "
                    + (closed[0][:200] if closed else "no closing evidence"))
        try:
            out.append(episode(
                subject=subject, observed_outcome=observed,
                leading=str(belief.get("proposition") or ""),
                alternative=alt_claim,
                expected_under_leading=expect_leading,
                expected_under_alternative=expect_alt,
                discriminating_evidence=(closed[0][:240] if closed else ""),
                resolution=resolution,
                lesson=_lesson(family, resolution, subject, opened, closed),
                scope=_scope(family, resolution, opened),
                provenance={
                    "family": family, "subject": subject,
                    "belief_id": str(row.get("hypothesis_id") or ""),
                    "expectation_id": str(row.get("expectation_id") or ""),
                    "outcome": str(row.get("outcome") or ""),
                    "opened_by": "; ".join(o[:120] for o in opened[:2]),
                    "closed_by": "; ".join(c[:120] for c in closed[:2]),
                    "preregistered_at": str(exp.get("preregistered_at") or ""),
                    "evaluated_at": str(row.get("evaluated_at") or ""),
                }))
        except EpisodeRejected:
            continue
    return tuple(out)


#: Words whose presence in the OPENING evidence means the belief was proposed
#: by a cost or price observation rather than a demand one.
_COST_WORDS = ("loss", "restructur", "layoff", "cutting", "cost", "margin",
               "impairment", "writedown", "write-down")
#: A market's opinion about a company is not an observation of the company.
_PRICE_WORDS = ("stock falls", "stock drops", "shares fall", "shares drop",
                "shares slide", "stock slides", "shares jump", "stock jumps",
                "shares surge", "soars")


def _lesson(family: str, resolution: str, subject: str,
            opened: Sequence[str], closed: Sequence[str]) -> str:
    """What a later, analogous episode should do differently.

    Read off the OPENING evidence, because the reusable failure is almost
    always in what was allowed to propose the belief rather than in what
    scored it.
    """
    opening = " ".join(opened).lower()
    if resolution == WEAKENED:
        if any(word in opening for word in _COST_WORDS):
            return ("the belief was opened by evidence whose demand content "
                    "and cost content shared a sentence, and the classifier "
                    "bound the cost half to a demand family. A revenue "
                    "figure and a margin figure in one sentence must not "
                    "open a demand belief on the strength of the margin "
                    "half — the next such sentence should open a margin "
                    "belief or none")
        if any(word in opening for word in _PRICE_WORDS):
            return ("the belief was opened by a share-price movement. A "
                    "price move is the market's opinion about a company, "
                    "not an observation of it, and the later evidence here "
                    "showed the company beating and raising while the price "
                    "fell. Price language must not reach a demand family")
        return (f"the preregistered direction for {family} did not hold for "
                f"{subject}, and the opening evidence gives no reason it "
                f"should not have. That is a fact about the mechanism rather "
                f"than about how the belief was proposed")
    if any(word in opening for word in _PRICE_WORDS):
        return (f"the direction held for {subject}, but the belief was "
                f"opened partly by price language. A confirmation reached "
                f"through the wrong kind of evidence is not a licence to "
                f"keep using it — the same route produced a contradiction "
                f"elsewhere in this ledger")
    return (f"the preregistered direction for {family} held for {subject} "
            f"against a stated alternative that expected the opposite. One "
            f"test it could have failed, which is worth more than agreement "
            f"found afterwards and much less than a repeated result")


def _scope(family: str, resolution: str, opened: Sequence[str]) -> str:
    opening = " ".join(opened).lower()
    if resolution == WEAKENED and (
            any(w in opening for w in _COST_WORDS)
            or any(w in opening for w in _PRICE_WORDS)):
        # The failure is in how evidence becomes an event, so it applies
        # wherever that code runs — which is everywhere.
        return THIS_CLASSIFIER
    return THIS_MECHANISM


def recall(episodes: Sequence[CounterfactualEpisode], *, subject: str,
           family: str) -> Tuple[CounterfactualEpisode, ...]:
    """The memories a new episode of this shape should be checked against."""
    return tuple(e for e in episodes
                 if e.applies_to(subject=subject, family=family))


def summarise(episodes: Sequence[CounterfactualEpisode]) -> dict:
    by_resolution = collections.Counter(e.resolution for e in episodes)
    return {
        "contract": CONTRACT,
        "episodes": len(episodes),
        "subjects": sorted({e.subject for e in episodes}),
        "by_resolution": dict(by_resolution),
        "strengthened": by_resolution.get(STRENGTHENED, 0),
        "weakened": by_resolution.get(WEAKENED, 0),
        "by_scope": dict(collections.Counter(e.future_use_scope
                                             for e in episodes)),
        "lessons": [{"subject": e.subject, "scope": e.future_use_scope,
                     "lesson": e.lesson} for e in episodes
                    if e.resolution == WEAKENED],
        "note": ("an alternative that expects the same thing as the leading "
                 "explanation is refused: no observation could separate "
                 "them, so the pair would teach nothing"),
    }


# ---------------------------------------------------------------------------
# using a past episode on a new one — as an analogy, never as evidence
# ---------------------------------------------------------------------------
#
# THE LINE THIS DRAWS
# -------------------
# A stored episode says: last time a demand belief was opened by a headline
# whose demand content and cost content shared a sentence, the later evidence
# contradicted it. That is worth surfacing when the same shape appears again.
#
# It is NOT worth counting. The new company is not the old company, and an
# analogy that becomes evidence is how a system talks itself into a
# conclusion it has already reached elsewhere — the exact failure that makes
# "we have seen this before" dangerous rather than useful.
#
# So `apply` returns CANDIDATE alternatives and CANDIDATE falsifiers, tagged,
# with `is_evidence` false and no evidence ids. Nothing downstream can
# mistake one for an observation, because it carries none.
ANALOGY = "ANALOGY"


@dataclass(frozen=True)
class AppliedAnalogy:
    """A past episode, offered against a present one. Never counted."""
    episode_id: str
    from_subject: str
    to_subject: str
    shared_shape: str
    candidate_alternative: str
    candidate_falsifier: str
    what_it_is_not: str = (
        "an analogy, not an observation: it carries no evidence ids, cannot "
        "update a posterior, and cannot resolve an expectation")
    is_evidence: bool = False
    kind: str = ANALOGY

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "kind": self.kind,
            "episode_id": self.episode_id,
            "from_subject": self.from_subject, "to_subject": self.to_subject,
            "shared_shape": self.shared_shape,
            "candidate_alternative": self.candidate_alternative,
            "candidate_falsifier": self.candidate_falsifier,
            "is_evidence": self.is_evidence,
            "evidence_ids": [],
            "what_it_is_not": self.what_it_is_not,
        }


def apply(episodes: Sequence[CounterfactualEpisode], *, subject: str,
          family: str, opening_evidence: Sequence[str] = ()
          ) -> Tuple[AppliedAnalogy, ...]:
    """Offer past episodes of the same SHAPE against a new one.

    The shape is what makes an analogy admissible, and it is matched on the
    OPENING EVIDENCE rather than on the company: a cost signal opening a
    demand belief is the same shape whoever it happens to.
    """
    opening = " ".join(opening_evidence).lower()
    shapes = []
    if any(word in opening for word in _COST_WORDS):
        shapes.append(("a cost or margin figure sharing a sentence with a "
                       "revenue figure", _COST_WORDS))
    if any(word in opening for word in _PRICE_WORDS):
        shapes.append(("a share-price movement standing in for a company "
                       "observation", _PRICE_WORDS))

    out: List[AppliedAnalogy] = []
    for episode_ in recall(episodes, subject=subject, family=family):
        if episode_.subject == subject:
            continue          # not an analogy; the same case
        past_opening = episode_.provenance.get("opened_by", "").lower()
        for description, words in shapes:
            if not any(word in past_opening for word in words):
                continue
            out.append(AppliedAnalogy(
                episode_id=episode_.episode_id,
                from_subject=episode_.subject, to_subject=subject,
                shared_shape=description,
                candidate_alternative=episode_.strongest_alternative,
                candidate_falsifier=episode_.discriminating_evidence))
            break
    return tuple(out)
