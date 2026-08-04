"""A macro factor may not appear without a company-specific mechanism.

The sentence these tests exist to make impossible:

    "Interest rates affect technology companies."

True of every technology company ever, therefore worth nothing to any of them.
"""
import pytest

from intent_engine.external_intel import macro_contract as MC
from intent_engine.external_intel import macro_exposure as MX
from intent_engine.external_intel import macro_provider as MP


def _observation(**kw):
    base = dict(factor_key=MX.PUBLIC_DEFENCE_SPEND, label="DoD outlays",
                series_id="MTS-5", current_value=678.7, prior_value=647.4,
                unit="$bn", observation_date="2026-06-30",
                frequency="monthly", source="US Treasury")
    base.update(kw)
    return MC.MacroObservation(**base)


def _exposure(**kw):
    base = dict(factor_key=MX.PUBLIC_DEFENCE_SPEND,
                mechanism="Sells into federal defence budgets.",
                business_consequence="A wider pool, awarded slowly.",
                decision_implication="Whether to fund delivery capacity.",
                evidence_ids=("ev-1",), matched_on="government contracts")
    base.update(kw)
    return MC.Exposure(**base)


def _factor(observation=None, exposure=None, **kw):
    base = dict(observation=observation or _observation(),
                exposure=exposure or _exposure(),
                limitation="Does not measure how much revenue is exposed.",
                confidence_basis="Company evidence plus a published series.")
    base.update(kw)
    return MC.MacroFactor(**base)


TODAY = "2026-08-04"


# --- the exposure gate ------------------------------------------------------
def test_an_exposure_without_a_mechanism_is_rejected():
    with pytest.raises(MC.MacroRejected) as exc:
        _exposure(mechanism="")
    assert "generic macro sentence" in str(exc.value)


def test_an_exposure_without_evidence_is_rejected():
    """Sector is not evidence."""
    with pytest.raises(MC.MacroRejected) as exc:
        _exposure(evidence_ids=())
    assert "sector is not evidence" in str(exc.value)


def test_a_factor_reaching_no_decision_is_rejected():
    with pytest.raises(MC.MacroRejected) as exc:
        MC.validate_factor(_factor(exposure=_exposure(
            decision_implication="")), today=TODAY)
    assert "no decision" in str(exc.value)


def test_a_factor_without_a_limitation_is_rejected():
    with pytest.raises(MC.MacroRejected) as exc:
        MC.validate_factor(_factor(limitation=""), today=TODAY)
    assert "does NOT establish" in str(exc.value)


def test_a_factor_with_no_current_reading_is_rejected():
    with pytest.raises(MC.MacroRejected):
        MC.validate_factor(_factor(observation=_observation(
            current_value=None)), today=TODAY)


def test_a_stale_reading_cannot_describe_today():
    with pytest.raises(MC.MacroRejected) as exc:
        MC.validate_factor(
            _factor(observation=_observation(observation_date="2025-01-31")),
            today=TODAY)
    assert "days old" in str(exc.value)


def test_a_rejected_factor_is_dropped_silently_not_caveated():
    """A caveated generic macro sentence is still a generic macro sentence."""
    kept = MC.admissible([_factor(limitation="")], today=TODAY)
    assert kept == []


# --- exposure comes from evidence, never from the company's identity --------
def test_exposure_is_established_by_retrieved_evidence():
    obs = [{"observation_id": "ev-1",
            "text": "Provides platforms to US federal agencies under "
                    "multi-year government contracts."}]
    found = MX.find_exposures(obs)
    assert [e.factor_key for e in found] == [MX.PUBLIC_DEFENCE_SPEND]
    assert found[0].evidence_ids == ("ev-1",)


def test_masking_the_company_name_does_not_change_the_exposure():
    """The test that separates evidence from the model's prior.

    If defence exposure survives the company's name being replaced, it came
    from the document. If it would not, it came from knowing who this is.
    """
    named = [{"observation_id": "ev-1",
              "text": "Palantir provides software to the Department of "
                      "Defense under government contracts."}]
    masked = [{"observation_id": "ev-1",
               "text": "The company provides software to the Department of "
                       "Defense under government contracts."}]
    assert ([e.factor_key for e in MX.find_exposures(named)]
            == [e.factor_key for e in MX.find_exposures(masked)])


