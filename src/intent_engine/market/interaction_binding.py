"""Who acted, who answered, and what we are not entitled to say about why.

THE FOURTH INSTANCE
-------------------
`strategic_interaction.py` is complete and unusually strict. It refuses an
inferred objective that arrives without an alternative explanation, refuses a
response without its own date, and refuses an interaction with no evidence at
all. `learning_cycle.run` accepts `interactions=` and summarises them.

`strategic_interaction` appears zero times in `steps.py`. Nothing has ever
been passed, so `interactions: 0` has been reported since the subsystem was
built — the fourth time in this mission that a correct module turned out to be
unwired rather than unfinished.

WHAT COUNTS AS AN INTERACTION HERE
----------------------------------
Two companies in the same industry, one acting and the other making a
comparable move afterwards, inside a window short enough that the second could
plausibly be a response.

That is a weak claim and it is recorded as one. The engine sees two public
disclosures; it does not see a boardroom. So every record produced here:

  - names the alternative explanations, which are always live and always
    include "both were responding to the same market conditions";
  - carries `inferred_objective` empty unless the evidence names a motive,
    because `record` would otherwise force a fabricated alternative alongside
    a fabricated motive;
  - keeps `payoff_change` UNKNOWN, because nothing observed here measures a
    payoff.

WHAT IS DELIBERATELY NOT BUILT
------------------------------
A causal claim. An interaction is a SEQUENCE, and the module's own docstring
is right that sequence is not response. The value is that a preregisterable
question now exists — did B answer A? — where before there was no record that
the pair had moved at all.
"""
from __future__ import annotations

import collections
import datetime as _dt
from typing import Dict, List, Optional, Sequence, Tuple

from . import micro_evidence as ME
from . import strategic_interaction as SI

BINDING_VERSION = "interaction_binding.v1"

#: Beyond this many days apart, a second move is its own event rather than an
#: answer to the first. Deliberately short: a long window would let this
#: module pair up anything that happened in the same quarter.
MAX_RESPONSE_LAG_DAYS = 45

#: Event types where one company acting plausibly provokes another. Excludes
#: earnings results, which every company in an industry reports on its own
#: calendar -- pairing those would manufacture an "interaction" out of the
#: reporting season.
RESPONSIVE_TYPES = frozenset({
    ME.PRICING_SIGNAL, ME.PRICE_CHANGE, ME.PRODUCT_LAUNCH,
    ME.CAPEX_SIGNAL, ME.MA_ACTIVITY, ME.PARTNERSHIP,
    ME.CONTRACT_AWARD, ME.COMPETITOR_ACTION,
})

ALWAYS_ALIVE = (
    "both companies were responding to the same market conditions, and "
    "neither move answered the other",
    "the second move was already planned before the first became public",
    "the two moves are unrelated and the ordering is coincidence",
)


