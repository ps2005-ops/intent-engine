"""Durable feedback — or an honest refusal to accept it.

THE DEFECT THIS REPLACES
------------------------
The success page said "Feedback recorded". It said that because the code
reached the next line, which is not the same thing as the bytes surviving. On a
deployment whose runtime root is replaced on redeploy, the write succeeded, the
page was truthful about the function call, and the tester's feedback was gone
by the next deploy.

This is the same shape as the error page that promised "it has been logged"
while the traceback was never written: a claim about internal state, presented
to a user as a fact, that nobody had checked.

THE RULE
--------
Success is claimed only after a durable write is confirmed by reading the
record back. Where durability has not been demonstrated on this deployment, the
form does not pretend: it says feedback is temporarily unavailable and why.
Refusing to collect feedback is a real cost, and it is smaller than collecting
it under a false promise — a tester who believes their comment was received
does not send it again.

Local and test storage stay separate from any production claim: a passing test
proves the contract holds, never that a given deployment is durable.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

FEEDBACK_VERSION = "webapp_feedback.v1"

RATINGS = ("yes", "partly", "no")
CATEGORIES = ("accuracy", "usefulness", "clarity", "speed", "trust", "other")


class FeedbackNotDurable(RuntimeError):
    """The write could not be confirmed, so no success may be claimed."""


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    run_id: str
    company: str
    page: str
    rating: str
    comment: str
    submitted_at: str
    deployed_commit: str = ""
    analysis_version: str = ""
    category: str = ""
    user_id: str = ""
    schema_version: str = FEEDBACK_VERSION

    def as_dict(self) -> dict:
        return dict(self.__dict__)


class FeedbackLog:
    """Append-only feedback events with a confirmed-write contract.

    Deliberately its own file rather than a corner of an existing store: this
    is the one artefact whose loss the product apologises for by name, and it
    should be trivially exportable and inspectable without decoding anything
    else.
    """

    FILENAME = "feedback.jsonl"

    def __init__(self, runtime_root):
        self.root = Path(runtime_root)
        self.path = self.root / self.FILENAME

    # --- write ------------------------------------------------------------
    def record(self, *, run_id, company, page, rating, comment,
               deployed_commit="", analysis_version="", category="",
               user_id="", now=None) -> FeedbackRecord:
        """Append one record and CONFIRM it by reading it back.

        The read-back is the whole point. Without it this function reports the
        success of a call, and the call succeeding is exactly what was true
        while the tester's feedback was being lost.
        """
        if rating not in RATINGS:
            raise ValueError(f"unknown rating {rating!r}")
        if category and category not in CATEGORIES:
            raise ValueError(f"unknown category {category!r}")
        record = FeedbackRecord(
            feedback_id=f"fb-{uuid.uuid4().hex[:16]}",
            run_id=run_id, company=company, page=page, rating=rating,
            comment=(comment or "")[:4000], submitted_at=now or _now(),
            deployed_commit=deployed_commit,
            analysis_version=analysis_version, category=category,
            user_id=user_id)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.as_dict(),
                                        sort_keys=True) + "\n")
                handle.flush()
                import os
                os.fsync(handle.fileno())
        except OSError as exc:
            raise FeedbackNotDurable(
                f"feedback could not be written: {type(exc).__name__}") \
                from exc
        if not self.contains(record.feedback_id):
            raise FeedbackNotDurable(
                "feedback was written but could not be read back")
        return record

    # --- read -------------------------------------------------------------
    def all(self) -> list:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue        # a torn tail line never hides the rest
        return out

    def contains(self, feedback_id: str) -> bool:
        return any(r.get("feedback_id") == feedback_id for r in self.all())

    def find(self, *, run_id: str = "", company: str = "") -> list:
        rows = self.all()
        if run_id:
            rows = [r for r in rows if r.get("run_id") == run_id]
        if company:
            rows = [r for r in rows if (r.get("company") or "").lower()
                    == company.lower()]
        return rows

    def export_jsonl(self) -> str:
        """Everything, one record per line — the operator's copy."""
        return "\n".join(json.dumps(r, sort_keys=True) for r in self.all())

    def summary(self) -> dict:
        rows = self.all()
        counts: dict = {}
        for row in rows:
            counts[row.get("rating", "?")] = counts.get(
                row.get("rating", "?"), 0) + 1
        return {"total": len(rows), "by_rating": counts,
                "with_comment": sum(1 for r in rows
                                    if (r.get("comment") or "").strip()),
                "runs": sorted({r.get("run_id", "") for r in rows} - {""}),
                "schema_version": FEEDBACK_VERSION}
