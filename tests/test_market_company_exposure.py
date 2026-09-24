"""What connects an economy to a company, and the shortcut that ruins it.

The shortcut is the sector prior. "Airlines are exposed to fuel" is usually
true, is not a measurement, and produces the IDENTICAL claim for every airline
— so the most specific-sounding output in the model would carry the least
information in it.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import company_exposure as CX
from intent_engine.market import macro_state as MS

REAL_LEDGER = pathlib.Path("/Users/prathamsharma/intent-engine-market/"
                           "reports/market/learning_ledger.jsonl")


def row(fact, *, company="acme", role="regulatory_filing", eid="ev_1"):
    return {"record": "evidence", "subject_company": company, "fact": fact,
            "source_role": role, "evidence_id": eid,
            "observed_at": "2026-07-01"}


# --- the shortcut this module refuses --------------------------------------

def test_an_exposure_may_not_be_inferred_from_a_sector():
    with pytest.raises(CX.ExposureRejected, match="sector"):
        CX.infer_from_sector(company_id="acme", sector="airlines")


def test_a_rated_exposure_without_evidence_is_refused():
    """A claim about a category wearing a company's name."""
    with pytest.raises(CX.ExposureRejected, match="evidence"):
        CX.Exposure(company_id="acme", dimension=CX.RATE,
                    standing=CX.OBSERVED, basis="rates matter to us")


def test_a_rated_exposure_without_its_wording_is_refused():
    with pytest.raises(CX.ExposureRejected, match="wording"):
        CX.Exposure(company_id="acme", dimension=CX.RATE,
                    standing=CX.OBSERVED, basis="  ",
                    evidence_ids=("ev_1",))


def test_unknown_is_not_unexposed():
    """A company with no debt and a company whose filings never mention debt
    look identical from outside."""
    e = CX.unknown("acme", CX.RATE)
    assert e.standing == CX.UNKNOWN
    assert not e.conditions
    assert "either way" in e.note


# --- who is entitled to establish it ---------------------------------------

def test_a_share_price_headline_does_not_establish_a_cost_structure():
    """THE CASE THAT FORCED THE RULE. "Shares Fall 6% After Capex Boost
    Surpasses EPS Gain" rated the company OBSERVED capital-intensive because
    the word Capex appeared in a headline about its stock."""
    got = CX.read_exposures(
        [row("Linde plc Shares Fall 6% After Capex Boost Surpasses EPS Gain",
             company="linde", role="independent_reporting")],
        company_id="linde")
    assert [e.standing for e in got] == [CX.INFERRED]


def test_a_filing_establishes_the_companys_own_exposure():
    got = CX.read_exposures(
        [row("Our results remain sensitive to interest rates on the "
             "floating rate portion of the facility.")],
        company_id="acme")
    assert got and got[0].standing == CX.OBSERVED


def test_a_filing_upgrades_a_headline_rather_than_being_dropped():
    """The company's own word outranks a report of it, whichever arrived
    first."""
    rows = [row("Acme capex boost surprises analysts",
                role="independent_reporting", eid="ev_news"),
            row("Our capital expenditure programme continues.",
                role="regulatory_filing", eid="ev_filing")]
    got = {e.dimension: e for e in CX.read_exposures(rows, company_id="acme")}
    assert got[CX.CAPITAL_INTENSITY].standing == CX.OBSERVED
    assert got[CX.CAPITAL_INTENSITY].evidence_ids == ("ev_filing",)


def test_an_unclassified_publisher_establishes_nothing():
    got = CX.read_exposures(
        [row("Our interest rate exposure is material.", role="blog")],
        company_id="acme")
    assert got == []


@pytest.mark.parametrize("role,expected", [
    ("regulatory_filing", CX.OBSERVED), ("company_owned", CX.OBSERVED),
    ("independent_reporting", CX.INFERRED), ("analyst_coverage", CX.INFERRED),
    ("", CX.UNKNOWN), ("rumour", CX.UNKNOWN)])
def test_standing_is_decided_by_publisher_class(role, expected):
    assert CX.standing_for(role) == expected


