"""The market engine's learning report, read on the founder side.

WHY IT CROSSES AS A FILE AND NOT A FIELD
----------------------------------------
Every other market artefact reaches this product per company, through
`demo_snapshots/<company>.json`. Learning does not fit that shape: a
learning session is GLOBAL -- one cycle reads many companies and the
resulting knowledge effects, contradictions and reconciliations belong to
the engine, not to any one subject. `strategic_publish` accordingly never
passes `learning_summary` to the per-company snapshot, and it serialises as
UNAVAILABLE in all 26.

That absence was read as "learning is not published". It is published, as
`reports/learning/{daily,weekly,monthly}/*.json` under contract
`market_learning_report.v1`, and it already carries what a reader needs:
what changed, what was merely re-observed, the current bottleneck and the
next research priority.

WHAT THIS MODULE MAY NOT DO
---------------------------
Compute a learning metric. Every number here is read from the report the
market engine wrote; there is no second definition of "novel evidence" on
this side, because two definitions of one metric is how a dashboard starts
disagreeing with the engine it describes.

It also may not fill a gap. The report itself marks
`independent_evidence_rows` UNAVAILABLE with a note explaining that
independence is produced on the founder branch -- that honesty survives to
the reader rather than being quietly completed from founder data.
"""
from __future__ import annotations

import json
import pathlib
from typing import Optional, Tuple

CONTRACT = "market_learning_report.v1"

#: Where the crossed reports live, relative to the market snapshot root.
#: The same root the dossier bridge uses, so one env var configures both.
DIRNAME = "reports/learning"

PERIODS = ("day", "week", "month")

#: Directory per period, as the market engine writes them.
_DIRS = {"day": "daily", "week": "weekly", "month": "monthly"}

# --- states, so an empty page is never mistaken for a quiet engine ---------

AVAILABLE = "LEARNING_AVAILABLE"
#: The root is configured and holds no report for this period. The engine
#: may simply not have run a cycle of that length yet.
NOT_PUBLISHED = "LEARNING_NOT_PUBLISHED"
#: No snapshot root is configured at all -- a deployment fact, not a
#: statement about learning.
NOT_CONFIGURED = "LEARNING_ROOT_NOT_CONFIGURED"
#: A file exists and does not parse, or is not this contract.
UNREADABLE = "LEARNING_REPORT_UNREADABLE"


class LearningReport:
    """One period's canonical learning report, or a stated absence."""

    __slots__ = ("state", "period", "payload", "path", "reason")

    def __init__(self, state, *, period="", payload=None, path="", reason=""):
        self.state = state
        self.period = period
        self.payload = payload or {}
        self.path = path
        self.reason = reason

    @property
    def available(self) -> bool:
        return self.state == AVAILABLE

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "state": self.state,
                "period": self.period, "path": self.path,
                "reason": self.reason, "report": self.payload}


def _root() -> Optional[pathlib.Path]:
    """The market snapshot root, or None. Never raises."""
    try:
        from intent_engine.demo_dossier import bridge as _B
        for name in ("snapshot_root", "configured_root", "resolve_root"):
            fn = getattr(_B, name, None)
            if callable(fn):
                found = fn()
                if found:
                    return pathlib.Path(found)
    except Exception:                                       # noqa: BLE001
        pass
    import os
    raw = os.environ.get("MARKET_SNAPSHOT_ROOT", "")
    return pathlib.Path(raw) if raw else None


def load(period: str = "day", *, root=None) -> LearningReport:
    """The latest report for `period`. Never raises.

    A failure to read is a STATE with a reason, because "we published no
    learning" and "the disk is not mounted" are different facts and a reader
    that cannot tell them apart will read the second as the first.
    """
    period = str(period or "day").lower()
    if period not in PERIODS:
        return LearningReport(NOT_PUBLISHED, period=period,
                              reason=f"unknown period {period!r}")
    base = pathlib.Path(root) if root is not None else _root()
    if base is None:
        return LearningReport(
            NOT_CONFIGURED, period=period,
            reason="no market snapshot root is configured for this "
                   "deployment, so no learning report can be read")
    folder = base / DIRNAME / _DIRS[period]
    try:
        files = sorted(folder.glob("*.json"))
    except Exception:                                       # noqa: BLE001
        files = []
    if not files:
        return LearningReport(
            NOT_PUBLISHED, period=period, path=str(folder),
            reason=f"the market engine has published no {period} learning "
                   f"report to this deployment")
    latest = files[-1]
    try:
        payload = json.loads(latest.read_text())
    except Exception as exc:                                # noqa: BLE001
        return LearningReport(UNREADABLE, period=period, path=str(latest),
                              reason=f"the report could not be read: {exc}")
    if str(payload.get("contract") or "") != CONTRACT:
        return LearningReport(
            UNREADABLE, period=period, path=str(latest),
            reason=f"the file is not a {CONTRACT}; refusing to read a "
                   f"document whose shape is not the one this understands")
    return LearningReport(AVAILABLE, period=period, payload=payload,
                          path=str(latest))


# --- the interpretation a count cannot give --------------------------------

ACCELERATING = "ACCELERATING"
STABLE = "STABLE"
PLATEAUING = "PLATEAUING"
DEGRADING = "DEGRADING"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


def activity_versus_learning(report: LearningReport) -> dict:
    """Separate how much was READ from how much was LEARNED.

    THE DISTINCTION THIS SURFACE EXISTS FOR. A cycle that re-reads eighty
    pages and changes nothing has been busy, not productive, and a dashboard
    that shows "86 arrivals" as its headline number teaches a reader to
    mistake the first for the second.

    Every figure is read from the report; the only thing computed here is
    which of them to put next to which.
    """
    if not report.available:
        return {"state": report.state, "reason": report.reason}
    evidence = (report.payload.get("channels") or {}).get("evidence") or {}
    arrivals = evidence.get("arrivals_total")
    novel = evidence.get("evidence_rows")
    reobserved = evidence.get("re_observations")
    changed = evidence.get("evidence_that_changed_something")
    effects = evidence.get("effects_by_type") or {}
    no_change = effects.get("NO_CHANGE")
    share = evidence.get("new_information_share")

    verdict, why = INSUFFICIENT_SAMPLE, "too little arrived to judge"
    if isinstance(arrivals, (int, float)) and arrivals >= 10:
        if isinstance(changed, (int, float)) and changed == 0:
            verdict = PLATEAUING
            why = ("nothing that arrived changed the model: the period was "
                   "active and taught the engine nothing")
        elif isinstance(share, (int, float)) and share < 0.15:
            verdict = STABLE
            why = ("most of what arrived had been seen before; the model "
                   "moved on the small share that was new")
        else:
            verdict = ACCELERATING
            why = "a large share of what arrived was new information"
    return {"state": AVAILABLE, "verdict": verdict, "why": why,
            "arrivals": arrivals, "novel": novel, "re_observed": reobserved,
            "changed_the_model": changed, "tested_and_unchanged": no_change,
            "new_information_share": share}
