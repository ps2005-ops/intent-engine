"""The analysis a company gets is chosen from what kind of business it is.

The defect these pin: every company was asked one constant question, so the
executive reads for Cloudflare, Shopify and Johnson & Johnson came back
0.94-0.96 similar. A test that only asserted "the text differs" would have
passed on a synonym table, so these assert the SELECTION -- the question, the
signals, the channel, the causal question, the competitors -- and assert that
each one is derived from the business model rather than from the company name.
"""
import pytest

from intent_engine.executive import analysis_selection as AS
from intent_engine.executive import company_profile as CP


def _facts(**kw):
    return AS.RecordFacts(**kw)


# --- the profile ------------------------------------------------------------

def test_a_company_outside_the_manifest_is_unknown_not_average():
    """The dangerous failure is borrowing another company's economics."""
    profile = CP.profile_for("not-a-real-company-xyz",
                             name="Not A Real Company XYZ")
    assert profile.known is False
    assert profile.business_model == CP.UNKNOWN
    assert profile.primary_revenue_drivers == ()
    assert profile.strategic_competitors == ()
    # and it SAYS why, rather than looking like a company with no economics
    assert "not in the validation manifest" in profile.basis


def test_different_business_models_get_different_economics():
    bank = CP.profile_for("jpmorgan-chase", name="JPMorgan Chase & Co.")
    miner = CP.profile_for("agnico-eagle-mines", name="Agnico Eagle Mines")
    software = CP.profile_for("cloudflare", name="Cloudflare, Inc.")
    known = [p for p in (bank, miner, software) if p.known]
    assert len(known) >= 2, "manifest resolution regressed"
    models = {p.business_model_class for p in known}
    assert len(models) == len(known), "distinct businesses share a model class"
    for a, b in ((bank, miner), (bank, software), (miner, software)):
        if a.known and b.known:
            assert a.primary_revenue_drivers != b.primary_revenue_drivers
            assert a.business_model != b.business_model


def test_a_commodity_price_is_revenue_at_a_producer_and_cost_elsewhere():
    """The single worst error available here, pinned.

    A commodity price is an INPUT COST almost everywhere and IS THE REVENUE
    LINE at a producer. Reporting both the same way would make the economic
    section actively misleading for exactly the companies it matters most to.
    """
    producer = CP.profile_for("vale", name="Vale S.A.") if CP.profile_for(
        "vale", name="Vale S.A.").known else None
    if producer is None:
        producer = next(
            (p for p in (CP.profile_for(c) for c in
                         ("agnico-eagle-mines", "barrick-gold", "bhp-group"))
             if p.known and p.business_model_class == "COMMODITY_PRODUCER"),
            None)
    if producer is None:
        pytest.skip("no commodity producer in the manifest to test against")
    consumer = CP.profile_for("procter-and-gamble",
                              name="The Procter & Gamble Company")
    sel_p = AS.select(producer.company_id, profile=producer,
                      facts=_facts(economic_ids=("GLOBAL:COMMODITY",)))
    assert sel_p.transmission, "a producer has no commodity mechanism"
    assert "revenue line" in sel_p.transmission[0].business_variable
    if consumer.known:
        sel_c = AS.select(consumer.company_id, profile=consumer,
                          facts=_facts(economic_ids=("GLOBAL:COMMODITY",)))
        assert sel_c.transmission
        assert "revenue line" not in sel_c.transmission[0].business_variable
        assert "cost" in sel_c.transmission[0].business_variable


# --- the selection ----------------------------------------------------------

def test_the_decision_question_is_not_a_constant_with_a_name_in_it():
    """The exact defect: same sentence, company substituted."""
    names = [("cloudflare", "Cloudflare, Inc."),
             ("johnson-and-johnson", "Johnson & Johnson"),
             ("boeing", "The Boeing Company"),
             ("bank-of-america", "Bank of America Corporation"),
             ("mckinsey", "McKinsey & Company")]
    questions = {}
    for key, name in names:
        sel = AS.select(key, name=name, facts=_facts(evidence=4, beliefs=2))
        if sel.profile and sel.profile.known:
            # strip the company name: what is left must still differ
            questions[key] = sel.decision_question.replace(name, "<C>")
    assert len(questions) >= 4, "manifest resolution regressed"
    assert len(set(questions.values())) == len(questions), (
        "two companies got the same question once the name was removed: "
        f"{questions}")


def test_the_selection_says_why_it_chose_that_question():
    sel = AS.select("boeing", name="The Boeing Company",
                    facts=_facts(evidence=3, beliefs=2))
    assert sel.profile.known
    assert sel.why_this_question
    assert sel.considered, "nothing was considered, so nothing was chosen"
    # every archetype considered carries a score and a reason
    for row in sel.considered:
        assert row["archetype"] and row["why"]
    scores = [r["score"] for r in sel.considered]
    assert scores == sorted(scores, reverse=True)
    assert sel.archetype == sel.considered[0]["archetype"]


