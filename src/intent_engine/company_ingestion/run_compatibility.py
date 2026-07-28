"""Whether a stored analysis may still be shown as this product's answer.

THE PROBLEM THIS SOLVES
-----------------------
The brief carried the line "reusing a compatible earlier analysis" with
nothing behind the word compatible. Any stored result for a run was served
again, whatever had changed underneath it — so the fixes that stopped every
company being described as a commerce company, or that capped confidence
without an outside source, did not reach anyone whose analysis predated them.
They saw the old answer, stamped with today's date, and had no way to tell.

Worse in the other direction: a run that ended badly stayed ended. A reader
who got a weak report had a terminal result attached to their company, and the
product's own cache was what kept them there.

HOW IT WORKS
------------
Each stage that can change what a reader is shown declares a version. A stored
analysis records the versions it was produced under. On reuse the two are
compared component by component, and any difference makes the stored analysis
INCOMPATIBLE — not wrong, not deleted, just no longer this product's answer.

Deliberately strict. A "compatible enough" rule needs someone to decide which
changes are cosmetic, that judgement is made once and then inherited by every
future change, and the failure mode is silent: a reader is served a stale
answer that looks current. Re-running is cheap; being quietly wrong is not.
"""
from __future__ import annotations

RUN_COMPATIBILITY_VERSION = "ci_run_compat.v1"


def current_versions(app_version: str = "") -> dict:
    """Every version that can change what a reader sees.

    Imported lazily so this module stays importable from anywhere in the
    pipeline without dragging the synthesis layer in behind it.
    """
    from intent_engine.company_ingestion.readiness import READINESS_VERSION
    from intent_engine.company_ingestion.research_modes import (
        RESEARCH_MODE_VERSION,
    )
    from intent_engine.strategic_intelligence.brief import BRIEF_VERSION
    from intent_engine.strategic_intelligence.conversation import (
        CONVERSATION_VERSION,
    )
    from intent_engine.strategic_intelligence.slides import SLIDES_VERSION
    return {
        "app": app_version or "",
        "readiness": READINESS_VERSION,
        "research_mode": RESEARCH_MODE_VERSION,
        "brief": BRIEF_VERSION,
        "slides": SLIDES_VERSION,
        "conversation": CONVERSATION_VERSION,
        "compatibility": RUN_COMPATIBILITY_VERSION,
    }


def stamp(result: dict, *, app_version: str = "") -> dict:
    """Record the versions a freshly composed analysis was produced under."""
    out = dict(result or {})
    out["pipeline_versions"] = current_versions(app_version)
    return out


def assess(stored: dict, *, app_version: str = "") -> dict:
    """Whether `stored` may be served again, and what a reader should be told.

    Returns `reusable`, the component names that moved, and a plain-language
    reason — never an enum, because this decision is shown to a reader.
    """
    current = current_versions(app_version)
    recorded = (stored or {}).get("pipeline_versions")
    if not recorded:
        # Produced before versions were recorded at all. It cannot be shown to
        # agree with anything, so it does not get to claim it does.
        return {
            "reusable": False,
            "changed": ["unknown"],
            "reason": "This analysis was produced before the current version "
                      "of the product and cannot be checked against it.",
            "compatibility_version": RUN_COMPATIBILITY_VERSION,
        }
    changed = sorted(name for name, version in current.items()
                     if name != "app" and recorded.get(name) != version)
    app_changed = recorded.get("app") != current.get("app")
    if not changed and not app_changed:
        return {
            "reusable": True, "changed": [],
            "reason": "This analysis was produced by the current version of "
                      "the product.",
            "compatibility_version": RUN_COMPATIBILITY_VERSION,
        }
    if changed:
        reason = ("The way this product gathers evidence and writes its "
                  "briefing has changed since this analysis was produced, so "
                  "it is being run again.")
    else:
        reason = ("The product has been updated since this analysis was "
                  "produced, so it is being run again.")
    return {
        "reusable": False,
        "changed": changed or ["app"],
        "reason": reason,
        "compatibility_version": RUN_COMPATIBILITY_VERSION,
    }
