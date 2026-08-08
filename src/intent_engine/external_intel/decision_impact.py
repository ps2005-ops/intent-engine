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

    return {
        ASSUMPTION: assumptions,
        STRATEGIC_MECHANISM: mechanisms,
        EVIDENCE_REQUIREMENT: requirements,
        MONITORING_PRIORITY: monitoring,
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
