"""A source family is integrated on measured yield, never on how it sounded.

Everything here runs offline against injected fixtures. The live numbers are
recorded in the checkpoint; what these tests hold is the contract — that a
closed family cannot be re-measured, that a keyword hit is not an identity,
that an award is not a dependence, and that the precision fixes which took
the prose families from ~40% to ~90% real edges stay fixed.
"""
from __future__ import annotations

import pytest

from intent_engine.market import actor_relationships as AR
from intent_engine.market import counterparty_sources as CS
from intent_engine.market import customer_case_studies as CC
from intent_engine.market import gov_awards as GA
from intent_engine.market import partnership_releases as PR


def award(recipient="CATERPILLAR INC", agency="Department of Defense",
          sub="Defense Logistics Agency", start="2025-05-21",
          end="2026-07-31", award_id="SPE8EC25F0653"):
    return CS.Document(
        document_id=f"usaspending:{award_id}", family=CS.GOVERNMENT_AWARD,
        subject="caterpillar", title="", text="D9R TRACTOR DOZER",
        url=f"https://www.usaspending.gov/award/{award_id}",
        published_at=start,
        fields={"recipient": recipient, "agency": agency, "sub_agency": sub,
                "amount": "97125952.0", "start_date": start, "end_date": end})


def release(text, subject="stripe", title="Stripe announces"):
    return CS.Document(
        document_id="release:https://stripe.com/newsroom/x",
        family=CS.PARTNERSHIP_RELEASE, subject=subject, title=title,
        text=text, url="https://stripe.com/newsroom/x",
        published_at="2026-08-07", fields={"publisher_host": "stripe.com"})


def case_study(title, text, subject="shopify"):
    return CS.Document(
        document_id="case_study:https://www.shopify.com/customers/x",
        family=CS.CUSTOMER_CASE_STUDY, subject=subject, title=title,
        text=text, url="https://www.shopify.com/customers/x",
        published_at="2026-08-07",
        fields={"publisher_host": "www.shopify.com"})


# --- the settled families stay settled -----------------------------------

def test_a_closed_family_cannot_be_re_measured():
    for family in CS.CLOSED_FAMILIES:
        with pytest.raises(ValueError, match="settled"):
            CS.measure(family, subjects=[], fetch=lambda *a: [],
                       extract=lambda *a: ((), {}, {}))


def test_the_closed_families_carry_their_measurement():
    assert "3,959" in CS.CLOSED_FAMILIES["periodic_report"]
    assert "7,247" in CS.CLOSED_FAMILIES["current_report"]


# --- identity: a keyword hit is not a company ----------------------------

def test_a_one_token_alias_may_not_claim_a_longer_name():
    """`Linear Minerals Corp.` once satisfied the alias `Linear`."""
    assert CS.resolution("Linear Minerals Corp.", ["Linear"]) == CS.NO_MATCH
    assert CS.resolution("Linear", ["Linear"]) == CS.EXACT


def test_a_corporate_suffix_does_not_defeat_a_match():
    assert CS.resolution("CATERPILLAR INC", ["Caterpillar"]) == CS.EXACT
    assert CS.resolution("Shopify Inc.", ["Shopify"]) == CS.EXACT


def test_a_subsidiary_resolves_but_is_labelled_as_one():
    got = CS.resolution("AMERICA MOVIL PERU SAC", ["America Movil"])
    assert got == CS.SUBSIDIARY_OR_DIVISION
    assert CS.resolution("Johnson & Johnson Health Care Systems Inc.",
                         ["Johnson & Johnson"]) == CS.SUBSIDIARY_OR_DIVISION


def test_an_unrelated_company_does_not_resolve():
    assert not CS.resolves_to("Toyota Industries Corporation", ["Honda"])
    assert not CS.resolves_to("ACME Widgets", ["Caterpillar"])


# --- an award is an event, not a dependence ------------------------------

def test_an_award_admits_sells_to_and_nothing_stronger():
    (got,), refused, counts = GA.extract(award(), "caterpillar",
                                         ["Caterpillar"])
    assert got.predicate == AR.SELLS_TO
    assert got.predicate != AR.DEPENDS_ON
    assert got.object_kind == AR.GOVERNMENT
    assert counts["identity_resolved"] == 1


def test_the_relationship_is_bounded_by_the_contracts_own_period():
    (got,), _, _ = GA.extract(award(start="2025-05-21", end="2026-07-31"),
                              "caterpillar", ["Caterpillar"])
    assert got.valid_from == "2025-05-21"
    assert got.valid_to == "2026-07-31"


