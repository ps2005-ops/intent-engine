"""Append-only persistence for beliefs, expectations and evidence.

WHY APPEND-ONLY
---------------
Same reason the asset ledger is: the value of a belief record is the trail, not
the current number. A store that overwrote would answer "what do we believe"
and lose "what changed our mind", and the second question is the one that shows
whether the engine is learning or drifting.

Rebuildable by construction. Every derived view — current posteriors, open
expectations — is a fold over the log, so the projection into the Business
Graph can be regenerated at any time and never becomes a second source of
truth.

A CORRUPT LINE IS SKIPPED, NEVER REPAIRED
-----------------------------------------
Matching `assets.AssetLedger` deliberately. Repairing a malformed row means
editing history, which is precisely what an append-only log exists to prevent.
`health` counts the skips so corruption is visible rather than silent.
"""
from __future__ import annotations

import datetime as _dt

import json
import pathlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import beliefs as B
from . import expectation as EXP
from . import micro_evidence as ME

DEFAULT_PATH = "reports/market/learning_ledger.jsonl"

BELIEF = "belief"
BELIEF_UPDATE = "belief_update"
EXPECTATION = "expectation"
RECONCILIATION = "reconciliation"
EVIDENCE = "evidence"
CYCLE = "cycle"
#: A belief's currency changing over time — stale, revalidated, retired.
#: A separate record kind rather than a field on the belief, because the
#: belief row is history: editing it to say "this is stale now" would
#: destroy the record of when it was not.
LIFECYCLE = "belief_lifecycle"
#: A fact the sweep read AGAIN. Not a second observation — the same one,
#: still there. Recorded so "this page still said X a week later" survives
#: without becoming a row that could test a belief.
EVIDENCE_SEEN = "evidence_seen"
#: A relationship between two actors, written where every other durable
#: thing is written.
#:
#: This kind did not exist until wave 11, and its absence is the reason
#: three valid COMPETES_WITH edges were discovered in wave 5 and measured as
#: ZERO in wave 10: `actor_relationships` built them, the run reported them,
#: and nothing could write them down. The store had `record_evidence`,
#: `record_expectation`, `record_cycle`, `record_reconciliation` and
#: `record_lifecycle` — and no way to record a relationship at all. The seam
#: was not broken; it was missing.
RELATIONSHIP = "relationship"
#: Later evidence for a relationship already on the ledger. Append-only,
#: exactly like `evidence_seen`: the original row is history and editing it
#: to add support would destroy the record of what was known when.
RELATIONSHIP_SUPPORT = "relationship_support"
#: A relationship the engine no longer holds. Never a deletion — the row
#: that asserted it stays, and this says when we stopped believing it.
RELATIONSHIP_RETIRED = "relationship_retired"
#: A preregistered CROSS-ACTOR expectation: what we think rival B will do
#: about rival A's move, written down BEFORE the answer is looked for.
#:
#: Distinct from EXPECTATION, which is a company-level expected
#: observation. This one had no write path either, and preregistration
#: whose record does not survive the process is not preregistration — the
#: whole claim is that it existed before the evidence.
CROSS_ACTOR_EXPECTATION = "cross_actor_expectation"
#: How a preregistered cross-actor expectation turned out.
CROSS_ACTOR_OUTCOME = "cross_actor_outcome"
#: The ADJUDICATION over a counterfactual episode: which explanation the
#: later evidence favoured, and the lesson drawn.
#:
#: The episodes themselves are a fold over the ledger and recompute every
#: run. The adjudication is not — it is a judgement made once, and the
#: retention audit read it as LOST for two waves because nothing wrote it.
COUNTERFACTUAL_ADJUDICATION = "counterfactual_adjudication"
#: A durable falsifier: what would change the engine's mind. Learning
#: indefinitely is impossible if this is forgotten every restart.
FALSIFIER = "falsifier"
#: A standing instruction to watch a counterparty for a preregistered
#: response.
RESPONSE_WATCH = "response_watch"
#: A competing objective attributed to an actor's move, kept with its
#: alternatives.
STRATEGIC_OBJECTIVE = "strategic_objective"
#: A grounded rivalry episode: whose action, whose counterparty, what object.
STRATEGIC_INTERACTION = "strategic_interaction"
#: One observed instance of an actor answering another. Observational
#: history, never a preregistration.
ACTOR_RESPONSE_EPISODE = "actor_response_episode"

#: One dated figure about one economic condition. DURABLE rather than
#: re-fetched, because an engine that reads the current value of a series
#: every cycle and keeps none of them can never see that a regime changed —
#: it only ever knows what the economy is doing today, which is exactly the
#: knowledge a world model is supposed to accumulate.
MACRO_OBSERVATION = "macro_observation"
#: One source family's standing per cycle. Successes are recorded too:
#: a log that keeps only the outages cannot answer "when did this last
#: work", which is the question that decides whether silence is new.
SOURCE_HEALTH = "source_health"
KNOWLEDGE_EFFECT = "knowledge_effect"

#: The choice, written BEFORE the external call, with the menu attached. Every
#: other research row in this ledger was inferred from a document that
#: survived, so an action that returned nothing left no trace. These three
#: kinds are the only ones that can hold a research action which produced
#: nothing, and they are therefore the only ones a policy can honestly learn
#: from.
RESEARCH_DECISION = "research_decision"
RESEARCH_OUTCOME = "research_outcome"
#: A consequence that arrived later. Appended beside the immediate outcome
#: rather than folded into it, because rewriting the first would destroy the
#: only honest record of what was knowable at the time.
RESEARCH_DELAYED_OUTCOME = "research_delayed_outcome"

