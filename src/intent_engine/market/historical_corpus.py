"""Decisions the past already answered, walled off from the ones it has not.

WHY THIS EXISTS AND WHAT IT MAY NOT BE USED FOR
-----------------------------------------------
The prospective gates need 100 decisions and stand at 34. They rise at the rate
the world produces them, which is a few a night, and nothing in this module
changes that. A historical episode is NOT a prospective decision and may never
be counted as one: the engine did not choose it, did not wait for it, and knows
how it came out.

What a historical episode CAN do is train a reward model, validate an estimator
and calibrate a scenario today rather than in a year. All of that value rests
on one property, and if the property fails the value is negative — a confident
number computed from information nobody had:

    the state at T0 must be computed only from what was knowable at T0.

WHY THIS IS NOT `vintage.freeze`
--------------------------------
`vintage` already walls a corpus at an instant, and this module builds on the
same distinction — a row is visible when it was KNOWN, not when it HAPPENED.
Two things are different here.

First, `vintage` admits on observation time and merely *reports* occurrence
time. This wall also REFUSES on `published_at`: a record whose publication date
is after T0 cannot have been observed before T0, and a row asserting both is
corrupt rather than early. Reporting it as a publication lag would let a
corrupt row through.

Second, `vintage.freeze` partitions and returns counts. This wall returns a
NAMED reason per refused record, because "the snapshot admitted 12 of 400 rows"
and "the snapshot admitted 12 of 400 rows, 388 of which carried no observation
time at all" are different findings and only the second one is actionable.

PUBLISHED_AT MAY REFUSE. IT MAY NEVER ADMIT.
--------------------------------------------
This is the single most important line in the file. `published_at` is a
CONSTRAINT field: if it is after T0 the record is refused. It is not a
KNOWLEDGE field: a record carrying only `published_at` has not been shown to
have been observed by anyone, and admitting it on that basis is substitution.

The substitution is not hypothetical. The live ledger holds 2,347 macro
observations whose `retrieved_at` all fall inside one month while their
`published_at` spans three years. Filtering on publication time would admit
1,572 rows at 2026-01-01 that the engine had never seen, and every replay built
on them would look entirely healthy. `KNOWLEDGE_FIELDS` and `CONSTRAINT_FIELDS`
are disjoint by assertion at import, and `test_market_historical_corpus.py`
fails if anyone moves `published_at` across that line.

REVISED OUTCOMES ARE KEPT, NOT DELETED
--------------------------------------
An episode whose outcome was revised after T0 is real history and stays in the
corpus. It is flagged `REVISED` and refused at the estimator gate, because the
number an estimator would be scored against was produced later than the episode
it belongs to. Deleting the episode instead would destroy the only record that
the outcome moved at all, which is itself a finding about the series.

So a refusal reason names THE GATE THAT REFUSED. `WALL_VIOLATION`,
`NO_OBSERVABLE` and `INSUFFICIENT_PROVENANCE` refuse at the build gate and
produce no episode. `REVISED_OUTCOME` refuses at the estimator gate and the
episode still exists.

EMPTY STATES, DECLARED BEFORE SHIPPING
--------------------------------------
`NO_INPUT` (nothing was offered) and `NOTHING_KNOWN_AT_T0` (rows were offered
and none was knowable) are different claims, and a builder that returned an
empty list for both would report a corpus with no history and a corpus whose
wall rejected everything identically. `T0Snapshot.standing` separates them, and
`Corpus.standing` does the same for the corpus itself. An empty corpus is
reported as empty. It is never seeded with invented episodes.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

CONTRACT = "historical_corpus.v1"

DEFAULT_PATH = "reports/market/historical_corpus.jsonl"

# --- populations ---------------------------------------------------------------
#
# THE WALL THIS PROGRAM IS BUILT AROUND. A prospective decision was made by the
# engine running forward with the answer unavailable. A historical episode was
# assembled afterwards from a past whose answer is on record. Pooling them lets
# the second establish the standing of the first, and the prospective gate —
# the one number that says how much the engine has actually been tested — would
# clear itself the day somebody imported a spreadsheet.
HISTORICAL = "HISTORICAL"
PROSPECTIVE = "PROSPECTIVE"
POPULATIONS = (HISTORICAL, PROSPECTIVE)

# --- refusal vocabulary --------------------------------------------------------
#
# Named, closed, and shared by both gates. A free-text reason cannot be counted,
# and a refusal that cannot be counted is a silent drop with a nicer name.

#: A record was dated after T0, or an episode resolves before it forms. Either
#: way the episode would have used information that did not exist yet.
WALL_VIOLATION = "WALL_VIOLATION"
#: The outcome moved after T0. The episode is kept and flagged; it is this
#: reason that refuses it at the estimator gate.
REVISED_OUTCOME = "REVISED_OUTCOME"
#: Nothing was observed at T1, or nothing was named that WOULD have been
#: observed. An episode with no observable cannot come out wrong.
NO_OBSERVABLE = "NO_OBSERVABLE"
#: The record does not establish where it came from, or does not say what was
#: decided. An episode nobody can trace is an anecdote.
INSUFFICIENT_PROVENANCE = "INSUFFICIENT_PROVENANCE"

REFUSAL_REASONS = (WALL_VIOLATION, REVISED_OUTCOME, NO_OBSERVABLE,
                   INSUFFICIENT_PROVENANCE)

# --- population failure states (B-HIST-002) ------------------------------------
#: A row that declares no population. Refused, never defaulted.
UNTAGGED_ROW_REFUSED = "UNTAGGED_ROW_REFUSED"
#: A query that did not say which populations it wanted. There is no default.
MIXED_QUERY_UNSPECIFIED = "MIXED_QUERY_UNSPECIFIED"
POPULATION_REFUSALS = (UNTAGGED_ROW_REFUSED, MIXED_QUERY_UNSPECIFIED)

# --- time fields ---------------------------------------------------------------
#
# KNOWLEDGE fields say when the engine LEARNED a record and are the only fields
# that may admit one. Ordered most trustworthy first; `known_at` is the name
# this module writes, the rest exist on records older than it.
KNOWLEDGE_FIELDS = ("known_at", "observed_at", "first_seen_at", "retrieved_at")

#: CONSTRAINT fields say when the thing HAPPENED or was PUBLISHED. They may
#: refuse a record and may never admit one. `published_at` lives here, alone
#: among the timestamp fields in being both mandatory to check and forbidden to
#: rely on: a record published after T0 cannot have been seen before T0, so its
#: presence past the wall is corruption rather than lag.
CONSTRAINT_FIELDS = ("published_at", "occurred_at", "event_date")

# The substitution guard, executable. If someone adds `published_at` to
# KNOWLEDGE_FIELDS to "fix" a snapshot that admits nothing, the package stops
# importing rather than quietly admitting 1,572 rows nobody had seen.
assert not (set(KNOWLEDGE_FIELDS) & set(CONSTRAINT_FIELDS)), (
    "published_at may refuse a record and may never admit one; a field cannot "
    "be in both lists")
assert "published_at" not in KNOWLEDGE_FIELDS
assert "published_at" in CONSTRAINT_FIELDS

# --- snapshot standings --------------------------------------------------------
#: Nothing was offered to the builder. The corpus has no history here.
NO_INPUT = "NO_INPUT"
#: Records were offered and the wall admitted none of them. Very different from
#: NO_INPUT: this is a T0 at which the engine knew nothing, which is a
#: measurement of the corpus rather than an absence of one.
NOTHING_KNOWN_AT_T0 = "NOTHING_KNOWN_AT_T0"
POPULATED = "POPULATED"
STANDINGS = (NO_INPUT, NOTHING_KNOWN_AT_T0, POPULATED)


class EpisodeRefused(ValueError):
    """An episode that would have known something it could not have known.

    Carries `reason` from `REFUSAL_REASONS` so a caller can count refusals by
    kind instead of parsing a message.
    """

    def __init__(self, reason: str, detail: str = ""):
        if reason not in REFUSAL_REASONS:
            raise ValueError(f"unknown refusal reason {reason!r}")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class StaleContract(EpisodeRefused):
    """A row written by a producer version this reader does not speak.

    A separate class rather than a message a caller has to grep for. A guard
    that identifies its own failure state by matching prose matches the comment
    explaining the removal just as happily as the thing it was looking for.
    """


class PopulationUnstated(ValueError):
    """A row or a query that did not say which population it belongs to."""

    def __init__(self, reason: str, detail: str = ""):
        if reason not in POPULATION_REFUSALS:
            raise ValueError(f"unknown population refusal {reason!r}")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _stamp(value) -> str:
    """Normalise a timestamp to the precision the wall compares at.

    Truncation to seconds matches `vintage`, so a record that one module admits
    is not refused by the other over a microsecond nobody recorded on purpose.
    """
    return str(value)[:19] if value else ""


def _row_ref(row: dict) -> str:
    """A short, stable handle for a refused record.

    The whole row is NOT stored on the refusal. A refusal list that carries
    every rejected record is a second copy of the corpus, and the one time it
    matters — a snapshot that refused four hundred rows — it is also the reason
    nobody reads the report.
    """
    for name in ("record_id", "evidence_id", "observation_id", "decision_id",
                 "id"):
        if row.get(name):
            return str(row[name])[:64]
    return (str(row.get("record") or "row") + ":"
            + _digest({k: row.get(k) for k in sorted(row)}))


# --- what the engine could have known at T0 ------------------------------------

def knowledge_time(row: dict) -> str:
    """When the engine LEARNED this record, or "" if it never said.

    Reads `KNOWLEDGE_FIELDS` only. `published_at` is not consulted here and
    must never be added: this is the function a substitution would be made in.
    """
    for name in KNOWLEDGE_FIELDS:
        value = row.get(name)
        if value:
            return _stamp(value)
    return ""


def constraint_times(row: dict) -> Dict[str, str]:
    """Every occurrence/publication stamp the record carries.

    Returned as a mapping rather than a single value because the wall must
    check ALL of them — a record with an early `published_at` and a late
    `occurred_at` is still describing something that had not happened.
    """
    out: Dict[str, str] = {}
    for name in CONSTRAINT_FIELDS:
        value = row.get(name)
        if value:
            out[name] = _stamp(value)
    return out


@dataclass(frozen=True)
class Refusal:
    """One record the wall would not admit, and why."""

    reason: str
    row_ref: str
    detail: str = ""
    field: str = ""
    value: str = ""

    def __post_init__(self) -> None:
        if self.reason not in REFUSAL_REASONS:
            raise ValueError(f"unknown refusal reason {self.reason!r}")

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class T0Snapshot:
    """The state of knowledge at one historical instant, and what it cost.

    `refusals` is not diagnostic colour. It is half the result: a snapshot that
    admitted three rows out of four hundred is only interpretable next to the
    reason the other 397 went, and a builder that returned the three alone
    would present a starved snapshot as a thin corpus.
    """

    t0: str
    subject: str
    admitted: Tuple[dict, ...]
    refusals: Tuple[Refusal, ...] = ()

    @property
    def snapshot_id(self) -> str:
        return "t0_" + _digest({
            "t0": self.t0, "subject": self.subject,
            "admitted": sorted(_row_ref(r) for r in self.admitted)})

    @property
    def standing(self) -> str:
        if not self.admitted and not self.refusals:
            return NO_INPUT
        if not self.admitted:
            return NOTHING_KNOWN_AT_T0
        return POPULATED

    @property
    def refusals_by_reason(self) -> Dict[str, int]:
        """Every reason, always, including the ones that fired zero times.

        A dict built only from the reasons that occurred makes an absent key
        indistinguishable from a zero, and the first question anyone asks of
        this snapshot is whether the wall fired at all.
        """
        out = {reason: 0 for reason in REFUSAL_REASONS}
        for refusal in self.refusals:
            out[refusal.reason] += 1
        return out

    @property
    def leak_surface(self) -> int:
        """Records a publication-time filter would have admitted.

        The size of the error this wall avoids, measured rather than asserted.
        These are records whose publication or occurrence stamp is at or before
        T0 and whose knowledge stamp is missing or after it — exactly the rows
        that made the live macro corpus look replayable.
        """
        return sum(1 for r in self.refusals if r.detail.startswith("leakable:"))

    def rows(self, *, record: str = "") -> Tuple[dict, ...]:
        got = self.admitted
        if record:
            got = tuple(r for r in got if r.get("record") == record)
        return got

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "record": "t0_snapshot",
            "snapshot_id": self.snapshot_id, "t0": self.t0,
            "subject": self.subject, "standing": self.standing,
            "admitted": len(self.admitted),
            "refused": len(self.refusals),
            "refusals_by_reason": self.refusals_by_reason,
            "leak_surface": self.leak_surface,
            "note": ("leak_surface counts records that had been published or "
                     "had occurred by t0 and that the engine had not observed "
                     "by t0; a publication-time filter would have admitted "
                     "every one of them"),
        }


def build_t0_snapshot(rows: Iterable[dict], *, t0: str,
                      subject: str = "") -> T0Snapshot:
    """Partition a corpus at T0, refusing with a named reason and counting.

    THE COMPARISON IS `<= t0`. A record stamped exactly at T0 was knowable at
    T0; one stamped a second later was not. That single comparison is the whole
    wall, which is why the tests pin both sides of the boundary rather than
    checking a comfortable case in the middle.

    Three ways out, all counted:

      no knowledge stamp        -> INSUFFICIENT_PROVENANCE. Never admitted on
                                   the grounds that it is probably old enough.
      knowledge stamp  > t0     -> WALL_VIOLATION.
      constraint stamp > t0     -> WALL_VIOLATION. A record published after t0
                                   that claims to have been observed before it
                                   is corrupt, and admitting it because its
                                   knowledge field looked fine would let the
                                   corruption set the wall.
    """
    if not t0:
        raise EpisodeRefused(
            WALL_VIOLATION,
            "a snapshot needs an instant; building at an unspecified time "
            "admits everything, which is the leak this exists to stop")
    cut = _stamp(t0)
    admitted: List[dict] = []
    refusals: List[Refusal] = []
    for row in rows:
        known = knowledge_time(row)
        constraints = constraint_times(row)
        if not known:
            # `leakable:` marks the rows a publication-time filter would have
            # taken. Recorded in the detail rather than as a second field so
            # the refusal shape stays one thing.
            leakable = any(value <= cut for value in constraints.values())
            refusals.append(Refusal(
                reason=INSUFFICIENT_PROVENANCE, row_ref=_row_ref(row),
                detail=(("leakable: " if leakable else "")
                        + "no knowledge stamp in "
                        + "/".join(KNOWLEDGE_FIELDS)
                        + (f"; it carries {sorted(constraints)} and admitting "
                           "it on those would be substituting publication "
                           "time for observation time" if constraints else
                           "; it carries no timestamp at all")),
                field="", value=""))
            continue
        if known > cut:
            leakable = any(value <= cut for value in constraints.values())
            refusals.append(Refusal(
                reason=WALL_VIOLATION, row_ref=_row_ref(row),
                detail=(("leakable: " if leakable else "")
                        + f"observed {known}, after the {cut} wall; nobody "
                        "knew this yet"),
                field=_knowledge_field(row), value=known))
            continue
        late = sorted((name, value) for name, value in constraints.items()
                      if value > cut)
        if late:
            name, value = late[0]
            refusals.append(Refusal(
                reason=WALL_VIOLATION, row_ref=_row_ref(row),
                detail=(f"claims it was observed {known} but its {name} is "
                        f"{value}, after the {cut} wall; a record cannot have "
                        "been seen before it existed, so this row is corrupt "
                        "rather than early"),
                field=name, value=value))
            continue
        admitted.append(row)
    return T0Snapshot(t0=cut, subject=subject, admitted=tuple(admitted),
                      refusals=tuple(refusals))


def _knowledge_field(row: dict) -> str:
    for name in KNOWLEDGE_FIELDS:
        if row.get(name):
            return name
    return ""


# --- one episode ---------------------------------------------------------------

@dataclass(frozen=True)
class HistoricalEpisode:
    """A decision the past already answered, with the wall it was built behind.

    `population` is fixed at HISTORICAL and validated rather than defaulted,
    because the field exists to stop exactly one thing: a row of this kind
    reaching a prospective count. A field that silently defaults cannot stop
    it, since the row that gets there will be the one nobody set.

    `actual_observable` is `Optional[str]`. `None` means NOT OBSERVED and `""`
    means OBSERVED AND EMPTY, and the two are refused with different details
    because ABSENT and NO_CHANGE are different findings about the world.
    """

    subject: str
    t0: str
    t1: str
    decision: str
    declared_expectation: str
    expected_observable: str
    actual_observable: Optional[str]
    provenance: Tuple[str, ...]
    population: str = HISTORICAL
    outcome_revised_at: str = ""
    revision_detail: str = ""
    t0_snapshot_id: str = ""
    t0_rows_admitted: int = 0
    t0_rows_refused: int = 0
    t0_refusals_by_reason: Tuple[Tuple[str, int], ...] = ()
    selection_rule: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.population != HISTORICAL:
            raise EpisodeRefused(
                INSUFFICIENT_PROVENANCE,
                f"population {self.population!r}: this module builds "
                f"{HISTORICAL} episodes only, and a row of this kind carrying "
                f"{PROSPECTIVE} is the relabelling the whole node exists to "
                "prevent")
        if not self.subject.strip():
            raise EpisodeRefused(INSUFFICIENT_PROVENANCE,
                                 "an episode with no subject cannot be joined "
                                 "to anything it is supposed to be about")
        if not self.t0 or not self.t1:
            raise EpisodeRefused(WALL_VIOLATION,
                                 "an episode needs both instants")
        if _stamp(self.t1) <= _stamp(self.t0):
            raise EpisodeRefused(
                WALL_VIOLATION,
                f"t1 {self.t1} is not after t0 {self.t0}; an episode that "
                "resolves before it forms is a lookup wearing the shape of a "
                "prediction")
        if not self.decision.strip():
            raise EpisodeRefused(
                INSUFFICIENT_PROVENANCE,
                "an episode with no decision is an observation; there is "
                "nothing here for a reward model to attribute")
        if not self.declared_expectation.strip():
            raise EpisodeRefused(
                INSUFFICIENT_PROVENANCE,
                "an episode with no declared expectation cannot come out "
                "wrong, and one that cannot come out wrong teaches nothing")
        if not self.expected_observable.strip():
            raise EpisodeRefused(
                NO_OBSERVABLE,
                "an episode must name what would have shown the expectation "
                "held; without it the episode can only ever be UNRESOLVED for "
                "a reason nobody stated")
        if self.actual_observable is None:
            raise EpisodeRefused(
                NO_OBSERVABLE,
                f"no observation at t1 for {self.expected_observable!r}; the "
                "episode is unresolved, which is not the same as the "
                "expectation having failed")
        if not str(self.actual_observable).strip():
            raise EpisodeRefused(
                NO_OBSERVABLE,
                f"the observation at t1 for {self.expected_observable!r} is "
                "empty; an empty reading is an absent one, and recording it "
                "as a value would score the episode against a blank")
        if not self.provenance:
            raise EpisodeRefused(
                INSUFFICIENT_PROVENANCE,
                "an episode with no provenance cannot be checked by anyone "
                "who was not in the room; an untraceable episode is an "
                "anecdote and this corpus is meant to be evidence")

    @property
    def episode_id(self) -> str:
        return "he_" + _digest({
            "subject": self.subject, "t0": _stamp(self.t0),
            "t1": _stamp(self.t1), "decision": self.decision,
            "expectation": self.declared_expectation,
            "observable": self.expected_observable})

    @property
    def revised(self) -> bool:
        """Whether the outcome moved after T0.

        Compared against T0 rather than T1 on purpose: a figure restated at any
        point after the episode formed is a figure the episode's own timeline
        did not produce, and an estimator scored against it is being scored
        against a later world.
        """
        return bool(self.outcome_revised_at
                    and _stamp(self.outcome_revised_at) > _stamp(self.t0))

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["provenance"] = list(self.provenance)
        out["t0_refusals_by_reason"] = {k: v
                                        for k, v in self.t0_refusals_by_reason}
        out.update(record="historical_episode", contract=CONTRACT,
                   episode_id=self.episode_id, revised=self.revised)
        return out


def build_episode(*, subject: str, t0: str, t1: str, decision: str,
                  declared_expectation: str, expected_observable: str,
                  actual_observable: Optional[str],
                  provenance: Sequence[str],
                  rows: Sequence[dict] = (),
                  snapshot: Optional[T0Snapshot] = None,
                  outcome_revised_at: str = "", revision_detail: str = "",
                  selection_rule: str = "",
                  note: str = "") -> HistoricalEpisode:
    """Build one episode behind a T0 wall. THE PRODUCER.

    Either `rows` or `snapshot` may be supplied and the wall runs either way —
    passing `rows` builds the snapshot here so a caller cannot assemble the
    state itself and hand in a pre-leaked one. The snapshot's counts travel on
    the episode, so an episode persisted tonight still says how much its wall
    refused when it is read back in six months and the source rows are gone.
    """
    if snapshot is None:
        snapshot = build_t0_snapshot(rows, t0=t0, subject=subject)
    elif _stamp(snapshot.t0) != _stamp(t0):
        raise EpisodeRefused(
            WALL_VIOLATION,
            f"the supplied snapshot stands at {snapshot.t0} and the episode "
            f"forms at {t0}; a snapshot borrowed from another instant is the "
            "quietest way to leak")
    # THE EPISODE MAY NOT CITE WHAT THE WALL REFUSED. Walling the snapshot is
    # not enough on its own: the provenance list is written by whoever built
    # the candidate, and an episode whose stated basis includes a record from
    # after T0 is an episode reasoning from a fact it did not have, however
    # clean the snapshot beside it looks.
    refused = {r.row_ref for r in snapshot.refusals
               if r.reason == WALL_VIOLATION}
    cited = sorted({str(p) for p in provenance} & refused)
    if cited:
        raise EpisodeRefused(
            WALL_VIOLATION,
            f"the episode cites {cited}, which the {snapshot.t0} wall refused; "
            "an episode whose stated basis postdates its own T0 is a "
            "reconstruction of what we now know, not of what was knowable")
    return HistoricalEpisode(
        subject=subject, t0=_stamp(t0), t1=_stamp(t1), decision=decision,
        declared_expectation=declared_expectation,
        expected_observable=expected_observable,
        actual_observable=actual_observable,
        provenance=tuple(str(p) for p in provenance),
        population=HISTORICAL,
        outcome_revised_at=_stamp(outcome_revised_at),
        revision_detail=revision_detail,
        t0_snapshot_id=snapshot.snapshot_id,
        t0_rows_admitted=len(snapshot.admitted),
        t0_rows_refused=len(snapshot.refusals),
        t0_refusals_by_reason=tuple(sorted(
            snapshot.refusals_by_reason.items())),
        selection_rule=selection_rule, note=note)


def from_dict(row: dict) -> HistoricalEpisode:
    """Rebuild an episode from a persisted row. THE CONSUMER SIDE.

    Deliberately strict about two things a lenient reader would wave through:

    `population` is REQUIRED and is not consulted through any legacy table. A
    corpus row that does not say which population it belongs to is refused
    here, full stop — unlike `population_of`, which resolves ledger rows
    written before the field existed. The two readers must not be merged: the
    reason a legacy bridge is safe on the ledger is that those rows carry an
    explicit `provenance`, and no such bridge exists or should exist for a file
    this module writes.

    `contract` is checked. A row written by an older producer is refused rather
    than read with today's field meanings, because the failure mode of a silent
    version skew is a field that changed meaning and a reader that cannot tell.
    """
    if not isinstance(row, dict):
        raise EpisodeRefused(INSUFFICIENT_PROVENANCE,
                             f"expected a persisted row, got {type(row)!r}")
    contract = str(row.get("contract") or "")
    if not contract:
        raise StaleContract(
            INSUFFICIENT_PROVENANCE,
            "the row states no contract, so nothing says which producer's "
            "field meanings apply to it")
    if contract != CONTRACT:
        raise StaleContract(
            INSUFFICIENT_PROVENANCE,
            f"row was written by {contract}, this reader is {CONTRACT}; a "
            "stale producer's row is refused rather than read with today's "
            "field meanings")
    population = str(row.get("population") or "")
    if not population:
        raise PopulationUnstated(
            UNTAGGED_ROW_REFUSED,
            f"corpus row {row.get('episode_id') or '?'} declares no "
            "population; defaulting it is how a historical row reaches a "
            "prospective count")
    if population not in POPULATIONS:
        raise PopulationUnstated(
            UNTAGGED_ROW_REFUSED,
            f"unknown population {population!r}, expected one of "
            f"{list(POPULATIONS)}")
    refusals = row.get("t0_refusals_by_reason") or {}
    if isinstance(refusals, dict):
        refusals = tuple(sorted(refusals.items()))
    else:
        refusals = tuple(sorted((str(k), int(v)) for k, v in refusals))
    # `actual_observable` is read with a sentinel rather than `or ""`, so an
    # explicit null survives as None and is refused as NO_OBSERVABLE instead of
    # becoming an empty string that is refused for the wrong reason.
    observed = row["actual_observable"] if "actual_observable" in row else None
    return HistoricalEpisode(
        subject=str(row.get("subject") or ""),
        t0=_stamp(row.get("t0")), t1=_stamp(row.get("t1")),
        decision=str(row.get("decision") or ""),
        declared_expectation=str(row.get("declared_expectation") or ""),
        expected_observable=str(row.get("expected_observable") or ""),
        actual_observable=(None if observed is None else str(observed)),
        provenance=tuple(str(p) for p in (row.get("provenance") or ())),
        population=population,
        outcome_revised_at=_stamp(row.get("outcome_revised_at")),
        revision_detail=str(row.get("revision_detail") or ""),
        t0_snapshot_id=str(row.get("t0_snapshot_id") or ""),
        t0_rows_admitted=int(row.get("t0_rows_admitted") or 0),
        t0_rows_refused=int(row.get("t0_rows_refused") or 0),
        t0_refusals_by_reason=refusals,
        selection_rule=str(row.get("selection_rule") or ""),
        note=str(row.get("note") or ""))


# --- the corpus ----------------------------------------------------------------

@dataclass(frozen=True)
class Corpus:
    """Episodes that were built, and the ones that were not, with reasons."""

    episodes: Tuple[HistoricalEpisode, ...]
    refusals: Tuple[Refusal, ...] = ()
    built_at: str = ""

    @property
    def standing(self) -> str:
        if not self.episodes and not self.refusals:
            return NO_INPUT
        if not self.episodes:
            return NOTHING_KNOWN_AT_T0
        return POPULATED

    @property
    def refusals_by_reason(self) -> Dict[str, int]:
        out = {reason: 0 for reason in REFUSAL_REASONS}
        for refusal in self.refusals:
            out[refusal.reason] += 1
        return out

    def as_dict(self) -> dict:
        validation, excluded = for_estimator_validation(self.episodes)
        return {
            "contract": CONTRACT, "record": "historical_corpus_summary",
            "built_at": self.built_at, "population": HISTORICAL,
            "standing": self.standing,
            "episodes": len(self.episodes),
            "refused": len(self.refusals),
            "refusals_by_reason": self.refusals_by_reason,
            "revised": sum(1 for e in self.episodes if e.revised),
            "estimator_validation_eligible": len(validation),
            "estimator_validation_excluded": len(excluded),
            "counts_toward_prospective_gate": 0,
            "note": ("every episode here is HISTORICAL and none of it counts "
                     "toward the prospective decision gate; a refusal count "
                     "of zero on a real corpus means the wall never fired, "
                     "which is a finding about the builder rather than about "
                     "the data"),
        }


def build_corpus(candidates: Sequence[dict], *, rows_for: Optional[Dict] = None,
                 built_at: str = "") -> Corpus:
    """Build every candidate episode, keeping the ones that were refused.

    A candidate is a mapping of the keyword arguments `build_episode` takes.
    Refusals are collected rather than raised so one bad candidate does not
    take the corpus with it — and they are COLLECTED rather than dropped,
    because a builder that silently skipped would report a clean corpus of
    three episodes out of a hundred candidates and nothing would say so.
    """
    episodes: List[HistoricalEpisode] = []
    refusals: List[Refusal] = []
    for index, candidate in enumerate(candidates):
        payload = dict(candidate)
        if rows_for is not None and "rows" not in payload:
            payload["rows"] = rows_for.get(payload.get("subject", ""), ())
        try:
            episodes.append(build_episode(**payload))
        except EpisodeRefused as exc:
            refusals.append(Refusal(
                reason=exc.reason,
                row_ref=str(payload.get("subject") or f"candidate[{index}]"),
                detail=exc.detail))
        except PopulationUnstated as exc:
            refusals.append(Refusal(
                reason=INSUFFICIENT_PROVENANCE,
                row_ref=str(payload.get("subject") or f"candidate[{index}]"),
                detail=f"{exc.reason}: {exc.detail}"))
    return Corpus(episodes=tuple(episodes), refusals=tuple(refusals),
                  built_at=built_at)


def for_estimator_validation(episodes: Sequence[HistoricalEpisode]
                             ) -> Tuple[Tuple[HistoricalEpisode, ...],
                                        Tuple[Refusal, ...]]:
    """The episodes an estimator may be scored on, and the ones refused.

    THE REVISED GATE. An episode whose outcome moved after T0 is excluded here
    and kept in the corpus, because the episode is real history and the number
    is not the one its own timeline produced. Returning the exclusions rather
    than a filtered list is the difference between "the estimator scored 0.8 on
    40 episodes" and "the estimator scored 0.8 on the 40 of 52 episodes whose
    outcome never moved" — and only the second sentence is a result.
    """
    kept: List[HistoricalEpisode] = []
    excluded: List[Refusal] = []
    for episode in episodes:
        if episode.population != HISTORICAL:
            excluded.append(Refusal(
                reason=INSUFFICIENT_PROVENANCE, row_ref=episode.episode_id,
                detail=f"population {episode.population!r} is not {HISTORICAL}"))
            continue
        if episode.revised:
            excluded.append(Refusal(
                reason=REVISED_OUTCOME, row_ref=episode.episode_id,
                detail=(f"the outcome was revised {episode.outcome_revised_at}"
                        f", after t0 {episode.t0}"
                        + (f": {episode.revision_detail}"
                           if episode.revision_detail else "")),
                field="outcome_revised_at",
                value=episode.outcome_revised_at))
            continue
        kept.append(episode)
    return tuple(kept), tuple(excluded)


# --- persistence ---------------------------------------------------------------

class HistoricalCorpusStore:
    """Append-only JSONL beside the learning ledger, one row per episode.

    Append-only for the same reason the learning ledger is: an episode is a
    record of what was knowable at an instant, and a store that overwrote could
    be brought into line with a later understanding of the same past. That is
    precisely the edit this corpus exists to make impossible.

    A corrupt line is skipped and counted, never repaired.
    """

    def __init__(self, path=DEFAULT_PATH):
        self.path = pathlib.Path(path)
        self._corrupt = 0
        self._untagged = 0
        self._stale_contract = 0

    def record_episode(self, episode: HistoricalEpisode) -> bool:
        """Write one episode. Returns False if it was already written.

        Idempotent on `episode_id`: rebuilding the corpus is the normal
        operation — a reward model is retrained, an estimator is revalidated —
        and a store that appended every rebuild would grow without bound while
        the fold hid it.
        """
        if episode.population != HISTORICAL:
            raise PopulationUnstated(
                UNTAGGED_ROW_REFUSED,
                f"refusing to write population {episode.population!r} into "
                f"the {HISTORICAL} corpus")
        if episode.episode_id in self.episode_ids():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(episode.as_dict(), sort_keys=True,
                                    default=str) + "\n")
        return True

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

    def rows(self) -> Tuple[dict, ...]:
        """The persisted rows as written. The middle of the three shapes."""
        return tuple(self._rows())

    def episode_ids(self) -> frozenset:
        return frozenset(r.get("episode_id") for r in self._rows()
                         if r.get("episode_id"))

    def episodes(self) -> Tuple[HistoricalEpisode, ...]:
        """Reload every episode, refusing untagged and stale rows.

        A refused row is COUNTED, not dropped: `health()` reports
        `untagged_rows_refused` and `stale_contract_rows_refused`, so a corpus
        that silently halved between two releases says which half went where.
        """
        self._untagged = 0
        self._stale_contract = 0
        out: List[HistoricalEpisode] = []
        for row in self._rows():
            try:
                out.append(from_dict(row))
            except PopulationUnstated:
                self._untagged += 1
            except StaleContract:
                self._stale_contract += 1
            except EpisodeRefused:
                self._corrupt += 1
        return tuple(out)

    def health(self) -> dict:
        episodes = self.episodes()
        validation, excluded = for_estimator_validation(episodes)
        return {
            "contract": CONTRACT, "path": str(self.path),
            "exists": self.path.exists(),
            "population": HISTORICAL,
            "episodes": len(episodes),
            "revised": sum(1 for e in episodes if e.revised),
            "estimator_validation_eligible": len(validation),
            "estimator_validation_excluded": len(excluded),
            "corrupt_lines_skipped": self._corrupt,
            "untagged_rows_refused": self._untagged,
            "stale_contract_rows_refused": self._stale_contract,
            # NOT a zero that could be mistaken for a measurement. A corpus
            # file that does not exist and a corpus file holding no episodes
            # are different states, and the second one means the builder ran.
            "standing": (NO_INPUT if not self.path.exists()
                         else NOTHING_KNOWN_AT_T0 if not episodes
                         else POPULATED),
        }


# --- population separation, at read (B-HIST-002) --------------------------------
#
# Declared HERE, next to the corpus that produces the historical half, and
# RESTATED in `docs/execution/v4/metrics.py`. The restatement is not laziness:
# `metrics.py` is run as `python3 docs/execution/v4/metrics.py` with no
# PYTHONPATH and must stay stdlib-only, exactly as the founder branch cannot
# import this package. The two copies are held together by a test that runs
# both against the same adversarial rows and fails if they disagree.

#: A narrow, closed table of declarations made under the field name that
#: existed BEFORE `population` did. Keyed on record kind, field and exact
#: value, so nothing generalises to a record kind nobody considered.
#:
#: WHY THIS IS NOT A DEFAULT. A `research_decision` row carrying
#: `provenance=PROSPECTIVE` was written by the live engine, before the external
#: call, with the answer unavailable — which is the definition of the
#: prospective population, asserted explicitly by the producer in the only
#: field the schema had at the time. Reading it is a translation. Assuming a
#: population for a row that declared none would be a default, and that is
#: refused below.
#:
#: `provenance=RECONSTRUCTED` is deliberately absent: a reconstructed row is
#: not a historical episode either, so it resolves to no population and is
#: refused rather than counted on either side.
LEGACY_POPULATION_DECLARATIONS = {
    ("research_decision", "provenance", PROSPECTIVE): PROSPECTIVE,
}


def population_of(row: dict) -> str:
    """The population a LEDGER row declares, or "" if it declares none.

    Resolution order, and the order is the guard: the explicit `population`
    field is read FIRST, so a row tagged HISTORICAL stays historical no matter
    what else it carries. The adversarial case is a historical row injected
    with `provenance=PROSPECTIVE` attached, and it must lose.

    Returns "" rather than raising, so a caller can count untagged rows.
    `require_population` raises for the callers that should not continue.
    """
    declared = str(row.get("population") or "")
    if declared:
        return declared if declared in POPULATIONS else ""
    kind = str(row.get("record") or "")
    for (record, field, value), population in \
            LEGACY_POPULATION_DECLARATIONS.items():
        if kind == record and str(row.get(field) or "") == value:
            return population
    return ""


def require_population(row: dict) -> str:
    """The row's population, or a refusal. Never a default."""
    population = population_of(row)
    if not population:
        raise PopulationUnstated(
            UNTAGGED_ROW_REFUSED,
            f"row {_row_ref(row)} declares no population and none can be "
            "resolved from what it does declare; counting it would put a row "
            "of unknown provenance into a population gate")
    return population