def _date(text: str) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def bind(evidence: Sequence[ME.MicroEvidence], *,
         industry_of: Optional[Dict[str, str]] = None,
         competitors_of: Optional[Dict[str, frozenset]] = None
         ) -> Tuple[Tuple[SI.StrategicInteraction, ...], Dict[str, int]]:
    """Pair actions with plausible later responses from a NAMED RIVAL.

    WHY THIS REFUSES MORE THAN IT ACCEPTS, AND WHY THAT IS THE RESULT
    ----------------------------------------------------------------
    The first version matched on shared SECTOR and produced three records, all
    of them nonsense. It paired ASML's semiconductor-equipment partnership with
    Infosys's IT-services partnership because both are "Technology" and both
    are PARTNERSHIP events, then emitted the same pair in both directions
    because each fact carried several evidence ids.

    Two things were wrong and both are structural:

    1. **Sector is not rivalry.** ASML and Infosys do not compete for a
       customer, so neither can be answering the other. A response needs a
       counterparty that had a reason to respond, and only a named competitor
       relationship establishes one.
    2. **`observed_at` is the INGESTION date, not the event date.** The ASML
       item says "May 16, 2026" in its own text and carries `observed_at`
       2026-08-05. Ordering on it measures the order the sweep happened to
       read things, which is not evidence about who moved first.

    So `competitors_of` is required. Without a named-rival relationship this
    returns nothing, and the honest state of the corpus is that no defensible
    interaction exists yet — the world model has no actor-to-actor edges to
    read, which is a measured finding rather than a gap in this module.
    """
    refused: Dict[str, int] = collections.Counter()
    if not industry_of:
        refused["no_industry_map"] += 1
        return (), dict(refused)
    if not competitors_of:
        # Refusing here is the point. Falling back to sector matching is what
        # produced the fabricated records this guard exists to prevent.
        refused["no_competitor_relationships_available"] += 1
        return (), dict(refused)

    usable: List[ME.MicroEvidence] = []
    for item in evidence:
        if item.evidence_type not in RESPONSIVE_TYPES:
            refused["action_does_not_provoke_a_response"] += 1
            continue
        if not industry_of.get((item.subject_company or "").lower()):
            refused["subject_has_no_industry"] += 1
            continue
        if _date(item.observed_at) is None:
            refused["undated"] += 1
            continue
        usable.append(item)

    usable.sort(key=lambda e: (e.observed_at, e.evidence_id))
    out: List[SI.StrategicInteraction] = []
    paired: set = set()

    for i, first in enumerate(usable):
        first_at = _date(first.observed_at)
        industry = industry_of[(first.subject_company or "").lower()]
        for second in usable[i + 1:]:
            if second.subject_company == first.subject_company:
                continue
            if industry_of.get((second.subject_company or "").lower()) != \
                    industry:
                continue
            # A NAMED rival, not merely a sector neighbour.
            rivals = competitors_of.get(
                (first.subject_company or "").lower(), frozenset())
            if (second.subject_company or "").lower() not in rivals:
                refused["counterparty_is_not_a_named_competitor"] += 1
                continue
            second_at = _date(second.observed_at)
            if second_at is None or second_at < first_at:
                continue
            if (second_at - first_at).days > MAX_RESPONSE_LAG_DAYS:
                break          # sorted, so everything later is further away
            if second.evidence_type != first.evidence_type:
                # A comparable move. A different KIND of action is a different
                # decision, not an answer to this one.
                continue
            # One pairing per company pair per action, in one direction.
            # Without this the same two facts produced A->B and B->A and
            # each duplicate evidence id repeated the pair again.
            key = tuple(sorted((first.subject_company,
                                second.subject_company))) + (
                first.evidence_type,)
            if key in paired:
                refused["already_paired"] += 1
                continue
            paired.add(key)
            try:
                out.append(SI.record(
                    focal_actor=first.subject_company,
                    responding_actor=second.subject_company,
                    initial_action=f"{first.evidence_type}: "
                                   f"{first.fact[:150]}",
                    at=first.observed_at,
                    response=f"{second.evidence_type}: {second.fact[:150]}",
                    response_at=second.observed_at,
                    # No payoff is observed here, and UNKNOWN is the only
                    # honest value. Guessing one would put a number on a
                    # boardroom nobody saw.
                    payoff_change=SI.UNKNOWN,
                    market_context=f"both operate in {industry}",
                    alternative_explanations=ALWAYS_ALIVE,
                    evidence_ids=(first.evidence_id, second.evidence_id)))
            except SI.InteractionRejected:
                refused["rejected_by_contract"] += 1
    return tuple(out), dict(refused)


def summarise(interactions: Sequence[SI.StrategicInteraction],
              refused: Dict[str, int]) -> dict:
    return {
        "contract": BINDING_VERSION,
        "interactions": len(interactions),
        "actors": len({i.focal_actor for i in interactions}
                      | {i.responding_actor for i in interactions}),
        "with_response": sum(1 for i in interactions if i.response),
        "max_response_lag_days": MAX_RESPONSE_LAG_DAYS,
        "refused": dict(sorted(refused.items())),
        "note": ("a pairing is a SEQUENCE, not a response; every record keeps "
                 "the same-market-conditions explanation alive and asserts no "
                 "motive"),
    }
