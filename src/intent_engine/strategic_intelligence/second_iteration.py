"""What the second look changed — and what it merely confirmed.

THE QUESTION THIS ANSWERS. A chief executive who runs the same company twice
is asking whether the system is learning or just re-rendering. Answering that
with "the recommendation is the same" is useless, and answering it with "here
is what changed" is worse, because it rewards change and a system that is
rewarded for changing its mind will change it.

CHANGE IS NOT LEARNING, AND STABILITY IS NOT STAGNATION
-------------------------------------------------------
A belief that was TESTED by new evidence and held is a stronger position than
one that has never been challenged, and it must be reportable as a gain. So
the states below separate three things a single diff would collapse:

    did new information arrive?
    did it bear on the decision?
    did the decision move?

Only the combination is meaningful. "New information arrived, it tested the
central claim, the claim held, the recommendation is unchanged" is a good day,
and it must not render as "nothing happened".

THE REPLAY WALL
---------------
Running the identical analysis a third time must produce NOTHING. Not a
smaller delta -- nothing. Re-reading a document the system already holds is
not an observation, and a system that counts it as one manufactures a learning
curve out of its own repetition. That is the single most flattering error
available here, so it is the one with the most tests.
"""
from __future__ import annotations

from typing import Dict, Sequence

CONTRACT = "second_iteration.v1"

FIRST_OBSERVATION = "FIRST_OBSERVATION"
NEW_INFORMATION_CHANGED_VIEW = "NEW_INFORMATION_CHANGED_VIEW"
NEW_INFORMATION_CONFIRMED_VIEW = "NEW_INFORMATION_CONFIRMED_VIEW"
NEW_INFORMATION_NOT_DECISION_RELEVANT = "NEW_INFORMATION_NOT_DECISION_RELEVANT"
REOBSERVATION_TESTED_AND_HELD = "REOBSERVATION_TESTED_AND_HELD"
NO_NEW_INFORMATION = "NO_NEW_INFORMATION"
INCOMPARABLE = "INCOMPARABLE"

ITERATION_STATES = (FIRST_OBSERVATION, NEW_INFORMATION_CHANGED_VIEW,
                    NEW_INFORMATION_CONFIRMED_VIEW,
                    NEW_INFORMATION_NOT_DECISION_RELEVANT,
                    REOBSERVATION_TESTED_AND_HELD, NO_NEW_INFORMATION,
                    INCOMPARABLE)

#: States that represent a real gain in what the system knows. Holding under
#: test is here on purpose: a belief that survived new evidence is worth more
#: than one nobody has challenged.
REPRESENTS_LEARNING = frozenset({NEW_INFORMATION_CHANGED_VIEW,
                                 NEW_INFORMATION_CONFIRMED_VIEW,
                                 REOBSERVATION_TESTED_AND_HELD})

#: States a surface must never render as a learning gain.
NO_GAIN = frozenset({NO_NEW_INFORMATION, INCOMPARABLE,
                     NEW_INFORMATION_NOT_DECISION_RELEVANT})


def _ids(rows: Sequence[dict], key: str = "content_hash") -> set:
    out = set()
    for row in rows or ():
        value = str((row or {}).get(key) or "").strip()
        if value:
            out.add(value)
    return out


def _decision_fields(decision: dict) -> dict:
    d = decision or {}
    return {
        "standing": str(d.get("standing") or ""),
        "recommended_next_move": str(d.get("recommended_next_move") or ""),
        "current_read": str(d.get("current_read") or ""),
        "decision_question": str(d.get("decision_question") or ""),
    }


