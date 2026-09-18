"""What changed the engine's mind, as a record rather than a reconstruction.

WHY A CHAIN AND NOT A FIELD
---------------------------
`economic_thesis.supersede` already returns the retired thesis beside its
successor, so the engine can hold both. What it cannot do is say WHY the second
replaced the first: which evidence moved it, which knowledge object actually
changed, which field of the claim differs, and whether the standing went up or
down.

That question — "what changed your mind?" — is the one a CEO asks when a
recommendation reverses, and it is the one an engine is most tempted to answer
by having a model read the two claims and narrate a difference. A narration is
not a record. It is generated after the fact from the same text a reader can
see, it cannot be wrong in any way that shows, and it will confabulate a reason
when the real reason is that a threshold moved.

So a revision carries the KnowledgeEffect ids that caused it. Those were
written at real state-change seams, and if none exists the transition is
refused rather than explained.

APPEND-ONLY, AND CONTIGUOUS
---------------------------
A revision names the revision it follows. Appending one whose parent is not the
current head is refused, because a chain that can fork silently is a chain
where the losing branch disappears — which is exactly the history worth
keeping. Nothing here rewrites a prior row.

WHAT A TRANSITION MAY NOT DO
----------------------------
A revision may not raise standing without supporting evidence, and it may not
drop an alternative without saying which evidence eliminated it. Both are ways
a thesis quietly becomes more certain than its evidence, and both look like
tidying up in a diff.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "thesis_history.v1"

# --- what happened to a thesis -------------------------------------------------
CREATED = "CREATED"
STRENGTHENED = "STRENGTHENED"
WEAKENED = "WEAKENED"
CONTESTED = "CONTESTED"
FALSIFIED = "FALSIFIED"
SUPERSEDED = "SUPERSEDED"
RETIRED = "RETIRED"
TRANSITIONS = (CREATED, STRENGTHENED, WEAKENED, CONTESTED, FALSIFIED,
               SUPERSEDED, RETIRED)

#: Transitions that make a thesis MORE believed. These are the ones that need
#: evidence; a transition that weakens a claim is allowed on less, because
#: doubting something on thin grounds is not the failure mode this guards.
UPWARD = frozenset({STRENGTHENED})


class RevisionRejected(ValueError):
    """A revision that would make the history unable to answer for itself."""


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


@dataclass(frozen=True)
class ThesisRevision:
    """One dated change to one thesis, and what caused it."""

    thesis_id: str
    transition: str
    previous_standing: str
    new_standing: str
    reason: str
    changed_at: str
    previous_revision: str = ""
    #: The attributions that caused this. Written at state-change seams, so a
    #: revision pointing at them can be checked against what actually moved.
    knowledge_effect_ids: Tuple[str, ...] = ()
    triggering_evidence: Tuple[str, ...] = ()
    changed_fields: Tuple[str, ...] = ()
    alternatives_before: Tuple[str, ...] = ()
    alternatives_after: Tuple[str, ...] = ()
    provenance: str = "cycle"

    def __post_init__(self) -> None:
        if self.transition not in TRANSITIONS:
            raise RevisionRejected(f"unknown transition {self.transition!r}")
        if not self.thesis_id or not self.changed_at:
            raise RevisionRejected(
                "a revision needs the thesis it belongs to and the moment it "
                "happened")
        if not self.reason.strip():
            raise RevisionRejected(
                "an unexplained revision is a history that cannot answer the "
                "one question it exists for")
        caused = bool(self.knowledge_effect_ids or self.triggering_evidence)
        if self.transition != CREATED and not caused:
            raise RevisionRejected(
                f"{self.transition} names no knowledge effect and no "
                "triggering evidence; a transition whose cause is only prose "
                "is a narration of a change, not a record of one")
        if self.transition in UPWARD and not self.knowledge_effect_ids:
            raise RevisionRejected(
                f"{self.transition} raises standing on triggering evidence "
                "alone; a claim may only become more believed on evidence "
                "that CHANGED something, and that is what an effect id is")
        # An alternative removed without a named cause is the quiet way a
        # thesis becomes the only explanation.
        dropped = set(self.alternatives_before) - set(self.alternatives_after)
        if dropped and not caused:
            raise RevisionRejected(
                f"alternatives {sorted(dropped)} disappeared without evidence "
                "eliminating them")

    @property
    def revision_id(self) -> str:
        return "rev_" + _digest({
            "thesis": self.thesis_id, "transition": self.transition,
            "at": self.changed_at, "prev": self.previous_revision,
            "effects": sorted(self.knowledge_effect_ids)})

    @property
    def raises_standing(self) -> bool:
        return self.transition in UPWARD

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        for key in ("knowledge_effect_ids", "triggering_evidence",
                    "changed_fields", "alternatives_before",
                    "alternatives_after"):
            out[key] = list(getattr(self, key))
        out.update(record="thesis_revision", contract=CONTRACT,
                   revision_id=self.revision_id)
        return out


def diff(before, after) -> Tuple[str, ...]:
    """Which fields of a thesis differ. Compared as data, not as prose."""
    fields = ("claim", "leading_mechanism", "alternatives", "macro_conditions",
              "exposures", "supporting_evidence", "contradicting_evidence",
              "unknowns", "horizon_days", "standing")
    out = []
    for name in fields:
        one, two = getattr(before, name, None), getattr(after, name, None)
        if name == "leading_mechanism":
            one = getattr(one, "description", one)
            two = getattr(two, "description", two)
        elif name == "alternatives":
            one = tuple(getattr(m, "description", m) for m in (one or ()))
            two = tuple(getattr(m, "description", m) for m in (two or ()))
        if one != two:
            out.append(name)
    return tuple(out)


def classify(before, after) -> str:
    """What KIND of change this was, from the standings and the fields."""
    from . import economic_thesis as ET

    old, new = before.standing, after.standing
    if new == ET.REFUTED:
        return FALSIFIED
    if new == ET.SUPERSEDED:
        return SUPERSEDED
    if new == ET.WEAKENED and old != ET.WEAKENED:
        return WEAKENED
    if old == ET.PROPOSED and new in (ET.SUPPORTED, ET.TESTED):
        return STRENGTHENED
    if new == ET.SUPPORTED and old == ET.WEAKENED:
        return STRENGTHENED
    if after.contradicting_evidence and not before.contradicting_evidence:
        return CONTESTED
    if len(after.supporting_evidence) > len(before.supporting_evidence):
        return STRENGTHENED
    return CONTESTED


def revision_from_row(row: dict) -> ThesisRevision:
    """One stored row back into the record it was written from.

    Only the fields `ThesisRevision` declares are read. `as_dict` adds
    `record`, `contract` and the derived `revision_id`; passing those back
    into the constructor would be an error, and recomputing `revision_id`
    rather than trusting the stored one means a row whose id was edited no
    longer matches its own content.
    """
    fields = {f.name for f in dataclasses.fields(ThesisRevision)}
    kwargs = {k: v for k, v in dict(row).items() if k in fields}
    for name in ("knowledge_effect_ids", "triggering_evidence",
                 "changed_fields", "alternatives_before",
                 "alternatives_after"):
        if name in kwargs:
            kwargs[name] = tuple(kwargs[name] or ())
    return ThesisRevision(**kwargs)


class ThesisHistory:
    """The append-only chain, and the answers it can give."""

    def __init__(self, revisions: Sequence[ThesisRevision] = ()):
        self._rows: List[ThesisRevision] = []
        for revision in revisions:
            self.append(revision)

    # --- writing ----------------------------------------------------------
    def head(self, thesis_id: str) -> str:
        for revision in reversed(self._rows):
            if revision.thesis_id == thesis_id:
                return revision.revision_id
        return ""

    def append(self, revision: ThesisRevision) -> ThesisRevision:
        current = self.head(revision.thesis_id)
        if revision.previous_revision != current:
            raise RevisionRejected(
                f"revision for {revision.thesis_id} follows "
                f"{revision.previous_revision or 'nothing'} but the chain head "
                f"is {current or 'nothing'}; a history that can fork silently "
                "loses whichever branch is not read")
        self._rows.append(revision)
        return revision

    def record(self, before, after, *, changed_at: str, reason: str,
               knowledge_effect_ids: Sequence[str] = (),
               triggering_evidence: Sequence[str] = ()) -> ThesisRevision:
        """Build and append the revision between two states of one thesis."""
        return self.append(ThesisRevision(
            thesis_id=before.thesis_id,
            transition=classify(before, after),
            previous_standing=before.standing, new_standing=after.standing,
            reason=reason, changed_at=changed_at,
            previous_revision=self.head(before.thesis_id),
            knowledge_effect_ids=tuple(knowledge_effect_ids),
            triggering_evidence=tuple(triggering_evidence),
            changed_fields=diff(before, after),
            alternatives_before=tuple(
                m.description for m in (before.alternatives or ())),
            alternatives_after=tuple(
                m.description for m in (after.alternatives or ()))))

    @classmethod
    def load(cls, rows: Sequence[dict]) -> Tuple["ThesisHistory", List[str]]:
        """Rebuild the chain from stored rows, and say what would not fit.

        THE READ PATH THAT DID NOT EXIST. The cycle built a fresh, empty
        history every night, so `previous_revision` was "" on every row ever
        written and no chain had more than one link. The write path was live
        and verified; nothing read it back, which meant "what changed your
        mind?" was answered from a single night's comparison rather than from
        the record.

        Rows that cannot be placed are returned rather than raised on: a
        ledger written by an older derivation should not stop tonight's cycle.
        They are returned so the count reaches the report — a rehydration that
        drops rows silently is the same failure one layer down.
        """
        history = cls()
        dropped: List[str] = []
        for row in rows:
            try:
                revision = revision_from_row(row)
            except (RevisionRejected, TypeError, ValueError) as exc:
                dropped.append(f"{row.get('revision_id', '?')}: {exc}")
                continue
            try:
                history.append(revision)
            except RevisionRejected as exc:
                dropped.append(f"{revision.revision_id}: {exc}")
        return history, dropped

    # --- reading ----------------------------------------------------------
    def chain_all(self) -> Tuple[ThesisRevision, ...]:
        return tuple(self._rows)

    def chain(self, thesis_id: str) -> Tuple[ThesisRevision, ...]:
        return tuple(r for r in self._rows if r.thesis_id == thesis_id)

    def what_changed_your_mind(self, thesis_id: str) -> dict:
        """The exact answer, from records. No prose is generated here."""
        rows = self.chain(thesis_id)
        moves = [r for r in rows if r.transition != CREATED]
        if not moves:
            return {
                "contract": CONTRACT, "thesis_id": thesis_id,
                "changed": False,
                "answer": ("nothing has changed this thesis since it was "
                           "stated; it stands where it started"),
                "revisions": len(rows),
            }
        latest = moves[-1]
        return {
            "contract": CONTRACT, "thesis_id": thesis_id, "changed": True,
            "answer": latest.reason,
            "transition": latest.transition,
            "standing": f"{latest.previous_standing} -> "
                        f"{latest.new_standing}",
            "because_of_effects": list(latest.knowledge_effect_ids),
            "because_of_evidence": list(latest.triggering_evidence),
            "changed_fields": list(latest.changed_fields),
            "at": latest.changed_at,
            "revisions": len(rows),
            "strengthened_by": [e for r in rows if r.transition == STRENGTHENED
                                for e in r.knowledge_effect_ids],
            "weakened_by": [e for r in rows
                            if r.transition in (WEAKENED, FALSIFIED,
                                                CONTESTED)
                            for e in r.knowledge_effect_ids],
            "alternatives_eliminated": sorted(
                set(latest.alternatives_before)
                - set(latest.alternatives_after)),
        }

    def summarise(self) -> dict:
        import collections

        by_transition = collections.Counter(r.transition for r in self._rows)
        theses = {r.thesis_id for r in self._rows}
        unexplained = [r.revision_id for r in self._rows
                       if r.transition != CREATED
                       and not r.knowledge_effect_ids]
        return {
            "contract": CONTRACT,
            "revisions": len(self._rows),
            "theses": len(theses),
            "by_transition": {t: by_transition.get(t, 0) for t in TRANSITIONS},
            "theses_that_moved": len({r.thesis_id for r in self._rows
                                      if r.transition != CREATED}),
            # A revision explained only by evidence that changed nothing is
            # weaker than one backed by an effect. Counted rather than
            # refused, because a WEAKENED transition is allowed on it.
            "moves_without_an_effect": len(unexplained),
            "note": ("every transition other than CREATED names the evidence "
                     "or the knowledge effect that caused it; a strengthening "
                     "must name an effect, because a claim may only become "
                     "more believed on evidence that changed something"),
        }


# --- the production seam -------------------------------------------------------

def dependency_objects(thesis) -> frozenset:
    """The canonical objects this thesis rests on, in the ids effects use.

    THE FORMAT IS THE WHOLE POINT. An exposure effect is written with
    `target_id = f"{company_id}:{dimension}"` — that is the exposure object's
    canonical id. This set was previously built from the bare dimension
    names, so `"CAPITAL_INTENSITY"` was compared against
    `"america_movil:CAPITAL_INTENSITY"` and never matched. Two live cycles
    reported zero attributed effects, which read as a strict rule working and
    was a rule that could not fire.

    Bare dimensions are deliberately NOT accepted. `"CAPITAL_INTENSITY"`
    without a company matches every company's exposure, which is the
    over-attribution this guard exists to prevent, in a subtler form.
    """
    subject = getattr(thesis, "subject", "")
    area = str(getattr(thesis, "area", "") or "")
    out = set()
    prefix = f"{subject}:"
    for dimension in (getattr(thesis, "exposures", None) or ()):
        # `exposures` holds a bare dimension when the thesis was built from a
        # transmission, and an already-qualified reference when a caller
        # wrote one. Both name the same object; neither is normalised into a
        # bare dimension, because `"CAPITAL_INTENSITY"` with no company in
        # front of it matches every company's exposure.
        text = str(dimension)
        out.add(text if text.startswith(prefix) else prefix + text)
    for kind in (getattr(thesis, "macro_conditions", None) or ()):
        # An economic state is keyed `(area, state_kind)`. Unqualified kinds
        # are accepted only when the thesis itself does not know its area,
        # because otherwise a US rate effect would bear on a Canadian thesis.
        out.add(f"{area}:{kind}" if area else kind)
    mechanism = getattr(thesis, "leading_mechanism", None)
    if mechanism is not None:
        out.add(getattr(mechanism, "identity_key", "")
                or getattr(mechanism, "description", ""))
    out.update(getattr(thesis, "falsifiers", None) or ())
    out.discard("")
    return frozenset(out)


def effects_bearing_on(thesis, effects: Sequence) -> Tuple[str, ...]:
    """The effect ids that actually bear on THIS thesis.

    THE RULE THAT MATTERS. The lazy version attaches every effect from the
    cycle to every thesis about the same company, which makes each revision
    look thoroughly evidenced and means nothing: a thesis about capex would
    cite an effect on a demand state because they share a subject. Then the
    strengthening guard passes on evidence that had no bearing, and the guard
    is decoration.

    So an effect counts only when it names the thesis itself, or one of the
    canonical objects the thesis declares it depends on. Sharing a subject is
    not enough and never was.
    """
    from . import knowledge_effect as KE

    basis = dependency_objects(thesis)
    out = []
    for effect in effects:
        target_type = getattr(effect, "target_type", "")
        target_id = str(getattr(effect, "target_id", ""))
        if target_type == KE.THESIS and target_id == thesis.thesis_id:
            out.append(effect.effect_id)
        elif target_id and target_id in basis:
            out.append(effect.effect_id)
    return tuple(sorted(set(out)))


def identity(thesis) -> str:
    """What makes two theses the SAME thesis across cycles.

    This is `thesis_id`, and it is one value rather than a tuple assembled
    here. The previous identity was `(subject, question)`, chosen because
    `thesis_id` then hashed the claim and the date and so changed every night.
    That derivation has been repaired in `economic_thesis`; keeping a second,
    coarser notion of identity beside it is how the two drift apart.

    `(subject, question)` was also wrong on its own terms. A live cycle built
    eleven theses over seven of those pairs, because two economies can move
    the same condition for one company: `CA:MARKET_RATE` and `US:MARKET_RATE`
    are different states and were the same identity.
    """
    return thesis.thesis_id


def reconcile(previous: Sequence, current: Sequence, *, as_of: str,
              effects: Sequence = (), history: Optional[ThesisHistory] = None
              ) -> Tuple[ThesisHistory, dict]:
    """Compare two cycles' theses and record what moved.

    Returns the history and a bounded summary. A thesis present in both with
    no semantic difference records NOTHING — a revision per cycle per thesis
    would bury the real movements under a log of restatements.
    """
    from . import economic_thesis as ET

    history = history if history is not None else ThesisHistory()

    # ONE PRIOR, ONE CURRENT. `before` was a dict comprehension over the
    # priors, which silently kept the last snapshot per key, and nothing
    # stopped several current theses from matching one prior. A live cycle
    # reported `compared: 11` against `loaded: 7` — arithmetic that is not
    # possible for a one-to-one match, and the signal that eleven theses were
    # being graded against seven other theses' pasts.
    before: Dict[str, object] = {}
    counts = {k: 0 for k in ("loaded", "current", "compared", "unchanged",
                             "created", "strengthened", "weakened",
                             "contested", "falsified", "superseded",
                             "written", "unattributed", "identity_collisions",
                             "unmatched_prior", "unmatched_current")}
    for prior_thesis in previous:
        key = identity(prior_thesis)
        if key in before:
            # Two persisted theses with one identity. Neither can be compared
            # against, because there is no way to say which one a current
            # thesis descends from.
            counts["identity_collisions"] += 1
            continue
        before[key] = prior_thesis
    counts["loaded"] = len(previous)
    counts["current"] = len(current)

    consumed = set()
    for thesis in current:
        key = identity(thesis)
        prior = before.get(key)
        if prior is not None and key in consumed:
            counts["identity_collisions"] += 1
            continue
        if prior is None:
            counts["unmatched_current"] += 1
            if history.head(thesis.thesis_id):
                continue
            history.append(ThesisRevision(
                thesis_id=thesis.thesis_id, transition=CREATED,
                previous_standing="", new_standing=thesis.standing,
                reason=f"first stated for {thesis.subject}: {thesis.claim}",
                changed_at=as_of))
            counts["created"] += 1
            counts["written"] += 1
            continue
        consumed.add(key)
        counts["compared"] += 1
        changed = diff(prior, thesis)
        if not changed:
            counts["unchanged"] += 1
            continue
        bearing = effects_bearing_on(thesis, effects)
        transition = classify(prior, thesis)
        # A strengthening with no effect bearing on this thesis is not
        # recorded as a strengthening. The guard would refuse it anyway; the
        # honest reading is that the claim moved for a reason the ledger
        # cannot name, which is CONTESTED, not stronger.
        if transition in UPWARD and not bearing:
            counts["unattributed"] += 1
            continue
        evidence = tuple(thesis.supporting_evidence or ())
        if transition != CREATED and not bearing and not evidence:
            counts["unattributed"] += 1
            continue
        history.append(ThesisRevision(
            thesis_id=prior.thesis_id, transition=transition,
            previous_standing=prior.standing, new_standing=thesis.standing,
            reason=(f"{', '.join(changed)} moved between cycles"),
            changed_at=as_of, previous_revision=history.head(prior.thesis_id),
            knowledge_effect_ids=bearing, triggering_evidence=evidence,
            changed_fields=changed,
            alternatives_before=tuple(m.description
                                      for m in (prior.alternatives or ())),
            alternatives_after=tuple(m.description
                                     for m in (thesis.alternatives or ()))))
        counts[transition.lower()] = counts.get(transition.lower(), 0) + 1
        counts["written"] += 1

    counts["unmatched_prior"] = len(previous) - len(consumed)

    # THE INVARIANT, CHECKED RATHER THAN DOCUMENTED. Both conditions are
    # unreachable given the loop above, which is exactly why they are worth
    # asserting: if either fires, the matching rule has been changed and
    # revisions are being attributed to theses that did not earn them. That
    # is a wrong entry in an append-only record, so it stops the cycle rather
    # than being counted and written.
    if counts["compared"] > counts["loaded"]:
        raise RevisionRejected(
            f"compared {counts['compared']} theses against {counts['loaded']} "
            "prior snapshots; more comparisons than priors means some prior "
            "was reused, and a revision built on a reused prior names the "
            "wrong thesis")
    if len(consumed) > len(before):
        raise RevisionRejected(
            "more priors were consumed than were loaded; the match is no "
            "longer one-to-one")

    summary = dict(counts)
    summary.update(
        contract=CONTRACT,
        note=("a thesis present in both cycles with no semantic difference "
              "records nothing; `unattributed` counts claims that moved with "
              "no knowledge effect bearing on them, which is a finding about "
              "the attribution seam rather than a revision; "
              "`identity_collisions` counts theses that could not be matched "
              "one-to-one and were therefore not compared at all"))
    return history, summary
