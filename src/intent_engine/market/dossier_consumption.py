"""Did anything the market learned actually reach a founder's reasoning?

WHY THIS EXISTS
---------------
The market engine could say "I published 22 strategic dossiers" and could not
say whether one of them was ever read. `founder_utility.strategic_dossiers_
consumed` has reported `UNMEASURABLE` since learning health was built, which
was honest and useless: an engine that cannot tell whether its output is used
is optimising in the dark, and every learning metric upstream of that is a
claim about effort rather than value.

WHY THE ARCHITECTURE IS A FILE
------------------------------
The two systems are genuinely disjoint. The market package does not exist on
the founder branch and `external_intel` does not exist here; there is no
import path in either direction, deliberately, because a founder surface that
could reach into market internals would eventually render one. The only thing
they share is a directory: the market cycle writes
`reports/market/strategic/<company>.json` and the founder run reads it.

So the acknowledgement travels the same way, in the opposite direction, as an
append-only ledger beside the dossiers. No second event bus, no second graph,
no second dossier truth, and no HTTP round trip that would only work when both
services happen to be reachable.

The schema below is duplicated on the founder side rather than imported. That
duplication is a known and accepted cost -- the strategic allowlist is already
carried the same way for the same reason -- and `SCHEMA` is the thing both
copies must agree on.

WHAT COUNTS AS CONSUMPTION
--------------------------
Not an HTTP 200. Not a file that was opened. Not a dossier that was validated
and then ignored.

The stages below are ordered, and utility begins at `USED_IN_REASONING` --
the point where the dossier's content becomes reasoning material rather than
a file on disk. On the founder side that is one specific branch: the one that
turns strategic content into analysis blocks. A dossier that is received,
validated, eligible and then not selected has been handled, not used, and
this module reports the difference rather than averaging over it.
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import pathlib
from typing import Dict, List, Optional, Sequence, Tuple

SCHEMA = "dossier_consumption.v1"

#: Beside the dossiers it acknowledges, so the two move together when a root
#: is copied and neither can be found without the other.
LEDGER_PATH = "reports/market/dossier_consumption.jsonl"

# --- the stages, in order --------------------------------------------------
PUBLISHED = "PUBLISHED"
RECEIVED = "RECEIVED"
VALIDATED = "VALIDATED"
ELIGIBLE = "ELIGIBLE"
SELECTED = "SELECTED"
PROJECTED = "PROJECTED"
USED_IN_REASONING = "USED_IN_REASONING"
RENDERED_TO_FOUNDER = "RENDERED_TO_FOUNDER"
#: The dossier constrained something a founder acts on. The hardest stage
#: to reach, and the only one that answers "was this learning worth
#: having". Nothing emits it yet; it is defined so the ladder has a top.
DECISION_RELEVANT = "DECISION_RELEVANT"

STAGES: Tuple[str, ...] = (
    PUBLISHED, RECEIVED, VALIDATED, ELIGIBLE, SELECTED, PROJECTED,
    USED_IN_REASONING, RENDERED_TO_FOUNDER, DECISION_RELEVANT,
)
_ORDER = {name: i for i, name in enumerate(STAGES)}

#: Below this, the market learned something and it changed nothing.
UTILITY_BEGINS_AT = USED_IN_REASONING

# --- founder utility status ------------------------------------------------
UNMEASURABLE = "UNMEASURABLE"
NO_ELIGIBLE_DOSSIERS = "NO_ELIGIBLE_DOSSIERS"
PUBLISHED_NOT_CONSUMED = "PUBLISHED_NOT_CONSUMED"
CONSUMED_NO_VISIBLE_EFFECT = "CONSUMED_NO_VISIBLE_EFFECT"
CONSUMED_VISIBLE_EFFECT = "CONSUMED_VISIBLE_EFFECT"
DEGRADED = "DEGRADED"

UTILITY_STATUSES = frozenset({
    UNMEASURABLE, NO_ELIGIBLE_DOSSIERS, PUBLISHED_NOT_CONSUMED,
    CONSUMED_NO_VISIBLE_EFFECT, CONSUMED_VISIBLE_EFFECT, DEGRADED})

# --- refusal codes ---------------------------------------------------------
STALE_DOSSIER = "STALE_DOSSIER"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
SCHEMA_REJECTED = "SCHEMA_REJECTED"
NO_MATERIAL = "NO_MATERIAL"
ANALYSIS_PREDATES_DOSSIER = "ANALYSIS_PREDATES_DOSSIER"

REFUSAL_CODES = frozenset({
    STALE_DOSSIER, IDENTITY_MISMATCH, SCHEMA_REJECTED, NO_MATERIAL,
    ANALYSIS_PREDATES_DOSSIER})

#: A consumption rate over one or two analyses is not a rate.
MIN_EVENTS_FOR_RATE = 3


def _parse(value: object) -> Optional[_dt.datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def reached(record: dict, stage: str) -> bool:
    """Whether an acknowledgement got at least as far as `stage`."""
    got = _ORDER.get(str(record.get("stage") or ""))
    want = _ORDER.get(stage)
    return got is not None and want is not None and got >= want


def read(root, path: str = LEDGER_PATH) -> Tuple[dict, ...]:
    """Every acknowledgement on record. A corrupt line is skipped, not fatal.

    Returns an empty tuple when the ledger does not exist. That is NOT the
    same as zero consumption and callers must not treat it as such -- see
    `summarise`, which distinguishes the two.
    """
    target = pathlib.Path(root) / path
    if not target.exists():
        return ()
    out: List[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == SCHEMA:
            out.append(row)
    return tuple(out)


def record(root, *, dossier_id: str, company_id: str, stage: str,
           dossier_revision: str = "", market_runtime_sha: str = "",
           market_cycle_id: str = "", published_at: str = "",
           founder_received_at: str = "", founder_analysis_id: str = "",
           analysis_started_at: str = "", analysis_as_of: str = "",
           graph_projection_id: str = "", strategic_content_used: int = 0,
           founder_surface_rendered: str = "", refusal_code: str = "",
           refusal_reason: str = "", consumer_version: str = "",
           consumed_at: str = "", path: str = LEDGER_PATH) -> bool:
    """Append one acknowledgement. Idempotent on (analysis, dossier, stage).

    Idempotent because a founder run that is retried, or a page that is
    refreshed, must not inflate consumption. The identity is the analysis and
    the dossier revision, not the wall clock -- re-rendering the same analysis
    is the same consumption event, and counting it twice would make a reload
    button look like founder utility.
    """
    if stage not in _ORDER:
        raise ValueError(f"unknown consumption stage {stage!r}")
    if refusal_code and refusal_code not in REFUSAL_CODES:
        raise ValueError(f"unknown refusal code {refusal_code!r}")

    event_id = "|".join((founder_analysis_id or "-", dossier_id or "-",
                         dossier_revision or "-", stage))
    existing = read(root, path)
    if any(r.get("consumption_event_id") == event_id for r in existing):
        return False

    row = {
        "schema": SCHEMA,
        "consumption_event_id": event_id,
        "dossier_id": dossier_id,
        "dossier_revision": dossier_revision,
        "company_id": company_id,
        "market_runtime_sha": market_runtime_sha,
        "market_cycle_id": market_cycle_id,
        "published_at": published_at,
        "founder_received_at": founder_received_at,
        "founder_analysis_id": founder_analysis_id,
        "analysis_started_at": analysis_started_at,
        "analysis_as_of": analysis_as_of,
        "stage": stage,
        "graph_projection_id": graph_projection_id,
        "strategic_content_used": int(strategic_content_used or 0),
        "founder_surface_rendered": founder_surface_rendered,
        "consumed_at": consumed_at or _dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds"),
        "refusal_code": refusal_code,
        "refusal_reason": refusal_reason[:300],
        "consumer_version": consumer_version,
    }
    target = pathlib.Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return True


def _latest_per_analysis(events: Sequence[dict]) -> Dict[str, dict]:
    """The furthest stage each (analysis, dossier) pair reached.

    An analysis emits several rows as it advances, so counting rows would
    count one consumption up to eight times. The unit is the pairing, and its
    value is how far it got.
    """
    best: Dict[str, dict] = {}
    for row in events:
        key = f"{row.get('founder_analysis_id')}|{row.get('dossier_id')}"
        current = best.get(key)
        if current is None or _ORDER.get(str(row.get("stage")), -1) > \
                _ORDER.get(str(current.get("stage")), -1):
            best[key] = row
    return best


def summarise(root, *, published: int = 0,
              path: str = LEDGER_PATH) -> Dict[str, object]:
    """Founder utility, or an honest statement that it is not observable.

    `published` is what the market side knows it wrote. Everything else comes
    from acknowledgements the founder side chose to emit, so an absent ledger
    means "not observable from here", never "nobody used it".
    """
    events = read(root, path)
    if not events:
        return {
            "schema": SCHEMA,
            "dossiers_published": published,
            "dossiers_received": UNMEASURABLE,
            "dossiers_used": UNMEASURABLE,
            "consumption_rate": UNMEASURABLE,
            "founder_utility_status": UNMEASURABLE,
            "because": (
                "no consumption acknowledgement has reached this root. The "
                "founder service writes them beside the dossiers it reads, so "
                "an empty ledger means the two systems are not sharing a "
                "root -- it does not mean the dossiers went unused"),
        }

    pairs = _latest_per_analysis(events)
    counts = collections.Counter()
    for row in pairs.values():
        for stage in STAGES:
            if reached(row, stage):
                counts[stage] += 1

    refusals = collections.Counter(
        r.get("refusal_code") for r in events if r.get("refusal_code"))

    used = counts[USED_IN_REASONING]
    rendered = counts[RENDERED_TO_FOUNDER]
    received = counts[RECEIVED]

    # An analysis that started before the dossier was published cannot have
    # consumed it, whatever stage it claims to have reached.
    anachronistic = 0
    for row in pairs.values():
        started = _parse(row.get("analysis_started_at"))
        published_at = _parse(row.get("published_at"))
        if started and published_at and started < published_at:
            anachronistic += 1

    lag = []
    for row in pairs.values():
        if not reached(row, USED_IN_REASONING):
            continue
        start, end = _parse(row.get("published_at")), _parse(
            row.get("consumed_at"))
        if start and end and end >= start:
            lag.append((end - start).total_seconds())

    if len(pairs) < MIN_EVENTS_FOR_RATE:
        rate: object = UNMEASURABLE
    else:
        rate = used / len(pairs)

    if not received:
        status = PUBLISHED_NOT_CONSUMED
    elif not counts[ELIGIBLE]:
        status = NO_ELIGIBLE_DOSSIERS
    elif not used:
        status = PUBLISHED_NOT_CONSUMED
    elif rendered:
        status = CONSUMED_VISIBLE_EFFECT
    else:
        status = CONSUMED_NO_VISIBLE_EFFECT
    if anachronistic and anachronistic == used:
        # Everything that claims use is older than the thing it used.
        status = DEGRADED

    return {
        "schema": SCHEMA,
        "dossiers_published": published,
        "dossiers_received": received,
        "dossiers_validated": counts[VALIDATED],
        "dossiers_eligible": counts[ELIGIBLE],
        "dossiers_selected": counts[SELECTED],
        "dossiers_projected": counts[PROJECTED],
        "dossiers_used": used,
        "dossiers_rendered": rendered,
        "dossiers_decision_relevant": counts[DECISION_RELEVANT],
        "consumption_rate": rate,
        "time_to_consumption_seconds": (
            sorted(lag)[len(lag) // 2] if lag else UNMEASURABLE),
        "stale_dossier_refusals": refusals.get(STALE_DOSSIER, 0),
        "identity_refusals": refusals.get(IDENTITY_MISMATCH, 0),
        "schema_refusals": refusals.get(SCHEMA_REJECTED, 0),
        "analysis_predates_dossier": anachronistic,
        "analyses_seen": len(pairs),
        "founder_utility_status": status,
    }