def select(rows: Sequence[dict], *,
           populations: Optional[Sequence[str]] = None
           ) -> Tuple[Tuple[dict, ...], Dict[str, int]]:
    """Rows in the NAMED populations, plus a census of everything seen.

    `populations` has no default and an omitted argument raises. A default of
    "all" would make every existing call site a mixed query the day the first
    historical row landed, and a default of PROSPECTIVE would make the mixed
    case the one nobody wrote down. A mixed query names both:

        select(rows, populations=[HISTORICAL, PROSPECTIVE])

    The census counts by population INCLUDING the untagged, so a caller can
    see what it did not get. A filter that returned only the matches would
    report 40 prospective rows out of an unknown total.
    """
    if populations is None:
        raise PopulationUnstated(
            MIXED_QUERY_UNSPECIFIED,
            "a population query must name its populations explicitly; there "
            f"is no default. Name one of {list(POPULATIONS)}, or both for a "
            "mixed query")
    wanted = [str(p) for p in populations]
    if not wanted:
        raise PopulationUnstated(
            MIXED_QUERY_UNSPECIFIED,
            "an empty population list selects nothing and reads like a query "
            "for everything")
    unknown = [p for p in wanted if p not in POPULATIONS]
    if unknown:
        raise PopulationUnstated(
            MIXED_QUERY_UNSPECIFIED,
            f"unknown population(s) {unknown}, expected {list(POPULATIONS)}")
    census = {population: 0 for population in POPULATIONS}
    census[UNTAGGED_ROW_REFUSED] = 0
    kept: List[dict] = []
    for row in rows:
        population = population_of(row)
        if not population:
            census[UNTAGGED_ROW_REFUSED] += 1
            continue
        census[population] += 1
        if population in wanted:
            kept.append(row)
    return tuple(kept), census


