"""The evidence must establish what is being contested. Nothing may hand it over.

The failure this closes: 18 RELEVANT pairs, all Salesforce AI-agent posts,
every one "contesting an e-commerce platform" because the fetching harness
had labelled them that way. The system was narrating its own assumption back
to itself.
"""
from __future__ import annotations

import inspect

import pytest

from intent_engine.market import competitive_objects as CO


def pull(text, actor="Salesforce"):
    return CO.extract(text, action_id="a1", actor=actor, source="s",
                      created_at="2026-08-08")


# --- there is no way to hand an object in --------------------------------

def test_no_parameter_supplies_an_object():
    """The whole point: an object from outside the document is not evidence.

    `action_type` joined the signature in wave 8. It is not a way in: it
    selects which dimensions this KIND of action must establish and
    contributes no text of its own. The test below proves that separately.
    """
    params = set(inspect.signature(CO.extract).parameters)
    assert params == {"span", "action_id", "actor", "source", "created_at",
                      "evidence_ids", "action_type"}
    assert "competitive_object" not in params
    assert "object" not in params
    assert "relationship_object" not in params
    assert "buyer" not in params


@pytest.mark.parametrize("action_type", ["", "PRICE_CHANGE", "PRODUCT_LAUNCH",
                                         "MIGRATION_PROGRAMME", "PARTNERSHIP",
                                         "MARKET_ENTRY"])
def test_action_type_can_only_make_the_bar_higher(action_type):
    """Every value the object carries is a span cut out of the document.

    Whatever `action_type` is passed, no text appears that the sentence did
    not contain, and a type that requires MORE dimensions can only downgrade
    the standing — never invent the dimension it is asking for.
    """
    text = "Salesforce today launched Commerce Cloud checkout for enterprise retailers."
    got, _ = CO.extract(text, action_id="a1", actor="Salesforce", source="s",
                        created_at="2026-08-08", action_type=action_type)
    if got is None:
        return
    low = text.lower()
    for value in (got.buyer, got.workflow, got.substitute, got.geography):
        assert not value or value.lower() in low
    # MIGRATION_PROGRAMME demands a substitute this sentence does not name,
    # so it must NOT be established — the requirement cannot fill itself.
    if action_type == "MIGRATION_PROGRAMME":
        assert got.standing != CO.ESTABLISHED
        assert "substitute" in got.missing


def test_a_required_dimension_is_never_filled_by_requiring_it():
    """The break this guards: 'MIGRATION needs a substitute' must not become
    'MIGRATION has a substitute'."""
    got, _ = CO.extract(
        "We launched a migration programme for enterprise merchants.",
        action_id="a1", actor="BigCommerce", source="s",
        created_at="2026-08-08", action_type="MIGRATION_PROGRAMME")
    assert got.substitute == ""
    assert got.standing == CO.PARTIAL
    assert not got.is_usable


def test_the_module_never_reads_the_universe_or_the_curated_list():
    source = inspect.getsource(CO)
    assert "default_universe" not in source
    assert ".competitors" not in source
    assert "peer_group" not in source


# --- two axes, or it locates nothing --------------------------------------

ESTABLISHING = [
    ("product plus buyer",
     "Salesforce today launched Commerce Cloud checkout for enterprise "
     "retailers."),
    ("priced tier plus buyer",
     "Shopify cut its Plus pricing for mid-market merchants everywhere."),
    ("migration plus buyer",
     "Adobe introduced a migration offer for enterprise merchants "
     "replatforming from Magento."),
    ("workflow plus buyer",
     "Snowflake announced warehouse workloads for financial-services "
     "customers."),
    ("budget plus buyer",
     "Stripe bundles billing into the platform subscription budget for SMB "
     "merchants."),
]


@pytest.mark.parametrize("label,text", ESTABLISHING,
                         ids=[c[0] for c in ESTABLISHING])
def test_two_axes_establish_an_object(label, text):
    got, evidence = pull(text)
    assert got.standing == CO.ESTABLISHED, got.as_dict()
    assert got.buyer and (got.workflow or got.use_case)
    assert got.is_usable
    assert evidence.matched_span
    assert got.source_spans


