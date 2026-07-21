"""Deterministic audience selection (T017) — CRM facts only.

The CRM stays authoritative: this module READS `CRMService` folds and
signals as of a fixed timestamp and records the selection as a marketing
artifact. It never writes `crm.jsonl`, never fuzzy-matches identities,
never infers protected attributes, and never treats missing data as
positive intent. Closed relationships (lost / disqualified / churned) are
excluded unless an explicit inclusion rule asks for them.
"""
from __future__ import annotations

from intent_engine.marketing.records import MarketingError

AUDIENCE_RULE_VERSION = "audience.v1"

_CLOSED_CUSTOMER_STATES = {"churned"}


def select_audience(crm_service, *, as_of: str,
                    include_relationship=None, include_opportunity=None,
                    include_customer=None, include_health=None,
                    include_conversion=None, include_closed: bool = False,
                    require_decision_link: bool = False,
                    sample_limit: int = 25) -> dict:
    """Deterministic for a fixed `as_of`. Every entity carries an explicit
    inclusion or exclusion reason; nothing is selected by inference."""
    rows = crm_service.store.read_all()
    by_entity = {}
    for row in rows:
        if row.occurred_at <= as_of:
            by_entity.setdefault(row.crm_entity_id, []).append(row)

    included, excluded = [], []
    for entity_id in sorted(by_entity):
        try:
            state = crm_service.get_current_state(entity_id)
        except Exception as exc:  # noqa: BLE001 - a broken entity is excluded, loudly
            excluded.append({"crm_entity_id": entity_id,
                             "reason": f"state unavailable: {type(exc).__name__}"})
            continue
        reason = _evaluate(crm_service, entity_id, state, as_of,
                           include_relationship, include_opportunity,
                           include_customer, include_health,
                           include_conversion, include_closed,
                           require_decision_link)
        if reason is None:
            included.append(entity_id)
        else:
            excluded.append({"crm_entity_id": entity_id, "reason": reason})

    return {
        "rule_version": AUDIENCE_RULE_VERSION,
        "as_of": as_of,
        "selection_criteria": {
            "relationship": sorted(include_relationship or []),
            "opportunity": sorted(include_opportunity or []),
            "customer": sorted(include_customer or []),
            "health": sorted(include_health or []),
            "conversion": sorted(include_conversion or []),
            "require_decision_link": require_decision_link,
        },
        "exclusion_criteria": {
            "closed_relationships_excluded": not include_closed,
            "missing_signal_data_excluded_when_filtered": True,
        },
        "entity_count": len(included),
        "sample_entity_ids": sorted(included)[:sample_limit],
        "excluded_count": len(excluded),
        "exclusion_sample": sorted(excluded,
                                   key=lambda e: e["crm_entity_id"])[:sample_limit],
    }


def _evaluate(crm, entity_id, state, as_of, rel, opp, cust, health,
              conversion, include_closed, require_decision_link):
    """Return None to include, or a string reason to exclude."""
    if not include_closed and state.relationship == "closed":
        return f"relationship closed ({state.closed_reason})"
    if not include_closed and state.customer in _CLOSED_CUSTOMER_STATES:
        return f"customer state {state.customer}"
    if rel and state.relationship not in rel:
        return f"relationship {state.relationship} not in criteria"
    if opp and state.opportunity not in opp:
        return f"opportunity {state.opportunity} not in criteria"
    if cust and state.customer not in cust:
        return f"customer {state.customer} not in criteria"
    if health:
        signal = crm.get_health(entity_id, now=as_of)
        if signal["category"] == "UNKNOWN":
            # missing data is never positive intent
            return "health UNKNOWN — missing data is not intent"
        if signal["category"] not in health:
            return f"health {signal['category']} not in criteria"
    if conversion:
        signal = crm.get_conversion_signal(entity_id)
        if signal["category"] == "UNAVAILABLE":
            return "conversion readiness UNAVAILABLE — not treated as intent"
        if signal["category"] not in conversion:
            return f"conversion {signal['category']} not in criteria"
    if require_decision_link and not crm.get_decisions(entity_id):
        return "no linked decision"
    return None


def assert_no_probability_language(text: str) -> None:
    """CRM conversion readiness is a readiness band, never a purchase
    probability — marketing copy may not translate it into one."""
    lowered = (text or "").lower()
    for phrase in ("% likely to buy", "probability of purchase",
                   "chance of closing", "likely to convert"):
        if phrase in lowered:
            raise MarketingError(
                f"conversion readiness cannot become a purchase probability: "
                f"{phrase!r}")
