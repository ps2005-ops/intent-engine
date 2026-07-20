"""Deterministic, versioned customer signals (T014). Computed by code
from explicit facts — never asked of a model, never stored as source of
truth. Missing data yields UNKNOWN / UNAVAILABLE, never optimism. Every
result carries its rule version and visible reasons so a historical
output stays explainable after the rules evolve.
"""
from __future__ import annotations

from datetime import datetime, timezone

HEALTH_RULE_VERSION = 1
CONVERSION_RULE_VERSION = 1

_HEALTHY_WINDOW_DAYS = 30      # boundary tested: day 30 HEALTHY, day 31 not
_POSITIVE_EVENTS = {"crm.replied", "crm.meeting_booked"}
_CONTACT_EVENTS = {"crm.contacted", "crm.replied", "crm.meeting_booked"}


def _days_between(earlier_iso: str, later_iso: str) -> float:
    a = datetime.fromisoformat(earlier_iso)
    b = datetime.fromisoformat(later_iso)
    return (b - a).total_seconds() / 86400.0


def health_signal(events, state, now: str = None) -> dict:
    """HEALTHY | WATCH | AT_RISK | UNKNOWN, with reasons. Ordered rules:

    1. churned                       -> AT_RISK (terminal; stated, not hidden)
    2. explicit at-risk fact         -> AT_RISK
    3. zero contact facts            -> UNKNOWN (no data is NOT healthy)
    4. positive engagement within 30 days (occurred_at) -> HEALTHY
    5. otherwise                     -> WATCH (stale or unanswered)
    """
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = {"rule_version": HEALTH_RULE_VERSION, "reasons": []}
    if state.customer == "churned":
        result.update(category="AT_RISK")
        result["reasons"].append("customer churned (terminal fact)")
        return result
    if state.customer == "at_risk":
        result.update(category="AT_RISK")
        result["reasons"].append("explicit customer_at_risk fact is current")
        return result
    contacts = [ev for ev in events if ev.event_type in _CONTACT_EVENTS]
    if not contacts:
        result.update(category="UNKNOWN")
        result["reasons"].append(
            "no contact facts recorded — missing data is unknown, not healthy")
        return result
    last_contact = max(ev.occurred_at for ev in contacts)
    days = _days_between(last_contact, now)
    has_positive = any(ev.event_type in _POSITIVE_EVENTS for ev in contacts)
    if days <= _HEALTHY_WINDOW_DAYS and (has_positive
                                         or state.customer == "active"):
        result.update(category="HEALTHY")
        result["reasons"].append(
            f"positive engagement {days:.0f} day(s) ago (within "
            f"{_HEALTHY_WINDOW_DAYS}-day window)")
        return result
    result.update(category="WATCH")
    if days > _HEALTHY_WINDOW_DAYS:
        result["reasons"].append(
            f"last contact {days:.0f} day(s) ago (> {_HEALTHY_WINDOW_DAYS})")
    if not has_positive:
        result["reasons"].append("outreach without a recorded reply/meeting")
    return result


def conversion_signal(events, state) -> dict:
    """LOW | MEDIUM | HIGH | UNAVAILABLE, with reasons. Readiness, NOT a
    probability — no percentage, no accuracy claim, ever. Ordered rules:

    1. disqualified / lost / churned  -> LOW (dominates everything)
    2. won or existing customer       -> HIGH ("already converted")
    3. meeting, proposal, or open opportunity -> HIGH
    4. qualified or replied           -> MEDIUM
    5. contacted only                 -> LOW
    6. nothing relevant               -> UNAVAILABLE
    """
    result = {"rule_version": CONVERSION_RULE_VERSION, "reasons": []}
    if state.closed_reason in ("disqualified", "lost", "churned"):
        result.update(category="LOW")
        result["reasons"].append(
            f"terminal fact dominates: {state.closed_reason}")
        return result
    if state.opportunity == "won" or state.customer in ("active", "at_risk"):
        result.update(category="HIGH")
        result["reasons"].append("already converted (won / customer)")
        return result
    types = {ev.event_type for ev in events}
    if state.opportunity in ("opportunity", "proposal") \
            or "crm.meeting_booked" in types:
        result.update(category="HIGH")
        result["reasons"].append(
            "open opportunity / proposal / meeting on record")
        return result
    if state.opportunity == "qualified" or "crm.replied" in types:
        result.update(category="MEDIUM")
        result["reasons"].append("qualified or replied")
        return result
    if "crm.contacted" in types:
        result.update(category="LOW")
        result["reasons"].append("contacted; no response facts yet")
        return result
    result.update(category="UNAVAILABLE")
    result["reasons"].append("no relevant relationship facts recorded")
    return result
