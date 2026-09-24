"""One rule, four producers: a shortened quotation ends on an idea.

MEASURED LIVE. At 591041b0 the Netskope evidence page carried

    "Being CISO for a security technology vendor can be an interesting
     position. My job combines the usual CISO responsibilities alongside
     daily self and"

and `EVIDENCE_NO_BROKEN_SPANS` was the single failing gate in a
twenty-five company qualification. `adaptive.spans.trim_to_word` had
refused exactly this shape since bbb75261 -- the quote simply never reached
it, because three other places shorten a reader-facing quotation and each
had its own arithmetic.

TWO FACTS THIS FILE PINS, because the first one alone would have missed it:

  1. every producer applies the rule, and
  2. the rule is about the text the READER is shown, not about who cut it.
     That Netskope passage was 148 characters against a 320-character
     budget: nothing in this product truncated it. The publisher's own meta
     description ended on the conjunction, and a producer that only
     policed its own cuts would have printed it again.
"""
import inspect
import re

import pytest

from intent_engine.adaptive import spans
from intent_engine.adaptive.spans import elide, end_on_an_idea, trim_to_word
from intent_engine.company_ingestion import provenance
from intent_engine.founder_brief import narrative
from intent_engine.strategic_intelligence import brief

#: The live defect, byte for byte off the captured evidence page.
NETSKOPE = ("Being CISO for a security technology vendor can be an "
            "interesting position. My job combines the usual CISO "
            "responsibilities alongside daily self and")


def _last_word(text):
    words = str(text).rstrip(" …").split()
    return words[-1].lower().strip(",;:") if words else ""


# --------------------------------------------------------------------- 1
def test_the_live_netskope_passage_no_longer_ends_on_a_conjunction():
    out = provenance._passage({"meta_description": NETSKOPE})
    assert out, "the passage must still be shown -- a source removed is a " \
                "source the reader cannot check"
    assert _last_word(out) not in spans._DANGLING, out
    assert out.endswith("…"), \
        "the publisher's text was cut, and the reader has to be told"
    assert out.startswith("Being CISO for a security technology vendor")


def test_a_whole_passage_inside_the_budget_is_not_decorated():
    """The mirror image: an ellipsis on complete text is a false claim."""
    whole = ("Netskope helps enterprises apply zero trust principles to "
             "data in motion across the cloud estate.")
    assert provenance._passage({"meta_description": whole}) == whole


def test_an_over_budget_passage_is_cut_by_grammar_not_arithmetic():
    body = "Netskope sells to enterprises " * 40 + "and"
    out = provenance._passage({"meta_description": body})
    assert len(out) <= provenance.MAX_PASSAGE + 2
    assert _last_word(out) not in spans._DANGLING, out
    assert not re.search(r"[A-Za-z]…$", out), \
        "a character slice can end mid-word; trim_to_word must not"


# --------------------------------------------------------------------- 2
def test_the_executive_brief_marks_a_sentence_it_cut():
    out = brief.fit_to_words("word " * 100, 10)
    assert out.endswith("…"), out
    assert len(out.split()) == 11


def test_the_founder_brief_citation_ends_on_an_idea():
    body = " ".join(["alpha beta gamma delta epsilon zeta eta theta"] * 8) + " and"
    out = narrative._excerpt({"excerpt": body})
    assert _last_word(out) not in spans._DANGLING, out


# --------------------------------------------------------------------- 3
#: A CLOSED LIST OF EXAMPLES IS NOT A TEST OF A RULE (1b5689f6). Every word
#: the rule claims to govern is tried against every producer that shortens
#: a quotation, so adding a word to `_DANGLING` without teaching a producer
#: about it fails here rather than on a customer's screen.
@pytest.mark.parametrize("joiner", sorted(spans._DANGLING))
def test_no_producer_leaves_the_reader_holding_a_joining_word(joiner):
    tail = f"the company continued to invest across the estate {joiner}"
    long_tail = " ".join(["alpha beta gamma delta epsilon zeta"] * 8) + " " + joiner

    for label, out in (
        ("provenance._passage",
         provenance._passage({"meta_description": "Some real sentence. " + tail})),
        ("narrative._excerpt", narrative._excerpt({"excerpt": long_tail})),
        ("brief.fit_to_words", brief.fit_to_words(long_tail, 12)),
        ("spans.trim_to_word", trim_to_word(tail + " " + "x" * 400, 60)),
        ("spans.elide", elide(tail)),
    ):
        assert _last_word(out) not in spans._DANGLING, f"{label}: {out!r}"


# --------------------------------------------------------------------- 4
#: STRUCTURAL, AND IT READS THE CODE (not a comment about the code). A
#: fifth producer that restates the arithmetic instead of importing the
#: rule is the way this defect arrived, so the shape itself is refused.
_PRODUCERS = (provenance._passage, narrative._excerpt, brief.fit_to_words)


@pytest.mark.parametrize("fn", _PRODUCERS, ids=lambda f: f.__qualname__)
def test_a_producer_calls_the_shared_rule_rather_than_restating_it(fn):
    src = inspect.getsource(fn)
    calls = re.findall(r"\b(_?elide|end_on_an_idea|trim_to_word)\s*\(", src)
    assert calls, f"{fn.__qualname__} shortens a quotation without the rule"
    # the tell of a restatement: building the marker out of a literal
    assert not re.search(r'\+\s*"\s*(…|\\u2026)"', src), \
        f"{fn.__qualname__} appends its own ellipsis instead of using elide()"


def test_the_rule_is_one_function_with_one_definition():
    """`end_on_an_idea` and `_drop_dangling` are the same rule, not two."""
    assert end_on_an_idea("ending on the") == spans._drop_dangling("ending on the")
    # BOTH trailing joiners go: "on" is as much a dangling word as "the",
    # so the rule keeps popping until the quote ends on something said.
    assert end_on_an_idea("ending on the") == "ending"