def test_the_durability_note_says_what_the_award_does_not_establish():
    note = GA.durability_note(award())
    for word in ("dependence", "materiality", "renewal"):
        assert word in note


def test_the_specific_buyer_outranks_the_department():
    (got,), _, _ = GA.extract(award(), "caterpillar", ["Caterpillar"])
    assert got.object_actor == "Defense Logistics Agency"


def test_a_keyword_false_positive_is_counted_not_dropped():
    found, refused, counts = GA.extract(
        award(recipient="SOME OTHER COMPANY LLC"), "caterpillar",
        ["Caterpillar"])
    assert found == ()
    assert refused["recipient_is_not_the_subject"] == 1
    # It was still a candidate: both parties were named. The ratio of
    # candidates to resolutions is what says whether the query is the problem.
    assert counts["relationship_candidates"] == 1
    assert "identity_resolved" not in counts


def test_a_subsidiary_resolution_is_counted_apart():
    """A two-token alias may claim a longer name; a one-token alias may not,
    which is the rule that stops "Linear" claiming "Linear Minerals"."""
    _, _, counts = GA.extract(
        award(recipient="JOHNSON & JOHNSON HEALTH CARE SYSTEMS INC."),
        "johnson_johnson", ["Johnson & Johnson"])
    assert counts["identity_resolved_via_subsidiary"] == 1
    # And the one-token case is deliberately NOT extended.
    _, _, narrow = GA.extract(
        award(recipient="CATERPILLAR FINANCIAL SERVICES CORPORATION"),
        "caterpillar", ["Caterpillar"])
    assert "identity_resolved" not in narrow


# --- release semantics: keep the weakest accurate relation ---------------

def test_integrates_with_is_not_depends_on():
    (got,), _, _ = PR.extract(
        release("Stripe today announced that its platform integrates with "
                "NetSuite for automated reconciliation. NetSuite customers "
                "can enable it from the Stripe dashboard today."),
        "stripe", ["Stripe", "Stripe, Inc."])
    assert got.predicate == AR.COMPLEMENTS
    assert got.predicate != AR.DEPENDS_ON
    assert "states no commercial relationship" in got.relationship_span


def test_partners_with_is_not_supplies():
    (got,), _, _ = PR.extract(
        release("Stripe partners with OpenAI to bring payments to agents "
                "across the developer ecosystem. OpenAI will use the "
                "integration in its own products from this quarter."),
        "stripe", ["Stripe", "Stripe, Inc."])
    assert got.predicate == AR.PARTNERS_WITH
    assert got.predicate != AR.SUPPLIES


def test_selection_inverts_the_direction():
    (got,), _, _ = PR.extract(
        release("Acme Bank has selected Stripe to run its merchant payment "
                "infrastructure. Stripe will support Acme Bank across all "
                "of its retail branches from next quarter."),
        "stripe", ["Stripe", "Stripe, Inc."])
    # The buyer is named BEFORE the verb and the seller after it, so the
    # counterparty comes from the head of the sentence, not its tail.
    assert got.predicate == AR.SELLS_TO
    assert got.subject_actor.startswith("Stripe")
    assert got.object_actor == "Acme Bank"


def test_uses_and_works_with_state_no_holdable_relation():
    found, refused, _ = PR.extract(
        release("Stripe uses Datadog for observability and works with "
                "Segment on customer analytics across its estate."),
        "stripe", ["Stripe", "Stripe, Inc."])
    assert found == ()
    assert refused["states_no_commercial_relation"] >= 1


def test_supply_chain_does_not_produce_a_partner_called_chain():
    """Four live edges pointed at an actor named "Chain" before this.

    Two independent guards stop it — the pattern matches only the finite
    verb `supplies`, and the plausibility filter rejects the common noun.
    Both are proved, separately, because a test that passes under either one
    cannot say which is load-bearing.
    """
    found, refused, _ = PR.extract(
        release("Canadian National is investing in supply Chain "
                "Collaboration across its network. Chain Collaboration "
                "is a programme run with its terminal operators."),
        "canadian_national", ["Canadian National Railway"])
    assert all(r.object_actor != "Chain" for r in found)
    # The pattern is the first guard: a compound noun is not a verb.
    assert not any(p.search("investing in supply Chain Collaboration")
                   for p, pred, _l, _b, _m in PR._COMPILED
                   if pred == AR.SUPPLIES)