#: One dated change to one thesis, and the knowledge effects that caused it.
#: Append-only and contiguous: this is the only record of what the engine used
#: to believe, and a reversal is only legible against it.
THESIS_REVISION = "thesis_revision"
#: The thesis as it stood at the end of a cycle, so the NEXT cycle has
#: something to compare against. Without it every cycle rebuilds its theses
#: from scratch and the temporal comparison is lost, which is why no revision
#: was ever written.
THESIS_SNAPSHOT = "thesis_snapshot"

#: How one method did on one series, out of sample. Persisted so the answer to
#: "which method works for which question, in this regime" accumulates instead
#: of being a comparison a human ran once and wrote down.
METHOD_PERFORMANCE = "method_performance"
#: One assumption of one method, tested against one series. Kept beside the
#: performance row because a method that won while its critical assumption
#: failed has produced a description, not an effect, and the two rows must be
#: read together or the win reads as an identification.
METHOD_ASSUMPTION_CHECK = "method_assumption_check"

#: One causal question the engine ASKED, with what it concluded — including,
#: and especially, a refusal.
#:
#: A-WIRE-001's first live cycle formulated 25 real questions, refused all 25
#: for a named missing prerequisite, rendered that in the cycle report, and
#: appended NOTHING here. So `causal_estimates_attempted` still folded to 0 —
#: the same number it reads when the capability has never run at all. A metric
#: that cannot tell "asked 25 and refused 25" from "never asked" is the
#: missing-versus-zero collapse one layer above the estimator, and it is the
#: layer the planner reads.
#:
#: A refusal is therefore as durable as an estimate would have been. That is
#: not generosity toward failure: the refusals ARE the finding right now, and
#: an engine that persisted only its successes would have a research history
#: that is a success log.
CAUSAL_ESTIMATE = "causal_estimate"

RECORD_KINDS = frozenset({BELIEF, BELIEF_UPDATE, EXPECTATION,
                          RECONCILIATION, EVIDENCE, CYCLE, LIFECYCLE,
                          EVIDENCE_SEEN, RELATIONSHIP, RELATIONSHIP_SUPPORT,
                          RELATIONSHIP_RETIRED, CROSS_ACTOR_EXPECTATION,
                          CROSS_ACTOR_OUTCOME,
                          COUNTERFACTUAL_ADJUDICATION, FALSIFIER,
                          RESPONSE_WATCH, STRATEGIC_OBJECTIVE,
                          KNOWLEDGE_EFFECT,
                          RESEARCH_DECISION, RESEARCH_OUTCOME,
                          RESEARCH_DELAYED_OUTCOME,
                          THESIS_REVISION, THESIS_SNAPSHOT,
                          METHOD_PERFORMANCE, METHOD_ASSUMPTION_CHECK,
                          STRATEGIC_INTERACTION, ACTOR_RESPONSE_EPISODE,
                          MACRO_OBSERVATION, SOURCE_HEALTH,
                          CAUSAL_ESTIMATE})

# What a session actually produced. Recorded as a class, not as a count,
# because "3 things happened" is the sentence this project keeps having to
# take back. A cycle that ingested forty observations and moved nothing is
# NOT a cycle that gained knowledge, and the ledger has to be able to say so
# without a reader doing arithmetic on five other fields.
NEW_KNOWLEDGE = "NEW_KNOWLEDGE"              # a belief was declared
BELIEF_MOVEMENT = "BELIEF_MOVEMENT"          # an existing posterior moved
OBSERVED_NO_IMPACT = "OBSERVED_NO_IMPACT"    # evidence arrived, nothing moved
UNCLASSIFIABLE_INPUT = "UNCLASSIFIABLE_INPUT"  # candidates, no events
NO_NEW_EVIDENCE = "NO_NEW_EVIDENCE"          # nothing arrived at all
OUTCOME_CLASSES = (NEW_KNOWLEDGE, BELIEF_MOVEMENT, OBSERVED_NO_IMPACT,
                   UNCLASSIFIABLE_INPUT, NO_NEW_EVIDENCE)


#: Predicates where "A relates to B" and "B relates to A" are the same claim.
#: Rivalry is mutual; supply is not.
SYMMETRIC_PREDICATES = frozenset({"COMPETES_WITH", "PARTNERS_WITH",
                                  "SUBSTITUTES_FOR", "COMPLEMENTS"})


def relationship_scope(row: dict) -> str:
    """What makes two relationship claims THE SAME claim.

    Not the id: ids are content hashes that move when an extractor changes,
    and re-deriving the same rivalry after a pattern edit must not create a
    second edge. Not the pair alone either — "Shopify and Salesforce contest
    e-commerce platforms" and "... contest field service" are two different
    economic claims about the same two companies, and collapsing them would
    lose the scope that makes a rivalry actionable.

    For a SYMMETRIC predicate the pair is sorted, so the same rivalry derived
    from Shopify's page and from Salesforce's page is one edge.
    """
    subject = str(row.get("subject_actor_id") or "").strip().lower()
    obj = str(row.get("object_actor_id") or "").strip().lower()
    predicate = str(row.get("predicate") or "").strip().upper()
    scope = str(row.get("competitive_object")
                or row.get("relationship_object") or "").strip().lower()
    pair = (" & ".join(sorted((subject, obj)))
            if predicate in SYMMETRIC_PREDICATES else f"{subject} -> {obj}")
    return f"{predicate}|{pair}|{scope}"


