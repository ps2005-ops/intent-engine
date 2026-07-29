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
    action_kind, concrete_developments, descriptive_subjects,
    reads_as_taxonomy,
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
    ("Acme pricing and plans", "pricing"),
    ("Acme partners with Initech", "partnership"),
    ("Acme appoints new CFO", "leadership"),
])
def test_named_actions_are_recognised(text, kind):
    assert action_kind(text) == kind


@pytest.mark.parametrize("text", [
    "About us", "Our mission", "Bugs aren't great. But your code can be.",
    "Contact", "Media resources",
])
def test_descriptions_are_not_mistaken_for_actions(text):
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
