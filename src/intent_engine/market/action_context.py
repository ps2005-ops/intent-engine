"""The sentences immediately around an action, and nothing further away.

WHY THIS EXISTS
---------------
Shopify's developer changelog carries entries like

    TITLE  Full-stack capabilities to power app analytics
    TEXT   For app developers, building merchant-facing analytics has always
           meant standing up your own stack ... With these updates, Shopify
           Analytics becomes a full-stack analytics platform that apps can
           build on directly.

Both axes are present — "app developers" is the buyer and "Shopify Analytics"
is the thing — and sentence-level extraction reads neither, because the
announcement is in the TITLE and the buyer is in a different sentence from
the product. Wave 9 measured 9 of 15 real actions as "source missing the
information" and some of them were this shape: the document says it, one
sentence over.

WHY THE WINDOW IS SMALL AND NOT A PARAGRAPH
-------------------------------------------
A release-note index page is a list of unrelated announcements. Widening the
window until a buyer appears WILL find one — the page is full of them — and
it will belong to a different product. The window is therefore:

    heading, previous sentence, action sentence, next sentence

and it stops at a SECTION BOUNDARY. A neighbour that announces its own,
different action is a boundary: two announcements are two sections however
close together they sit, so an action can never borrow the buyer of the
announcement next to it.

WHAT THE CONTEXT MAY AND MAY NOT DO
-----------------------------------
It may supply a dimension the action's own sentence did not carry. It may
not supply the ACTION: an action still has to be announced by its own
sentence or its own heading, or a page's title would make every sentence
beneath it an announcement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

CONTRACT = "action_context.v1"

_SENTENCE = re.compile(r"(?<=[.!?])\s+")

#: A neighbour carrying one of these is announcing its OWN action, which
#: makes it a section of its own rather than context for this one.
_OWN_ANNOUNCEMENT = re.compile(
    r"\b(?:announc(?:ed|es|ing)|launch(?:ed|es|ing)|introduc(?:ed|es|ing)|"
    r"unveil(?:ed|s|ing)|releas(?:ed|es|ing)|expand(?:ed|s|ing))\b", re.I)

#: Navigation and boilerplate never describe the product above them.
_BOILERPLATE = re.compile(
    r"\b(?:cookie|privacy policy|terms of service|all rights reserved|"
    r"sign in|log in|subscribe|newsletter|follow us|contact sales|"
    r"skip to (?:main )?content)\b", re.I)


@dataclass(frozen=True)
class ActionContext:
    """One action's local neighbourhood, bounded and attributable."""
    action_id: str
    heading: str
    previous_sentence: str
    action_sentence: str
    next_sentence: str
    #: Why each neighbour was included or dropped. A context whose reasons
    #: are not inspectable is a paragraph with extra steps.
    provenance: Tuple[str, ...] = ()

    @property
    def window(self) -> str:
        """The text a dimension may be read from. Heading first: it is the
        most reliably on-topic thing on an entry page."""
        return " ".join(part for part in (
            self.heading, self.previous_sentence, self.action_sentence,
            self.next_sentence) if part)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "action_id": self.action_id,
            "heading": self.heading,
            "previous_sentence": self.previous_sentence,
            "action_sentence": self.action_sentence,
            "next_sentence": self.next_sentence,
            "provenance": list(self.provenance),
        }


def _usable(sentence: str) -> Tuple[bool, str]:
    text = (sentence or "").strip()
    if not text:
        return False, "absent"
    if _BOILERPLATE.search(text):
        return False, "boilerplate"
    if _OWN_ANNOUNCEMENT.search(text):
        return False, "announces its own action, so it is a section boundary"
    return True, "same section"


def build(document_text: str, action_sentence: str, *, action_id: str = "",
          heading: str = "", sibling_actions: int = 0
          ) -> Optional[ActionContext]:
    """Locate the action's sentence and take its immediate neighbours.

    `sibling_actions` is how many OTHER actions the same document announces.
    Above zero the document is an INDEX, and an index page's sentences are
    not context for one another — they are a list of unrelated
    announcements. Measured live, the window on Shopify's `/updates` page
    (7 actions) gave "Introducing JavaScript for Shopify Functions" the
    workflow `checkout` from the entry above it, and gave another action the
    buyer "Sidekick app extensionsApp store", which is two nav labels run
    together. Neither is a fact about the action it was attached to.

    Returns None when the sentence is not in the document, which is the
    honest answer: a context assembled from a sentence the document does not
    contain would be about a different document.
    """
    target = " ".join((action_sentence or "").split())
    if not target:
        return None
    if sibling_actions > 0:
        # The action stands on its own sentence, as it did before context
        # existed. This is a refusal, not a failure.
        return ActionContext(
            action_id=action_id, heading="", previous_sentence="",
            action_sentence=target, next_sentence="",
            provenance=(f"document announces {sibling_actions + 1} actions, "
                        f"so it is an index and its sentences are not "
                        f"context for one another",))
    body = " ".join((document_text or "").split())
    sentences = [s.strip() for s in _SENTENCE.split(body) if s.strip()]
    index = next((i for i, s in enumerate(sentences)
                  if s == target or target in s or s in target), None)
    if index is None:
        return None

    provenance: List[str] = []
    previous, following = "", ""

    if index > 0:
        ok, why = _usable(sentences[index - 1])
        provenance.append(f"previous: {why}")
        if ok:
            previous = sentences[index - 1]
    else:
        provenance.append("previous: absent")

    if index + 1 < len(sentences):
        ok, why = _usable(sentences[index + 1])
        provenance.append(f"next: {why}")
        if ok:
            following = sentences[index + 1]
    else:
        provenance.append("next: absent")

    head = " ".join((heading or "").split())
    if head and _BOILERPLATE.search(head):
        head, why = "", "boilerplate"
    provenance.append("heading: " + ("used" if head else "absent or refused"))

    return ActionContext(
        action_id=action_id, heading=head, previous_sentence=previous,
        action_sentence=target, next_sentence=following,
        provenance=tuple(provenance))


def summarise(contexts: Sequence[ActionContext]) -> dict:
    with_previous = sum(1 for c in contexts if c.previous_sentence)
    with_next = sum(1 for c in contexts if c.next_sentence)
    with_heading = sum(1 for c in contexts if c.heading)
    return {
        "contract": CONTRACT,
        "contexts": len(contexts),
        "with_previous_sentence": with_previous,
        "with_next_sentence": with_next,
        "with_heading": with_heading,
        "bounded_by_a_neighbouring_announcement": sum(
            1 for c in contexts
            if any("section boundary" in p for p in c.provenance)),
        "note": ("a neighbour that announces its own action is a boundary, "
                 "so an action can never borrow the buyer belonging to the "
                 "announcement next to it"),
    }
