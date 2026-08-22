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


# --- the classification has to be ACTED ON ---------------------------------
#
# `entity_type_of` typed the heading correctly and NOTHING READ THE ANSWER:
# `qualify` had no arm for CATEGORY_OR_PRACTICE, so it fell through to the
# ordinary company path and `may_contest` came back True. Goldman's live
# introduction read "contested directly by Banking Supervision and
# Compensation Practices" BOTH before the classifier was fixed and after --
# a classification nothing acts on is not a repair.

from intent_engine.executive.competitive_qualification import (        # noqa: E402
    CATEGORY_OR_PRACTICE_STATE, DIRECT_COMPETITOR, qualify,
)

_GOLDMAN = ("We compete with Banking Supervision and Compensation Practices "
            "and with JPMorgan Chase for institutional clients.")


def test_an_activity_may_not_contest():
    for name in ("Banking Supervision", "Compensation Practices"):
        q = qualify(candidate=name, evidence=_GOLDMAN, subject="Goldman")
        assert q.qualification_state == CATEGORY_OR_PRACTICE_STATE, name
        assert q.may_contest is False, name


def test_the_real_rival_in_the_same_sentence_still_contests():
    """THE CONTROL, and it must be able to fail."""
    q = qualify(candidate="JPMorgan Chase", evidence=_GOLDMAN,
                subject="Goldman")
    assert q.qualification_state == DIRECT_COMPETITOR
    assert q.may_contest is True


def test_an_activity_is_routed_not_deleted():
    """§6: it is a real fact about a bank, under the right heading."""
    q = qualify(candidate="Banking Supervision", evidence=_GOLDMAN,
                subject="Goldman")
    assert q.section == "Regulation and operating practice", q.section


def test_the_finder_returns_only_the_actor():
    """END TO END, through the producer that fed the live sentence."""
    from intent_engine.external_intel.competitor_finder import find_competitors
    documents = [{"text": _GOLDMAN * 4, "observation_id": "o1",
                  "source_title": "SEC 10-K",
                  "source_class": "investor_material", "date": "2026-02-25"}]
    names = [c.name for c in (find_competitors(
        documents, subject="The Goldman Sachs Group, Inc.") or ())]
    assert names == ["JPMorgan Chase"], names
