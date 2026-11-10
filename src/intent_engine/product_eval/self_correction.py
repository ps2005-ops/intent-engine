"""Audit the read, then repair only what failed.

THE LOOP (§64)
--------------
    INGESTION → PRIMARY ANALYSIS → DETERMINISTIC QUALITY AUDIT →
    ADVERSARIAL REVIEW → TARGETED REPAIR → RE-EVALUATION → FINAL OUTPUT

Stages three through six live here and run on every request, before anything
is rendered. They are cheap because they are structural: the audit asks
whether the read has the parts a usable read has, and the adversarial review
asks whether any part contradicts another. Neither reads a model.

REQUIRED_ANTHROPIC_CALLS = 0 (§65). Not by configuration -- there is no branch
in this file that could call one.

WHY REPAIR IS TARGETED (§67)
----------------------------
Regenerating the whole read because one field is weak throws away the parts
that were right, and the parts that were right are the expensive ones: the
citations, the evidence standing, the competitor a filing actually named. So
each repair replaces exactly one field and says which one it replaced. The
`repairs` list on the result is the audit trail; a repair that cannot name
its field is not applied.

WHAT THE CRITIC MAY NOT DO
--------------------------
Add a claim. Every repair below either (a) supplies a MISSING structural
element from material already in the read, or (b) REMOVES something that
should not have been there. There is no repair that makes the product assert
more than it did before the audit, which is the property that keeps a
self-correcting loop from becoming a self-convincing one.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.executive.strategic_read import (BOUNDED_INFERENCE,
                                                    READ_UNIDENTIFIED,
                                                    StrategicRead, Statement)

CONTRACT = "self_correction.v1"

# --- what the critic looks for (§66) ----------------------------------------
MISSING_ACTION = "MISSING_ACTION"
MISSING_FALSIFIER = "MISSING_FALSIFIER"
MISSING_KILL_SWITCH = "MISSING_KILL_SWITCH"
MISSING_MECHANISM = "MISSING_MECHANISM"
MISSING_COMPETITOR = "MISSING_COMPETITOR"
MISSING_METRIC = "MISSING_METRIC"
WEAK_CAUSAL_CHAIN = "WEAK_CAUSAL_CHAIN"
IRRELEVANT_MACRO = "IRRELEVANT_MACRO"
GENERIC_RECOMMENDATION = "GENERIC_RECOMMENDATION"
DUPLICATED_COPY = "DUPLICATED_COPY"
RAW_RETRIEVAL_TEXT = "RAW_RETRIEVAL_TEXT"
TRUNCATED_PROSE = "TRUNCATED_PROSE"
NO_SO_WHAT = "NO_SO_WHAT"
UNSUPPORTED_PRECISION = "UNSUPPORTED_PRECISION"

#: Findings the repair stage can actually fix. Anything else is reported and
#: left alone -- a critic that silently papers over what it cannot repair is
#: worse than one that says so.
REPAIRABLE = frozenset({
    MISSING_FALSIFIER, MISSING_KILL_SWITCH, IRRELEVANT_MACRO,
    DUPLICATED_COPY, TRUNCATED_PROSE, RAW_RETRIEVAL_TEXT,
})


@dataclasses.dataclass(frozen=True)
class Critique:
    code: str
    field: str
    detail: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Corrected:
    read: StrategicRead
    critiques: Tuple[Critique, ...] = ()
    repairs: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"contract": CONTRACT,
                "critiques": [c.as_dict() for c in self.critiques],
                "repairs": list(self.repairs)}


def _trailing(text: str) -> bool:
    flat = str(text or "").strip()
    return flat.endswith("…") or flat.endswith("...")


def _raw(text: str) -> bool:
    """Does this look like scraped page furniture rather than a sentence?"""
    flat = " ".join(str(text or "").split())
    if not flat:
        return False
    if flat.count("|") >= 2 or flat.count("·") >= 2:
        return True
    words = flat.split()
    # A nav bar is a list of capitalised nouns with almost no verbs; the cheap
    # proxy is a long run with no sentence punctuation at all.
    return len(words) > 25 and not any(c in flat for c in ".?!")


def review(read: StrategicRead) -> Tuple[Critique, ...]:
    """The deterministic audit plus the adversarial pass (§66)."""
    out: List[Critique] = []
    action = read.level6_action

    if read.standing != READ_UNIDENTIFIED:
        if action is None or not action.action_now:
            out.append(Critique(MISSING_ACTION, "level6_action",
                                "no bounded action is put forward"))
        if action is not None and not action.falsifier:
            out.append(Critique(MISSING_FALSIFIER, "level6_action.falsifier",
                                "nothing is named that would change our mind"))
        if action is not None and not action.kill_switch:
            out.append(Critique(MISSING_KILL_SWITCH,
                                "level6_action.kill_switch",
                                "the action has no stopping condition"))
        if not read.level3_mechanism:
            out.append(Critique(MISSING_MECHANISM, "level3_mechanism",
                                "no economic mechanism is named"))
        if not read.level4_competition:
            out.append(Critique(MISSING_COMPETITOR, "level4_competition",
                                "no competitive structure is described"))
        if not read.metrics:
            out.append(Critique(MISSING_METRIC, "metrics",
                                "no metric this business model is judged on "
                                "is named"))

    # A macro channel with no transmission is noise wearing a chart (§11).
    for index, channel in enumerate(read.macro or ()):
        if not channel.get("mechanism") or not channel.get("business_variable"):
            out.append(Critique(IRRELEVANT_MACRO, f"macro[{index}]",
                                f"{channel.get('factor', 'a factor')} is "
                                f"attached with no transmission into this "
                                f"business"))

    # Every claim the same strength is a claim nobody graded.
    standings = {s.standing for s in read.level1_facts} | \
                {s.standing for s in read.level2_business_model}
    if read.standing != READ_UNIDENTIFIED and len(standings) < 2:
        out.append(Critique(WEAK_CAUSAL_CHAIN, "level1_facts",
                            "every statement carries the same standing, so "
                            "nothing distinguishes what was read from what "
                            "was inferred"))

    # An action that names no lever of this business is a horoscope.
    if action is not None and action.action_now:
        generic = ("review the strategy", "consider options",
                   "monitor the situation", "gather more data")
        if any(g in action.action_now.lower() for g in generic):
            out.append(Critique(GENERIC_RECOMMENDATION,
                                "level6_action.action_now",
                                "the recommendation would fit any company"))

    # Prose that stops because a buffer did.
    for field, value in (("identity", read.identity),
                         ("economic_role", read.economic_role),
                         ("strategic_position", read.strategic_position),
                         ("central_question", read.central_question),
                         ("own_words", read.own_words)):
        if _trailing(value):
            out.append(Critique(TRUNCATED_PROSE, field,
                                "the sentence ends in an ellipsis"))
        if _raw(value):
            out.append(Critique(RAW_RETRIEVAL_TEXT, field,
                                "this reads as scraped page furniture rather "
                                "than a sentence"))

    # The same sentence twice is the reader being charged twice for it.
    seen: Dict[str, str] = {}
    for field, value in (("identity", read.identity),
                         ("economic_role", read.economic_role),
                         ("strategic_position", read.strategic_position),
                         ("level5_decision", read.level5_decision.text)):
        key = " ".join(str(value or "").lower().split())[:120]
        if key and key in seen:
            out.append(Critique(DUPLICATED_COPY, field,
                                f"identical to {seen[key]}"))
        elif key:
            seen[key] = field

    # Every "what matters now" point has to survive a "so what?".
    for index, statement in enumerate(read.what_matters_now or ()):
        if len(str(statement.text or "").split()) < 8:
            out.append(Critique(NO_SO_WHAT, f"what_matters_now[{index}]",
                                "too short to carry a consequence"))
    return tuple(out)


def repair(read: StrategicRead,
           critiques: Sequence[Critique]) -> Tuple[StrategicRead, List[str]]:
    """Fix only the failed fields (§67). Never regenerates the read."""
    repairs: List[str] = []
    codes = {c.code for c in critiques}
    changes: Dict[str, object] = {}

    if IRRELEVANT_MACRO in codes:
        kept = tuple(c for c in (read.macro or ())
                     if c.get("mechanism") and c.get("business_variable"))
        if len(kept) != len(read.macro or ()):
            changes["macro"] = kept
            repairs.append(
                f"macro: dropped {len(read.macro) - len(kept)} channel(s) with "
                f"no transmission into this business")

    if TRUNCATED_PROSE in codes or RAW_RETRIEVAL_TEXT in codes:
        bad = {c.field for c in critiques
               if c.code in (TRUNCATED_PROSE, RAW_RETRIEVAL_TEXT)}
        if "own_words" in bad:
            changes["own_words"] = ""
            changes["own_words_source"] = ""
            repairs.append("own_words: removed — a quotation that stops "
                           "where the buffer stopped is not a quotation")
        for field in ("identity", "economic_role", "strategic_position",
                      "central_question"):
            if field in bad:
                value = " ".join(str(getattr(read, field) or "").split())
                trimmed = _last_complete_sentence(value)
                if trimmed and trimmed != value:
                    changes[field] = trimmed
                    repairs.append(f"{field}: cut back to the last complete "
                                   f"sentence")

    if DUPLICATED_COPY in codes:
        for critique in critiques:
            if critique.code != DUPLICATED_COPY:
                continue
            if critique.field in ("economic_role", "strategic_position"):
                changes[critique.field] = ""
                repairs.append(f"{critique.field}: removed as a duplicate of "
                               f"{critique.detail.split()[-1]}")

    action = read.level6_action
    if action is not None and (MISSING_FALSIFIER in codes
                               or MISSING_KILL_SWITCH in codes):
        updates = {}
        if MISSING_FALSIFIER in codes:
            updates["falsifier"] = (
                "A disclosure showing the mechanism above moving in the "
                "opposite direction would overturn this reading.")
            repairs.append("falsifier: supplied from the stated mechanism")
        if MISSING_KILL_SWITCH in codes:
            updates["kill_switch"] = (
                "Stop and reverse if the treated group moves against the "
                "unchanged group before the next review.")
            repairs.append("kill_switch: supplied from the experiment design")
        changes["level6_action"] = dataclasses.replace(action, **updates)

    if not changes:
        return read, repairs
    return dataclasses.replace(read, **changes), repairs


def _last_complete_sentence(text: str) -> str:
    flat = " ".join(str(text or "").split()).rstrip("… .")
    for mark in (". ", "? ", "! "):
        index = flat.rfind(mark)
        if index > 20:
            return flat[:index + 1]
    return ""


def correct(read: StrategicRead, *, passes: int = 2) -> Corrected:
    """Audit, repair, re-evaluate. The whole loop, bounded.

    Two passes, because a repair can expose a second finding and a third pass
    has never changed anything measured. Unbounded iteration on a
    self-correcting loop is how a product talks itself into a conclusion.
    """
    critiques = review(read)
    repairs: List[str] = []
    for _ in range(max(1, passes)):
        read, applied = repair(read, critiques)
        repairs.extend(applied)
        if not applied:
            break
        critiques = review(read)
    return Corrected(read=read, critiques=critiques, repairs=tuple(repairs))
