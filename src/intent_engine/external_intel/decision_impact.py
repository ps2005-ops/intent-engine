"""Did the market's learning change anything a founder acts on?

WHY RENDERED IS NOT ENOUGH
--------------------------
The consumption ladder can now prove a dossier was published, validated,
reasoned over and rendered — 22 of 22 on the real corpus. None of that shows
the learning mattered. A strategic block can appear on the page, be perfectly
provenanced, and leave every risk, assumption, option and falsifier exactly as
it was. That state is real and common, and it has a name here rather than
being quietly counted as success.

WHAT IS DELIBERATELY NOT AN IMPACT
----------------------------------
Every one of these makes an analysis longer and none makes it better, so each
is rejected explicitly rather than left to judgement:

  - an extra paragraph or section header
  - an extra citation on a claim that already stood
  - a higher word count
  - a generic caution that would fit any company
  - the same content restated in a new place

The failure mode this guards against is the easy one: wire the metric to
"something changed" and it will read 100% forever, because something always
changes when you add a block. So the comparison is over SEMANTIC FIELDS, and
a field only counts as impacted when its content changed, not its length.

MATERIALITY IS ORDINAL, ON PURPOSE
----------------------------------
NONE / MINOR / MEANINGFUL / DECISION_CHANGING. No percentages: there is no
sample from which a decision-impact probability could be estimated, and a
number here would be the same error as printing a market belief's 0.586 prior
as founder confidence.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "decision_impact.v1"

# --- what a market-derived item is allowed to have changed ------------------
DIRECT_ANSWER = "DIRECT_ANSWER"
WHY_NOW = "WHY_NOW"
OPTION = "OPTION"
RECOMMENDATION = "RECOMMENDATION"
RISK = "RISK"
ASSUMPTION = "ASSUMPTION"
ALTERNATIVE = "ALTERNATIVE"
FALSIFIER = "FALSIFIER"
MONITORING_PRIORITY = "MONITORING_PRIORITY"
STRATEGIC_MECHANISM = "STRATEGIC_MECHANISM"
BOUNDED_CONCLUSION = "BOUNDED_CONCLUSION"
EVIDENCE_REQUIREMENT = "EVIDENCE_REQUIREMENT"

IMPACT_TYPES: Tuple[str, ...] = (
    DIRECT_ANSWER, WHY_NOW, OPTION, RECOMMENDATION, RISK, ASSUMPTION,
    ALTERNATIVE, FALSIFIER, MONITORING_PRIORITY, STRATEGIC_MECHANISM,
    BOUNDED_CONCLUSION, EVIDENCE_REQUIREMENT,
)

# --- how a field changed ----------------------------------------------------
UNCHANGED = "UNCHANGED"
ADDED = "ADDED"
REMOVED = "REMOVED"
STRENGTHENED = "STRENGTHENED"
WEAKENED = "WEAKENED"
BOUNDED = "BOUNDED"
REVERSED = "REVERSED"

CHANGE_KINDS = frozenset({UNCHANGED, ADDED, REMOVED, STRENGTHENED, WEAKENED,
                          BOUNDED, REVERSED})

# --- materiality ------------------------------------------------------------
NONE = "NONE"
MINOR = "MINOR"
MEANINGFUL = "MEANINGFUL"
DECISION_CHANGING = "DECISION_CHANGING"

MATERIALITY = (NONE, MINOR, MEANINGFUL, DECISION_CHANGING)

#: Fields whose change is, by itself, a decision changing. A recommendation or
#: a direct answer that moves is not a nuance.
_DECISIVE_FIELDS = frozenset({DIRECT_ANSWER, RECOMMENDATION,
                              BOUNDED_CONCLUSION})
#: Fields a founder acts on even when the headline is unchanged.
_MEANINGFUL_FIELDS = frozenset({RISK, ASSUMPTION, FALSIFIER, OPTION,
                                MONITORING_PRIORITY, WHY_NOW,
                                STRATEGIC_MECHANISM, ALTERNATIVE,
                                EVIDENCE_REQUIREMENT})

#: Phrases that would fit any company. A "change" made only of these is
#: cosmetic, and counting it is how this metric would become meaningless.
_GENERIC = re.compile(
    r"^(?:this (?:may|could|might)|it is important to|consider|note that|"
    r"the company should monitor|further evidence (?:is|would be) "
    r"(?:needed|helpful)|monitor (?:the )?(?:situation|developments)|"
    r"as always|in general|broadly speaking)\b", re.I)


def _norm(text: object) -> str:
    return " ".join(str(text or "").lower().split())


def _is_generic(text: str) -> bool:
    return bool(_GENERIC.match(_norm(text)))


def _content(items: Sequence[object]) -> List[str]:
    """Comparable content: normalised, de-duplicated, generics dropped."""
    out, seen = [], set()
    for item in items or ():
        text = _norm(item)
        if not text or _is_generic(text) or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


@dataclass(frozen=True)
class FieldDelta:
    """How one decision field differs between two analyses."""
    impact_type: str
    change: str
    before: Tuple[str, ...] = ()
    after: Tuple[str, ...] = ()
    added: Tuple[str, ...] = ()
    removed: Tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return self.change != UNCHANGED

    def as_dict(self) -> dict:
        return {"impact_type": self.impact_type, "change": self.change,
                "added": list(self.added), "removed": list(self.removed),
                "before_semantic_state": list(self.before),
                "after_semantic_state": list(self.after)}


def compare_field(impact_type: str, before: Sequence[object],
                  after: Sequence[object]) -> FieldDelta:
    """Semantic comparison of one decision field.

    Not a text diff. Two renderings of the same content are UNCHANGED, and a
    field that gained only boilerplate is UNCHANGED too — `_content` strips
    generics and duplicates before anything is compared, so the easy ways to
    fake an impact are removed before the comparison rather than judged after.
    """
    if impact_type not in IMPACT_TYPES:
        raise ValueError(f"unknown impact type {impact_type!r}")
    old, new = _content(before), _content(after)
    gained = tuple(x for x in new if x not in set(old))
    lost = tuple(x for x in old if x not in set(new))

    if not gained and not lost:
        change = UNCHANGED
    elif gained and not lost:
        change = ADDED if not old else STRENGTHENED
    elif lost and not gained:
        change = REMOVED if new else WEAKENED
    else:
        # Both directions. A field whose content was replaced rather than
        # extended is the strongest signal available short of an explicit
        # reversal marker.
        change = REVERSED
    return FieldDelta(impact_type=impact_type, change=change,
                      before=tuple(old), after=tuple(new),
                      added=gained, removed=lost)


def materiality_of(deltas: Sequence[FieldDelta]) -> str:
    """Ordinal materiality across every field that moved."""
    changed = [d for d in deltas if d.changed]
    if not changed:
        return NONE
    if any(d.impact_type in _DECISIVE_FIELDS for d in changed):
        return DECISION_CHANGING
    if any(d.impact_type in _MEANINGFUL_FIELDS for d in changed):
        return MEANINGFUL
    return MINOR


@dataclass(frozen=True)
class DecisionImpact:
    """One market-derived item, and what it did or did not change."""
    analysis_id: str
    company_id: str
    dossier_id: str
    dossier_revision: str
    belief_id: str
    graph_node_id: str
    deltas: Tuple[FieldDelta, ...]
    materiality: str
    reason: str
    provenance: Tuple[str, ...] = ()
    created_at: str = ""
    #: THE EVIDENCE EACH SIDE COULD SEE. Empty means it was not recorded,
    #: which is a third state and not a claim that the windows matched.
    #: Without these, a change between two revisions is attributed to the
    #: engine's reasoning when the available explanation is that the later
    #: run simply had three more weeks of filings. That confound cannot be
    #: detected after the fact, so it is represented before the first real
    #: pair exists rather than after.
    before_known_at: str = ""
    after_known_at: str = ""
    prior_revision_id: str = ""
    current_revision_id: str = ""

    @property
    def comparability(self) -> str:
        """Whether a difference here can be attributed to reasoning at all."""
        if not self.before_known_at or not self.after_known_at:
            return UNKNOWN_WINDOW
        if self.before_known_at == self.after_known_at:
            return SAME_WINDOW
        return WIDER_WINDOW

    @property
    def attributable(self) -> bool:
        """Whether this row may enter a rate about the engine's value."""
        return self.comparability == SAME_WINDOW

    @property
    def decision_impact_id(self) -> str:
        raw = "|".join((self.analysis_id, self.company_id,
                        self.dossier_revision, self.belief_id))
        return "di_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def changed(self) -> bool:
        return any(d.changed for d in self.deltas)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "decision_impact_id": self.decision_impact_id,
            "analysis_id": self.analysis_id,
            "company_id": self.company_id,
            "dossier_id": self.dossier_id,
            "dossier_revision": self.dossier_revision,
            "belief_id": self.belief_id,
            "graph_node_id": self.graph_node_id,
            "changed": self.changed,
            "materiality": self.materiality,
            "impact_types": sorted({d.impact_type for d in self.deltas
                                    if d.changed}),
            "deltas": [d.as_dict() for d in self.deltas if d.changed],
            "reason": self.reason,
            "provenance": list(self.provenance),
            "created_at": self.created_at,
            "before_known_at": self.before_known_at,
            "after_known_at": self.after_known_at,
            "prior_revision_id": self.prior_revision_id,
            "current_revision_id": self.current_revision_id,
            "comparability": self.comparability,
            "attributable": self.attributable,
        }