def test_a_place_is_refused_at_the_call_site_not_only_in_the_helper():
    """Testing the helper directly leaves the call site unguarded."""
    found, refused, _ = PR.extract(
        release("Grifols partners with Europe to expand plasma collection "
                "across the region. Europe remains a core market for the "
                "group and for its donors."),
        "grifols", ["Grifols", "Grifols S.A."])
    assert found == ()
    assert refused["counterparty_is_a_common_noun_or_place"] == 1


def test_a_place_name_is_not_a_counterparty():
    assert PR._plausible_counterparty("Europe", "text " * 40)
    assert PR._plausible_counterparty("European", "text " * 40)
    assert not PR._plausible_counterparty("OpenAI", "OpenAI and OpenAI again")


def test_a_one_word_name_appearing_once_is_refused():
    assert PR._plausible_counterparty("Zephyr", "Zephyr appears once here")
    assert not PR._plausible_counterparty(
        "Zephyr", "Zephyr appears here and Zephyr appears again")


def test_the_subject_cannot_partner_with_itself():
    found, refused, _ = PR.extract(
        release("Stripe partners with Stripe Inc to deliver a new service "
                "for merchants across every supported market."),
        "stripe", ["Stripe", "Stripe, Inc."])
    assert found == ()
    assert refused["counterparty_is_the_subject"] == 1


# --- case studies: the publisher settles the direction -------------------

def test_a_case_study_admits_sells_to_from_vendor_to_customer():
    (got,), _, _ = CC.extract(
        case_study("FreshBooks | Shopify",
                   "FreshBooks uses Shopify to run its storefront. " * 40),
        "shopify", ["Shopify", "Shopify Inc."])
    assert got.predicate == AR.SELLS_TO
    assert got.subject_actor.startswith("Shopify")
    assert got.object_actor == "FreshBooks"


def test_a_case_study_states_nothing_about_materiality_or_renewal():
    (got,), _, _ = CC.extract(
        case_study("FreshBooks | Shopify",
                   "FreshBooks uses Shopify to run its storefront. " * 40),
        "shopify", ["Shopify", "Shopify Inc."])
    for word in ("revenue contribution", "dependence", "materiality",
                 "renewal"):
        assert word in got.relationship_span


def test_a_page_that_names_a_company_without_stating_use_is_refused():
    found, refused, _ = CC.extract(
        case_study("FreshBooks | Shopify",
                   "FreshBooks was a sponsor of our annual event. " * 40),
        "shopify", ["Shopify", "Shopify Inc."])
    assert found == ()
    assert refused["page_states_no_use_of_a_product_or_service"] == 1


def test_a_narrative_opener_is_not_part_of_the_customers_name():
    """"How Cocunat..." produced a customer called "How Cocunat"."""
    (got,), _, _ = CC.extract(
        case_study("How Cocunat grew online",
                   "Cocunat uses Shopify for its storefront. " * 40),
        "shopify", ["Shopify", "Shopify Inc."])
    assert got.object_actor == "Cocunat"


def test_a_section_landing_page_is_not_a_customer():
    found, refused, _ = CC.extract(
        case_study("Shopify Case Studies",
                   "Customers use Shopify every day across the world. " * 40),
        "shopify", ["Shopify", "Shopify Inc."])
    assert found == ()
    assert refused["title_names_no_customer"] == 1


def test_a_headline_verb_terminates_the_customers_name():
    """"Jobber Expands With New..." produced "Jobber Expands With New"."""
    (got,), _, _ = CC.extract(
        case_study("Jobber Expands With New Payment Tools",
                   "Jobber uses Stripe for payments across its base. " * 40),
        "stripe", ["Stripe", "Stripe, Inc."])
    assert got.object_actor == "Jobber"


def test_a_title_opening_with_the_vendor_is_the_vendor_talking():
    (got,), _, _ = CC.extract(
        case_study("Stripe Supports Rivian",
                   "Rivian uses Stripe for payments across its estate. " * 40),
        "stripe", ["Stripe", "Stripe, Inc."])
    assert got.object_actor == "Rivian"


# --- the measurement harness ---------------------------------------------

def test_a_family_is_integrated_on_yield_and_nothing_else():
    barren = CS.Yield(family="x", documents_retrieved=100,
                      relationships_accepted=0)
    assert barren.verdict()[0] == CS.REJECT
    productive = CS.Yield(family="x", documents_retrieved=20,
                          relationships_accepted=5)
    assert productive.verdict()[0] == CS.INTEGRATE


