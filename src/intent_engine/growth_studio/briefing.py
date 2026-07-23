"""V2.0 daily briefing contract — structured, evidence-carrying, deterministic.

Every statement carries evidence refs, a timeframe, and a confidence
band. The brief is composed from reads; it invents nothing and calls no
model in deterministic operation."""
from __future__ import annotations

from intent_engine.growth_studio.records import StudioError

BRIEF_SECTIONS = (
    "what_changed", "what_performed", "what_did_not_perform",
    "what_remains_inconclusive", "customer_audience_signals",
    "product_friction_signals", "competitor_category_signals",
    "experiments_awaiting_review", "measurements_due",
    "learnings_proposed", "decisions_needed",
)

CONFIDENCE_BANDS = ("HIGH", "MODERATE", "LOW", "INSUFFICIENT_EVIDENCE")


def statement(text: str, *, evidence: list, timeframe: str,
              confidence: str) -> dict:
    if not text or not isinstance(text, str):
        raise StudioError("briefing statement needs text")
    if confidence not in CONFIDENCE_BANDS:
        raise StudioError(f"confidence must be one of {CONFIDENCE_BANDS}")
    if not isinstance(evidence, list):
        raise StudioError("evidence must be a list of refs")
    if confidence != "INSUFFICIENT_EVIDENCE" and not evidence:
        raise StudioError("a briefing statement above "
                          "INSUFFICIENT_EVIDENCE requires evidence refs")
    if not timeframe:
        raise StudioError("briefing statement needs a timeframe")
    return {"text": text, "evidence": evidence, "timeframe": timeframe,
            "confidence": confidence}


def compose_brief(*, as_of_date: str, sections: dict) -> dict:
    unknown = set(sections) - set(BRIEF_SECTIONS)
    if unknown:
        raise StudioError(f"unknown briefing sections: {sorted(unknown)}")
    brief = {"as_of_date": as_of_date, "sections": {}}
    for name in BRIEF_SECTIONS:
        entries = sections.get(name, [])
        for entry in entries:
            for required in ("text", "evidence", "timeframe", "confidence"):
                if required not in entry:
                    raise StudioError(
                        f"briefing section {name!r} has a statement missing "
                        f"{required!r} — every statement carries evidence, "
                        f"timeframe, and confidence")
        brief["sections"][name] = list(entries)
    return brief