def test_a_company_with_no_supporting_evidence_gets_no_macro_section():
    """The whole point. A generic SaaS description earns nothing."""
    obs = [{"observation_id": "ev-1",
            "text": "A cloud software company that helps teams collaborate "
                    "on documents."}]
    assert MX.find_exposures(obs) == []


def test_sector_words_alone_do_not_establish_exposure():
    """"A technology company" is not an interest-rate exposure."""
    obs = [{"observation_id": "ev-1",
            "text": "A technology company in the enterprise software sector."}]
    assert MX.find_exposures(obs) == []


def test_a_trigger_inside_a_longer_word_does_not_fire():
    """Word boundaries: 'credit' must not fire on 'accreditation'."""
    obs = [{"observation_id": "ev-1",
            "text": "The product holds FedRAMP accreditation for its "
                    "collaboration suite."}]
    keys = [e.factor_key for e in MX.find_exposures(obs)]
    assert MX.INTEREST_RATES not in keys


def test_an_observation_with_no_id_cannot_carry_an_exposure():
    """An exposure a reader cannot click through to is unfalsifiable."""
    obs = [{"observation_id": "", "text": "Sells under government contracts."}]
    assert MX.find_exposures(obs) == []


def test_every_mechanism_says_how_money_reaches_the_company():
    """A mechanism that restates the factor's name teaches nothing."""
    for rule in MX.RULES:
        assert len(rule.mechanism) > 80, rule.factor_key
        assert rule.decision.lower().startswith("whether"), rule.factor_key
        # The mechanism must not merely echo the factor key back.
        words = set(rule.factor_key.split("_"))
        assert not rule.mechanism.lower().startswith(tuple(words))


# --- direction --------------------------------------------------------------
def test_a_small_wobble_is_flat_not_a_direction():
    assert _observation(current_value=100.2,
                        prior_value=100.0).direction == MC.FLAT


def test_a_real_move_reports_its_direction():
    assert _observation(current_value=110.0,
                        prior_value=100.0).direction == MC.RISING
    assert _observation(current_value=90.0,
                        prior_value=100.0).direction == MC.FALLING


def test_a_missing_prior_reports_no_direction_rather_than_flat():
    """No comparison point is not "unchanged"."""
    assert _observation(prior_value=None).direction == ""


# --- the assembled result ---------------------------------------------------
def _fake_fetcher(payloads):
    def fetch(url):
        for key, body in payloads.items():
            if key in url:
                return body
        return None
    return fetch


def test_a_factor_is_only_fetched_after_exposure_is_established(tmp_path):
    """Order matters, and not for performance.

    Fetching the macro picture first and then looking for a company to attach
    it to is how generic macro commentary gets written.
    """
    asked = []

    def watcher(url):
        asked.append(url)
        return None

    MP.build_factors([{"observation_id": "e1", "text": "A collaboration app."}],
                     root=tmp_path, today=TODAY, fetcher=watcher)
    assert asked == [], "no series should be fetched without an exposure"


def test_the_assembled_factor_carries_everything_a_reader_needs(tmp_path):
    treasury = {"data": [
        {"record_date": "2026-06-30",
         "classification_desc": "Total--Department of Defense--Military "
                                "Programs",
         "current_fytd_net_outly_amt": "678660955344.65"},
        {"record_date": "2025-06-30",
         "classification_desc": "Total--Department of Defense--Military "
                                "Programs",
         "current_fytd_net_outly_amt": "647400000000.00"}]}
    factors = MP.build_factors(
        [{"observation_id": "ev-1",
          "text": "Delivers platforms to federal agencies under government "
                  "contracts."}],
        root=tmp_path, today=TODAY,
        fetcher=_fake_fetcher({"mts_table_5": treasury}))
    assert len(factors) == 1
    d = factors[0].as_dict()
    assert d["direction"] == MC.RISING
    assert d["evidence_ids"] == ["ev-1"]
    assert d["company_exposure_mechanism"]
    assert d["affected_kpi_or_decision"]
    assert d["limitation"]
    assert d["source"] and d["observation_date"]
    assert d["comparison_note"], "a year-to-date figure needs its comparison"


