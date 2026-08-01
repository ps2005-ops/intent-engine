"""Cross-layer consistency — six surfaces, one interpretation.

WHY PROPERTY CHECKS AND NOT SENTENCE EQUALITY
---------------------------------------------
The layers are SUPPOSED to differ. The 60-second brief clips to a reading
budget, the story expands, the executive brief deduplicates against both, and
Q&A answers a specific question. Asserting identical strings would force them
to be the same page, which is the failure this whole rebuild exists to fix.

What must hold is that none of them CONTRADICTS another:

    same central fact          traced to one insight, not compared verbatim
    compatible implication     same claim, any wording
    compatible decision        same trade-off
    compatible confidence      no layer claims high while another says thin
    compatible evidence        no layer cites evidence another rejected
    no revived refusal         a withheld thesis stays withheld everywhere

The last one is the one that would actually hurt a user. Everything else is a
polish problem; reviving a refused claim in the assistant is a lie.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

_STRONG = ("high", "strong", "certain", "confident", "clear")
_WEAK = ("low", "limited", "thin", "weak", "insufficient", "by construction")


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{4,}", (text or "").lower())}


def _compatible(a: str, b: str, floor: float = 0.25) -> bool:
    """Do two phrasings describe the same thing?

    Deliberately loose. The layers clip and rephrase, so a strict threshold
    would flag good writing as a contradiction. What this catches is a layer
    that talks about something else entirely.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return True          # nothing to contradict
    return len(ta & tb) / min(len(ta), len(tb)) >= floor


@dataclass(frozen=True)
class ConsistencyResult:
    passed: bool
    failures: tuple
    checked: int

    def as_dict(self) -> dict:
        return {"passed": self.passed, "failures": list(self.failures),
                "checked": self.checked}


def check(*, brief, dashboard=None, story=None, executive=None,
          actions=None, qa=None) -> ConsistencyResult:
    """Every layer that was supplied is checked against the shared object."""
    failures: List[str] = []
    k = brief.key_insight
    withheld = k is None
    checked = 0

    # --- dashboard ----------------------------------------------------------
    if dashboard is not None:
        checked += 1
        tiles = {m.key: m for m in dashboard}
        decision_map = tiles.get("decision_map")
        if k and decision_map:
            if not _compatible(decision_map.what_changed, k.fact):
                failures.append("the dashboard's decision map states a "
                                "different central fact from the brief")
            if not _compatible(decision_map.so_what, k.so_what):
                failures.append("the dashboard implies a different "
                                "'why this matters' from the brief")
        if withheld and decision_map is not None:
            failures.append("the dashboard shows a decision map for a company "
                            "whose strategic reading was withheld")

    # --- decision story -----------------------------------------------------
    if story is not None:
        checked += 1
        keys = {s["key"] for s in story}
        if k and "decision" not in keys:
            failures.append("the decision story omits its decision section")
        text = " ".join(p for s in story for p in s["paragraphs"])
        if withheld and _looks_strategic(text):
            failures.append("the decision story asserts a strategic reading "
                            "the brief withheld")

    # --- executive brief ----------------------------------------------------
    if executive is not None:
        checked += 1
        sections = {s["key"]: " ".join(s["paragraphs"])
                    for s in executive.get("sections", [])}
        bottom = sections.get("bottom_line", "")
        if k and bottom and not _compatible(bottom, k.interpretation, 0.15):
            failures.append("the executive brief opens with a different "
                            "thesis from the brief")
        if not executive.get("within_budget", True):
            failures.append("the executive brief exceeds its word budget")

    # --- actions ------------------------------------------------------------
    if actions is not None:
        checked += 1
        if len(actions) > 4:
            failures.append(f"{len(actions)} actions offered; the primary "
                            f"experience caps recommendations at three")
        if k:
            joined = " ".join(a.recommended_action for a in actions)
            if joined and not _compatible(joined, k.decision, 0.10):
                failures.append("the action layer recommends a decision "
                                "unrelated to the brief's trade-off")

    # --- Q&A ----------------------------------------------------------------
    if qa is not None:
        checked += 1
        if withheld and not qa.withheld and _looks_strategic(qa.direct_answer):
            failures.append("Q&A revived a strategic claim the primary "
                            "experience refused")
        if k and qa.decision_affected and not _compatible(
                qa.decision_affected, k.decision):
            failures.append("Q&A names a different decision from the brief")
        if k and qa.so_what and not _compatible(qa.so_what, k.so_what):
            failures.append("Q&A gives a different implication from the brief")
        if qa.evidence_ids and k and set(qa.evidence_ids) - set(k.evidence_ids):
            failures.append("Q&A cites evidence the brief does not")
        if _contradicts_confidence(brief.confidence, qa.confidence):
            failures.append(f"confidence disagrees across layers: brief says "
                            f"{brief.confidence!r}, Q&A says {qa.confidence!r}")
    return ConsistencyResult(not failures, tuple(failures), checked)


def _looks_strategic(text: str) -> bool:
    """Does this assert a direction the evidence did not support?"""
    low = (text or "").lower()
    if "not going to give you a strategic read" in low:
        return False
    return any(m in low for m in (
        "is shifting", "is moving toward", "is repositioning", "strategy is",
        "the company is becoming", "is transitioning", "pivoting"))


def _contradicts_confidence(a: str, b: str) -> bool:
    """High in one place and thin in another is the contradiction that most
    misleads: the reader trusts whichever they saw last."""
    la, lb = (a or "").lower(), (b or "").lower()
    a_strong = any(w in la for w in _STRONG) and not any(w in la for w in _WEAK)
    b_strong = any(w in lb for w in _STRONG) and not any(w in lb for w in _WEAK)
    a_weak = any(w in la for w in _WEAK)
    b_weak = any(w in lb for w in _WEAK)
    return (a_strong and b_weak) or (b_strong and a_weak)