def test_a_live_economic_condition_can_change_which_decision_is_selected():
    """The economy choosing the question -- not decorating the answer."""
    quiet = AS.select("nextera-energy", name="NextEra Energy, Inc.",
                      facts=_facts(evidence=5, beliefs=3))
    if not quiet.profile.known:
        pytest.skip("company not in the manifest")
    loud = AS.select("nextera-energy", name="NextEra Energy, Inc.",
                     facts=_facts(evidence=5, beliefs=3,
                                  economic_ids=("US:MARKET_RATE",)))
    ranks = {r["archetype"]: i for i, r in enumerate(quiet.considered)}
    ranks_loud = {r["archetype"]: i for i, r in enumerate(loud.considered)}
    favoured = [a for a in AS._CHANNEL_FAVOURS["MARKET_RATE"]
                if a in ranks and a in ranks_loud]
    assert favoured, "no favoured archetype is on this company's menu"
    assert any(ranks_loud[a] <= ranks[a] for a in favoured)
    assert loud.transmission, "a live channel produced no transmission row"


def test_a_channel_with_no_mechanism_into_this_business_is_not_an_exposure():
    """§6: factor -> mechanism -> variable -> implication, or nothing."""
    software = CP.profile_for("cloudflare", name="Cloudflare, Inc.")
    if not software.known:
        pytest.skip("company not in the manifest")
    sel = AS.select(software.company_id, profile=software,
                    facts=_facts(economic_ids=("GLOBAL:COMMODITY",)))
    assert sel.transmission == ()
    assert "an established mechanism" in sel.no_exposure_reason
    assert "COMMODITY" in sel.no_exposure_reason, (
        "the dropped channel is not named, so a reader cannot check it")
    for row in AS.select(software.company_id, profile=software,
                         facts=_facts(economic_ids=("US:MARKET_RATE",))
                         ).transmission:
        assert row.mechanism and row.business_variable
        assert row.decision_implication


def test_the_causal_question_comes_from_the_decision_not_the_data():
    """Never picked by scanning for the largest effect."""
    bank = AS.select("bank-of-america", name="Bank of America Corporation",
                     facts=_facts(evidence=6, beliefs=4))
    consumer = AS.select("procter-and-gamble",
                         name="The Procter & Gamble Company",
                         facts=_facts(evidence=6, beliefs=4))
    for sel in (bank, consumer):
        if not sel.profile.known:
            pytest.skip("company not in the manifest")
        assert sel.causal_question
        assert "chosen from the decision" in sel.why_this_causal_question
    assert bank.causal_question != consumer.causal_question


def test_competitors_are_selected_by_business_model_and_state_their_basis():
    sel = AS.select("bank-of-america", name="Bank of America Corporation",
                    facts=_facts(evidence=3, beliefs=2))
    if not sel.profile.known:
        pytest.skip("company not in the manifest")
    peers = sel.profile.strategic_competitors
    assert peers, "no competitor selected"
    assert all(p.why and p.basis for p in peers)
    assert all(p.name != sel.profile.company_name for p in peers)
    # a bank's peers are not a software company's peers
    other = AS.select("cloudflare", name="Cloudflare, Inc.",
                      facts=_facts(evidence=3, beliefs=2))
    if other.profile.known:
        assert not ({p.name for p in peers}
                    & {p.name for p in other.profile.strategic_competitors})


def test_the_adversary_refuses_to_fabricate_a_probability():
    sel = AS.select("boeing", name="The Boeing Company",
                    facts=_facts(evidence=3, beliefs=2))
    if not sel.profile.known:
        pytest.skip("company not in the manifest")
    assert [m.level for m in sel.adversary] == ["L0", "L1", "L2"]
    for move in sel.adversary:
        assert move.actor and move.action and move.countermeasure
        assert move.observable_signal and move.kill_switch
        text = " ".join(move.as_dict().values()).lower()
        assert "%" not in text
        assert "probability of" not in text


def test_every_scenario_starts_from_a_management_lever_and_ends_in_a_stop():
    sel = AS.select("mckinsey", name="McKinsey & Company",
                    facts=_facts(evidence=3, beliefs=2))
    if not sel.profile.known:
        pytest.skip("company not in the manifest")
    assert [s.name for s in sel.scenarios] == ["BASE", "UPSIDE", "DOWNSIDE",
                                               "ADVERSARIAL"]
    for scenario in sel.scenarios:
        assert scenario.lever and scenario.kill_switch
        assert scenario.first_order and scenario.second_order
        # §11: never invent a business-looking number
        assert not any(ch.isdigit() for ch in scenario.outcome_range)


def test_an_unknown_company_still_gets_an_honest_decision_question():
    sel = AS.select("nowhere-ltd", name="Nowhere Ltd")
    assert sel.archetype == CP.UNKNOWN
    assert sel.decision_question
    assert sel.signals == ()
    assert sel.scenarios == ()
    # The reason must say the business model was never established, and say
    # what would resolve it. This assertion used to pin one phrasing ("not
    # classified"); the profile layer now carries a fuller statement of the
    # same fact, so the intent is asserted rather than the old wording.
    why = sel.why_this_question.lower()
    assert "has not been established" in why or "not classified" in why
    assert "manifest" in why