# --- the who-axis, as live pricing pages actually write it ----------------
#
# Wave 7 required a qualifier from a closed list AND a noun from a closed
# list. Every real pricing page failed it: "for solo entrepreneurs" and "for
# small teams" carry qualifiers nobody listed. The discriminating test is the
# HEAD NOUN — whether the phrase names somebody who can hold a budget.

BUYER_PHRASES = [
    ("solo entrepreneurs", "Basic. CA$37/mo. For solo entrepreneurs.",
     "solo entrepreneurs"),
    ("small teams", "Grow. CA$99/mo. For small teams.", "small teams"),
    ("complex businesses", "Plus. from CA$3,400/mo. For complex businesses.",
     "complex businesses"),
    ("segment without for",
     "Core. New businesses with up to $30K in annual sales. $29.",
     "New businesses"),
]


@pytest.mark.parametrize("label,text,expected", BUYER_PHRASES,
                         ids=[c[0] for c in BUYER_PHRASES])
def test_a_buyer_is_recognised_by_its_head_noun(label, text, expected):
    got, _ = pull(text, actor="BigCommerce")
    assert got is not None and got.buyer.lower() == expected.lower()


NOT_A_BUYER = [
    # A benefit wearing a buyer's grammar. "reach" is not somebody.
    ("benefit noun", "Advanced. CA$389/mo. For global reach."),
    ("abstract noun", "Enterprise. Custom pricing. For the future of retail."),
    # Second person addresses the reader and names no segment.
    ("second person", "New pricing for your business is now available."),
    ("our customers", "We cut prices for our customers this quarter."),
    # A bare plural with no scale marker is every company on earth.
    ("bare plural", "The company is committed to helping businesses grow."),
]


@pytest.mark.parametrize("label,text", NOT_A_BUYER,
                         ids=[c[0] for c in NOT_A_BUYER])
def test_a_benefit_or_a_reader_is_not_a_buyer(label, text):
    """These are the phrases that would make every vendor page establish a
    buyer, which is the same as no page establishing one."""
    got, _ = pull(text, actor="BigCommerce")
    assert got is None or not got.buyer
    assert got is None or got.standing != CO.ESTABLISHED


def test_the_substitute_is_the_named_incumbent():
    got, _ = CO.extract(
        "Easily migrate from Shopify and Adobe Commerce with our migration "
        "app for growing businesses.",
        action_id="a1", actor="BigCommerce", source="s",
        created_at="2026-08-08", action_type="MIGRATION_PROGRAMME")
    assert got.substitute == "Shopify"
    assert got.standing == CO.ESTABLISHED


def test_an_enumeration_names_every_incumbent_not_one_run_together():
    """"Shopify and Adobe Commerce" is not an incumbent; it is two."""
    got, _ = CO.extract(
        "Easily migrate from Shopify, WooCommerce and Adobe Commerce with "
        "our migration app for growing businesses.",
        action_id="a1", actor="BigCommerce", source="s",
        created_at="2026-08-08", action_type="MIGRATION_PROGRAMME")
    assert got.substitute == "Shopify"
    assert got.substitutes == ("Shopify", "WooCommerce", "Adobe Commerce")
    assert all(" and " not in s for s in got.substitutes)


def test_an_effective_date_is_read_off_the_document():
    got, _ = CO.extract(
        "Starting June 1, 2026, BigCommerce is updating Scale pricing for "
        "high-volume businesses.", action_id="a1", actor="BigCommerce",
        source="s", created_at="2026-08-08", action_type="PRICE_CHANGE")
    assert got.effective_date == "June 1, 2026"


NOT_ESTABLISHING = [
    ("bare launch", "Salesforce launches Agentforce."),
    ("AI announcement",
     "Salesforce today announced new AI capabilities across the platform."),
    ("keynote",
     "Our keynote explored the future of enterprise software and innovation."),
    ("corporate prose",
     "The company is committed to helping businesses grow with technology."),
    ("unrelated partnership",
     "Shopify partnered with a logistics provider on an unrelated project."),
    ("stock article",
     "Shares of Shopify rose after the announcement this morning."),
]


