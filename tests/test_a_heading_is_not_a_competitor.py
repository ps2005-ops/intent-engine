"""A filing heading may not be rendered as the company's rival.

MEASURED LIVE on cb9e6b7, on the introduction a Goldman Sachs customer reads:

    "contested directly by Banking Supervision and Compensation Practices"

That is an Item heading from the 10-K's regulatory section. It reached the
page because every discriminator in this module reads the CLAUSE, and when
the clause carries no regulatory cue the name's own words decide -- so the
heading was typed FINANCIAL_INSTITUTION on the strength of "Banking", and
"Risk Management and Internal Controls" was typed COMPANY on nothing at all.

The test is MORPHOLOGICAL, not another entity stoplist: this module's history
records three live rounds in which word lists were defeated within a deploy,
because headings are built from the same vocabulary as the list. English
process nouns end in a small closed set of suffixes, and a phrase whose
content words are all of that form names an activity, not an actor.
"""
import pytest

from intent_engine.executive.competitive_qualification import (
    ENTITY_CATEGORY, ENTITY_COMPANY, entity_type_of, names_an_activity,
)

#: Real firms, several of them measured on live introductions.
ACTORS = (
    "JPMorgan Chase", "Morgan Stanley", "Bank of America", "Komatsu",
    "Applied Materials", "Under Armour", "Texas Instruments", "Boeing",
    "Deere & Company", "Wells Fargo Equipment Finance Inc.", "Corning",
    "Advanced Micro Devices", "Samsung Electronics", "Li Ning",
)
#: Headings and section titles.
ACTIVITIES = (
    "Banking Supervision and Compensation Practices",
    "Risk Management and Internal Controls",
    "Compensation Practices",
    "Regulation and Supervision",
    "Information Technology Management",
    "Environmental Remediation Obligations",
)


@pytest.mark.parametrize("name", ACTORS)
def test_a_real_firm_is_never_refused(name):
    """THE CONTROL, and it must be able to fail.

    "Li Ning" is NIKE's rival and is on its live introduction. "Ning" ends in
    -ing, and a first version of this rule refused the company outright --
    which is a worse defect than the heading it was written to remove.
    """
    assert names_an_activity(name) is False, name


@pytest.mark.parametrize("name", ACTIVITIES)
def test_a_heading_is_named_as_an_activity(name):
    assert names_an_activity(name) is True, name


def test_the_live_defect_is_typed_as_a_category():
    kind, why = entity_type_of(
        "Banking Supervision and Compensation Practices",
        "We compete with Banking Supervision and Compensation Practices.")
    assert kind == ENTITY_CATEGORY, (kind, why)


def test_a_real_rival_in_the_same_clause_is_still_a_company():
    kind, _why = entity_type_of(
        "JPMorgan Chase", "We compete with JPMorgan Chase for clients.")
    assert kind == ENTITY_COMPANY


def test_a_corporate_designator_settles_it_immediately():
    """A firm is a firm whatever its nouns look like."""
    assert names_an_activity("Compensation Management Solutions Inc.") is False
    assert names_an_activity("Supervision Holdings plc") is False


def test_a_single_word_is_never_an_activity():
    """One word carries no phrase structure to read."""
    for name in ("Banking", "Supervision", "Compensation"):
        assert names_an_activity(name) is False, name