def census(rows: Sequence[dict]) -> Dict[str, int]:
    """Rows by population, with the untagged counted rather than assigned."""
    _, counts = select(rows, populations=list(POPULATIONS))
    return counts


# --- deriving candidates from the engine's own resolved past --------------------

def candidates_from_reconciliations(rows: Sequence[dict]) -> List[dict]:
    """Episodes the engine already lived through, as `build_episode` kwargs.

    WHY THIS IS LEGITIMATE HISTORY AND NOT A RELABELLED PROSPECTIVE ROW.
    An `expectation` is preregistered — it names a metric, a direction and a
    falsifier at a stated instant, BEFORE the outcome. A `reconciliation`
    resolves it later against evidence. That pair is exactly a historical
    decision episode: a decision at T0, a declared expectation, an observable,
    and what the observable turned out to be at T1.

    It does not move one row into the prospective count. The prospective gates
    read `research_decision` rows on the learning ledger and filter on
    population; these candidates produce rows in a different file, and
    B-HIST-002's guard asserts a historical row cannot move a prospective gate.

    PROVENANCE IS THE T0 BASIS, NEVER THE RESOLUTION.
    `expectation.evidence_basis` is what was known when the expectation was
    written; `reconciliation.evidence_ids` is what resolved it, and every one
    of those postdates T0 by construction. Citing them would be citing exactly
    what the wall refused, and `build_episode` rejects an episode whose stated
    basis includes a record the snapshot excluded. Passing them would turn a
    wall into a formality.
    """
    expectations = {str(r.get("expectation_id") or ""): r
                    for r in rows if r.get("record") == "expectation"}
    out: List[dict] = []
    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        expectation = expectations.get(str(row.get("expectation_id") or ""))
        if expectation is None:
            # A resolution naming no expectation on the ledger cannot be
            # walled: there is no T0 to stand at. Skipped here and visible as
            # the gap between reconciliations and candidates.
            continue
        t0 = _stamp(expectation.get("preregistered_at"))
        t1 = _stamp(row.get("evaluated_at"))
        if not t0 or not t1 or t1 <= t0:
            # A resolution at or before the instant the expectation was
            # written is not an outcome, whatever the dates say.
            continue
        observed = row.get("observed_direction") or row.get("observed_value")
        out.append({
            "subject": str(expectation.get("subject") or ""),
            "t0": t0,
            "t1": t1,
            "decision": (f"preregister {expectation.get('metric')} "
                         f"{expectation.get('expected_direction')}"),
            "declared_expectation": str(expectation.get("expected_direction")
                                        or ""),
            "expected_observable": str(expectation.get("metric") or ""),
            "actual_observable": None if observed is None else str(observed),
            "provenance": tuple(expectation.get("evidence_basis") or ()),
            "selection_rule": ("every reconciliation on the ledger that names "
                               "an expectation, in ledger order; nothing is "
                               "chosen by what its outcome turned out to be"),
            "note": str(row.get("outcome") or ""),
        })
    return out
