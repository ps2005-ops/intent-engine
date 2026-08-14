"""The validation manifest is a validation universe, not a knowledge base.

WHAT WENT WRONG. 16 of the 26 companies with live market snapshots -- Toyota,
Vale, ASML among them -- read as UNKNOWN, and the executive analysis fell to
its generic path for every one. The cause was not an identity defect: all 16
resolve correctly and none duplicates a manifest entry. The cause was that
membership in a curated 100-company VALIDATION universe had become the
precondition for knowing what kind of business a company is.

These tests pin the repair and, more importantly, its limits: a company may
be classified from a regulator's own industry code, that classification is
labelled PARTIAL because it is coarser, and a residual industry code
classifies nothing at all rather than being guessed.
"""
import pytest

from intent_engine.executive import analysis_selection as AS
from intent_engine.executive.company_profile import (PROFILE_AVAILABLE,
                                                     PROFILE_PARTIAL,
                                                     PROFILE_SPARSE,
                                                     PROFILE_STATES,
                                                     classify_sic, profile_for)
from intent_engine.validation import load as load_manifest


# --- every company has a stated profile state ------------------------------

def test_every_manifest_company_is_profile_available():
    """100/100, and no company reaches a state by a join quietly failing."""
    manifest = load_manifest()
    states = {c.company_id: profile_for(c.company_id,
                                        name=c.canonical_name,
                                        manifest=manifest).profile_state
              for c in manifest.companies}
    assert len(states) == 100
    not_available = {k: v for k, v in states.items()
                     if v != PROFILE_AVAILABLE}
    assert not not_available, (
        f"manifest companies without a full profile: {not_available}")


def test_profile_state_is_always_one_of_the_three():
    """There is no fourth state, and no empty one."""
    cases = [
        profile_for("cloudflare", name="Cloudflare, Inc."),
        profile_for("toyota-motor-corporation", name="Toyota Motor Corp",
                    registrant={"sic": "3711",
                                "sic_description": "Motor Vehicles"}),
        profile_for("nobody-at-all", name="No Such Company Ltd"),
    ]
    for profile in cases:
        assert profile.profile_state in PROFILE_STATES


def test_manifest_company_never_needs_a_registrant():
    """A company in the manifest is classified by the manifest, and a
    registrant lookup cannot downgrade or override it."""
    with_reg = profile_for("cloudflare", name="Cloudflare, Inc.",
                           registrant={"sic": "1000",
                                       "sic_description": "Metal Mining"})
    assert with_reg.profile_state == PROFILE_AVAILABLE
    assert with_reg.profile_source == "VALIDATION_MANIFEST"
    # The regulator code said metal mining. The manifest is the authority.
    assert with_reg.business_model_class == "SUBSCRIPTION_SOFTWARE"


# --- the regulator-classified path -----------------------------------------

@pytest.mark.parametrize("sic,expected_model", [
    ("3711", "MANUFACTURE_AND_AFTERMARKET"),    # Toyota, Honda
    ("1000", "COMMODITY_PRODUCER"),             # Vale, BHP
    ("3559", "DESIGN_AND_MANUFACTURE"),         # ASML
    ("2834", "REGULATED_PRODUCT_OR_PROVIDER"),  # Grifols
    ("6029", "BALANCE_SHEET_OR_NETWORK"),       # HDFC Bank
    ("7372", "SUBSCRIPTION_SOFTWARE"),          # Check Point, Duolingo
    ("7371", "PEOPLE_OR_ROUTE_BASED_SERVICES"), # Infosys
])
def test_sic_classifies_the_business_model(sic, expected_model):
    assert classify_sic(sic) is not None
    assert classify_sic(sic)[0] == expected_model


def test_a_company_outside_the_manifest_is_still_classified():
    """Toyota is not in the manifest and is not therefore unknown."""
    profile = profile_for(
        "toyota-motor-corporation", name="Toyota Motor Corporation",
        registrant={"sic": "3711",
                    "sic_description": "Motor Vehicles & Passenger Car"})
    assert profile.profile_state == PROFILE_PARTIAL
    assert profile.profile_source == "SEC_SIC"
    assert profile.known is True
    assert profile.business_model_class == "MANUFACTURE_AND_AFTERMARKET"
    # and the specialization layer above it actually specialises
    assert profile.decision_archetypes
    assert profile.strategic_competitors
    assert profile.relevant_macro_channels


