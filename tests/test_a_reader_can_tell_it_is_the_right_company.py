"""Two defects found live on the 25, both about what a reader is shown.

Neither could have come from a fixture: one needed a company whose legal
name shares no word with its product name, the other needed a real sentence
long enough to be cut.
"""
from __future__ import annotations

from intent_engine.adaptive import spans
from intent_engine.company_ingestion.entities import REGISTRY
from intent_engine.company_ingestion.name_entry import _recognisable


def _profile(entity_id):
    return next(p for p in REGISTRY if p.entity_id == entity_id)


# --- the name a reader typed ------------------------------------------------

def test_a_legal_name_sharing_no_word_with_the_typed_name_carries_it():
    """MEASURED LIVE on 1Password (bbb75261).

    A person typed "1Password" and every heading read "AgileBits Inc." --
    correct, and sharing not one word with what they typed. The only clue
    the right company had been opened was the domain in small type.
    """
    shown = _recognisable(_profile("onepassword"))
    assert "1Password" in shown, shown
    assert "AgileBits" in shown, "the legal entity must not be dropped"


def test_a_legal_name_that_already_carries_the_typed_word_is_left_alone():
    """The condition is a SHARED TOKEN, not a list of exceptions."""
    for entity_id in ("rubrik", "descartes", "okta", "motive"):
        shown = _recognisable(_profile(entity_id))
        assert "(" not in shown, f"{entity_id} was decorated unnecessarily: {shown}"


def test_a_corporate_suffix_alone_does_not_count_as_sharing():
    """"Inc." is in every legal name and makes none of them recognisable."""
    class P:
        legal_name = "Zeta Holdings Inc."
        common_name = "Quill Inc."
    assert "(Quill Inc.)" in _recognisable(P())


# --- the end of a quotation -------------------------------------------------

def test_a_truncated_quote_does_not_end_on_a_joining_word():
    """MEASURED LIVE on Netskope (bbb75261).

        "My job combines the usual CISO responsibilities alongside daily
         self and"

    The cut was at a word boundary, which is what `trim_to_word` promised.
    A word boundary is not a grammatical one.
    """
    body = ("Being CISO for a security technology vendor can be an "
            "interesting position My job combines the usual CISO "
            "responsibilities alongside daily self and team development "
            "across every region we operate in")
    # 95 is where the cut LANDS on a joining word for this sentence.
    # At 140 it lands on 'daily' and the defect cannot appear, which is
    # how the first version of this test passed against broken code.
    out = spans.trim_to_word(body, 95)
    stripped = out.rstrip(" …").rstrip()
    last = stripped.split()[-1].lower().strip(",;:")
    assert last not in spans._DANGLING, f"quote ends on {last!r}: {out!r}"


def test_the_dangling_trim_does_not_eat_a_whole_quote():
    body = "and of the to with " * 20
    assert spans.trim_to_word(body, 60) in ("", " …", "…")


def test_a_quote_that_fits_is_returned_unchanged():
    body = "Netskope secures data wherever it goes."
    assert spans.trim_to_word(body, 400) == body