def test_another_companys_document_does_not_establish_this_ones_exposure():
    rows = [row("Our currency exposure is significant.", company="rival")]
    assert CX.read_exposures(rows, company_id="acme") == []


# --- the join to the economy ------------------------------------------------

def _state(kind=MS.POLICY_RATE, standing=MS.OBSERVED):
    o = MS.MacroObservation(
        state_kind=kind, series_id="S1", label="rate", value=4.0, unit="%",
        reference_period="2026-06-30", published_at="2026-07-15",
        standing=standing)
    return MS.state_of(kind, [o], as_of="2026-08-01")


def test_a_transmission_needs_both_an_economy_and_an_exposure():
    exposed = CX.Exposure(company_id="acme", dimension=CX.RATE,
                          standing=CX.OBSERVED, basis="rate sensitivity",
                          evidence_ids=("ev_1",))
    assert CX.conditions_transmission(exposed, _state())
    # ...and neither half alone.
    assert not CX.conditions_transmission(exposed, None)
    assert not CX.conditions_transmission(None, _state())
    assert not CX.conditions_transmission(CX.unknown("acme", CX.RATE),
                                          _state())
    assert not CX.conditions_transmission(
        exposed, _state(standing=MS.HYPOTHESIZED))


def test_an_unrelated_condition_has_no_route_into_the_company():
    """A rate exposure is not a route for an energy price."""
    exposed = CX.Exposure(company_id="acme", dimension=CX.RATE,
                          standing=CX.OBSERVED, basis="rate sensitivity",
                          evidence_ids=("ev_1",))
    assert not CX.conditions_transmission(exposed, _state(MS.ENERGY_PRICE))


def test_every_dimension_names_the_conditions_it_is_sensitive_to():
    for dimension in CX.DIMENSIONS:
        assert CX.SENSITIVE_TO.get(dimension), dimension
        for kind in CX.SENSITIVE_TO[dimension]:
            assert kind in MS.STATE_KINDS, (dimension, kind)


# --- the profile is total ---------------------------------------------------

def test_the_profile_names_every_dimension_including_the_missing_ones():
    """A caller given only the rated dimensions forgets the others exist, and
    the missing ones are what a reader most needs to be told."""
    p = CX.profile([row("Our capital expenditure programme continues.")],
                   company_id="acme")
    assert set(p) == set(CX.DIMENSIONS)
    assert p[CX.CAPITAL_INTENSITY].conditions
    assert not p[CX.FX].conditions


def test_the_summary_counts_and_does_not_score():
    p = {"acme": CX.profile([row("Our capex programme continues.")],
                            company_id="acme")}
    got = CX.summarise(p)
    assert got["companies"] == 1
    assert got["rated_exposures"] == 1
    assert "score" not in got
    assert got["by_standing"][CX.UNKNOWN] == len(CX.DIMENSIONS) - 1


# --- against the real corpus ------------------------------------------------

def test_the_real_corpus_is_mostly_unknown_and_says_so():
    """A press-release corpus does not establish exposures, and a fully
    populated profile would be a guessed one. This asserts the SHAPE — most
    unknown, some rated — not the counts, which move as evidence arrives."""
    if not REAL_LEDGER.exists():                          # pragma: no cover
        return
    rows = [json.loads(l) for l in REAL_LEDGER.read_text().splitlines()
            if l.strip()]
    companies = sorted({r.get("subject_company") for r in rows
                        if r.get("record") == "evidence"
                        and r.get("subject_company")})
    profiles = {c: CX.profile(rows, company_id=c) for c in companies}
    got = CX.summarise(profiles)
    assert got["companies"] >= 20
    assert got["by_standing"].get(CX.UNKNOWN, 0) > got["rated_exposures"], \
        "a corpus of headlines should not populate an exposure model"
    # Whatever is rated must carry its wording and its evidence.
    for company_profile in profiles.values():
        for exposure in company_profile.values():
            if exposure.conditions:
                assert exposure.basis.strip()
                assert exposure.evidence_ids