def test_partial_profile_states_its_own_limitation():
    """The caveat is carried on the profile, so no surface invents one."""
    profile = profile_for(
        "vale-s-a", name="Vale S.A.",
        registrant={"sic": "1000", "sic_description": "Metal Mining"})
    assert profile.profile_state == PROFILE_PARTIAL
    assert profile.profile_limitation
    assert "1000" in profile.profile_limitation
    # It must name what is NOT established, not merely that something isn't.
    assert "capital intensity" in profile.profile_limitation.lower()


def test_partial_profile_does_not_claim_manifest_only_fields():
    """PARTIAL means the per-company detail is absent -- not defaulted."""
    profile = profile_for(
        "vale-s-a", name="Vale S.A.",
        registrant={"sic": "1000", "sic_description": "Metal Mining"})
    assert profile.capital_intensity == "UNKNOWN"
    assert profile.cyclical_exposure == "UNKNOWN"
    assert profile.regulatory_exposure == "UNKNOWN"


# --- the refusals ----------------------------------------------------------

@pytest.mark.parametrize("residual", ["7389", "7380", "3990", "9995"])
def test_a_residual_industry_code_classifies_nothing(residual):
    """'Not elsewhere classified' is defined by what it is not. Inferring a
    business model from it would be the guess this layer exists to refuse --
    7389 covers a marketplace and a payroll bureau equally well."""
    assert classify_sic(residual) is None


def test_a_residual_code_produces_sparse_not_a_guess():
    profile = profile_for("etsy-inc", name="Etsy, Inc.",
                          registrant={"sic": "7389",
                                      "sic_description":
                                          "Services-Business Services, NEC"})
    assert profile.profile_state == PROFILE_SPARSE
    assert profile.known is False
    assert profile.business_model_class == "UNKNOWN"
    assert "residual" in profile.profile_limitation.lower()


def test_no_registrant_at_all_is_sparse_and_says_why():
    """Olo was taken private and is no longer a filer. That is a real state
    with a real reason, not a blank."""
    profile = profile_for("olo-inc", name="Olo Inc.", registrant=None)
    assert profile.profile_state == PROFILE_SPARSE
    assert profile.profile_limitation
    assert "validation manifest" in profile.profile_limitation


def test_sparse_never_borrows_another_companys_economics():
    """The failure mode this replaces was an implicit UNKNOWN. The failure
    mode it must not introduce is an implicit AVERAGE."""
    profile = profile_for("olo-inc", name="Olo Inc.", registrant=None)
    assert profile.strategic_competitors == ()
    assert profile.relevant_macro_channels == ()
    assert profile.decision_archetypes == ()
    assert profile.primary_revenue_drivers == ()


# --- the selection layer consumes it ---------------------------------------

def test_selection_specialises_a_regulator_classified_company():
    """The point of the repair: Toyota and Vale must not get one answer."""
    toyota = AS.select("toyota-motor-corporation",
                       name="Toyota Motor Corporation",
                       registrant={"sic": "3711",
                                   "sic_description": "Motor Vehicles"})
    vale = AS.select("vale-s-a", name="Vale S.A.",
                     registrant={"sic": "1000",
                                 "sic_description": "Metal Mining"})
    assert toyota.archetype not in ("", "UNKNOWN")
    assert vale.archetype not in ("", "UNKNOWN")
    assert toyota.decision_question != vale.decision_question
    assert {s.name for s in toyota.signals} != {s.name for s in vale.signals}


def test_sparse_company_selection_explains_itself():
    """An unclassified company gets the generic path AND is told why."""
    sel = AS.select("olo-inc", name="Olo Inc.", registrant=None)
    assert sel.why_this_question
    assert "manifest" in sel.why_this_question.lower()
