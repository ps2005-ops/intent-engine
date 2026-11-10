"""What the object extractor refused, and whether the answer was there.

WHY A REFUSAL IS A RECORD AND NOT A NONE
----------------------------------------
`competitive_objects.extract` returns `(None, None)` when it establishes
nothing. That is the right ANSWER and the wrong RECORD: it discards which
dimensions were present, which were missing, and what the sentence actually
said. Wave 8 handed forward "84 UNKNOWN objects" as a corpus and the corpus
did not exist — the refusals had never been written down, so the number was
recovered by re-running the extractor over stored spans.

THE QUESTION THIS MODULE EXISTS TO ANSWER
-----------------------------------------
There are two completely different reasons an object is not established, and
they have opposite remedies:

    EXTRACTION_RECOVERABLE      the buyer is IN the sentence and was missed
    SOURCE_MISSING_INFORMATION  the document never says who it is for

Improving extraction cannot fix the second. Buying more documents cannot fix
the first. Conflating them is how a project spends a wave on the wrong half,
so the adjudication is a stored, auditable label rather than an impression.

AND A THIRD ANSWER NOBODY EXPECTED
----------------------------------
Most refusals are neither. They are sentences that are not actions at all —
release cadences, navigation, benefit copy, customer testimonials. For those
the object extractor is behaving correctly and the defect is upstream, in
what the action detector admitted. A near-miss corpus that does not separate
NOT_AN_ACTION from a real missing dimension will send every wave to improve
the extractor, forever.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "near_miss.v1"

# --- why no object was established (structural, read off the extractor) -----
NOT_AN_ACTION = "NOT_AN_ACTION"
NO_BUYER = "NO_BUYER"
NO_PRODUCT = "NO_PRODUCT"
NO_WHAT_OR_WHO = "NO_WHAT_OR_WHO"
PARTIAL_OBJECT = "PARTIAL_OBJECT"

CLUSTERS = (NOT_AN_ACTION, NO_BUYER, NO_PRODUCT, NO_WHAT_OR_WHO,
            PARTIAL_OBJECT)

# --- whether the information was there (adjudicated against the document) ---
EXTRACTION_RECOVERABLE = "EXTRACTION_RECOVERABLE"
SOURCE_MISSING_INFORMATION = "SOURCE_MISSING_INFORMATION"
TRUNCATED_CONTEXT = "TRUNCATED_CONTEXT"
WRONG_DOCUMENT = "WRONG_DOCUMENT"
AMBIGUOUS = "AMBIGUOUS"
CORRECT_UNKNOWN = "CORRECT_UNKNOWN"

ADJUDICATIONS = (EXTRACTION_RECOVERABLE, SOURCE_MISSING_INFORMATION,
                 TRUNCATED_CONTEXT, WRONG_DOCUMENT, AMBIGUOUS,
                 CORRECT_UNKNOWN)

#: Adjudications that a better EXTRACTOR could convert. `TRUNCATED_CONTEXT`
#: is included because the fix is the same kind — read more of the document
#: that was already retrieved — and it is reported separately so the two are
#: never silently merged.
RECOVERABLE = frozenset({EXTRACTION_RECOVERABLE, TRUNCATED_CONTEXT})


@dataclass(frozen=True)
class NearMiss:
    """One refusal, with enough of its context to be argued about."""
    action_id: str
    actor: str
    source_family: str
    action_type: str
    span: str
    dimensions_present: Tuple[str, ...]
    missing_dimensions: Tuple[str, ...]
    cluster: str
    #: Set only by adjudication against the real document. Absent means
    #: nobody has looked, which is distinct from "we looked and it was
    #: absent" — the whole point of the module.
    adjudication: str = ""
    note: str = ""

    @property
    def is_adjudicated(self) -> bool:
        return bool(self.adjudication)

    @property
    def is_recoverable(self) -> bool:
        return self.adjudication in RECOVERABLE

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "action_id": self.action_id,
            "actor": self.actor, "source_family": self.source_family,
            "action_type": self.action_type, "span": self.span,
            "dimensions_present": list(self.dimensions_present),
            "missing_dimensions": list(self.missing_dimensions),
            "cluster": self.cluster, "adjudication": self.adjudication,
            "note": self.note,
        }


def cluster_of(obj, action_type: str = "") -> str:
    """Which structural class a refusal falls into.

    This reads only what the extractor produced. It cannot tell an action
    from a description — that is what adjudication is for — so a refusal
    with nothing at all is `NO_WHAT_OR_WHO` here and may still turn out to
    be `NOT_AN_ACTION` once somebody reads the sentence.
    """
    if obj is None:
        return NO_WHAT_OR_WHO
    present = set(getattr(obj, "dimensions_present", ()) or ())
    missing = {m.upper() for m in (getattr(obj, "missing", ()) or ())}
    if getattr(obj, "standing", "") == "ESTABLISHED":
        return ""
    if missing == {"WHO"}:
        return NO_BUYER
    if missing == {"WHAT"}:
        return NO_PRODUCT
    if present:
        return PARTIAL_OBJECT
    return NO_WHAT_OR_WHO


#: Curly quotes, dashes and runs of whitespace differ between the page, the
#: stored span and anything typed by hand. A label that misses because of a
#: quote character reads as "nobody has adjudicated this", which is the one
#: state the corpus exists to distinguish.
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"',
                         "”": '"', "–": "-", "—": "-",
                         " ": " "})

#: How much of a sentence has to agree for a label to apply. Long enough
#: that two different announcements cannot collide, short enough to survive
#: a trailing clause being re-parsed.
LABEL_KEY_CHARS = 60


def label_key(span: str) -> str:
    """The stable part of a sentence, for matching a hand label to it."""
    text = " ".join((span or "").translate(_QUOTES).split()).lower()
    return text[:LABEL_KEY_CHARS]


def collect(actions: Sequence[dict], objects: Dict[str, object],
            labels: Optional[Dict[str, dict]] = None) -> Tuple[NearMiss, ...]:
    """Every action that did not establish an object, with its class.

    `labels` is keyed by `label_key(span)`. Keying on the sentence rather
    than the action id is deliberate: ids are content hashes that move when
    an extractor changes, and a hand adjudication is about the sentence,
    which does not.
    """
    labels = {label_key(k): v for k, v in (labels or {}).items()}
    out: List[NearMiss] = []
    for act in actions:
        obj = objects.get(act.get("action_id", ""))
        standing = getattr(obj, "standing", None) or (
            obj.get("standing") if isinstance(obj, dict) else None)
        if standing == "ESTABLISHED":
            continue
        cluster = cluster_of(_as_obj(obj), act.get("action_type", ""))
        label = labels.get(label_key(act.get("span", "")), {})
        out.append(NearMiss(
            action_id=act.get("action_id", ""), actor=act.get("actor", ""),
            source_family=act.get("source_family", ""),
            action_type=act.get("action_type", ""),
            span=act.get("span", ""),
            dimensions_present=tuple(
                (_get(obj, "dimensions_present") or ()) if obj else ()),
            missing_dimensions=tuple((_get(obj, "missing") or ()) if obj else ()),
            cluster=cluster,
            adjudication=str(label.get("adjudication", "") or ""),
            note=str(label.get("note", "") or "")))
    return tuple(out)


def _get(obj, name):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


class _Shim:
    def __init__(self, data):
        self.standing = data.get("standing", "")
        self.dimensions_present = tuple(data.get("dimensions_present") or ())
        self.missing = tuple(data.get("missing") or ())


def _as_obj(obj):
    return _Shim(obj) if isinstance(obj, dict) else obj


def summarise(misses: Sequence[NearMiss]) -> dict:
    """Counts, and the one rate that decides what to build next.

    `recoverable_object_rate` is computed over ADJUDICATED REAL ACTIONS
    only. Including unadjudicated rows would report a low rate for work
    nobody has done, and including non-actions would report a low rate for
    a problem the extractor does not have.
    """
    by_cluster = collections.Counter(m.cluster for m in misses)
    by_adjudication = collections.Counter(
        m.adjudication for m in misses if m.is_adjudicated)
    adjudicated = [m for m in misses if m.is_adjudicated]
    real_actions = [m for m in adjudicated
                    if m.adjudication != WRONG_DOCUMENT]
    recoverable = [m for m in real_actions if m.is_recoverable]
    not_actions = by_adjudication.get(WRONG_DOCUMENT, 0)
    return {
        "contract": CONTRACT,
        "near_misses": len(misses),
        "adjudicated": len(adjudicated),
        "unadjudicated": len(misses) - len(adjudicated),
        "by_cluster": {c: by_cluster.get(c, 0) for c in CLUSTERS
                       if by_cluster.get(c, 0)},
        "by_adjudication": {a: by_adjudication.get(a, 0)
                            for a in ADJUDICATIONS if by_adjudication.get(a, 0)},
        "not_an_action": not_actions,
        "real_actions_adjudicated": len(real_actions),
        "recoverable": len(recoverable),
        "recoverable_object_rate": (
            round(len(recoverable) / len(real_actions), 4)
            if real_actions else None),
        "not_an_action_rate": (
            round(not_actions / len(adjudicated), 4) if adjudicated else None),
        "note": ("recoverable_object_rate is over adjudicated REAL actions. "
                 "A sentence that is not an action at all is not a missing "
                 "buyer, and counting it as one would send every wave to "
                 "improve an extractor that was already right to refuse."),
    }
