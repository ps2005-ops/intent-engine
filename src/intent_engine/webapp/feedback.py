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

FEEDBACK_VERSION = "webapp_feedback.v2"

RATINGS = ("yes", "partly", "no")
CATEGORIES = ("accuracy", "usefulness", "clarity", "speed", "trust", "other")

#: §47. The 1-5 score, kept ALONGSIDE the three-value rating rather than
#: replacing it. Two reasons: every record already written carries a rating
#: and re-interpreting them as scores would invent precision that was never
#: collected, and a coarse rating is what a reader answers in one second
#: while a score is what a defect matrix can average. Both are optional at
#: the boundary and neither is inferred from the other.
SCORES = ("1", "2", "3", "4", "5")

#: §48. Quick tags. Each maps to a defect class the repair loop already
#: knows how to cluster on, which is the point: a free-text box produces
#: sympathy, and a tag produces a queue.
TAGS = (
    ("too_generic", "Too generic"),
    ("wrong_fact", "Wrong fact"),
    ("missing_metric", "Missing metric"),
    ("weak_competitors", "Weak competitor analysis"),
    ("weak_economics", "Weak economic analysis"),
    ("weak_recommendation", "Weak recommendation"),
    ("history_not_useful", "History not useful"),
    ("presentation_unclear", "Presentation unclear"),
    ("excellent_insight", "Excellent insight"),
    ("would_use", "Would use this"),
)

TAG_KEYS = tuple(key for key, _ in TAGS)

#: Which defect class a tag belongs to, so feedback lands in the SAME
#: taxonomy the machine rubric uses (§50). A tag with no mapping would be a
#: sentiment counter; a tag with one is a defect report from a customer.
TAG_DEFECT = {
    "too_generic": "TEMPLATE_COLLAPSE",
    "wrong_fact": "FABRICATED_OR_WRONG_FACT",
    "missing_metric": "DATA_RESOLUTION_GAP",
    "weak_competitors": "COMPETITOR_QUALITY",
    "weak_economics": "ECONOMIC_REASONING",
    "weak_recommendation": "WEAK_RECOMMENDATION",
    "history_not_useful": "HISTORY_QUALITY",
    "presentation_unclear": "PRESENTATION_CLARITY",
}

#: The tags that are praise. Kept separate so a positive tag can never be
#: counted as a defect by a loop that only looks at frequency.
POSITIVE_TAGS = frozenset({"excellent_insight", "would_use"})


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
    #: §47. Optional structured answers. Absent on every v1 record, which is
    #: why they default rather than being required.
    score: str = ""
    tags: tuple = ()
    most_useful: str = ""
    what_was_missing: str = ""
    what_looked_wrong: str = ""
    decision_use: str = ""
    would_connect: str = ""
    schema_version: str = FEEDBACK_VERSION

    def as_dict(self) -> dict:
        out = dict(self.__dict__)
        out["tags"] = list(self.tags)
        return out

    @property
    def defect_classes(self) -> tuple:
        """The defect classes this record reports. Praise maps to none."""
        return tuple(TAG_DEFECT[t] for t in self.tags if t in TAG_DEFECT)


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
               user_id="", score="", tags=(), most_useful="",
               what_was_missing="", what_looked_wrong="", decision_use="",
               would_connect="", now=None) -> FeedbackRecord:
        """Append one record and CONFIRM it by reading it back.

        The read-back is the whole point. Without it this function reports the
        success of a call, and the call succeeding is exactly what was true
        while the tester's feedback was being lost.
        """
        if rating not in RATINGS:
            raise ValueError(f"unknown rating {rating!r}")
        if category and category not in CATEGORIES:
            raise ValueError(f"unknown category {category!r}")
        if score and score not in SCORES:
            raise ValueError(f"unknown score {score!r}")
        # UNKNOWN TAGS ARE DROPPED, NOT REJECTED.
        #
        # Tags arrive from a form and a rejected submission loses the whole
        # record including the free text, which is the part that cannot be
        # re-derived. An unrecognised tag is worth nothing and the comment
        # beside it may be worth everything.
        kept_tags = tuple(t for t in (tags or ()) if t in TAG_KEYS)
        record = FeedbackRecord(
            feedback_id=f"fb-{uuid.uuid4().hex[:16]}",
            run_id=run_id, company=company, page=page, rating=rating,
            comment=(comment or "")[:4000], submitted_at=now or _now(),
            deployed_commit=deployed_commit,
            analysis_version=analysis_version, category=category,
            user_id=user_id, score=score, tags=kept_tags,
            most_useful=(most_useful or "")[:2000],
            what_was_missing=(what_was_missing or "")[:2000],
            what_looked_wrong=(what_looked_wrong or "")[:2000],
            decision_use=(decision_use or "")[:2000],
            would_connect=(would_connect or "")[:40])
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
        scores = [int(r["score"]) for r in rows
                  if str(r.get("score") or "").isdigit()]
        return {"total": len(rows), "by_rating": counts,
                "with_comment": sum(1 for r in rows
                                    if (r.get("comment") or "").strip()),
                "runs": sorted({r.get("run_id", "") for r in rows} - {""}),
                "scored": len(scores),
                "mean_score": (round(sum(scores) / len(scores), 2)
                               if scores else None),
                "schema_version": FEEDBACK_VERSION}

    # --- the learning seam -------------------------------------------------
    def defect_signal(self, *, company: str = "") -> dict:
        """§50-§51. Customer feedback as defect counts the repair loop reads.

        The whole reason the tags map to defect CLASSES rather than to their
        own vocabulary: a recurring "too generic" from customers and a
        TEMPLATE_COLLAPSE finding from the machine rubric are the same defect
        seen from two sides, and a loop that cannot join them will fix one
        and keep shipping the other.
        """
        rows = self.find(company=company) if company else self.all()
        defects: dict = {}
        praise: dict = {}
        companies: dict = {}
        for row in rows:
            for tag in (row.get("tags") or ()):
                if tag in POSITIVE_TAGS:
                    praise[tag] = praise.get(tag, 0) + 1
                    continue
                cls = TAG_DEFECT.get(tag)
                if not cls:
                    continue
                defects[cls] = defects.get(cls, 0) + 1
                names = companies.setdefault(cls, set())
                names.add(row.get("company", ""))
        scores = [int(r["score"]) for r in rows
                  if str(r.get("score") or "").isdigit()]
        return {"contract": FEEDBACK_VERSION,
                "records": len(rows),
                "by_defect_class": dict(sorted(defects.items(),
                                               key=lambda kv: -kv[1])),
                "companies_by_defect": {k: sorted(v - {""})
                                        for k, v in companies.items()},
                "praise": praise,
                "mean_score": (round(sum(scores) / len(scores), 2)
                               if scores else None)}