def assess(*, analysis_id: str, company_id: str, dossier_id: str = "",
           dossier_revision: str = "", belief_id: str = "",
           graph_node_id: str = "", before: Dict[str, Sequence[object]],
           after: Dict[str, Sequence[object]],
           provenance: Sequence[str] = ()) -> DecisionImpact:
    """Compare two analyses field by field and grade the difference.

    PROVENANCE IS REQUIRED FOR ANY CLAIM OF IMPACT. An impact that cannot name
    the evidence behind it is indistinguishable from the analysis having
    changed for some unrelated reason — a different retrieval, a different
    model sample — and crediting the market engine for that would corrupt the
    one metric that says whether its learning is worth anything.
    """
    deltas = tuple(
        compare_field(impact_type, before.get(impact_type, ()),
                      after.get(impact_type, ()))
        for impact_type in IMPACT_TYPES
        if impact_type in before or impact_type in after)

    grade = materiality_of(deltas)
    if grade != NONE and not provenance:
        grade = NONE
        reason = ("fields differ but no market evidence is cited for the "
                  "difference; an unprovenanced change is not attributable "
                  "to the market engine")
    elif grade == NONE:
        reason = ("the dossier was rendered and no decision field changed "
                  "content")
    else:
        moved = sorted({d.impact_type for d in deltas if d.changed})
        reason = f"changed: {', '.join(moved)}"

    return DecisionImpact(
        analysis_id=analysis_id, company_id=company_id,
        dossier_id=dossier_id or company_id,
        dossier_revision=dossier_revision, belief_id=belief_id,
        graph_node_id=graph_node_id, deltas=deltas, materiality=grade,
        reason=reason, provenance=tuple(provenance),
        created_at=_dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds"))


# ---------------------------------------------------------------------------
# the deterministic harness
# ---------------------------------------------------------------------------
def semantic_state(context) -> Dict[str, List[str]]:
    """Reduce an external context to the decision fields it constrains.

    DETERMINISTIC ON PURPOSE. Comparing two LLM generations would measure
    sampling noise and call it learning: run the same analysis twice with no
    dossier at all and the prose differs, so any text-level comparison starts
    at a false-positive rate near 100%.

    So the comparison runs one level below the language, over the structured
    inputs the reasoning is built from. A market belief enters as an
    ASSUMPTION (a reading held about the company), the mechanism it names
    enters as STRATEGIC_MECHANISM, and its stated limitations enter as
    EVIDENCE_REQUIREMENT — because "one period's result is a data point, not
    a trend" is exactly a statement about what evidence would be needed.
    """
    from intent_engine.external_intel import pack as ep

    blocks = ep.reasoning_pack(context)["blocks"]
    strategic = [b for b in blocks if b.get("context") == ep.STRATEGIC]

    assumptions: List[str] = []
    mechanisms: List[str] = []
    requirements: List[str] = []
    monitoring: List[str] = []
    bounded: List[str] = []

    for block in strategic:
        for fact in block.get("facts") or ():
            text = str(fact)
            if text.lower().startswith("market evidence currently supports"):
                assumptions.append(text)
            elif text.lower().startswith("basis:"):
                mechanisms.append(text)
            elif text.lower().startswith("standing:"):
                monitoring.append(text)
        for limitation in block.get("limitations") or ():
            requirements.append(str(limitation))
        # HOW SOUND THE EVIDENCE IS, read from the named key rather than
        # sniffed out of the prose. A trust note starts with none of the
        # prefixes above, so classifying it by text would drop the one line
        # that constrains the conclusion and report NO impact — the metric
        # would then be measuring its own blind spot.
        if block.get("evidence_standing"):
            bounded.append(str(block["evidence_standing"]))

    return {
        ASSUMPTION: assumptions,
        STRATEGIC_MECHANISM: mechanisms,
        EVIDENCE_REQUIREMENT: requirements,
        MONITORING_PRIORITY: monitoring,
        BOUNDED_CONCLUSION: bounded,
    }


def evidence_of(context) -> List[str]:
    """Market evidence ids behind the strategic blocks, for provenance."""
    from intent_engine.external_intel import pack as ep

    out: List[str] = []
    for block in ep.reasoning_pack(context)["blocks"]:
        if block.get("context") != ep.STRATEGIC:
            continue
        out.extend(str(e) for e in (block.get("evidence_ids") or ()))
    return out


# ---------------------------------------------------------------------------
# THE PRIOR STATE, WITHOUT WHICH THIS METRIC MEASURES ITS OWN PRESENCE
# ---------------------------------------------------------------------------
#
# MEASURED, 2026-08-09, ON ALL 59 LIVE DOSSIERS: 25 were available and every
# single one graded MEANINGFUL or DECISION_CHANGING. Sixteen the latter, nine
# the former, and NOT ONE `NONE`.
#
# The cause is not a threshold. The production call site builds its BEFORE as
# `build_context(strategic=None)`, and `semantic_state` of that context is
# EMPTY on all five fields. So every field goes empty -> populated, every
# field is "changed", and an available dossier is structurally incapable of
# grading NONE. The metric answers "was a dossier attached", which is already
# known, and reads 100% forever — the exact failure this module's own
# docstring predicted and named.
#
# A metric that cannot report the negative is not evidence. What the founder
# question actually asks is whether the NEW learning changed anything, so the
# BEFORE has to be what the founder saw LAST TIME: the previous revision of
# this company's dossier.
#
# Three outcomes, not two:
#
#   FIRST_OBSERVATION   no prior revision exists. Not an impact and not a
#                       non-impact — there was nothing to change. Counting it
#                       either way is what produced 25 of 25.
#   NONE / MINOR / ...  a real comparison against what was there before.
#
# The store is append-only and keyed by content, so re-deriving the same
# dossier appends nothing and a genuinely new revision is a second row.

FIRST_OBSERVATION = "FIRST_OBSERVATION"

# --- whether a difference can be attributed to reasoning at all -------------
#
# Three states, never two. A comparison whose evidence windows were not
# recorded is not a comparison whose windows matched, and pooling the two is
# how "the engine changed its mind" comes to mean "the engine saw more".
SAME_WINDOW = "SAME_EVIDENCE_WINDOW"      # a clean comparison
WIDER_WINDOW = "WIDER_EVIDENCE_WINDOW"    # the later side saw more
UNKNOWN_WINDOW = "UNKNOWN_EVIDENCE_WINDOW"  # not recorded; not a match
COMPARABILITY = (SAME_WINDOW, WIDER_WINDOW, UNKNOWN_WINDOW)

#: Outcomes that make no claim about impact and must never enter an impact
#: rate's numerator OR its denominator.
NON_CLAIMS = frozenset({FIRST_OBSERVATION})

REVISION_PATH = "reports/market/dossier_revisions.jsonl"


def revision_key(state: Dict[str, Sequence[object]]) -> str:
    """Content key for one semantic state. Same content, same key."""
    payload = "|".join(
        f"{field}:{';'.join(sorted(_content(state.get(field, ()))))}"
        for field in IMPACT_TYPES)
    return "rev_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_revisions(root, *, path: str = REVISION_PATH) -> Dict[str, dict]:
    """The newest recorded revision per company, by append order.

    Append order rather than a date field, for the same reason the market's
    learning windows use it: a date on a record is set by whoever wrote it,
    and the ledger already knows what order it accepted things in.
    """
    import json as _json
    import pathlib as _pathlib

    target = _pathlib.Path(root) / path
    if not target.exists():
        return {}
    latest: Dict[str, dict] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = _json.loads(line)
        except ValueError:
            continue          # a corrupt line is skipped, never repaired
        company = str(row.get("company_id") or "")
        if company:
            latest[company] = row
    return latest


def record_revision(root, *, company_id: str,
                    state: Dict[str, Sequence[object]],
                    dossier_revision: str = "",
                    path: str = REVISION_PATH) -> bool:
    """Persist one company's semantic state. False if unchanged.

    Returning False on an unchanged dossier is what keeps the file from
    growing by one row per company per cycle forever, and it is also the
    signal the caller needs: nothing to compare means nothing happened.
    """
    import json as _json
    import pathlib as _pathlib

    if not company_id:
        raise ValueError("a dossier revision needs the company it belongs to")
    key = revision_key(state)
    prior = load_revisions(root, path=path).get(company_id)
    if prior and str(prior.get("revision_key")) == key:
        return False
    target = _pathlib.Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "record": "dossier_revision", "contract": CONTRACT,
        "company_id": company_id, "revision_key": key,
        "dossier_revision": dossier_revision,
        "state": {field: list(_content(state.get(field, ())))
                  for field in IMPACT_TYPES},
        "recorded_at": _dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds"),
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(_json.dumps(row, sort_keys=True) + "\n")
    return True


def assess_against_prior(root, *, analysis_id: str, company_id: str,
                         after: Dict[str, Sequence[object]],
                         provenance: Sequence[str] = (),
                         dossier_revision: str = "",
                         path: str = REVISION_PATH) -> DecisionImpact:
    """Grade this dossier against the one the founder saw last time.

    The BEFORE is a recorded prior revision, never an empty context. When no
    prior exists the answer is FIRST_OBSERVATION, which is neither an impact
    nor a non-impact: there was nothing for the learning to change.
    """
    prior = load_revisions(root, path=path).get(company_id)
    if prior is None:
        return DecisionImpact(
            analysis_id=analysis_id, company_id=company_id,
            dossier_id=company_id, dossier_revision=dossier_revision,
            belief_id="", graph_node_id="", deltas=(),
            materiality=FIRST_OBSERVATION,
            reason=("no prior revision of this dossier is recorded, so there "
                    "was nothing for this learning to change; the state is "
                    "now recorded and the next revision can be compared"),
            provenance=tuple(provenance),
            created_at=_dt.datetime.now(
                _dt.timezone.utc).isoformat(timespec="seconds"))
    before = {field: list(values)
              for field, values in (prior.get("state") or {}).items()}
    return assess(analysis_id=analysis_id, company_id=company_id,
                  dossier_revision=dossier_revision, before=before,
                  after=after, provenance=provenance)


IMPACT_PATH = "reports/market/decision_impact.jsonl"


def record_impact(root, *, impact: DecisionImpact,
                  path: str = IMPACT_PATH) -> bool:
    """Persist one graded comparison, INCLUDING the ones that changed nothing.

    The production call site records an impact only `if impact.changed`, which
    makes the file a success log: a rate computed over it is 100% by
    construction and cannot fall. NONE and FIRST_OBSERVATION are the rows that
    give the rate a denominator, and they are the reason this function exists
    beside the receipt rather than inside it.

    Idempotent on `decision_impact_id`, so re-deriving the same comparison on
    the same day appends nothing.
    """
    import json as _json
    import pathlib as _pathlib

    target = _pathlib.Path(root) / path
    payload = impact.as_dict()
    impact_id = str(payload.get("decision_impact_id") or "")
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if impact_id and f'"{impact_id}"' in line:
                return False
    target.parent.mkdir(parents=True, exist_ok=True)
    payload["record"] = "decision_impact"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(_json.dumps(payload, sort_keys=True) + "\n")
    return True


def load_impacts(root, *, path: str = IMPACT_PATH) -> List[dict]:
    import json as _json
    import pathlib as _pathlib

    target = _pathlib.Path(root) / path
    if not target.exists():
        return []
    out: List[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(_json.loads(line))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# WHAT CHANGED YOUR MIND — three states, three answers, never two
# ---------------------------------------------------------------------------
#
# The question a founder asks that this system is least entitled to guess at.
# It must resolve:
#
#     thesis -> latest non-CREATED revision -> KnowledgeEffect -> evidence
#
# and it has exactly three honest outcomes. The one that matters is the third:
# a dossier that arrived WITHOUT revision history is not a thesis that never
# moved. Before the transport carried history, this consumer could only have
# said the second, and would have said it confidently.

HISTORY_AVAILABLE_NO_MOVEMENT = "HISTORY_AVAILABLE_NO_MOVEMENT"
HISTORY_AVAILABLE_MOVED = "HISTORY_AVAILABLE_MOVED"
#: The history was readable and holds no revision for this subject. NOT the
#: same as NO_MOVEMENT: there is no view here that could have stayed put. A
#: live audit found 22 of 25 published dossiers reporting NO_MOVEMENT with
#: zero revisions, which said "nothing has changed this view yet" about
#: companies for which no view had ever been formed.
HISTORY_AVAILABLE_NO_THESIS = "HISTORY_AVAILABLE_NO_THESIS"
HISTORY_UNAVAILABLE = "HISTORY_UNAVAILABLE"

_KNOWN_HISTORY_STATES = (HISTORY_AVAILABLE_NO_MOVEMENT,
                         HISTORY_AVAILABLE_MOVED,
                         HISTORY_AVAILABLE_NO_THESIS,
                         HISTORY_UNAVAILABLE)

_OPENING_TRANSITION = "CREATED"


def mind_change_state(intel) -> str:
    """Which of the four states this dossier is in.

    A producer that sends no `thesis_history` at all is UNAVAILABLE, not
    NO_MOVEMENT. An older producer that cannot send history must never be
    read as one reporting a quiet thesis.

    A producer that CLAIMS no movement while sending no revisions is not
    believed either. The status is stated rather than counted precisely so
    the two cannot be confused — but a stated status contradicted by the
    payload it describes is a producer defect, and reading it as the finding
    it claims to be would import that defect wholesale. The stricter reading
    wins here, as everywhere else on this bridge.
    """
    stated = getattr(intel, "thesis_history", None)
    if not isinstance(stated, dict) or not stated.get("status"):
        return HISTORY_UNAVAILABLE
    status = str(stated.get("status") or "")
    if status not in _KNOWN_HISTORY_STATES:
        return HISTORY_UNAVAILABLE
    if status == HISTORY_AVAILABLE_NO_MOVEMENT and not _revisions(intel):
        return HISTORY_AVAILABLE_NO_THESIS
    return status


def _revisions(intel) -> list:
    return [r for r in (getattr(intel, "thesis_revisions", ()) or ())
            if isinstance(r, dict)]


def what_changed_your_mind(intel) -> dict:
    """The answer, its state, and the records that support it.

    Returns the sentence to say and the ids behind it. It never composes a
    reason from the current thesis: a claim about what CHANGED a view can
    only come from a recorded transition, and inferring one from the view's
    present wording is the fabrication this whole chain exists to prevent.
    """
    state = mind_change_state(intel)
    if state == HISTORY_UNAVAILABLE:
        return {
            "state": state, "answer": (
                "I have the current view, but not enough revision history in "
                "this analysis to tell you what changed it."),
            "revisions": [], "effects": [], "evidence": [],
            "supported": False,
        }
    if state == HISTORY_AVAILABLE_NO_THESIS:
        return {
            "state": state, "answer": (
                "Nothing, because there is no view here yet. No economic "
                "thesis has been opened for this company, so there is nothing "
                "for evidence to have changed."),
            "revisions": [], "effects": [], "evidence": [],
            "supported": True,
        }
    moved = [r for r in _revisions(intel)
             if str(r.get("transition") or "") != _OPENING_TRANSITION]
    if not moved:
        return {
            "state": HISTORY_AVAILABLE_NO_MOVEMENT, "answer": (
                "Nothing has changed this view yet. This is still the first "
                "recorded version of it."),
            "revisions": [], "effects": [], "evidence": [],
            "supported": True,
        }
    latest = sorted(moved, key=lambda r: str(r.get("changed_at") or ""))[-1]
    effects = list(latest.get("knowledge_effect_ids") or ())
    evidence = list(latest.get("triggering_evidence") or ())
    # A TRANSITION WITH NO CAUSE IS NOT AN ANSWER. The record says the view
    # moved and cannot say what moved it, so the sentence says exactly that
    # rather than naming the transition as if it explained itself.
    if not effects and not evidence:
        return {
            "state": HISTORY_AVAILABLE_MOVED, "answer": (
                f"The view was recorded as {latest.get('transition')} on "
                f"{latest.get('changed_at')}, and the record does not name "
                f"the evidence behind that change."),
            "revisions": [latest.get("revision_id")], "effects": [],
            "evidence": [], "supported": False,
        }
    was = str(latest.get("previous_standing") or "its opening standing")
    now = str(latest.get("new_standing") or "an unrecorded standing")
    why = str(latest.get("reason") or "no reason was recorded")
    return {
        "state": HISTORY_AVAILABLE_MOVED, "answer": (
            f"The view moved from {was} to {now} on "
            f"{latest.get('changed_at')}: {why}."),
        "revisions": [latest.get("revision_id")], "effects": effects,
        "evidence": evidence, "supported": True,
    }
