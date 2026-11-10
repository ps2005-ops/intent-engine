"""Customer-facing absence: what may be said, and what must never be.

THE GOVERNING RULE (§0)
-----------------------
Absence must become useful intelligence, not silence. A customer who asked a
business question and received

    "No estimate was retrieved."
    "No competitor's account was retrieved."
    "No market expectation is measured here."

has been told the state of a retrieval attempt and nothing about their
decision. Those sentences terminate. There is no next line, nothing to weigh,
nothing to do — and they were the HEADLINE on three primary surfaces.

**AND ITS LIMIT, WHICH IS ABSOLUTE (§106).** "Never say no information" does
NOT mean invent information. It means exhaust `executive.resolution`'s ladder
— direct measure, contemporaneous proxy, structural inference, peer baseline,
bounded range — and, where the ladder genuinely ends, say what is not known,
what would settle it, and which decision it bears on. A fabricated figure is a
far worse outcome than the sentence this module exists to remove.

WHY A DETECTOR AND NOT A STYLE GUIDE
------------------------------------
Because the same defect came back three times in one previous cycle, from
three different producers, and each time it was invisible in a passing test
suite and obvious in a browser. A phrase list in a document is advice. A
detector that runs over RENDERED HTML is a gate, and it is the only form of
this rule that has ever held.

WHAT COUNTS AS A DEAD END
-------------------------
Not the words themselves — an analysis that never says what it does not know
is worse than one that does. A dead end is an absence phrase that is not
RESOLVED: no bounded finding, no next measurement, no decision it bears on,
within the same sentence or the one that follows. `adjudicate` decides that,
and it is deliberately conservative in the direction of flagging: a false
flag costs a minute of reading, and a missed one costs a customer.
"""
from __future__ import annotations

import dataclasses
import re
from html import unescape
from typing import List, Sequence, Tuple

CONTRACT = "customer_absence_guard.v1"

#: Phrases that announce an absence to a customer. Matched case-insensitively
#: on rendered TEXT, never on markup.
ABSENCE_PHRASES: Tuple[str, ...] = (
    "no information",
    "no estimate",
    "no competitor",
    "no evidence",
    "no result",
    "no strategic reading",
    "no market expectation",
    "no history",
    "no data",
    "not retrieved",
    "nothing was found",
    "nothing found",
    "unavailable",
    "did not run",
    "cannot say",
    "unable to determine",
    "could not be determined",
    "is not established",
    "not measured here",
    "no dated record",
    # Found live on the Full Analysis, which said "No market snapshot has
    # been published for this company, so there is no read on what investors
    # currently expect." None of the phrases above matched it — the sentence
    # names our integration rather than the customer's question, which is
    # exactly why it read as a dead end and exactly why it escaped a phrase
    # list written from the last cycle's defects.
    "no market snapshot",
    "no read on what",
    "no snapshot",
    "is not measured",
    "not established here",
)

#: What makes an absence RESOLVED rather than terminal. One of these must
#: appear in the same sentence or the next one.
#:
#: Every entry is a phrase that introduces a next step, a bound, or a decision
#: — never merely a softener. "Unfortunately" resolves nothing.
RESOLUTION_MARKERS: Tuple[str, ...] = (
    "what would",
    "would settle",
    "would resolve",
    "would draw",
    "would turn",
    "what it would take",
    "next measurement",
    "minimum viable",
    "so instead",
    "instead,",
    "what can be said",
    "bears on",
    "decision it affects",
    "modelled",
    "modeled",
    "benchmark",
    "bounded",
    "the range is",
    "open question",
    "connect",
    "supply",
    "which is why",
    "this is a limit of what was retrieved",
    "treat this as",
    "in its place",
    # An IMPERATIVE next step resolves an absence as well as a described one.
    # Found on the Full Analysis: "…or the second is an aspiration with no
    # evidence. Check that against the company before relying on the
    # analogy." The second sentence is exactly the action the reader needs
    # and none of the markers above matched it, because they were all
    # phrased as descriptions of a measurement rather than as instructions
    # to take one.
    "check that",
    "check whether",
    "verify",
    "before relying",
    "ask for",
    "request",
)

#: Sentences that name an INTERNAL state for an operator, not a finding for a
#: customer. Excluded from the sweep because they are not customer copy — an
#: operator console saying a credential is unavailable is being accurate.
INTERNAL_CONTEXTS: Tuple[str, ...] = (
    "credential", "api key", "env var", "environment variable",
    "scheduler", "worker", "commit", "deploy", "runtime", "http ",
)


@dataclasses.dataclass(frozen=True)
class DeadEnd:
    """One unresolved absence, with enough context to fix it."""
    phrase: str
    sentence: str
    following: str = ""

    def as_dict(self) -> dict:
        return {"phrase": self.phrase, "sentence": self.sentence,
                "following": self.following}


_TAG = re.compile(r"<[^>]+>")
_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WS = re.compile(r"\s+")


def visible_text(html: str) -> str:
    """The words a customer reads. Script, style and markup removed.

    `<style>` matters: the generated rail CSS contains selectors and would
    otherwise be swept for phrases, and a false flag in a stylesheet trains a
    reader to ignore this guard.
    """
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", str(html or ""))
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", unescape(text)).strip()


def sentences(text: str) -> List[str]:
    return [s.strip() for s in _SPLIT.split(text) if s.strip()]


def adjudicate(html: str, *, phrases: Sequence[str] = ABSENCE_PHRASES
               ) -> List[DeadEnd]:
    """Every unresolved absence in a rendered page. Empty is the pass state.

    An absence is resolved when its own sentence, or the next one, offers a
    bound, a next measurement or a decision. Both are consulted because the
    honest pattern is usually two sentences — "X was not retrieved. What would
    settle it is Y." — and requiring one sentence would push producers into
    worse prose to satisfy a checker.
    """
    lines = sentences(visible_text(html))
    found: List[DeadEnd] = []
    for index, sentence in enumerate(lines):
        low = sentence.lower()
        if any(marker in low for marker in INTERNAL_CONTEXTS):
            continue
        hit = next((p for p in phrases if p in low), None)
        if hit is None:
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        window = (low + " " + following.lower())
        if any(marker in window for marker in RESOLUTION_MARKERS):
            continue
        found.append(DeadEnd(phrase=hit, sentence=sentence,
                             following=following))
    return found


def headline_dead_end(html: str) -> List[DeadEnd]:
    """§43. An absence that is the MAIN MESSAGE of a page or a slide.

    Stricter than `adjudicate`: a heading has no following sentence to
    resolve it, so an absence phrase in an h1/h2 or a slide title is a dead
    end whatever the body says. A slide whose title is "we could not retrieve
    X" has already failed by the time the reader gets to the resolution.
    """
    out: List[DeadEnd] = []
    for match in re.finditer(r"(?is)<(h1|h2)[^>]*>(.*?)</\1>", str(html or "")):
        text = visible_text(match.group(2))
        low = text.lower()
        hit = next((p for p in ABSENCE_PHRASES if p in low), None)
        if hit is not None:
            out.append(DeadEnd(phrase=hit, sentence=text))
    return out


def report(pages: Sequence[Tuple[str, str]]) -> dict:
    """Sweep several (name, html) surfaces. The shape the guard asserts on."""
    findings = {}
    for name, html in pages or ():
        dead = adjudicate(html)
        heads = headline_dead_end(html)
        if dead or heads:
            findings[name] = {"unresolved": [d.as_dict() for d in dead],
                              "headline": [d.as_dict() for d in heads]}
    return {"contract": CONTRACT, "surfaces": len(pages or ()),
            "clean": not findings, "findings": findings}
