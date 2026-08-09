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
KNOWLEDGE_EFFECT = "knowledge_effect"

RECORD_KINDS = frozenset({BELIEF, BELIEF_UPDATE, EXPECTATION,
                          RECONCILIATION, EVIDENCE, CYCLE, LIFECYCLE,
                          EVIDENCE_SEEN, RELATIONSHIP, RELATIONSHIP_SUPPORT,
                          RELATIONSHIP_RETIRED, CROSS_ACTOR_EXPECTATION,
                          CROSS_ACTOR_OUTCOME,
                          COUNTERFACTUAL_ADJUDICATION, FALSIFIER,
                          RESPONSE_WATCH, STRATEGIC_OBJECTIVE,
                          KNOWLEDGE_EFFECT,
                          STRATEGIC_INTERACTION, ACTOR_RESPONSE_EPISODE,
                          MACRO_OBSERVATION})

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

    def knowledge_effect_ids(self) -> frozenset:
        return frozenset(str(r.get("effect_id") or "")
                         for r in self._rows()
                         if r.get("record") == KNOWLEDGE_EFFECT)

    def knowledge_effects(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == KNOWLEDGE_EFFECT)

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

    def health(self) -> dict:
        rows = self._rows()
        counts: Dict[str, int] = {}
        for row in rows:
            kind = row.get("record", "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        return {"path": str(self.path), "rows": len(rows),
                "by_record": counts, "corrupt_lines_skipped": self._corrupt,
                "exists": self.path.exists()}
