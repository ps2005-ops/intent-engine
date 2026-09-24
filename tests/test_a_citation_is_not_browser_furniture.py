"""A quotation may not be what a browser produced.

MEASURED LIVE at d1c9beae, on two of twenty-five captured cohorts. These are
the exact strings that reached customer surfaces:

    Coveo       the WHOLE citation, under the heading "Discusses the company
                directly":  "Loading. x Sorry to interrupt. CSS Error.
                Refresh."  -- a Salesforce Community shell, scraped before
                client-side rendering replaced it.
    Chainguard  "...The world's leading companies trust Chainguard. null."
                -- three true sentences and one that was the string `null`.

Those two shapes are why the rule works per SENTENCE. Refusing whole passages
would have left Chainguard's in; refusing Chainguard's whole passage would
throw away three true sentences to remove one artefact.

THE FLOOR IS CONDITIONAL, and that is the bug this file exists to keep out.
A first version applied a 40-character "is what's left still a citation?"
floor unconditionally, and deleted "exposes a surface others can build on"
(37 characters, no artefact in it) on four companies plus Cribl's "Flexibl
pricing to meet your needs." A rule that only cleans may shorten; it may not
delete text it had no objection to.
"""
import pytest

from intent_engine.adaptive import spans
from intent_engine.adaptive.spans import drop_rendering_artefacts as drop
from intent_engine.company_ingestion import provenance
from intent_engine.founder_brief import narrative

COVEO = "Loading. ×Sorry to interrupt. CSS Error. Refresh."
CHAINGUARD = ("Operationalize SOC 2 in real time to accelerate enterprise "
              "trust and reduce risk without slowing innovation. "
              "Continuously updated open source artifacts, built from "
              "source. The world’s leading companies trust Chainguard. "
              "null.")
#: Real, short, and containing nothing this rule objects to.
SHORT_REAL = ("exposes a surface others can build on",
              "Flexibl pricing to meet your needs.")


def test_the_live_coveo_citation_is_refused_entirely():
    assert drop(COVEO) == ""
    assert provenance._passage({"meta_description": COVEO}) == ""


def test_the_live_chainguard_citation_keeps_its_true_sentences():
    out = drop(CHAINGUARD)
    assert out, "the whole passage must not be thrown away"
    assert "null" not in out.lower().split(), out
    assert "Operationalize SOC 2" in out
    assert "Continuously updated open source artifacts" in out
    assert "trust Chainguard" in out


@pytest.mark.parametrize("text", SHORT_REAL)
def test_a_short_real_passage_is_not_deleted(text):
    """THE CONTROL. The floor may only fire after something was removed."""
    assert drop(text) == text, f"deleted a passage it had no objection to: {text!r}"


@pytest.mark.parametrize("artefact", [
    "null", "undefined", "NaN", "nil", "[object Object]",
    "Loading", "Loading...", "Please wait.", "Sorry to interrupt",
    "CSS Error", "Refresh.", "Enable JavaScript",
    "JavaScript is disabled", "JavaScript is required",
])
def test_a_sentence_that_is_only_furniture_goes(artefact):
    real = ("Netskope helps enterprises apply zero trust principles to data "
            "in motion across the cloud estate.")
    out = drop(f"{real} {artefact}.")
    assert out.strip() == real, f"{artefact!r} survived: {out!r}"


@pytest.mark.parametrize("keeper", [
    "The null hypothesis was rejected by the study.",
    "Refresh rates improved across the fleet this quarter.",
    "Our loading dock throughput doubled after the rebuild.",
    "We enable JavaScript developers to ship faster.",
])
def test_a_real_sentence_containing_the_word_is_kept(keeper):
    """The words are ordinary English. Only a sentence that is NOTHING BUT
    furniture goes -- the anchored pattern is the whole point."""
    assert drop(keeper) == keeper, keeper


def test_nothing_real_means_no_citation_at_all():
    assert drop("null. undefined. NaN.") == ""
    assert drop("") == ""


def test_the_remainder_must_still_be_a_citation():
    """A two-word remainder after an artefact was cut is not a quotation."""
    assert drop("Yes. null.") == ""


def test_the_founder_brief_citation_applies_the_rule():
    out = narrative._excerpt({"excerpt": CHAINGUARD})
    assert out and "null" not in out.lower().split(), out


def test_the_rule_is_anchored_not_a_substring_wall():
    """A substring wall is how this codebase produced three separate P0s."""
    assert spans._ARTEFACT.match("null")
    assert not spans._ARTEFACT.match("the null hypothesis")
    assert not spans._ARTEFACT.match("uploading sensitive data")