def test_a_zero_over_too_few_documents_is_not_a_verdict():
    thin = CS.Yield(family="x", documents_retrieved=2,
                    relationships_accepted=0)
    assert thin.verdict()[0] == CS.INSUFFICIENT_SAMPLE


def test_errors_with_no_documents_read_unreachable_not_rejected():
    broken = CS.Yield(family="x", errors=["boom"])
    assert broken.verdict()[0] == CS.UNREACHABLE


def test_yield_is_per_document_not_per_request():
    """A thousand documents with one edge is worse than three with one."""
    many = CS.Yield(family="x", subjects_attempted=1, document_attempts=1000,
                    documents_retrieved=1000, relationships_accepted=1)
    few = CS.Yield(family="y", subjects_attempted=1, document_attempts=3,
                   documents_retrieved=3,
                   relationships_accepted=1)
    assert few.yield_per_document > many.yield_per_document


def test_one_failing_subject_does_not_end_the_sweep():
    def fetch(subject, aliases, as_of):
        if subject == "broken":
            raise RuntimeError("unreachable host")
        return [award()]

    def extract(document, subject, aliases):
        return (object(),), {}, {}

    found, report = CS.measure(
        CS.GOVERNMENT_AWARD,
        subjects=[("broken", []), ("ok", []), ("also_ok", [])],
        fetch=fetch, extract=extract)
    assert len(report.errors) == 1
    assert report.documents_retrieved == 2
    assert report.relationships_accepted == 2


def test_the_same_relationship_across_documents_counts_once():
    class Row:
        relationship_id = "rel_same"

    found, report = CS.measure(
        CS.GOVERNMENT_AWARD, subjects=[("a", []), ("b", [])],
        fetch=lambda *a: [award(), award()],
        extract=lambda *a: ((Row(),), {}, {}))
    assert report.relationships_accepted == 1
    assert report.duplicates == 3
    assert report.duplicate_rate == 0.75


# --- the acquisition step -------------------------------------------------

def test_acquisition_is_night_only_and_never_fetches_in_a_dry_run(tmp_path):
    import pathlib as _p

    from intent_engine.market import cycle as C
    from intent_engine.market import steps as S

    assert "source_acquisition" in [n for n, _ in S.night_steps()]
    assert "source_acquisition" not in [n for n, _ in S.day_steps()]
    got = S.source_acquisition_step(C.CycleContext(
        cycle="night", as_of="2026-08-07", root=_p.Path(tmp_path),
        session=None, run_id="t", dry_run=True))
    assert "other people's sites" in got["skipped"]


def test_every_family_carries_a_cadence():
    from intent_engine.market import steps as S

    assert set(S.SOURCE_CADENCE_DAYS) == {
        CS.GOVERNMENT_AWARD, CS.PARTNERSHIP_RELEASE, CS.CUSTOMER_CASE_STUDY}
    # The structured family is cheap and runs every night; the prose ones
    # cost minutes of other people's web servers and do not.
    assert S.SOURCE_CADENCE_DAYS[CS.GOVERNMENT_AWARD] == 1
    assert all(v > 1 for k, v in S.SOURCE_CADENCE_DAYS.items()
               if k != CS.GOVERNMENT_AWARD)


def test_interactions_stay_blocked_and_name_the_missing_predicate(tmp_path):
    """Customers and partners are published; rivals are not."""
    import pathlib as _p

    from intent_engine.market import cycle as C
    from intent_engine.market import steps as S

    ctx = C.CycleContext(cycle="night", as_of="2026-08-07",
                         root=_p.Path(tmp_path), session=None, run_id="t",
                         dry_run=True)
    ctx.results["source_acquisition"] = {"relationships": [
        {"relationship_id": "r1", "subject_actor_id": "Shopify Inc.",
         "predicate": AR.SELLS_TO, "object_actor_id": "FreshBooks",
         "subject_kind": AR.LEGAL_ENTITY, "object_kind": AR.LEGAL_ENTITY,
         "epistemic_status": AR.OBSERVED, "evidence_ids": ["e"],
         "source_document_ids": ["u"], "subject_span": "s",
         "object_span": "o", "relationship_span": "span"}]}
    got = S.knowledge_step(ctx)["world_model"]
    assert got["relationships"] == 1
    assert got["competitor_edges"] == 0
    assert got["interactions"] == 0
    assert got["missing_for_interactions"].startswith("COMPETES_WITH")
