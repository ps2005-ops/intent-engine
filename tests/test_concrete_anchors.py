"""Finding the concrete company facts a visible claim must be built from.

Sentry's live run retrieved a page titled "Sentry Acquires Codecov" -- a named
acquisition, the hardest fact in the whole run -- and the presentation opened
instead with "broadening from a focused tool toward being the place a team's
work is stored", which is the tool_to_system_of_record scaffold and would read
identically for Notion, Linear or Atlassian.

This module finds what the claim should have been made of. It is not yet wired
into the presentation; see docs/CONTINUATION.md for why and what remains.
"""
import pytest

from intent_engine.strategic_intelligence.concrete import (
    action_kind, clean_title, concrete_developments, descriptive_subjects,
    reads_as_taxonomy, select_founder_claim_anchor,
)


class _Obs:
    def __init__(self, oid, title, excerpt):
        self.observation_id = oid
        self.source_title = title
        self.excerpt = excerpt
        self.date = "2026-07-29"
        self.source_class = "company_owned"


SENTRY = [
    _Obs("o1", "About Sentry | Sentry", "Bugs aren't great."),
    _Obs("o2", "Sentry Acquires Codecov | Sentry", "Find current press releases."),
    _Obs("o3", "Application Performance Monitoring & Error Tracking | Sentry",
         "Application performance monitoring for developers."),
]


def test_the_acquisition_is_found_and_ranked_first():
    found = concrete_developments(SENTRY)
    assert found, "the hardest fact in the run was not found"
    assert found[0]["kind"] == "acquisition"
    assert "Codecov" in found[0]["title"]


@pytest.mark.parametrize("text,kind", [
    ("Acme Acquires Widgetco", "acquisition"),
    ("Acme raises Series C", "funding"),
    ("Introducing Acme Cloud", "launch"),
    ("Changes to our pricing", "pricing"),
    ("Acme partners with Initech", "partnership"),
    ("Acme appoints new CFO", "leadership"),
])
def test_named_actions_are_recognised(text, kind):
    assert action_kind(text) == kind


@pytest.mark.parametrize("text", [
    "About us", "Our mission", "Bugs aren't great. But your code can be.",
    "Contact", "Media resources",
    # A pricing PAGE is not an action. Every company has one, and matching it
    # handed the takeover to an adversarial fixture whose only qualifying
    # "development" was a page called "Hostile Co pricing".
    "Acme pricing and plans", "Pricing", "Plans", "Hostile Co pricing",
    # nor is marketing copy about expanding
    "We are expanding our team",
])
def test_pages_and_marketing_copy_are_not_mistaken_for_actions(text):
    assert action_kind(text) is None


def test_observations_work_as_records_or_as_dicts():
    """Observations arrive as records from the reasoning layer and as plain
    dicts once a report has been serialised."""
    as_dicts = [{"observation_id": o.observation_id,
                 "source_title": o.source_title, "excerpt": o.excerpt,
                 "date": o.date, "source_class": o.source_class}
                for o in SENTRY]
    assert concrete_developments(as_dicts)[0]["kind"] == "acquisition"
    assert descriptive_subjects(as_dicts)


def test_site_suffixes_are_stripped_from_subjects():
    subjects = [d["text"] for d in descriptive_subjects(SENTRY)]
    assert all("| Sentry" not in s for s in subjects)


@pytest.mark.parametrize("text", [
    "becoming the place a team's work is stored",
    "a system of record for the team",
    "matches the tool-to-system-of-record mechanism",
    "absorbing adjacent tools",
])
def test_ontology_vocabulary_is_recognised(text):
    assert reads_as_taxonomy(text), text


@pytest.mark.parametrize("text", [
    "Sentry Acquires Codecov",
    "Application performance monitoring for developers",
    "Pricing starts at $26 per month",
])
def test_company_specific_prose_is_not_flagged(text):
    assert not reads_as_taxonomy(text), text


def test_hyphenated_spellings_are_normalised():
    """Only "system of record" was matched, so "tool-to-system-of-record" --
    the spelling the reasoning layer actually emits -- reached a slide."""
    assert reads_as_taxonomy("the tool-to-system-of-record mechanism")
    assert reads_as_taxonomy("a system_of_record play")


# --- the takeover gate -----------------------------------------------------

def test_a_named_acquisition_earns_the_takeover():
    anchor = select_founder_claim_anchor(SENTRY, company="Sentry")
    assert anchor and anchor["kind"] == "acquisition"
    assert anchor["fact"] == "Sentry acquired Codecov."
    assert anchor["source"] == "concrete"


def test_ordinary_pages_do_not_earn_the_takeover():
    """The rule that protects thin and adversarial companies: only replace the
    fallback when there is a real fact strong enough to earn it."""
    ordinary = [_Obs("o1", "About Us | Bloom Dental", "A family dental practice."),
                _Obs("o2", "Contact | Bloom Dental", "Call us."),
                _Obs("o3", "Bloom Dental pricing", "Our fees.")]
    assert select_founder_claim_anchor(ordinary, company="Bloom Dental") == {}


def test_an_adversarial_pricing_page_does_not_earn_the_takeover():
    """hostile_co's only qualifying "development" was a page titled
    "Hostile Co pricing", which handed it a factual headline it had not
    earned and dropped it to FAILED_PRODUCT_QUALITY."""
    hostile = [_Obs("o1", "Hostile Co pricing", "Our plans."),
               _Obs("o2", "About Hostile Co", "Founded in 2021.")]
    assert select_founder_claim_anchor(hostile, company="Hostile Co") == {}


@pytest.mark.parametrize("title,expected", [
    ("Sentry Acquires Codecov | Sentry Blog", "Sentry acquired Codecov."),
    ("Press Release: Acme Partners With Initech", "Acme partnered with Initech."),
    ("Stripe Launches Tap to Pay on iPhone", "Stripe launched Tap to Pay on iPhone."),
    # a title that already opens on a gerund reads fine as one
    ("Introducing GitLab Duo | GitLab", "Introducing GitLab Duo."),
])
def test_titles_become_sentences_without_mangling_names(title, expected):
    """Proper nouns and acronyms survive; the headline verb goes to the past."""
    assert clean_title(title, "Sentry") == expected
