"""Executive reports — assembled from agents (T023).

Three mandatory profiles for T023: the morning brief, the weekly founder
review, and the board update draft. Each is a deterministic composition of
already-implemented sections; every line cites its source artifact. The
report architecture registers the other profiles (investor, hiring,
product, research, monthly) so they can be added later as thin
deterministic views — but they are not implemented in T023 and return an
honest "registered, not yet supported" result.

A board update is a DRAFT. It is assembled and returned; nothing is sent,
published, or delivered.
"""
from __future__ import annotations

from intent_engine.personal.briefing import assemble_brief
from intent_engine.personal.records import PersonalError

REPORT_VERSION = "personal_report.v1"

# The three implemented profiles, plus the registered-but-deferred ones.
IMPLEMENTED_PROFILES = ("morning_brief", "weekly_founder_review",
                        "board_update_draft")
DEFERRED_PROFILES = ("investor", "hiring", "product", "research", "monthly")
ALL_PROFILES = IMPLEMENTED_PROFILES + DEFERRED_PROFILES


def _weekly_founder_review(brief: dict) -> dict:
    """A thin deterministic view over the brief's sections — the week's
    decisions, risks, and investigations, grouped."""
    sections = brief["sections"]
    return {
        "profile": "weekly_founder_review",
        "as_of": brief["as_of"],
        "decisions_this_period": sections["executive_decisions"],
        "top_of_queue": sections["top_of_queue"],
        "risks": sections["risks"],
        "open_investigations": sections["recommended_investigations"],
        "gaps_named": brief["gaps_named"],
    }


def _board_update_draft(brief: dict) -> dict:
    """A board update, DRAFTED. Assembled from executive + product +
    research sections; every line cited; explicitly a draft."""
    sections = brief["sections"]
    return {
        "profile": "board_update_draft",
        "as_of": brief["as_of"],
        "disposition": "DRAFT — assembled for the founder to review; nothing "
                       "is sent",
        "executive_summary": sections["executive_decisions"],
        "research": sections["research_highlights"],
        "portfolio": sections["portfolio"],
        "risks_and_conflicts": sections["risks"],
        "open_questions": sections["open_questions"],
        "gaps_named": brief["gaps_named"],
    }


def assemble_report(profile: str, *, research_adapter, executive_adapter,
                    product_adapter, as_of: str, portfolio_id: str = None) -> dict:
    """Assemble one report profile. The three implemented profiles compose
    the same cited sections; a deferred profile returns honestly."""
    if profile not in ALL_PROFILES:
        raise PersonalError(f"unknown report profile: {profile!r} — one of "
                            f"{list(ALL_PROFILES)}")
    if profile in DEFERRED_PROFILES:
        return {"report_version": REPORT_VERSION, "profile": profile,
                "available": False,
                "reason": f"the {profile} profile is registered but not yet a "
                          "supported view in T023; it arrives when it is a "
                          "thin deterministic view over implemented sections",
                "as_of": as_of}

    brief = assemble_brief(research_adapter=research_adapter,
                           executive_adapter=executive_adapter,
                           product_adapter=product_adapter, as_of=as_of,
                           portfolio_id=portfolio_id)
    if profile == "morning_brief":
        body = {"profile": "morning_brief", **brief}
    elif profile == "weekly_founder_review":
        body = _weekly_founder_review(brief)
    else:
        body = _board_update_draft(brief)
    return {"report_version": REPORT_VERSION, "available": True, **body}