def compare(*, previous_decision: dict = None, current_decision: dict = None,
            previous_documents: Sequence[dict] = (),
            current_documents: Sequence[dict] = (),
            tested_claims: Sequence[str] = ()) -> Dict[str, object]:
    """The one canonical delta between two analyses of the same company.

    Evidence identity is the CONTENT HASH, never the URL and never the
    retrieval date. The same page fetched twice is one observation; a page at
    the same address whose content changed is two. Keying on anything else is
    how a system credits itself for re-reading its own library.
    """
    prev_docs = _ids(previous_documents)
    curr_docs = _ids(current_documents)
    genuinely_new = sorted(curr_docs - prev_docs)
    reobserved = sorted(curr_docs & prev_docs)

    base = {
        "contract": CONTRACT,
        "new_evidence": len(genuinely_new),
        "reobserved_evidence": len(reobserved),
        "duplicate_evidence": len(reobserved),
        "tested_claims": [str(c) for c in tested_claims if str(c or "").strip()],
        "changed_fields": [],
        "decision_changed": False,
        "recommendation_changed": False,
    }

    if previous_decision is None:
        return dict(base, state=FIRST_OBSERVATION,
                    represents_learning=False,
                    statement=("This is the first reading of this company, so "
                               "there is nothing yet to compare it against."))

    before, after = (_decision_fields(previous_decision),
                     _decision_fields(current_decision))
    if not before.get("decision_question") or not after.get("decision_question"):
        return dict(base, state=INCOMPARABLE, represents_learning=False,
                    statement=("The two readings did not answer the same "
                               "question, so the difference between them is "
                               "not a change of mind."))
    if before["decision_question"] != after["decision_question"]:
        return dict(base, state=INCOMPARABLE, represents_learning=False,
                    statement=("The decision question changed between runs, "
                               "so these two readings are not comparable."))

    changed = sorted(k for k in after if after[k] != before[k])
    base["changed_fields"] = changed
    base["decision_changed"] = bool(changed)
    base["recommendation_changed"] = "recommended_next_move" in changed

    # THE REPLAY WALL. Nothing arrived that we did not already hold, so
    # nothing can have been learned -- whatever else moved.
    if not genuinely_new:
        if changed:
            # Same evidence, different answer. That is not learning; it is
            # instability, and calling it learning would hide it.
            return dict(base, state=INCOMPARABLE, represents_learning=False,
                        statement=("The reading moved without any new evidence "
                                   "arriving. That is a change in us, not a "
                                   "change in what is known."))
        if reobserved and tested_claims:
            return dict(base, state=REOBSERVATION_TESTED_AND_HELD,
                        represents_learning=True,
                        statement=(f"No new evidence arrived. "
                                   f"{len(reobserved)} source(s) we already "
                                   f"held were re-read and the reading still "
                                   f"follows from them."))
        return dict(base, state=NO_NEW_INFORMATION, represents_learning=False,
                    statement=("Nothing arrived that we did not already hold, "
                               "so there was nothing to test."))

    if changed:
        return dict(base, state=NEW_INFORMATION_CHANGED_VIEW,
                    represents_learning=True,
                    statement=(f"{len(genuinely_new)} new source(s) arrived and "
                               f"the reading moved."))
    if tested_claims:
        return dict(base, state=NEW_INFORMATION_CONFIRMED_VIEW,
                    represents_learning=True,
                    statement=(f"{len(genuinely_new)} new source(s) arrived and "
                               f"tested the reading, which held. A position "
                               f"that has survived new evidence is stronger "
                               f"than one nothing has challenged."))
    return dict(base, state=NEW_INFORMATION_NOT_DECISION_RELEVANT,
                represents_learning=False,
                statement=(f"{len(genuinely_new)} new source(s) arrived and "
                           f"none of them bore on the decision."))


def hero(delta: Dict[str, object]) -> Dict[str, str]:
    """The seven lines the second-iteration card renders.

    Carried as one object so the card, the deck and the Q&A cannot describe
    the same two runs differently.
    """
    d = delta or {}
    state = str(d.get("state") or "")
    tested = d.get("tested_claims") or []

    # STATE EXCLUSIVITY. Every line below is a claim ABOUT A PRIOR, and a
    # state with no prior cannot license any of them. This rendered all seven
    # unconditionally, so a first reading of Cloudflare said, on one card:
    # "This is the baseline reading. There is no earlier view to compare it
    # against yet." then "10 source(s) we had not seen before" then "This did
    # not add to what the system knows." Each line was separately true of some
    # quantity in the delta; together they describe three different worlds.
    #
    # "Not seen before" is measured against the previous run's documents, and
    # on a baseline that set is empty -- so the count is the whole corpus and
    # the sentence is an artefact of comparing against nothing. Suppressed
    # rather than reworded: there is no honest phrasing of novelty relative to
    # a prior that does not exist.
    comparative = state not in (FIRST_OBSERVATION, INCOMPARABLE)
    return {
        "state": state,
        "new_information": (f"{d.get('new_evidence', 0)} source(s) we had not "
                            f"seen before") if comparative else "",
        "what_it_tested": (("; ".join(str(t) for t in tested[:3]) if tested
                            else "nothing that bore on the decision")
                           if comparative else ""),
        "what_held": ("the reading" if state in (
            NEW_INFORMATION_CONFIRMED_VIEW, REOBSERVATION_TESTED_AND_HELD)
            else ""),
        "what_changed": (", ".join(str(f).replace("_", " ")
                                   for f in (d.get("changed_fields") or []))
                         if comparative else ""),
        "decision_effect": (("the recommendation changed"
                             if d.get("recommendation_changed") else
                             "the recommendation is unchanged")
                            if comparative else ""),
        "statement": str(d.get("statement") or ""),
    }
