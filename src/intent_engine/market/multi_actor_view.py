"""What a founder is shown about a competitive move — and what is withheld.

THE SENTENCE THIS EXISTS TO MAKE IMPOSSIBLE
-------------------------------------------
    "Salesforce is attacking Shopify's enterprise base to take share."

Every word of that is a motive, and the engine observes actions. The safe
form of the same intelligence is longer and worth more:

    "Salesforce launched X into the same enterprise-commerce buying decision
     where Shopify has been evaluated. That makes the move strategically
     relevant. The public evidence does not establish whether the objective
     is share capture, bundling pressure, or customer retention."

So `render` takes objective HYPOTHESES, never an objective, and refuses to
build a view from a hypothesis whose standing claims more than WEAK unless
the evidence promoted it. A view carries every alternative it was given.

SIX SECTIONS, AND THE FOURTH IS NOT OPTIONAL
--------------------------------------------
    WHAT HAPPENED          the action, as stated
    WHO IT AFFECTS         the counterparty, via the relationship
    WHY IT MAY MATTER      the mechanism, hedged
    WHAT WE DO NOT KNOW    the objective set, and the object's standing
    WHAT RESPONSE WE EXPECT the preregistered class, with its window
    WHAT TO WATCH          the eligible evidence

A view missing "what we do not know" is refused. It is the section that
turns a competitive story into a claim somebody can check, and it is the
first thing that disappears when a summary is written to sound confident.

PROVENANCE OR NOTHING
---------------------
Every section names the record it came from. There is no free-text path into
this view: `render` accepts records and reads their fields, so a sentence
nobody can trace to a relationship, an action or an expectation cannot
appear.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "multi_actor_view.v1"

REQUIRED_SECTIONS = ("what_happened", "who_it_affects", "why_it_may_matter",
                     "what_we_do_not_know", "what_response_we_expect",
                     "what_to_watch")

#: Language that asserts a motive. Checked on the rendered output, because
#: the failure mode is a sentence rather than a field.
_MOTIVE = (
    "in order to", "is attacking", "is trying to", "aims to take",
    "wants to", "intends to", "so that it can", "because it wants",
    "is going after", "designed to steal", "to take share from",
)


class ViewRejected(ValueError):
    """The view was asked to state something the evidence does not carry."""


@dataclass(frozen=True)
class MultiActorStrategicView:
    view_id: str
    subject: str
    counterparty: str
    sections: Dict[str, str]
    provenance: Dict[str, str]
    objectives_considered: Tuple[str, ...]
    uncertainty: str
    falsifier: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "view_id": self.view_id,
            "subject": self.subject, "counterparty": self.counterparty,
            "sections": dict(self.sections),
            "provenance": dict(self.provenance),
            "objectives_considered": list(self.objectives_considered),
            "uncertainty": self.uncertainty, "falsifier": self.falsifier,
        }

    def render(self) -> str:
        return "\n\n".join(
            f"{name.replace('_', ' ').upper()}\n{self.sections[name]}"
            for name in REQUIRED_SECTIONS)


def _who(counterparty: str, actor: str, relationship) -> str:
    contested = getattr(relationship, "competitive_object", "") \
        or "a contested decision"
    buyer = getattr(relationship, "buyer_or_market", "") or "a named buyer"
    return (f"{counterparty}, which the public record ties to {actor} over "
            f"{contested} for {buyer}.")


def build(*, relationship, action, competitive_object, interaction_id: str,
          objectives: Sequence, expectation=None) -> MultiActorStrategicView:
    """Assemble the founder-facing view from records, never from prose.

    `objectives` must contain at least two hypotheses, or the view would
    present one reading as the reading — which is the sentence in the module
    docstring.
    """
    hypotheses = tuple(getattr(o, "objective", "") for o in objectives
                       if getattr(o, "objective", ""))
    if len(hypotheses) < 2:
        raise ViewRejected(
            "a view needs at least two objective hypotheses; with one, the "
            "founder reads a motive rather than a question")
    for candidate in objectives:
        if getattr(candidate, "standing", "") not in ("WEAK", "PLAUSIBLE",
                                                      "SUPPORTED",
                                                      "CONTESTED"):
            raise ViewRejected("an objective with no standing is an assertion")

    actor = getattr(action, "actor", "")
    counterparty = getattr(relationship, "actor_a", "")
    if counterparty == actor:
        counterparty = getattr(relationship, "actor_b", "")
    obj_text = (getattr(competitive_object, "use_case", "")
                or getattr(competitive_object, "workflow", ""))
    buyer = getattr(competitive_object, "buyer", "")
    standing = getattr(competitive_object, "standing", "UNKNOWN")

    sections = {
        "what_happened": (
            f"{actor} {getattr(action, 'action_type', '').lower().replace('_', ' ')}"
            f": {getattr(action, 'span', '')}"),
        "who_it_affects": _who(counterparty, actor, relationship),
        "why_it_may_matter": (
            f"The action targets {obj_text or 'an unstated object'} for "
            f"{buyer or 'an unstated buyer'}. Where that is the same buying "
            f"decision the two already contest, the move is strategically "
            f"relevant; where it is adjacent, it may change nothing."),
        "what_we_do_not_know": (
            f"The objective. The evidence is consistent with "
            f"{', '.join(hypotheses[:-1])} or {hypotheses[-1]}, and does not "
            f"discriminate between them. The competitive object is "
            f"{standing}."),
        "what_response_we_expect": (
            (f"{getattr(expectation, 'counterparty', counterparty)} would, "
             f"if the mechanism holds, respond through "
             f"{', '.join(getattr(expectation, 'expected_response_class', ()))} "
             f"by {getattr(expectation, 'resolution_window', '')}.")
            if expectation is not None else
            "No response has been preregistered, because no interaction has "
            "met the bar that would license one."),
        "what_to_watch": (
            (f"{getattr(expectation, 'disconfirming_outcome', '')} would "
             f"show the reading is wrong.")
            if expectation is not None else
            f"A document from {counterparty} naming the same buyer and "
            f"workflow, which is what is missing."),
    }

    rendered = " ".join(sections.values()).lower()
    for phrase in _MOTIVE:
        if phrase in rendered:
            raise ViewRejected(
                f"the view states a motive ({phrase!r}); the engine observes "
                f"actions and infers nothing about why")

    missing = [s for s in REQUIRED_SECTIONS if not sections.get(s, "").strip()]
    if missing:
        raise ViewRejected(f"sections missing: {missing}")

    return MultiActorStrategicView(
        view_id=f"mav_{interaction_id}",
        subject=actor, counterparty=counterparty, sections=sections,
        provenance={
            "relationship": getattr(relationship, "claim_id", ""),
            "action": getattr(action, "action_id", ""),
            "competitive_object": getattr(competitive_object, "object_id", ""),
            "interaction": interaction_id,
            "expectation": getattr(expectation, "expectation_id", "")
            if expectation is not None else "",
        },
        objectives_considered=hypotheses,
        uncertainty=sections["what_we_do_not_know"],
        falsifier=sections["what_to_watch"])


# --- what a view may change on the founder's decision ----------------------
#
# A competitor MENTION changes nothing. A view changes a field only where it
# alters what the founder would do, and the fields are closed so a
# competitive story cannot quietly reach a pricing recommendation.
IMPACT_FIELDS = ("competitive_risk", "option_timing", "pricing_watch",
                 "migration_risk", "distribution_risk", "assumption",
                 "falsifier", "monitoring")


def decision_impact(view: MultiActorStrategicView, *,
                    object_standing: str) -> dict:
    """Which founder fields this view is entitled to move.

    An UNESTABLISHED object moves `monitoring` and nothing else: the engine
    knows something happened and cannot say whether it touches the founder's
    decision, and that is exactly a monitoring instruction rather than a
    risk update.
    """
    if object_standing != "ESTABLISHED":
        return {
            "changed": ["monitoring"],
            "unchanged": [f for f in IMPACT_FIELDS if f != "monitoring"],
            "reason": (f"the competitive object is {object_standing}: the "
                       f"engine cannot say the action touches this founder's "
                       f"buying decision, so it may add a thing to watch and "
                       f"may not move a risk"),
        }
    return {
        "changed": ["competitive_risk", "monitoring", "falsifier"],
        "unchanged": ["pricing_watch", "migration_risk", "distribution_risk",
                      "option_timing", "assumption"],
        "reason": ("the object is established and overlaps the contested "
                   "decision; risk and falsifier move, and pricing stays put "
                   "until a pricing action is observed"),
    }


def summarise(views: Sequence[MultiActorStrategicView]) -> dict:
    return {
        "contract": CONTRACT,
        "views": len(views),
        "subjects": sorted({v.subject for v in views}),
        "objectives_per_view": (
            round(sum(len(v.objectives_considered) for v in views)
                  / len(views), 2) if views else 0.0),
        "required_sections": list(REQUIRED_SECTIONS),
        "note": ("a view carries objective HYPOTHESES and never an "
                 "objective; motive language is refused on the rendered "
                 "output, because the failure mode is a sentence rather "
                 "than a field"),
    }