def test_an_exposure_whose_series_fails_produces_no_factor(tmp_path):
    """Fail closed: no reading means no section, never a placeholder."""
    factors = MP.build_factors(
        [{"observation_id": "ev-1", "text": "Sells under government "
                                            "contracts."}],
        root=tmp_path, today=TODAY, fetcher=lambda url: None)
    assert factors == []


def test_a_year_to_date_figure_compares_against_the_same_month(tmp_path):
    """Comparing June FYTD with May FYTD shows growth that is only one more
    month of spending."""
    treasury = {"data": [
        {"record_date": "2026-06-30", "current_fytd_net_outly_amt": "600"},
        {"record_date": "2026-05-31", "current_fytd_net_outly_amt": "500"},
        {"record_date": "2025-06-30", "current_fytd_net_outly_amt": "550"}]}
    got = MP._treasury_defence(tmp_path,
                               fetcher=_fake_fetcher({"mts": treasury}))
    assert got.prior_value == round(550 / 1e9, 1)


# --- the two-tier trigger rule ----------------------------------------------
# Found on the DEPLOYED product: Shopify's B2B page says "procurement
# workflows and purchase orders", `procurement` was a defence trigger, and a
# commerce company was told its decision turned on US Department of Defense
# outlays -- with a confident mechanism about federal appropriations attached.
# A single ambiguous keyword fabricated a company-specific exposure, which is
# exactly what this contract exists to refuse.


def test_a_supporting_trigger_alone_cannot_establish_an_exposure():
    obs = [{"observation_id": "ev-1",
            "text": "Streamline commerce operations with B2B wholesale, "
                    "procurement workflows and purchase orders."}]
    keys = [e.factor_key for e in MX.find_exposures(obs)]
    assert MX.PUBLIC_DEFENCE_SPEND not in keys


def test_a_strong_trigger_alone_does_establish_one():
    obs = [{"observation_id": "ev-1",
            "text": "Delivers software to US federal agencies under "
                    "government contracts."}]
    keys = [e.factor_key for e in MX.find_exposures(obs)]
    assert MX.PUBLIC_DEFENCE_SPEND in keys


def test_supporting_evidence_joins_an_exposure_a_strong_trigger_opened():
    """It adds corroboration; it never opens the door itself."""
    obs = [{"observation_id": "ev-1",
            "text": "Delivers software under government contracts."},
           {"observation_id": "ev-2",
            "text": "Revenue concentrates in a few large procurement awards."}]
    found = MX.find_exposures(obs)
    defence = next(e for e in found
                   if e.factor_key == MX.PUBLIC_DEFENCE_SPEND)
    assert set(defence.evidence_ids) == {"ev-1", "ev-2"}


def test_hiring_and_employees_do_not_establish_a_labour_exposure():
    """Every company hires and every About page names employees, so firing on
    them would print the same labour paragraph for every company."""
    obs = [{"observation_id": "ev-1",
            "text": "We have 500 employees and are hiring across teams."}]
    keys = [e.factor_key for e in MX.find_exposures(obs)]
    assert MX.LABOUR_MARKET not in keys


def test_a_commerce_company_gets_commerce_exposures_not_defence():
    """The deployed defect, end to end."""
    obs = [{"observation_id": "ev-1",
            "text": "Streamline commerce operations with B2B wholesale and "
                    "procurement workflows."},
           {"observation_id": "ev-2",
            "text": "Sell to retail and direct-to-consumer shoppers with "
                    "checkout and payments."}]
    keys = [e.factor_key for e in MX.find_exposures(obs)]
    assert keys and MX.PUBLIC_DEFENCE_SPEND not in keys
    assert MX.CONSUMER_PRICES in keys


def test_exposures_are_ordered_by_evidence_not_by_declaration_order():
    """A surface with room for one factor takes the first, and taking
    whichever rule happens to be written first is how a commerce company led
    with defence spending."""
    obs = [{"observation_id": "ev-1", "text": "Sold under government "
                                              "contracts."},
           {"observation_id": "ev-2", "text": "Serving retail shoppers."},
           {"observation_id": "ev-3", "text": "Merchants at checkout."},
           {"observation_id": "ev-4", "text": "Consumer demand for "
                                              "e-commerce."}]
    found = MX.find_exposures(obs)
    assert found[0].factor_key == MX.CONSUMER_PRICES
    assert len(found[0].evidence_ids) > len(found[-1].evidence_ids)
