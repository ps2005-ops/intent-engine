"""Ranking decisions, and the daily view assembled from them.

Ten equally-weighted items is the same as no guidance at all -- the reader
does the prioritising, which is the work they came here to have done. So
ranking is deterministic and lives here rather than being asked of the model:
a model asked to order its own output will order it by how interesting it
found each item, and interest is not leverage.

The ordering is a judgement and it is written down so it can be argued with:

    leverage = impact x urgency x cost-of-delay, discounted by how confident
               we are, and weighted UP for one-way doors

Reversibility earning weight is the least obvious term and the most useful.
An easily reversed call does not deserve a founder's morning even when it is
urgent -- they can simply make it and change it later. A one-way door deserves
attention out of proportion to its urgency, because attention is the only
thing that can still be spent on it.
"""
from __future__ import annotations

_IMPACT_WEIGHT = {"high": 3.0, "medium": 1.8, "low": 1.0}
_URGENCY_WEIGHT = {"decide_now": 3.0, "this_quarter": 2.2,
                   "this_year": 1.4, "watch_only": 0.6}
# a one-way door is worth thinking about now even if it is not urgent
_REVERSIBILITY_WEIGHT = {"one_way_door": 1.6, "costly_to_reverse": 1.25,
                         "easily_reversible": 0.85}
# low confidence does not mean ignore -- it means the cheapest next move is to
# learn, not to act. It discounts leverage; it does not zero it.
_CONFIDENCE_WEIGHT = {"high": 1.15, "moderate": 1.0, "low": 0.8}
# a verdict of ignore should not float to the top on impact alone
_VERDICT_WEIGHT = {"do_now": 1.2, "research": 1.0, "monitor": 0.9,
                   "wait": 0.75, "ignore": 0.3}

#: phrases that mean the recommendation was never actually made
NON_ANSWERS = ("it depends", "further analysis is needed", "time will tell",
               "remains to be seen", "hard to say", "too early to tell")


def leverage(decision) -> float:
    """How much of a founder's attention this decision has earned."""
    d = decision or {}
    score = (_IMPACT_WEIGHT.get(d.get("business_impact"), 1.0)
             * _URGENCY_WEIGHT.get(d.get("urgency"), 1.0)
             * _REVERSIBILITY_WEIGHT.get(d.get("reversibility"), 1.0)
             * _CONFIDENCE_WEIGHT.get(d.get("confidence"), 1.0)
             * _VERDICT_WEIGHT.get(d.get("verdict"), 1.0))
    # a decision that names what it costs to wait has demonstrated the cost is
    # real; one that cannot is softer by construction
    if not (d.get("cost_of_waiting") or "").strip():
        score *= 0.85
    return round(score, 3)


def rank_decisions(decisions) -> list:
    """Highest-leverage first. Stable for equal scores, so a re-run of the
    same evidence presents the same order."""
    scored = [(leverage(d), i, d) for i, d in enumerate(decisions or [])]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [dict(d, leverage=s, rank=n + 1)
            for n, (s, _, d) in enumerate(scored)]


def todays_decision(decisions):
    """The single decision that has earned today, or None.

    Deliberately returns nothing when the top-ranked item is one a founder
    should not spend today on. "Nothing today" is a real and useful answer;
    manufacturing a daily action is how a product teaches people to ignore it.
    """
    ranked = rank_decisions(decisions)
    if not ranked:
        return None
    top = ranked[0]
    if top.get("verdict") in ("ignore", "wait"):
        return None
    return top


def weakest_assumption(assumptions):
    """The load-bearing belief least supported by evidence -- the thing most
    worth being wrong about."""
    order = {"low": 0, "moderate": 1, "high": 2}
    load = {"high": 0, "medium": 1, "low": 2}
    ranked = sorted(
        (a for a in (assumptions or []) if a.get("assumption")),
        key=lambda a: (order.get(a.get("confidence"), 1),
                       load.get(a.get("how_load_bearing"), 1)))
    return ranked[0] if ranked else None


def daily_view(analysis, *, memory=None) -> dict:
    """One screen. What changed, what deserves today, what can be ignored.

    `memory` is the output of `strategic_memory.compare` when a previous run
    exists; without it the view is honest about being a first look rather than
    implying nothing changed.
    """
    a = analysis or {}
    decisions = a.get("decisions") or []
    ranked = rank_decisions(decisions)
    comp = a.get("competitive") or {}
    scen = a.get("scenarios") or {}
    blind = a.get("blind_spots") or {}
    weakest = weakest_assumption(a.get("assumptions"))
    today = todays_decision(decisions)

    ignorable = [d for d in ranked if d.get("verdict") in ("ignore", "wait")]

    return {
        "headline": (a.get("the_insight") or {}).get("sentence", ""),
        "what_changed": (memory or {}).get("summary")
                        or "First look at this company -- nothing to compare "
                           "against yet.",
        "biggest_opportunity": scen.get("upside_case", ""),
        "biggest_threat": scen.get("downside_case", ""),
        "wild_card": scen.get("wild_card", ""),
        "most_uncertain_assumption": (weakest or {}).get("assumption", ""),
        "what_would_break_it": (weakest or {}).get("what_would_break_it", ""),
        "competitor_to_watch": comp.get("who_is_forcing_the_change", ""),
        "todays_decision": today,
        "safe_to_ignore": [d.get("decision", "") for d in ignorable],
        "nobody_is_discussing": blind.get("almost_nobody_is_discussing", ""),
        "leading_indicators": list(scen.get("leading_indicators") or [])[:3],
        "confidence_trend": (memory or {}).get("confidence_trend", "unknown"),
        "evidence_added": (memory or {}).get("evidence_added", 0),
        "decisions_ranked": ranked,
    }
