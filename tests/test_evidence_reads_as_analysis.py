"""Supporting evidence must explain itself.

Every case here was read off the deployed product, not inferred from code.
"""
import pytest

from intent_engine.strategic_intelligence.observations import (
    _SIGNAL_LABEL, _SIGNAL_RELEVANCE, _NEUTRAL_LABEL, derive_observations,
    observation_sentence,
)


def _doc(sid, title, text, url="https://sentry.io/blog", **kw):
    base = dict(source_id=sid, title=title, text_content=text, final_url=url,
                meta_description="", source_type="blog",
                source_class="company_owned", freshness="CURRENT")
    base.update(kw)
    return base


# --- the defect, as it was rendered ----------------------------------------

def test_the_company_is_the_subject_not_the_page_title():
    """LIVE on Sentry's brief, under "What supports it":

        "API Authentication Bypass | Sentry Blog exposes a surface others
         can build on"

    The subject of the sentence was the headline of the page the signal was
    found on. It reads as though a blog post were doing the positioning, and
    on Linear it produced "Linear customers publishes named customers" --
    a plural subject with a singular verb, from the title "Linear customers".
    """
    docs = [_doc("s1", "API Authentication Bypass | Sentry Blog",
                 "The Sentry API supports issues, projects and webhooks for "
                 "developers building integrations on our platform.")]
    observations = derive_observations(docs, company="Sentry")
    assert observations, "no observation derived"
    text = observations[0].text
    assert text.startswith("Sentry "), text
    assert "API Authentication Bypass" not in text
    assert "| Sentry Blog" not in text


def test_every_supporting_sentence_says_why_it_matters():
    docs = [_doc("s1", "Sentry docs",
                 "The Sentry API supports issues, projects and webhooks for "
                 "developers building integrations on our platform.")]
    text = derive_observations(docs, company="Sentry")[0].text
    # the observation, then the consequence -- not the observation alone
    assert "," in text and text.endswith(".")
    assert len(text.split()) > 12, f"no reasoning in: {text}"


@pytest.mark.parametrize("signal", sorted(set(_SIGNAL_LABEL) | set(_NEUTRAL_LABEL)))
def test_every_signal_states_a_consequence(signal):
    """Five of twenty-six had a clause; the rest fell back to "retrieved
    evidence", which is not a reason. A signal with no stated consequence
    produces a bullet that restates itself and stops."""
    assert signal in _SIGNAL_RELEVANCE, \
        f"{signal} has no stated consequence, so its bullet cannot say why " \
        f"it matters"


def test_a_signal_with_no_consequence_stops_cleanly():
    """The clause is dropped, never faked. "which is a strategic signal" is
    the template wording this product exists to avoid."""
    sentence = observation_sentence("Acme", "no_such_signal", "does a thing")
    assert sentence == "Acme does a thing."


def test_the_sentence_is_not_a_title_glued_to_a_label():
    sentence = observation_sentence("Acme", "consolidation",
                                    _NEUTRAL_LABEL["consolidation"])
    assert sentence.startswith("Acme positions itself as")
    assert sentence.endswith(".")
    assert sentence.count(".") == 1, "one claim, one sentence"
