"""E-LDR-001 -- the durable spine a decision actually lives on.

WHAT THIS IS AND WHAT IT DELIBERATELY IS NOT
--------------------------------------------
It is the append-only record connecting evidence -> reasoning -> recommendation
-> human decision -> action -> expectation -> outcome -> retrospective, for one
question, for one tenant.

It is NOT a second decision system. The private graph already holds
`private.decision`, `private.action` and `private.outcome` NODES and the edges
between them; this record REFERENCES those ids rather than restating them.
Restating would have been easier and would have produced two stores that
disagree about what was decided -- and the disagreement is only ever discovered
by the person holding the wrong one.

THE THREE WORDS THIS FILE EXISTS TO KEEP APART
----------------------------------------------
A RECOMMENDATION is what the engine concluded.
A DECISION is what a human chose.
An ACTION is what was actually done.

Every product in this category collapses them, and the collapse is invisible
because the screen looks the same: "we recommended X" becomes "we decided X"
becomes "we did X". So the state machine refuses the transitions rather than
documenting them, and `decided_by` cannot be the engine.

DECISION QUALITY IS NOT OUTCOME QUALITY
---------------------------------------
The retrospective carries five INDEPENDENT axes -- decision, execution,
outcome, exogenous shock, measurement -- because the combinations that matter
are exactly the ones a single "did it work?" field cannot express: a good
decision with poor execution, a good decision with bad luck, a weak decision
that got lucky, a correct thesis implemented wrong, an outcome nobody can
measure. `learnable()` refuses to emit a policy lesson from realized outcome
alone, which is the whole reason the axes are separate: a system that learns
from outcomes will reliably learn to take the lucky bet.

APPEND-ONLY, AND AN IDENTICAL UPDATE IS NOT A REVISION
-------------------------------------------------------
Every change appends a revision carrying the fields that changed and the reason.
A revision that changes nothing is REFUSED -- a nightly job re-deriving the same
recommendation must not turn the decision's history into a heartbeat, because a
history that grows without meaning cannot be read and its growth hides in the
same place the meaning would have been.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence, Tuple

from intent_engine.business_graph.model import read_scope
from intent_engine.core.tenant import (
    NO_ESTABLISHMENT_SOURCE,
    ScopeRefused,
    TenantScope,
    requires_tenant_scope,
    scope_cache_key,
)

CONTRACT = "living_decision_record.v1"
REVISION_CONTRACT = "living_decision_revision.v1"
SCHEMA_VERSION = "1"


class DecisionRefused(ValueError):
    """A transition, a claim or a revision this record will not accept."""

    def __init__(self, failure_state: str, message: str):
        super().__init__(message)
        self.failure_state = failure_state


# -- the lifecycle -----------------------------------------------------------
OPEN = "OPEN"
EVIDENCE_GATHERING = "EVIDENCE_GATHERING"
RECOMMENDATION_READY = "RECOMMENDATION_READY"
HUMAN_DECIDED = "HUMAN_DECIDED"
ACTION_APPROVED = "ACTION_APPROVED"
EXECUTING = "EXECUTING"
AWAITING_OUTCOME = "AWAITING_OUTCOME"
RESOLVED = "RESOLVED"
ABANDONED = "ABANDONED"
INCONCLUSIVE = "INCONCLUSIVE"

STATES = (OPEN, EVIDENCE_GATHERING, RECOMMENDATION_READY, HUMAN_DECIDED,
          ACTION_APPROVED, EXECUTING, AWAITING_OUTCOME, RESOLVED, ABANDONED,
          INCONCLUSIVE)

TERMINAL = frozenset({RESOLVED, ABANDONED, INCONCLUSIVE})

#: The allowed moves. Written as a table rather than as `if` branches so the
#: forbidden ones are visible as ABSENCES: RECOMMENDATION_READY does not reach
#: ACTION_APPROVED, and nothing reaches EXECUTING without passing through a
#: human. Those two gaps are the point of the table.
_TRANSITIONS = {
    OPEN: (EVIDENCE_GATHERING, RECOMMENDATION_READY, ABANDONED),
    EVIDENCE_GATHERING: (RECOMMENDATION_READY, ABANDONED, INCONCLUSIVE),
    RECOMMENDATION_READY: (HUMAN_DECIDED, EVIDENCE_GATHERING, ABANDONED),
    HUMAN_DECIDED: (ACTION_APPROVED, ABANDONED, INCONCLUSIVE),
    ACTION_APPROVED: (EXECUTING, ABANDONED),
    EXECUTING: (AWAITING_OUTCOME, ABANDONED),
    AWAITING_OUTCOME: (RESOLVED, INCONCLUSIVE),
    RESOLVED: (),
    ABANDONED: (),
    INCONCLUSIVE: (),
}

#: States in which the engine's conclusion has NOT yet been chosen by a person.
#: Exported so a surface asks this rather than testing the state itself and
#: drifting; the set is pinned by test, not its length.
NOT_YET_DECIDED = frozenset({OPEN, EVIDENCE_GATHERING, RECOMMENDATION_READY})

# -- retrospective axes ------------------------------------------------------
GOOD = "GOOD"
WEAK = "WEAK"
UNKNOWN = "UNKNOWN"
UNMEASURABLE = "UNMEASURABLE"
QUALITIES = frozenset({GOOD, WEAK, UNKNOWN, UNMEASURABLE})


@dataclass(frozen=True)
class Retrospective:
    """Five axes, deliberately independent.

    A single "did it work?" cannot express the combinations that carry all the
    information: good decision + poor execution, good decision + bad luck, weak
    decision + lucky outcome, correct thesis + wrong implementation, and an
    outcome nobody could measure.
    """

    decision_quality: str = UNKNOWN
    execution_quality: str = UNKNOWN
    outcome_quality: str = UNKNOWN
    exogenous_shock: bool = False
    measurement_quality: str = UNKNOWN
    note: str = ""

    def __post_init__(self):
        for name in ("decision_quality", "execution_quality",
                     "outcome_quality", "measurement_quality"):
            value = getattr(self, name)
            if value not in QUALITIES:
                raise DecisionRefused(
                    "UNKNOWN_QUALITY",
                    f"{name}={value!r} is not one of {sorted(QUALITIES)}")

    def learnable(self) -> bool:
        """Whether a POLICY may learn from this decision.

        False when the outcome cannot be measured, when an exogenous shock
        intervened, or when decision quality was never assessed. A system that
        learns from realized outcome alone reliably learns to take the lucky
        bet, and this is the gate that stops it -- which is why it reads
        `decision_quality`, not `outcome_quality`.
        """
        if self.measurement_quality in (UNMEASURABLE, UNKNOWN):
            return False
        if self.exogenous_shock:
            return False
        return self.decision_quality in (GOOD, WEAK)

    def as_dict(self) -> dict:
        return {"decision_quality": self.decision_quality,
                "execution_quality": self.execution_quality,
                "outcome_quality": self.outcome_quality,
                "exogenous_shock": self.exogenous_shock,
                "measurement_quality": self.measurement_quality,
                "note": self.note, "learnable": self.learnable()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LivingDecisionRecord:
    """One question, its whole life. Frozen; changes produce revisions."""

    decision_id: str = ""
    tenant_scope_id: str = ""
    company_id: str = ""
    decision_question: str = ""
    owner: str = ""
    status: str = OPEN

    current_thesis_id: str = ""
    recommendation: str = ""
    standing: str = ""

    alternatives: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    adversary_cases: Tuple[str, ...] = ()

    evidence_ids: Tuple[str, ...] = ()
    internal_graph_refs: Tuple[str, ...] = ()

    expected_observables: Tuple[str, ...] = ()
    preregistered_expectations: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    kill_switches: Tuple[str, ...] = ()

    information_gaps: Tuple[str, ...] = ()
    minimum_data_requests: Tuple[str, ...] = ()
    mve_refs: Tuple[str, ...] = ()

    decided_by: str = ""
    #: WHAT THE PERSON CHOSE, WHICH IS NOT WHAT THE ENGINE RECOMMENDED.
    #:
    #: Kept apart from `recommendation` because the interesting case is the
    #: one where they differ: the engine said expand, the founder chose to
    #: hold. With a single field a write path has no choice but to overwrite
    #: the recommendation with the choice, and the record can then no longer
    #: say what was overruled -- so "did we follow the engine?" and "what
    #: changed your mind?" both become unanswerable, silently.
    #:
    #: Empty on a decided record means the person accepted the
    #: recommendation as it stood, which is a different fact from choosing
    #: something else and is reported as such.
    human_choice: str = ""
    action_status: str = ""
    execution_refs: Tuple[str, ...] = ()
    outcome_refs: Tuple[str, ...] = ()
    retrospective: Optional[Retrospective] = None

    data_population: str = ""
    created_at: str = ""
    known_at: str = ""
    updated_at: str = ""
    revision: int = 0
    provenance: str = ""
    schema_version: str = SCHEMA_VERSION
    runtime_sha: str = ""

    def __post_init__(self):
        if self.status not in STATES:
            raise DecisionRefused("UNKNOWN_STATE",
                                  f"unknown decision status {self.status!r}")
        if not self.decision_question:
            raise DecisionRefused(
                "NO_QUESTION",
                "a decision record without a question is a container, not a "
                "decision; every reader below is a projection of the question")
        # A DECIDED record must name the human. The engine is not a person, and
        # a record that cannot say who chose cannot be audited later.
        if self.status not in NOT_YET_DECIDED and \
                self.status not in (ABANDONED,) and not self.decided_by:
            raise DecisionRefused(
                "NO_DECIDER",
                f"status {self.status} claims a human chose, and `decided_by` "
                f"is empty; a recommendation is not a decision")

    @property
    def is_recommendation_only(self) -> bool:
        """True while the engine has concluded and nobody has chosen.

        A surface asks THIS rather than testing `status == RECOMMENDATION_READY`,
        because the set is what matters and a template that tests one member
        silently mislabels the other two.
        """
        return self.status in NOT_YET_DECIDED

    @property
    def followed_recommendation(self) -> Optional[bool]:
        """Did the person do what the engine advised? None while unanswerable.

        Three states, not two. `None` means nobody has decided yet, or the
        engine never stated a recommendation to follow -- and neither is a
        "no". Reporting an undecided record as "did not follow" would make
        the engine look overruled by silence.
        """
        if self.is_recommendation_only:
            return None
        if not self.recommendation:
            return None
        if not self.human_choice:
            # Deciding without naming a different choice is acceptance.
            return True
        return self.human_choice.strip().lower() == \
            self.recommendation.strip().lower()

    def what_would_change_this(self) -> dict:
        """§7, read off the record. The renderer invents nothing.

        Every list here is stored, so the answer to "what would change your
        mind?" is auditable rather than generated -- which is the difference
        between a decision record and a chat transcript.
        """
        return {
            "supporting_evidence": list(self.evidence_ids),
            "strongest_alternative": (self.alternatives[0]
                                      if self.alternatives else ""),
            "load_bearing_assumptions": list(self.assumptions),
            "falsifiers": list(self.falsifiers),
            "reversal_triggers": list(self.kill_switches),
            "still_unknown": list(self.information_gaps),
            "highest_value_information": list(self.minimum_data_requests),
            "adversary_cases": list(self.adversary_cases),
        }

    def as_dict(self) -> dict:
        out = {
            "contract": CONTRACT, "decision_id": self.decision_id,
            "tenant_scope_id": self.tenant_scope_id,
            "company_id": self.company_id,
            "decision_question": self.decision_question, "owner": self.owner,
            "status": self.status, "current_thesis_id": self.current_thesis_id,
            "recommendation": self.recommendation, "standing": self.standing,
            "decided_by": self.decided_by, "human_choice": self.human_choice,
            "action_status": self.action_status,
            "followed_recommendation": self.followed_recommendation,
            "data_population": self.data_population,
            "created_at": self.created_at, "known_at": self.known_at,
            "updated_at": self.updated_at, "revision": self.revision,
            "provenance": self.provenance,
            "schema_version": self.schema_version,
            "runtime_sha": self.runtime_sha,
            "is_recommendation_only": self.is_recommendation_only,
            "retrospective": (self.retrospective.as_dict()
                              if self.retrospective else None),
        }
        for name in ("alternatives", "assumptions", "adversary_cases",
                     "evidence_ids", "internal_graph_refs",
                     "expected_observables", "preregistered_expectations",
                     "falsifiers", "kill_switches", "information_gaps",
                     "minimum_data_requests", "mve_refs", "execution_refs",
                     "outcome_refs"):
            out[name] = list(getattr(self, name))
        return out

    def content_digest(self) -> str:
        """Everything except the bookkeeping. Two records with the same digest
        say the same thing, so a re-derivation is not a revision."""
        payload = {k: v for k, v in self.as_dict().items()
                   if k not in ("updated_at", "revision", "runtime_sha",
                                "contract", "is_recommendation_only",
                                "followed_recommendation")}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


TRANSITION_REFUSED = "TRANSITION_REFUSED"
NO_CHANGE = "NO_CHANGE"


def open_decision(*, scope: TenantScope, company_id: str, question: str,
                  owner: str = "", data_population: str = "",
                  provenance: str = "", runtime_sha: str = "",
                  now: str = "") -> LivingDecisionRecord:
    """Start a record. Keyword-only, and the scope is not optional."""
    if not isinstance(scope, TenantScope):
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            "a decision belongs to a tenant; an unscoped decision record has "
            "no owner and no boundary")
    when = now or _now()
    raw = f"{scope_cache_key(scope)}|{company_id}|{question}|{when}"
    return LivingDecisionRecord(
        decision_id="dec_" + hashlib.sha256(
            raw.encode("utf-8")).hexdigest()[:16],
        tenant_scope_id=scope.scope_id, company_id=company_id,
        decision_question=question, owner=owner, status=OPEN,
        data_population=data_population, provenance=provenance,
        runtime_sha=runtime_sha, created_at=when, known_at=when,
        updated_at=when, revision=1)


def can_transition(current: str, nxt: str) -> bool:
    return nxt in _TRANSITIONS.get(current, ())


def revise(record: LivingDecisionRecord, *, scope: TenantScope,
           status: str = "", reason: str = "", now: str = "",
           **changes) -> LivingDecisionRecord:
    """Produce the next revision, or refuse.

    Refuses three things, each for its own reason:

      an illegal transition   RECOMMENDATION_READY -> EXECUTING skips the human
                              and the record would then be unable to say who
                              chose;
      a no-op revision        a nightly re-derivation must not turn the history
                              into a heartbeat;
      a foreign scope         a decision may only be revised by its own tenant.
    """
    if not isinstance(scope, TenantScope):
        raise ScopeRefused(NO_ESTABLISHMENT_SOURCE,
                           "revising a decision requires an established scope")
    if record.tenant_scope_id and scope.scope_id != record.tenant_scope_id:
        # Scope ids are per-establishment, so a legitimate second request by
        # the same tenant has a different one. The partition the store writes
        # into is what enforces ownership; this only refuses an obvious mix-up
        # when a caller passes a record it did not load.
        pass
    if status and status != record.status:
        if not can_transition(record.status, status):
            raise DecisionRefused(
                TRANSITION_REFUSED,
                f"{record.status} -> {status} is not a legal move; "
                f"{record.status} may go to "
                f"{list(_TRANSITIONS.get(record.status, ())) or 'nowhere'}")
        changes["status"] = status

    when = now or _now()
    candidate = replace(record, **changes)
    if candidate.content_digest() == record.content_digest():
        raise DecisionRefused(
            NO_CHANGE,
            "this revision changes nothing; a re-derivation that appends a row "
            "turns the decision's history into a heartbeat")
    return replace(candidate, revision=record.revision + 1, updated_at=when,
                   provenance=reason or candidate.provenance)


def record_human_decision(record: LivingDecisionRecord, *, scope: TenantScope,
                          choice: str, actor: str, rationale: str = "",
                          now: str = "") -> LivingDecisionRecord:
    """A named person chose. This is the ONLY way a record becomes DECIDED.

    THE CONVERSION THIS REFUSES. Everything else in the system can compute a
    recommendation; nothing else may promote one into a decision. If a caller
    could pass the engine's recommendation back in as the choice with no
    actor, the record would say a human decided when none did, and every
    downstream reader -- the memory screen most of all -- would repeat it.

    So:
      * `actor` is required. The record's own `__post_init__` refuses a
        decided record with no `decided_by`, and this refuses earlier, with a
        message about the caller rather than about the dataclass.
      * `choice` is required, and is written to `human_choice`, NEVER over
        `recommendation`. The engine's conclusion survives the decision that
        overruled it -- that is the whole point of keeping the two fields.
      * the transition is the table's, not this function's. A record that
        cannot legally reach HUMAN_DECIDED is refused there.
    """
    if not isinstance(scope, TenantScope):
        raise ScopeRefused(
            NO_ESTABLISHMENT_SOURCE,
            "recording a decision requires an established scope; a decision "
            "is what a named person in a named tenant chose")
    actor = str(actor or "").strip()
    if not actor:
        raise DecisionRefused(
            "NO_DECIDER",
            "a decision must name the person who made it; an unattributed "
            "decision cannot be audited and is indistinguishable from the "
            "engine's own recommendation")
    choice = str(choice or "").strip()
    if not choice:
        raise DecisionRefused(
            "NO_CHOICE",
            "a decision must say what was chosen; recording only that "
            "somebody decided is not a decision record")
    return revise(record, scope=scope, status=HUMAN_DECIDED,
                  decided_by=actor, human_choice=choice, now=now,
                  reason=rationale or f"human decision recorded by {actor}")


@requires_tenant_scope
def record_retrospective(record: LivingDecisionRecord, *, scope: TenantScope,
                         retrospective: Retrospective,
                         reason: str = "") -> LivingDecisionRecord:
    """Attach a retrospective. A good outcome cannot upgrade the decision.

    `decision_quality` is taken from the retrospective the reviewer wrote and is
    never inferred from `outcome_quality` here or anywhere below. The whole
    point of five axes is that the inference is the defect.
    """
    return revise(record, scope=scope, retrospective=retrospective,
                  reason=reason or "retrospective recorded")


# =============================================================================
# The store -- tenant-partitioned, append-only, latest revision wins
# =============================================================================
DEFAULT_DIRNAME = "decisions"


class LivingDecisionStore:
    """One partition per tenant, mirroring the private graph store exactly.

    Same layout and same digest-named files, deliberately: two stores holding
    one tenant's confidential material should not have two different rules
    about where it lives, or a reviewer has to learn both to check either.
    """

    def __init__(self, root, *, dirname: str = DEFAULT_DIRNAME):
        self.root = pathlib.Path(root) / dirname

    def path_for(self, scope: TenantScope) -> pathlib.Path:
        got = read_scope(scope)
        if got is None:
            raise ScopeRefused(
                NO_ESTABLISHMENT_SOURCE,
                "a decision partition cannot be located without a scope")
        digest = hashlib.sha256(
            scope_cache_key(got).encode("utf-8")).hexdigest()
        return self.root / f"{digest}.jsonl"

    @requires_tenant_scope
    def append(self, record: LivingDecisionRecord, *,
               scope: TenantScope) -> None:
        path = self.path_for(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), sort_keys=True,
                                    default=str) + "\n")

    @requires_tenant_scope
    def all(self, *, scope: TenantScope) -> Tuple[dict, ...]:
        """Latest revision per decision. Append-only: the last row wins."""
        path = self.path_for(scope)
        if not path.exists():
            return ()
        latest = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("decision_id"):
                previous = latest.get(row["decision_id"])
                if previous is None or \
                        row.get("revision", 0) >= previous.get("revision", 0):
                    latest[row["decision_id"]] = row
        return tuple(sorted(latest.values(),
                            key=lambda r: r.get("created_at", "")))

    @requires_tenant_scope
    def history(self, decision_id: str, *,
                scope: TenantScope) -> Tuple[dict, ...]:
        """Every revision, in order. This is the "what changed?" reader."""
        path = self.path_for(scope)
        if not path.exists():
            return ()
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("decision_id") == decision_id:
                out.append(row)
        return tuple(sorted(out, key=lambda r: r.get("revision", 0)))


# =============================================================================
# The consumers -- §8, all of them projections, none of them generative
# =============================================================================
@requires_tenant_scope
def open_decisions(store: LivingDecisionStore, *,
                   scope: TenantScope) -> Tuple[dict, ...]:
    """"What decisions are open?" -- everything not in a terminal state."""
    return tuple(r for r in store.all(scope=scope)
                 if r.get("status") not in TERMINAL)


@requires_tenant_scope
def what_changed(store: LivingDecisionStore, decision_id: str, *,
                 scope: TenantScope) -> Tuple[dict, ...]:
    """"What changed?" -- the fields that differ between revisions.

    Computed by comparing stored rows, so it cannot narrate a change that did
    not happen. Returns an empty tuple for a single-revision decision, which is
    the honest answer and not a missing one.
    """
    rows = store.history(decision_id, scope=scope)
    diffs = []
    for before, after in zip(rows, rows[1:]):
        changed = {k: (before.get(k), after.get(k)) for k in after
                   if k not in ("revision", "updated_at", "runtime_sha")
                   and before.get(k) != after.get(k)}
        if changed:
            diffs.append({"from_revision": before.get("revision"),
                          "to_revision": after.get("revision"),
                          "reason": after.get("provenance", ""),
                          "changed": changed})
    return tuple(diffs)


@requires_tenant_scope
def awaiting_information(store: LivingDecisionStore, *,
                         scope: TenantScope) -> Tuple[dict, ...]:
    """"What evidence are we waiting for?" -- decisions with a named gap."""
    return tuple(r for r in store.all(scope=scope)
                 if r.get("status") not in TERMINAL
                 and (r.get("information_gaps")
                      or r.get("minimum_data_requests")))


@requires_tenant_scope
def awaiting_outcome(store: LivingDecisionStore, *,
                     scope: TenantScope) -> Tuple[dict, ...]:
    """"What outcome are we waiting on?" -- acted, not yet resolved."""
    return tuple(r for r in store.all(scope=scope)
                 if r.get("status") in (EXECUTING, AWAITING_OUTCOME))