@pytest.mark.parametrize("label,text", NOT_ESTABLISHING,
                         ids=[c[0] for c in NOT_ESTABLISHING])
def test_generic_language_never_establishes_an_object(label, text):
    got, _ = pull(text)
    assert got is None or got.standing != CO.ESTABLISHED
    assert got is None or not got.is_usable


def test_a_product_with_no_buyer_is_partial_not_unknown():
    """Readable, not usable. Forcing it either way loses information.

    `missing` names DIMENSIONS from wave 8 on, so the gap reads "who" rather
    than "buyer" — the same gap in the vocabulary the requirement is stated
    in.
    """
    got, _ = pull("Salesforce launches Agentforce.")
    assert got.standing == CO.PARTIAL
    assert CO.WHO.lower() in got.missing
    assert CO.WHAT in got.dimensions_present


def test_a_vacuous_word_is_not_a_product():
    got, _ = pull("Salesforce today announced Commerce for everyone.")
    assert got is None or got.use_case.lower() not in CO._VACUOUS


def test_the_actors_own_name_is_not_the_object():
    got, _ = pull("Salesforce launches Salesforce.", actor="Salesforce")
    assert got is None or got.use_case != "Salesforce"


def test_precision_on_the_shaped_corpus_is_total():
    established = sum(1 for _, t in ESTABLISHING
                      if (pull(t)[0] or CO).__dict__.get("standing")
                      == CO.ESTABLISHED)
    false_positives = sum(
        1 for _, t in NOT_ESTABLISHING
        if (pull(t)[0] is not None and pull(t)[0].standing == CO.ESTABLISHED))
    assert false_positives == 0
    assert established == len(ESTABLISHING)


# --- overlap is conservative ---------------------------------------------

def test_a_named_workflow_match_is_strong():
    got, _ = pull("Salesforce launched checkout for enterprise retailers.")
    kind, why = CO.overlap(got, "checkout infrastructure")
    assert kind == CO.STRONG
    assert "same thing" in why


def test_an_adjacent_workflow_never_reaches_strong():
    got, _ = pull("Snowflake announced warehouse workloads for "
                  "financial-services customers.")
    kind, why = CO.overlap(got, "enterprise commerce platform")
    assert kind in (CO.ADJACENT, CO.NONE)
    if kind == CO.ADJACENT:
        assert "never builds an interaction" in why


def test_shared_vacuous_words_do_not_create_overlap():
    """Sharing "enterprise" and "platform" is sharing nothing. Asserting
    only "not STRONG" would pass with the vacuous filter removed, since
    those words produce ADJACENT rather than STRONG either way."""
    got, _ = pull("Salesforce launched checkout for enterprise retailers.")
    kind, _ = CO.overlap(got, "enterprise platform technology")
    assert kind == CO.NONE


def test_no_object_means_no_overlap():
    kind, why = CO.overlap(None, "E-commerce platform")
    assert kind == CO.NONE


# --- the live corpus ------------------------------------------------------

def test_the_live_actions_establish_nothing_and_that_is_the_finding():
    """Five real actions survive the announcement patterns; none names both
    a buyer and a workflow, so none can be shown to contest anything."""
    import json
    import pathlib

    measured = pathlib.Path(
        "/private/tmp/claude-501/-Users-prathamsharma/"
        "88a4600b-3357-43cf-9a33-f6b392f47edf/scratchpad/"
        "actions_measured.json")
    if not measured.exists():                          # pragma: no cover
        return
    actions = json.loads(measured.read_text())["actions"]
    usable = [a for a in actions
              if (CO.extract(a["span"], action_id=a["action_id"],
                             actor=a["actor"], source="s",
                             created_at=a["event_time"])[0] or CO
                  ).__dict__.get("standing") == CO.ESTABLISHED]
    assert usable == []