class LearningStore:
    """The append-only learning log, and folds over it."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = pathlib.Path(path)
        self._corrupt = 0

    # --- writing ----------------------------------------------------------
    def _append(self, record: str, payload: dict) -> None:
        if record not in RECORD_KINDS:
            raise ValueError(f"unknown record kind {record!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(payload)
        row["record"] = record
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def declare_belief(self, belief: B.StrategicBelief) -> bool:
        """Declare a belief once. Returns False if it was already declared.

        Idempotent because the cycle is: a nightly run that re-reads the same
        filings would otherwise append a fresh declaration every night. The
        fold already keeps the first, so the duplicates were invisible in the
        projection and unbounded on disk — the worst combination, because
        nothing would ever have surfaced the growth.
        """
        if belief.belief_id in self.belief_ids():
            return False
        self._append(BELIEF, belief.as_dict())
        return True

    def belief_ids(self) -> frozenset:
        return frozenset(r.get("belief_id") for r in self._rows()
                         if r.get("record") == BELIEF and r.get("belief_id"))

    def record_update(self, belief_id: str,
                      update: B.BeliefUpdate) -> None:
        payload = update.as_dict()
        payload["belief_id"] = belief_id
        self._append(BELIEF_UPDATE, payload)

    def record_causal_estimate(self, resolution) -> bool:
        """Persist one causal resolution, FITTED OR REFUSED. Idempotent.

        Keyed on `resolution_id`, which is derived from the question and the
        as-of date, so a nightly cycle that re-derives the same 25 refusals from
        the same unchanged events appends them once. Without that this row grows
        by 25 every night forever while the fold shows a constant number — the
        combination that hides its own growth, which this ledger has already
        paid for once with duplicate belief declarations.
        """
        payload = resolution.as_dict() if hasattr(resolution, "as_dict") \
            else dict(resolution)
        rid = payload.get("resolution_id")
        if not rid:
            raise ValueError("a causal estimate row needs a resolution_id")
        if rid in self.causal_estimate_ids():
            return False
        # WHEN this estimate was made. Every causal row written before
        # 2026-08-12 carried no timestamp of any kind — only a state such as
        # PANEL_UNAVAILABLE — so the whole causal channel was invisible to
        # every reporting window. That was a producer gap, not a reader gap:
        # no priority of field names can date a row that was never stamped.
        # Historical rows stay unstamped and report LEGACY_UNDATABLE; they are
        # not back-filled, because inventing a date for a past estimate is
        # exactly the kind of fabrication this ledger refuses.
        payload.setdefault("estimated_at", _dt.date.today().isoformat())
        self._append(CAUSAL_ESTIMATE, payload)
        return True

    def causal_estimate_ids(self) -> frozenset:
        return frozenset(r.get("resolution_id") for r in self._rows()
                         if r.get("record") == CAUSAL_ESTIMATE
                         and r.get("resolution_id"))

    def record_expectation(self, e: EXP.ExpectedObservation) -> bool:
        """Preregister once. A re-registered expectation is not a new test."""
        if e.expectation_id in self.expectation_ids():
            return False
        self._append(EXPECTATION, e.as_dict())
        return True

    def expectation_ids(self) -> frozenset:
        return frozenset(r.get("expectation_id") for r in self._rows()
                         if r.get("record") == EXPECTATION
                         and r.get("expectation_id"))

    def record_cycle(self, *, as_of: str, cycle: str, outcome: str,
                     detail: str = "", counts: Optional[dict] = None) -> bool:
        """One row per learning session, saying what class of thing happened.

        Idempotent on (as_of, cycle): a job that fires twice records one
        session, matching every other hosted job's contract. Replayable, and
        the only place the ledger states an interpretation rather than a fact
        — which is why the interpretation is a closed vocabulary.
        """
        if outcome not in OUTCOME_CLASSES:
            raise ValueError(f"unknown outcome class {outcome!r}")
        cycle_id = f"{as_of[:10]}|{cycle}"
        if cycle_id in self.cycle_ids():
            return False
        self._append(CYCLE, {"cycle_id": cycle_id, "as_of": as_of[:10],
                             "cycle": cycle, "outcome": outcome,
                             "detail": detail[:400],
                             "counts": dict(counts or {}),
                             "schema": "learning_cycle_record.v1"})
        return True

    def cycle_ids(self) -> frozenset:
        return frozenset(r.get("cycle_id") for r in self._rows()
                         if r.get("record") == CYCLE and r.get("cycle_id"))

    def cycles(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows() if r.get("record") == CYCLE)

    def record_reconciliation(self, r: EXP.Reconciliation) -> None:
        self._append(RECONCILIATION, r.as_dict())

    def record_evidence(self, e: ME.MicroEvidence) -> bool:
        """Ingest one observation once. Returns False if it is a re-read.

        Idempotent on OCCURRENCE, not on id, so rows written before the id
        included the sweep date are still recognised. A re-read appends an
        `evidence_seen` row instead: the fact that a page still says the same
        thing a week later is real information, and it is not a second
        observation that could score a belief against itself.
        """
        key = ME.occurrence_key(
            subject_company=e.subject_company,
            evidence_type=e.evidence_type, fact=e.fact, source=e.source)
        held = self._occurrence_first_seen()
        if key not in held:
            self._append(EVIDENCE, e.as_dict())
            return True
        # A re-read is only worth a row when it is a LATER day. Re-running
        # today's sweep is a replay, and a replay must leave the ledger
        # byte-identical — the property `test_break_append_only_by_replaying
        # _a_session` exists to hold. Same-day re-reads and repeats of a
        # sighting already recorded are both silent.
        seen_at = e.observed_at[:10]
        if seen_at <= held[key]:
            return False
        sighting = f"{e.evidence_id}|{seen_at}"
        if sighting not in self._sightings():
            self._append(EVIDENCE_SEEN, {
                "sighting_id": sighting, "evidence_id": e.evidence_id,
                "seen_at": seen_at, "subject_company": e.subject_company,
                "source": e.source, "occurrence_first_seen": held[key]})
        return False

    def _sightings(self) -> frozenset:
        return frozenset(r.get("sighting_id") for r in self._rows()
                         if r.get("record") == EVIDENCE_SEEN)

    def _occurrence_first_seen(self) -> Dict[str, str]:
        """occurrence key -> the date it was FIRST written."""
        out: Dict[str, str] = {}
        for r in self._rows():
            if r.get("record") != EVIDENCE:
                continue
            key = ME.occurrence_key(
                subject_company=str(r.get("subject_company") or ""),
                evidence_type=str(r.get("evidence_type") or ""),
                fact=str(r.get("fact") or ""),
                source=str(r.get("source") or ""))
            date = str(r.get("observed_at") or "")[:10]
            if key not in out or date < out[key]:
                out[key] = date
        return out

    def occurrence_keys(self) -> frozenset:
        """Every evidence row's occurrence identity, recomputed from the row.

        Recomputed rather than stored so the 249 rows written under the old
        date-bearing id are covered without rewriting history.
        """
        return frozenset(self._occurrence_first_seen())

    def re_observations(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == EVIDENCE_SEEN)

    # --- relationships ----------------------------------------------------

    def record_macro_observation(self, obs) -> bool:
        """Persist one dated economic figure. False if already held.

        Idempotent on `observation_id`, which is keyed on the series, the
        period, the publication date and the value — so re-reading the same
        figure next cycle appends nothing, while a REVISION of the same period
        is a different id and is kept alongside the original. That is what
        makes "what did we believe about Q2 in July" answerable later.
        """
        payload = obs.as_dict() if hasattr(obs, "as_dict") else dict(obs)
        oid = str(payload.get("observation_id") or "")
        if not oid:
            raise ValueError(
                "a macro observation needs its content-keyed id; without one "
                "every cycle would append the same figure again")
        if oid in self.macro_observation_ids():
            return False
        self._append(MACRO_OBSERVATION, payload)
        return True

    def record_knowledge_effect(self, effect) -> bool:
        """Persist one attribution: what this evidence did to what.

        Idempotent on `effect_id`, which is keyed on the evidence, the target
        and the day it was written — so a fold that re-derives the same
        attribution on the same day appends nothing, while the same evidence
        moving the same object again tomorrow is a second, real record.

        NO_CHANGE rows are stored exactly like changes. An effect log that
        only keeps the positives is a success log, and a success log cannot
        price a research action, which is the only reason this table exists.
        """
        payload = (effect.as_dict() if hasattr(effect, "as_dict")
                   else dict(effect))
        eid = str(payload.get("effect_id") or "")
        if not eid:
            raise ValueError("a knowledge effect needs its content-keyed id")
        if eid in self.knowledge_effect_ids():
            return False
        self._append(KNOWLEDGE_EFFECT, payload)
        return True

    def record_source_health(self, health) -> None:
        """One source family's standing this cycle. Appended, never merged.

        NOT idempotent and deliberately so: the same source being down again
        tomorrow is a second real observation, and it is the streak that
        turns a bad minute into an outage. Collapsing repeats would delete
        the only evidence that distinguishes them.
        """
        payload = (health.as_dict() if hasattr(health, "as_dict")
                   else dict(health))
        payload.pop("record", None)
        if not str(payload.get("source_family") or ""):
            raise ValueError(
                "a source health record needs the family it describes")
        self._append(SOURCE_HEALTH, payload)

    def source_health(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == SOURCE_HEALTH)

    def latest_source_health(self) -> Dict[str, dict]:
        """The newest standing per family, by append order.

        Append order rather than `detected_at`: the ledger is the record of
        what was written and when, and a date field can be set by a caller.
        """
        latest: Dict[str, dict] = {}
        for row in self.source_health():
            family = str(row.get("source_family") or "")
            if family:
                latest[family] = row
        return latest

    def knowledge_effect_ids(self) -> frozenset:
        return frozenset(str(r.get("effect_id") or "")
                         for r in self._rows()
                         if r.get("record") == KNOWLEDGE_EFFECT)

    def knowledge_effects(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == KNOWLEDGE_EFFECT)

    def record_research_decision(self, decision) -> bool:
        """Persist one choice, written before the call it describes.

        Idempotent on `decision_id`, which is keyed on the subject, question,
        chosen action, timestamp and the CANDIDATE SET — so re-deciding the
        same question with a different menu is a different decision, which is
        the case a policy most needs to be able to see.
        """
        payload = (decision.as_dict() if hasattr(decision, "as_dict")
                   else dict(decision))
        did = str(payload.get("decision_id") or "")
        if not did:
            raise ValueError("a research decision needs its content-keyed id")
        if did in self.research_decision_ids():
            return False
        self._append(RESEARCH_DECISION, payload)
        return True

    def record_research_outcome(self, outcome) -> bool:
        """Persist what a logged decision returned, including nothing.

        Refuses an outcome whose decision was never written. An outcome with
        no choice attached is the row this whole table exists to stop: it is
        indistinguishable from the reconstructed evidence the engine already
        had, and it would reintroduce the success bias through the back door.
        """
        payload = (outcome.as_dict() if hasattr(outcome, "as_dict")
                   else dict(outcome))
        did = str(payload.get("decision_id") or "")
        if not did:
            raise ValueError("a research outcome needs its decision_id")
        if did not in self.research_decision_ids():
            raise ValueError(
                f"no research decision {did!r} was written before this "
                "outcome; the decision must be durable BEFORE the call, or "
                "the log is a reconstruction wearing a prospective label")
        self._append(RESEARCH_OUTCOME, payload)
        return True

    def record_research_delayed_outcome(self, delayed) -> bool:
        """Append a later consequence. Never rewrites the immediate reward."""
        payload = (delayed.as_dict() if hasattr(delayed, "as_dict")
                   else dict(delayed))
        did = str(payload.get("delayed_id") or "")
        if not did:
            raise ValueError("a delayed outcome needs its content-keyed id")
        if did in frozenset(str(r.get("delayed_id") or "")
                            for r in self._rows()
                            if r.get("record") == RESEARCH_DELAYED_OUTCOME):
            return False
        self._append(RESEARCH_DELAYED_OUTCOME, payload)
        return True

    def research_decision_ids(self) -> frozenset:
        return frozenset(str(r.get("decision_id") or "")
                         for r in self._rows()
                         if r.get("record") == RESEARCH_DECISION)

    def research_decisions(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == RESEARCH_DECISION)

    def research_outcomes(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == RESEARCH_OUTCOME)

    def research_delayed_outcomes(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == RESEARCH_DELAYED_OUTCOME)

    def record_thesis_revision(self, revision) -> bool:
        """Append one revision. Idempotent on the content-keyed revision id."""
        payload = (revision.as_dict() if hasattr(revision, "as_dict")
                   else dict(revision))
        rid = str(payload.get("revision_id") or "")
        if not rid:
            raise ValueError("a thesis revision needs its content-keyed id")
        if rid in frozenset(str(r.get("revision_id") or "")
                            for r in self._rows()
                            if r.get("record") == THESIS_REVISION):
            return False
        self._append(THESIS_REVISION, payload)
        return True

    def thesis_revisions(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == THESIS_REVISION)

    def record_thesis_snapshot(self, thesis, *, as_of: str) -> bool:
        """Keep this cycle's thesis so the next cycle can compare to it."""
        payload = (thesis.as_dict() if hasattr(thesis, "as_dict")
                   else dict(thesis))
        payload["snapshot_as_of"] = as_of
        key = (str(payload.get("thesis_id") or ""), as_of)
        if not key[0]:
            raise ValueError("a thesis snapshot needs its thesis_id")
        if key in frozenset(
                (str(r.get("thesis_id") or ""), str(r.get("snapshot_as_of")
                                                    or ""))
                for r in self._rows() if r.get("record") == THESIS_SNAPSHOT):
            return False
        self._append(THESIS_SNAPSHOT, payload)
        return True

    def thesis_snapshots(self, *, latest_only: bool = True
                         ) -> Tuple[dict, ...]:
        """Snapshots, by default only the most recent cycle's.

        Comparing against every historical snapshot would diff a thesis
        against its own ancestors and report movement that already happened.
        """
        rows = [r for r in self._rows() if r.get("record") == THESIS_SNAPSHOT]
        if not rows or not latest_only:
            return tuple(rows)
        newest = max(str(r.get("snapshot_as_of") or "") for r in rows)
        return tuple(r for r in rows
                     if str(r.get("snapshot_as_of") or "") == newest)

    def record_method_performance(self, performance, *, as_of: str,
                                  question_type: str = "") -> bool:
        """One method's out-of-sample score on one series, on one date.

        Keyed `(method, series, question_type, as_of)`. The date is in the key
        deliberately: a score is a measurement taken on a day, and next
        month's score on a longer series is a NEW measurement rather than a
        correction of this one. Folding them would make "AR1 beats
        persistence" a statement with no date attached, which is how a result
        outlives the regime it was measured in.
        """
        payload = (performance.as_dict() if hasattr(performance, "as_dict")
                   else dict(performance))
        payload["measured_as_of"] = as_of
        if question_type:
            payload.setdefault("question_type", question_type)
        key = (str(payload.get("method") or ""),
               str(payload.get("series") or ""),
               str(payload.get("question_type") or ""), as_of)
        if not key[0]:
            raise ValueError("a method performance row needs its method")
        held = frozenset(
            (str(r.get("method") or ""), str(r.get("series") or ""),
             str(r.get("question_type") or ""),
             str(r.get("measured_as_of") or ""))
            for r in self._rows() if r.get("record") == METHOD_PERFORMANCE)
        if key in held:
            return False
        self._append(METHOD_PERFORMANCE, payload)
        return True

    def method_performances(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == METHOD_PERFORMANCE)

    def record_method_assumption_check(self, check) -> bool:
        """Idempotent on the check's content-keyed id."""
        payload = (check.as_dict() if hasattr(check, "as_dict")
                   else dict(check))
        cid = str(payload.get("check_id") or "")
        if not cid:
            raise ValueError("an assumption check needs its content-keyed id")
        if cid in frozenset(str(r.get("check_id") or "")
                            for r in self._rows()
                            if r.get("record") == METHOD_ASSUMPTION_CHECK):
            return False
        self._append(METHOD_ASSUMPTION_CHECK, payload)
        return True

    def method_assumption_checks(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == METHOD_ASSUMPTION_CHECK)

    def macro_observation_ids(self) -> frozenset:
        return frozenset(str(r.get("observation_id") or "")
                         for r in self._rows()
                         if r.get("record") == MACRO_OBSERVATION)

    def macro_observations(self) -> Tuple[dict, ...]:
        """Every economic figure ever seen, revisions included.

        Revisions are NOT folded away here. A caller that wants the vintage
        available on a date asks `macro_state.as_known_at`; a caller that
        wants the history of what the engine believed needs both rows.
        """
        return tuple(r for r in self._rows()
                     if r.get("record") == MACRO_OBSERVATION)

    def record_relationship(self, rel) -> bool:
        """Persist one actor relationship. Returns False if already held.

        Idempotent on the SCOPE, not on the id: the same pair contesting a
        DIFFERENT competitive object is a different economic claim and gets
        its own row, while re-deriving the same claim from the same evidence
        appends support rather than a second edge.
        """
        payload = rel.as_dict() if hasattr(rel, "as_dict") else dict(rel)
        predicate = str(payload.get("predicate") or "").upper()
        scope_value = str(payload.get("competitive_object")
                          or payload.get("relationship_object") or "").strip()
        if predicate == "COMPETES_WITH" and not scope_value:
            raise ValueError(
                "a rivalry with no competitive object cannot be stored: its "
                "scope key would be empty, so every future claim about these "
                "two companies would collapse into this one edge")
        key = relationship_scope(payload)
        held = self.relationship_scopes()
        if key not in held:
            self._append(RELATIONSHIP, payload)
            return True
        new_evidence = set(payload.get("evidence_ids") or ()) - \
            self._relationship_evidence().get(key, set())
        if new_evidence:
            self._append(RELATIONSHIP_SUPPORT, {
                "relationship_id": held[key],
                "scope": key,
                "evidence_ids": sorted(new_evidence),
                "confirmed_at": str(payload.get("created_at") or "")[:10]})
        return False

    def relationships(self, *, include_retired: bool = False
                      ) -> Tuple[dict, ...]:
        """Every relationship still held, newest support folded in."""
        retired = self.retired_relationship_ids()
        return tuple(r for r in self._rows()
                     if r.get("record") == RELATIONSHIP
                     and (include_retired
                          or r.get("relationship_id") not in retired))

    def relationship_scopes(self) -> Dict[str, str]:
        """scope key -> relationship_id, for the rows still held."""
        return {relationship_scope(r): str(r.get("relationship_id") or "")
                for r in self.relationships()}

    def _relationship_evidence(self) -> Dict[str, set]:
        out: Dict[str, set] = {}
        for row in self.relationships():
            out.setdefault(relationship_scope(row), set()).update(
                row.get("evidence_ids") or ())
        for row in self._rows():
            if row.get("record") != RELATIONSHIP_SUPPORT:
                continue
            out.setdefault(str(row.get("scope") or ""), set()).update(
                row.get("evidence_ids") or ())
        return out

    def retire_relationship(self, relationship_id: str, *, reason: str,
                            as_of: str) -> bool:
        """Stop holding a relationship without deleting the claim."""
        if not reason.strip():
            raise ValueError("a retirement with no reason cannot be audited")
        if relationship_id in self.retired_relationship_ids():
            return False
        self._append(RELATIONSHIP_RETIRED, {
            "relationship_id": relationship_id, "reason": reason.strip(),
            "retired_at": as_of[:10]})
        return True

    def retired_relationship_ids(self) -> frozenset:
        return frozenset(str(r.get("relationship_id") or "") for r in self._rows()
                         if r.get("record") == RELATIONSHIP_RETIRED)

    def record_cross_actor_expectation(self, expectation) -> bool:
        """Write a preregistration down. Idempotent on `expectation_id`.

        Nothing else in this class matters as much for honesty: the claim a
        preregistration makes is that it EXISTED BEFORE the evidence, and an
        in-memory object cannot make that claim to anyone.
        """
        payload = (expectation.as_dict() if hasattr(expectation, "as_dict")
                   else dict(expectation))
        if payload.get("expectation_id") in self.cross_actor_expectation_ids():
            return False
        self._append(CROSS_ACTOR_EXPECTATION, payload)
        return True

    def cross_actor_expectations(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == CROSS_ACTOR_EXPECTATION)

    def cross_actor_expectation_ids(self) -> frozenset:
        return frozenset(str(r.get("expectation_id") or "")
                         for r in self.cross_actor_expectations())

    def record_cross_actor_outcome(self, *, expectation_id: str, outcome: str,
                                   observed_at: str,
                                   evidence_ids: Sequence[str] = ()) -> bool:
        """Record how a preregistration resolved, as a SEPARATE row.

        The expectation row is history. Editing it to carry its own outcome
        would destroy the evidence that it was written before the answer.
        """
        if expectation_id not in self.cross_actor_expectation_ids():
            raise ValueError(
                f"no preregistered expectation {expectation_id!r}: an outcome "
                f"for an expectation that was never written down is exactly "
                f"the retroactive story preregistration exists to prevent")
        self._append(CROSS_ACTOR_OUTCOME, {
            "expectation_id": expectation_id, "outcome": outcome,
            "observed_at": observed_at[:10],
            "evidence_ids": list(evidence_ids)})
        return True

    # --- memory that must survive a restart -------------------------------

    def _record_keyed(self, kind: str, payload: dict, key: str,
                      conflict_fields: Sequence[str] = ()) -> str:
        """Append once per key. Returns "written", "held" or "conflict".

        A SECOND adjudication that disagrees with the first is never a silent
        overwrite: the ledger is history, and "we changed our mind" is a
        different fact from "we always thought this".
        """
        held = {str(r.get(key) or ""): r for r in self._rows()
                if r.get("record") == kind}
        identity = str(payload.get(key) or "")
        if not identity:
            raise ValueError(f"a {kind} with no {key} cannot be stored")
        previous = held.get(identity)
        if previous is None:
            self._append(kind, payload)
            return "written"
        for field_name in conflict_fields:
            if str(previous.get(field_name) or "") != \
                    str(payload.get(field_name) or ""):
                self._append(kind, {**payload, "supersedes": identity,
                                    "conflict_on": field_name})
                return "conflict"
        return "held"

    def record_counterfactual_adjudication(self, episode) -> str:
        """Persist which explanation the evidence favoured, and the lesson."""
        payload = (episode.as_dict() if hasattr(episode, "as_dict")
                   else dict(episode))
        return self._record_keyed(
            COUNTERFACTUAL_ADJUDICATION, payload, "episode_id",
            conflict_fields=("resolution", "lesson"))

    def counterfactual_adjudications(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == COUNTERFACTUAL_ADJUDICATION)

    def record_falsifier(self, falsifier) -> str:
        payload = (falsifier.as_dict() if hasattr(falsifier, "as_dict")
                   else dict(falsifier))
        return self._record_keyed(FALSIFIER, payload, "falsifier_id",
                                  conflict_fields=("standing", "resolution"))

    def falsifiers(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows() if r.get("record") == FALSIFIER)

    def record_response_watch(self, watch) -> str:
        payload = (watch.as_dict() if hasattr(watch, "as_dict")
                   else dict(watch))
        return self._record_keyed(RESPONSE_WATCH, payload, "watch_id",
                                  conflict_fields=("status",))

    def response_watches(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == RESPONSE_WATCH)

    def record_strategic_objective(self, hypothesis) -> str:
        payload = (hypothesis.as_dict() if hasattr(hypothesis, "as_dict")
                   else dict(hypothesis))
        return self._record_keyed(STRATEGIC_OBJECTIVE, payload,
                                  "hypothesis_id",
                                  conflict_fields=("standing",))

    def strategic_objectives(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == STRATEGIC_OBJECTIVE)

    def record_strategic_interaction(self, interaction) -> str:
        payload = (interaction.as_dict() if hasattr(interaction, "as_dict")
                   else dict(interaction))
        return self._record_keyed(STRATEGIC_INTERACTION, payload,
                                  "interaction_id",
                                  conflict_fields=("standing",))

    def strategic_interactions(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == STRATEGIC_INTERACTION)

    def record_actor_response_episode(self, episode) -> str:
        """Observational history. Never a preregistration.

        Refused outright if the payload claims otherwise: a historical
        sequence relabelled as a prediction is the one move that would make
        every strategic result untrustworthy at once.
        """
        payload = (episode.as_dict() if hasattr(episode, "as_dict")
                   else dict(episode))
        if payload.get("preregistered"):
            raise ValueError(
                "an observed episode cannot be marked preregistered: it was "
                "read after both actions had happened")
        return self._record_keyed(ACTOR_RESPONSE_EPISODE, payload,
                                  "episode_id", conflict_fields=("standing",))

    def actor_response_episodes(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == ACTOR_RESPONSE_EPISODE)

    def record_lifecycle(self, event) -> bool:
        """Append one belief-lifecycle event. Idempotent on `event_id`.

        Idempotent because a decay pass is a fold over the ledger and may
        run more than once a day; a second pass finding the same belief
        still stale is not a second transition.
        """
        payload = event.as_dict() if hasattr(event, "as_dict") else dict(event)
        if payload.get("event_id") in self.lifecycle_ids():
            return False
        self._append(LIFECYCLE, payload)
        return True

    def lifecycle_ids(self) -> frozenset:
        return frozenset(r.get("event_id") for r in self._rows()
                         if r.get("record") == LIFECYCLE
                         and r.get("event_id"))

    def lifecycle_events(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == LIFECYCLE)

    # --- reading ----------------------------------------------------------
    def _rows(self) -> List[dict]:
        if not self.path.exists():
            return []
        rows: List[dict] = []
        self._corrupt = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                self._corrupt += 1
                continue
        return rows

    def beliefs(self) -> Tuple[B.StrategicBelief, ...]:
        """Fold declarations and updates into current beliefs.

        Declaration order is preserved; a re-declared belief keeps its
        original prior, because the first prior is the one the trail is
        anchored to.
        """
        declared: Dict[str, dict] = {}
        order: List[str] = []
        updates: Dict[str, List[dict]] = {}
        for row in self._rows():
            kind = row.get("record")
            if kind == BELIEF:
                bid = row.get("belief_id")
                if bid and bid not in declared:
                    declared[bid] = row
                    order.append(bid)
            elif kind == BELIEF_UPDATE:
                bid = row.get("belief_id")
                if bid:
                    updates.setdefault(bid, []).append(row)

        out: List[B.StrategicBelief] = []
        for bid in order:
            row = declared[bid]
            history = tuple(
                B.BeliefUpdate(
                    at=u.get("at", ""), prior=float(u.get("prior", 0.5)),
                    posterior=float(u.get("posterior", 0.5)),
                    method=u.get("method", B.CALIBRATED_HEURISTIC),
                    basis=u.get("basis", ""),
                    evidence_ids=tuple(u.get("evidence_ids") or ()),
                    effective_sample_size=float(
                        u.get("effective_sample_size", 0.0)))
                for u in sorted(updates.get(bid, []),
                                key=lambda u: u.get("at", "")))
            # Declared ids first: evidence that PROPOSED a belief is applied
            # from the moment it is declared, and a reload that forgot them
            # would let the same fact strengthen the belief it created.
            applied = tuple(row.get("applied_evidence_ids") or ()) + tuple(
                e for u in history for e in u.evidence_ids)
            out.append(B.StrategicBelief(
                belief_id=bid, proposition=row.get("proposition", ""),
                subject=row.get("subject", ""),
                prior_probability=float(row.get("prior_probability", 0.5)),
                posterior_probability=(history[-1].posterior if history
                                       else float(row.get(
                                           "posterior_probability", 0.5))),
                last_updated=(history[-1].at if history
                              else row.get("last_updated", "")),
                learning_speed=row.get("learning_speed", B.MEDIUM),
                applied_evidence_ids=applied,
                supporting_evidence_ids=tuple(
                    row.get("supporting_evidence_ids") or ()),
                contradicting_evidence_ids=tuple(
                    row.get("contradicting_evidence_ids") or ()),
                history=history,
                last_validated=row.get("last_validated", ""),
                decay_eligible=bool(row.get("decay_eligible", True)),
                review_interval_days=int(
                    row.get("review_interval_days", 90)),
                confidence_basis=row.get("confidence_basis", ""),
                limitations=tuple(row.get("limitations") or ()),
                lifecycle_state=row.get("lifecycle_state", B.ACTIVE)))
        return tuple(out)

    def open_expectations(self, *, as_of: str
                          ) -> Tuple[EXP.ExpectedObservation, ...]:
        """Preregistered expectations that have not yet been scored.

        Scored means a reconciliation with an INFORMATIVE outcome exists. A
        TOO_EARLY reconciliation deliberately leaves the expectation open —
        it is a note that the window is still running, not a verdict.
        """
        settled = {
            r.get("expectation_id") for r in self._rows()
            if r.get("record") == RECONCILIATION
            and r.get("outcome") in EXP.INFORMATIVE}
        out = []
        for row in self._rows():
            if row.get("record") != EXPECTATION:
                continue
            if row.get("expectation_id") in settled:
                continue
            rng = row.get("expected_range")
            out.append(EXP.ExpectedObservation(
                expectation_id=row.get("expectation_id", ""),
                hypothesis_id=row.get("hypothesis_id", ""),
                subject=row.get("subject", ""),
                expected_event=row.get("expected_event", ""),
                expected_direction=row.get("expected_direction", EXP.FLAT),
                preregistered_at=row.get("preregistered_at", ""),
                evaluation_window_ends=row.get("evaluation_window_ends", ""),
                falsifier=row.get("falsifier", ""),
                metric=row.get("metric", ""),
                evidence_basis=tuple(row.get("evidence_basis") or ()),
                expected_range=tuple(rng) if rng else None,
                relevant_actors=tuple(row.get("relevant_actors") or ()),
                expected_reactions=tuple(row.get("expected_reactions") or ()),
                uncertainty=float(row.get("uncertainty", 0.5))))
        return tuple(out)

    def evidence_ids(self) -> frozenset:
        """Every evidence id ever ingested — the dedup key across cycles."""
        return frozenset(r.get("evidence_id") for r in self._rows()
                         if r.get("record") == EVIDENCE
                         and r.get("evidence_id"))

    def evidence(self) -> Tuple[ME.MicroEvidence, ...]:
        """Rehydrate ingested evidence as objects, in ingestion order.

        WHY THIS DID NOT EXIST, AND WHY IT HAD TO
        -----------------------------------------
        Evidence was write-only: `record_evidence` put it in and
        `evidence_ids` read back nothing but the dedup key. That was
        sufficient while ingestion was the ONLY consumer, and became a trap
        the moment belief formation existed, because formation runs on the
        evidence a session brought in and nothing could reach the evidence
        already on the log. Rows ingested before formation existed were
        permanently unreachable by it.

        NOT A ROUND TRIP, AND THE DIFFERENCE MATTERS
        --------------------------------------------
        `as_dict` writes `independence` and `self_authored`, and BOTH are
        derived properties of `source_role`, not fields. Reconstructing them
        from the row would let a stored value contradict the rule that
        computes it -- an old row written under a different independence
        table would silently keep its old weighting and get a design-effect
        penalty nobody could explain. So they are dropped and recomputed, and
        `source_role` is the only thing trusted.

        A row missing the fields that make evidence evidence -- an id, a
        subject, a source -- is skipped rather than defaulted. Evidence with
        no source is exactly what rule 5 in `beliefs.py` refuses.
        """
        out: List[ME.MicroEvidence] = []
        for row in self._rows():
            if row.get("record") != EVIDENCE:
                continue
            if not (row.get("evidence_id") and row.get("subject_company")
                    and row.get("source")):
                continue
            numeric = row.get("numeric_values") or {}
            if isinstance(numeric, dict):
                numeric = tuple(numeric.items())
            else:
                numeric = tuple(tuple(pair) for pair in numeric)
            out.append(ME.MicroEvidence(
                evidence_id=row["evidence_id"],
                subject_company=row["subject_company"],
                actor=row.get("actor", ""),
                evidence_type=row.get("evidence_type", ""),
                observed_at=row.get("observed_at", ""),
                available_at=row.get("available_at", ""),
                source=row["source"],
                fact=row.get("fact", ""),
                source_author=row.get("source_author", ""),
                # The same literal the dataclass defaults to. A row written
                # before `source_role` existed reads as independent
                # reporting, which is what it was assumed to be then.
                source_role=row.get("source_role") or "independent_reporting",
                numeric_values=numeric,
                affected_hypotheses=tuple(row.get("affected_hypotheses") or ()),
                affected_hidden_states=tuple(
                    row.get("affected_hidden_states") or ()),
                affected_causal_nodes=tuple(
                    row.get("affected_causal_nodes") or ()),
                affected_interactions=tuple(
                    row.get("affected_interactions") or ()),
                reliability=float(row.get("reliability", 0.5)),
                relevance=float(row.get("relevance", 0.5)),
                contradiction_role=row.get("contradiction_role", ME.NEUTRAL),
                limitations=tuple(row.get("limitations") or ())))
        return tuple(out)

    def reconciliations(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == RECONCILIATION)

    def expectations(self) -> Tuple[dict, ...]:
        """Every preregistered expectation, for the publisher to filter.

        `expectation_ids` existed and this did not, so a caller wanting the
        expectations themselves had nothing to call -- which is why the demo
        snapshot was handed `information_priorities` instead and published
        zero expectations for every company while 76 sat in the ledger.
        """
        return tuple(r for r in self._rows()
                     if r.get("record") == EXPECTATION)

    def health(self) -> dict:
        rows = self._rows()
        counts: Dict[str, int] = {}
        for row in rows:
            kind = row.get("record", "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        return {"path": str(self.path), "rows": len(rows),
                "by_record": counts, "corrupt_lines_skipped": self._corrupt,
                "exists": self.path.exists()}
