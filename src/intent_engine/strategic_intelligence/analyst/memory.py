"""What changed since last time.

A founder opening this every morning does not want the same analysis again.
They want the delta: what is new, what held, what got weaker, and what they
were wrong about. Rebuilding strategy from scratch each run and presenting it
as fresh is how a daily product becomes a weekly one and then an ignored one.

The comparison is deterministic. It is a diff over two analyses, not a second
opinion about them -- asking a model "what changed?" invites it to narrate
differences that are really just rephrasings.
"""
from __future__ import annotations

import re

_CONF_RANK = {"low": 0, "moderate": 1, "high": 2}
_STOP = frozenset("""
the a an and or but if then that this these those with without into from for
to of in on at by as is are was were be been being it its their there what
which how why when where while more most less than not no can could will would
should may might must have has had do does did about over under between across
""".split())


def _key(text: str) -> frozenset:
    """A rough identity for a claim, so rewording is not reported as change."""
    words = re.findall(r"[a-z0-9][a-z0-9'-]+", (text or "").lower())
    return frozenset(w for w in words if len(w) >= 4 and w not in _STOP)


def _same(a: str, b: str, threshold=0.5) -> bool:
    ka, kb = _key(a), _key(b)
    if not ka or not kb:
        return False
    return len(ka & kb) / len(ka | kb) >= threshold


def _match(item, previous, field):
    for p in previous:
        if _same(item.get(field, ""), p.get(field, "")):
            return p
    return None


def compare(current, previous, *, evidence_count=None,
            previous_evidence_count=None) -> dict:
    """Diff two analyses for the same company.

    Returns what a founder should be told first: what is new, what held, which
    beliefs moved, and what contradicts last time's reading.
    """
    if not previous:
        return {"first_run": True,
                "summary": "First look at this company -- nothing to compare "
                           "against yet.",
                "new_decisions": [], "resolved_decisions": [],
                "assumptions_weakened": [], "assumptions_strengthened": [],
                "still_true": [], "surprises": [],
                "confidence_trend": "unknown", "evidence_added": 0}

    cur_d = current.get("decisions") or []
    prev_d = previous.get("decisions") or []

    new_decisions, carried = [], []
    for d in cur_d:
        match = _match(d, prev_d, "decision")
        if match is None:
            new_decisions.append(d.get("decision", ""))
        else:
            carried.append((d, match))

    # a decision that was on the list and no longer is has either been made,
    # been overtaken, or was never real. The product must not pretend to know
    # which -- it says it dropped off.
    dropped = [p.get("decision", "") for p in prev_d
               if _match(p, cur_d, "decision") is None]

    # urgency movement on decisions that persisted
    escalated = [d.get("decision", "") for d, p in carried
                 if _URGENCY_ORDER.get(d.get("urgency"), 0)
                 > _URGENCY_ORDER.get(p.get("urgency"), 0)]
    relaxed = [d.get("decision", "") for d, p in carried
               if _URGENCY_ORDER.get(d.get("urgency"), 0)
               < _URGENCY_ORDER.get(p.get("urgency"), 0)]

    cur_a = current.get("assumptions") or []
    prev_a = previous.get("assumptions") or []
    weakened, strengthened, still_true = [], [], []
    for a in cur_a:
        match = _match(a, prev_a, "assumption")
        if match is None:
            continue
        now = _CONF_RANK.get(a.get("confidence"), 1)
        before = _CONF_RANK.get(match.get("confidence"), 1)
        if now < before:
            weakened.append(a.get("assumption", ""))
        elif now > before:
            strengthened.append(a.get("assumption", ""))
        else:
            still_true.append(a.get("assumption", ""))

    # the insight itself changing is the biggest thing that can happen
    cur_ins = (current.get("the_insight") or {}).get("sentence", "")
    prev_ins = (previous.get("the_insight") or {}).get("sentence", "")
    insight_changed = bool(cur_ins and prev_ins and not _same(cur_ins,
                                                              prev_ins))

    surprises = []
    if insight_changed:
        surprises.append("The central reading changed. Last time: "
                         f"“{prev_ins}”")
    surprises += [f"Now more urgent: {d}" for d in escalated]
    surprises += [f"Belief weakened: {a}" for a in weakened]

    trend = "steady"
    if weakened and not strengthened:
        trend = "weakening"
    elif strengthened and not weakened:
        trend = "strengthening"
    elif weakened and strengthened:
        trend = "mixed"

    added = 0
    if evidence_count is not None and previous_evidence_count is not None:
        added = max(0, evidence_count - previous_evidence_count)

    return {
        "first_run": False,
        "summary": _summarise(insight_changed, new_decisions, escalated,
                              weakened, added),
        "insight_changed": insight_changed,
        "previous_insight": prev_ins,
        "new_decisions": new_decisions,
        "dropped_decisions": dropped,
        "escalated": escalated,
        "relaxed": relaxed,
        "assumptions_weakened": weakened,
        "assumptions_strengthened": strengthened,
        "still_true": still_true,
        "surprises": surprises,
        "confidence_trend": trend,
        "evidence_added": added,
    }


_URGENCY_ORDER = {"watch_only": 0, "this_year": 1, "this_quarter": 2,
                  "decide_now": 3}


def _summarise(insight_changed, new_decisions, escalated, weakened,
               added) -> str:
    """One line, and honest when the honest answer is 'nothing'."""
    parts = []
    if insight_changed:
        parts.append("the central reading changed")
    if new_decisions:
        parts.append(f"{len(new_decisions)} new decision"
                     f"{'s' if len(new_decisions) > 1 else ''}")
    if escalated:
        parts.append(f"{len(escalated)} became more urgent")
    if weakened:
        parts.append(f"{len(weakened)} belief"
                     f"{'s' if len(weakened) > 1 else ''} weakened")
    if not parts:
        # Saying "nothing changed" is the point of checking. A product that
        # cannot say it will invent change to justify the visit.
        return ("Nothing material changed since the last run"
                + (f"; {added} new source(s) retrieved." if added
                   else "."))
    return (", ".join(parts).capitalize()
            + (f"; {added} new source(s)." if added else "."))
