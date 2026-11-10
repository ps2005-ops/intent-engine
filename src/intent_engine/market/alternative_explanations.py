"""Alternative explanations as engine state, not as sentences in a prompt.

WHY THIS ONE
------------
Four subsystems already depend on alternatives and every one of them holds a
STRING:

    causal_episodes      COMMON_CAUSE and REPORTING_ARTEFACT, two constants
    economic_chain       one `alternative_explanation` per link
    counterfactual_memory  a per-family sentence
    strategic_intelligence  `scaffold["alternatives"]`, a literal list

A string cannot be compared to the next episode's string, cannot accumulate
evidence, cannot be tested, and cannot be retired when it stops applying. So
the same alternative is restated in four vocabularies, the engine cannot tell
that "a sector-wide demand shift moved both" appeared for the eleventh time,
and nothing ever finds out whether it was right.

Moving it into state gives the engine the four things it has never had about
its own competing stories: IDENTITY (the same claim is the same record),
ACCUMULATION (evidence attaches), TESTING (an alternative predicts something,
so it can be scored), and RETIREMENT (one that never survives contact stops
being offered).

WHAT THE LLM MAY AND MAY NOT DO
-------------------------------
It may PROPOSE. That is genuinely useful — generating the competing story a
rule-based engine would not think of is the thing language models are good
at, and refusing the help would be a different kind of mistake.

It may not do anything else. The engine owns:

    identity        the id is derived from the normalised claim, here, so
                    two proposals of the same idea are one record
    storage         append-only, engine-side
    comparison      whether a new proposal is already held
    testing         an alternative is scored by the same reconciliation
                    machinery as a belief
    retirement      by evidence, never by a caller asserting it

A proposal arrives at `validation_status = PROPOSED` and NOTHING reads it as
an alternative until it has been validated. That is the whole safety
property: an LLM's suggestion is a candidate, and `standing` says so until
the engine's own machinery says otherwise.

WHY AN ALTERNATIVE MUST PREDICT
-------------------------------
Same rule as `counterfactual_memory`, for the same reason. "It might be
something else" cannot be wrong, so it can never be ruled out and will be
offered forever. An alternative is admitted only with `expected_observations`
and a `falsifier`, and the engine refuses one whose expectations match the
claim it competes with.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "alternative_explanation.v1"

# --- who proposed it --------------------------------------------------------
ENGINE = "ENGINE"
LLM_PROPOSED = "LLM_PROPOSED"
SOURCES = (ENGINE, LLM_PROPOSED)

# --- what the engine has done about it --------------------------------------
PROPOSED = "PROPOSED"            # arrived; nothing reads it yet
VALIDATED = "VALIDATED"          # well-formed and not a duplicate
REJECTED = "REJECTED"            # malformed, or it predicts nothing
SUPERSEDED = "SUPERSEDED"        # the same claim is already held
VALIDATION_STATES = (PROPOSED, VALIDATED, REJECTED, SUPERSEDED)

# --- how it has fared -------------------------------------------------------
UNTESTED = "UNTESTED"
SURVIVING = "SURVIVING"          # observations went its way at least once
RULED_OUT = "RULED_OUT"          # an observation it predicted did not occur
CONTESTED = "CONTESTED"
RETIRED = "RETIRED"              # ruled out repeatedly; stop offering it
STANDINGS = (UNTESTED, SURVIVING, RULED_OUT, CONTESTED, RETIRED)

#: Ruled out this many times, at independent subjects, and it stops being
#: offered. Two, not one: a competing story that failed once at one company
#: has an exception, not a refutation.
RETIRE_AFTER_RULED_OUT = 2


class AlternativeRejected(ValueError):
    """The store was asked to hold a competing story that competes with nothing."""


def _normalise(claim: str) -> str:
    """The comparable form of a claim. Identity is the engine's, not the
    proposer's: two wordings of one idea must collapse to one record, or
    accumulation never happens."""
    text = re.sub(r"[^a-z0-9 ]+", " ", (claim or "").lower())
    stop = {"a", "an", "the", "is", "was", "were", "are", "of", "to", "and",
            "that", "this", "it", "its", "in", "on", "by", "for", "with",
            "may", "might", "could", "would", "rather", "than", "both",
            "have", "has", "had", "been", "be", "at", "as", "or", "from"}
    return " ".join(sorted(w for w in text.split() if w not in stop))


@dataclass(frozen=True)
class AlternativeExplanation:
    explanation_id: str
    subject: str
    claim: str
    applies_to: Tuple[str, ...]
    supporting_evidence: Tuple[str, ...]
    contradicting_evidence: Tuple[str, ...]
    expected_observations: Tuple[str, ...]
    falsifier: str
    standing: str
    source: str
    validation_status: str
    times_ruled_out: int = 0
    times_survived: int = 0
    provenance: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "explanation_id": self.explanation_id,
            "subject": self.subject, "claim": self.claim,
            "applies_to": list(self.applies_to),
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "expected_observations": list(self.expected_observations),
            "falsifier": self.falsifier, "standing": self.standing,
            "source": self.source,
            "validation_status": self.validation_status,
            "times_ruled_out": self.times_ruled_out,
            "times_survived": self.times_survived,
            "provenance": dict(self.provenance),
        }

    @property
    def is_offerable(self) -> bool:
        """Whether anything downstream may present this as an alternative."""
        return (self.validation_status == VALIDATED
                and self.standing != RETIRED)


def propose(*, subject: str, claim: str, applies_to: Sequence[str],
            expected_observations: Sequence[str], falsifier: str,
            source: str = ENGINE, competes_with: str = "",
            supporting_evidence: Sequence[str] = (),
            provenance: Optional[Dict[str, str]] = None
            ) -> AlternativeExplanation:
    """Admit a proposal at PROPOSED, or refuse it for predicting nothing.

    Note what this does NOT do: it never returns VALIDATED. Validation is
    `validate`, which needs the store — an alternative cannot know on its own
    whether the engine already holds it.
    """
    if source not in SOURCES:
        raise AlternativeRejected(f"unknown source {source!r}")
    if not claim.strip():
        raise AlternativeRejected("an alternative with no claim claims nothing")
    predictions = tuple(p for p in expected_observations if p.strip())
    if not predictions:
        raise AlternativeRejected(
            "an alternative that predicts nothing cannot be ruled out, so it "
            "would be offered forever; state what it expects to see")
    if not falsifier.strip():
        raise AlternativeRejected("an alternative must name what would break it")
    if competes_with and _normalise(competes_with) == _normalise(claim):
        raise AlternativeRejected(
            "this restates the explanation it is supposed to compete with")
    if competes_with and any(_normalise(p) == _normalise(competes_with)
                             for p in predictions):
        raise AlternativeRejected(
            "its expectation is the leading explanation's own claim, so no "
            "observation could separate them")
    return AlternativeExplanation(
        explanation_id="alt_" + hashlib.sha256(
            _normalise(claim).encode()).hexdigest()[:12],
        subject=subject, claim=" ".join(claim.split()),
        applies_to=tuple(dict.fromkeys(applies_to)),
        supporting_evidence=tuple(supporting_evidence),
        contradicting_evidence=(),
        expected_observations=predictions, falsifier=falsifier.strip(),
        standing=UNTESTED, source=source, validation_status=PROPOSED,
        provenance=dict(provenance or {}))


class AlternativeStore:
    """The engine's own record of every competing story it holds.

    Deliberately not a free function: identity, comparison and retirement are
    only meaningful against a population, and the population is the thing an
    LLM proposal must be checked against.
    """

    def __init__(self, rows: Sequence[AlternativeExplanation] = ()):
        self._rows: Dict[str, AlternativeExplanation] = {
            r.explanation_id: r for r in rows}

    def __len__(self) -> int:
        return len(self._rows)

    def all(self) -> Tuple[AlternativeExplanation, ...]:
        return tuple(self._rows.values())

    def get(self, explanation_id: str) -> Optional[AlternativeExplanation]:
        return self._rows.get(explanation_id)

    def validate(self, proposal: AlternativeExplanation
                 ) -> AlternativeExplanation:
        """Move a proposal to VALIDATED, SUPERSEDED or REJECTED.

        An LLM proposal that restates something already held is SUPERSEDED,
        not stored twice: that is the accumulation the string version could
        never do, and it is the only way "we have seen this story eleven
        times" ever becomes sayable.
        """
        held = self._rows.get(proposal.explanation_id)
        if held is not None:
            merged = AlternativeExplanation(**{
                **held.__dict__,
                "applies_to": tuple(dict.fromkeys(
                    held.applies_to + proposal.applies_to)),
                "supporting_evidence": tuple(dict.fromkeys(
                    held.supporting_evidence + proposal.supporting_evidence)),
            })
            self._rows[merged.explanation_id] = merged
            return AlternativeExplanation(**{
                **proposal.__dict__, "validation_status": SUPERSEDED})
        validated = AlternativeExplanation(**{
            **proposal.__dict__, "validation_status": VALIDATED})
        self._rows[validated.explanation_id] = validated
        return validated

    def offerable(self, *, subject: str = "", context: str = ""
                  ) -> Tuple[AlternativeExplanation, ...]:
        """The alternatives anything downstream is allowed to present.

        A PROPOSED row is never returned. That is the safety property: an
        LLM's suggestion is visible to the engine and invisible to the
        founder until the engine has validated it.
        """
        out = []
        for row in self._rows.values():
            if not row.is_offerable:
                continue
            if subject and row.subject and row.subject != subject:
                continue
            if context and row.applies_to and context not in row.applies_to:
                continue
            out.append(row)
        return tuple(sorted(out, key=lambda r: r.explanation_id))

    def record_test(self, explanation_id: str, *, survived: bool,
                    evidence_id: str = "", subject: str = ""
                    ) -> Optional[AlternativeExplanation]:
        """Score one alternative against one observation.

        Retirement is by accumulated evidence and never by assertion: there
        is no argument to this method that sets a standing directly.
        """
        held = self._rows.get(explanation_id)
        if held is None:
            return None
        survived_count = held.times_survived + int(survived)
        ruled_out = held.times_ruled_out + int(not survived)
        if ruled_out >= RETIRE_AFTER_RULED_OUT:
            standing = RETIRED
        elif survived_count and ruled_out:
            standing = CONTESTED
        elif ruled_out:
            standing = RULED_OUT
        elif survived_count:
            standing = SURVIVING
        else:
            standing = UNTESTED
        updated = AlternativeExplanation(**{
            **held.__dict__,
            "times_survived": survived_count, "times_ruled_out": ruled_out,
            "standing": standing,
            "applies_to": tuple(dict.fromkeys(
                held.applies_to + ((subject,) if subject else ()))),
            "supporting_evidence": (
                tuple(dict.fromkeys(held.supporting_evidence
                                    + ((evidence_id,) if survived
                                       and evidence_id else ())))),
            "contradicting_evidence": (
                tuple(dict.fromkeys(held.contradicting_evidence
                                    + ((evidence_id,) if not survived
                                       and evidence_id else ())))),
        })
        self._rows[explanation_id] = updated
        return updated

    def summarise(self) -> dict:
        rows = self.all()
        return {
            "contract": CONTRACT,
            "alternatives": len(rows),
            "by_source": dict(collections.Counter(r.source for r in rows)),
            "by_validation": dict(collections.Counter(
                r.validation_status for r in rows)),
            "by_standing": dict(collections.Counter(r.standing
                                                    for r in rows)),
            "offerable": len(self.offerable()),
            "llm_proposed_not_yet_validated": sum(
                1 for r in rows if r.source == LLM_PROPOSED
                and r.validation_status != VALIDATED),
            "note": ("an LLM may propose; the engine owns identity, storage, "
                     "comparison, testing and retirement. A PROPOSED row is "
                     "never offered downstream"),
        }


# --- migrating what the engine already says in strings ----------------------

def from_engine_constants() -> Tuple[AlternativeExplanation, ...]:
    """The alternatives the engine already asserts, as records.

    These are the two constants `causal_episodes` attaches to every episode.
    They were true and reusable and had no identity, so eleven episodes
    carrying the same competing story could not be told from eleven
    different ones.
    """
    from . import causal_episodes as CE

    return (
        propose(
            subject="", claim=CE.COMMON_CAUSE,
            applies_to=("causal_episode", "economic_chain",
                        "counterfactual_memory"),
            expected_observations=(
                "the same movement appears at unrelated companies in the "
                "same period",
                "a sector or macro series moves in the same direction over "
                "the same window"),
            falsifier=("the movement is confined to this company while its "
                       "sector series is flat"),
            source=ENGINE,
            provenance={"migrated_from": "causal_episodes.COMMON_CAUSE"}),
        propose(
            subject="", claim=CE.REPORTING_ARTEFACT,
            applies_to=("causal_episode", "economic_chain"),
            expected_observations=(
                "the sequence follows the company's disclosure calendar "
                "rather than any operating change",
                "the same ordering recurs every reporting period"),
            falsifier=("the two observations arrive from different sources "
                       "on dates the company does not control"),
            source=ENGINE,
            provenance={"migrated_from": "causal_episodes.REPORTING_ARTEFACT"}),
    )


def accept_llm_proposal(store: AlternativeStore, *, subject: str, claim: str,
                        applies_to: Sequence[str],
                        expected_observations: Sequence[str],
                        falsifier: str, competes_with: str = "",
                        model: str = "") -> AlternativeExplanation:
    """Take a model's suggestion through the engine's own gate.

    The single entry point for anything a model proposed, so there is one
    place to look when asking whether model output can reach a founder. It
    cannot: `validate` is what makes a row offerable, and it runs here, under
    the engine's rules, against the engine's population.
    """
    proposal = propose(
        subject=subject, claim=claim, applies_to=applies_to,
        expected_observations=expected_observations, falsifier=falsifier,
        source=LLM_PROPOSED, competes_with=competes_with,
        provenance={"proposed_by": model or "unnamed model"})
    return store.validate(proposal)
