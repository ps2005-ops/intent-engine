"""What a source class is worth.

The defect these pin, measured live on 2026-08-05 (Datadog, preview commit
16dc4b8): the run retrieved and quoted the company's 10-K, and still reported
"every source here is published by the company itself" and withheld every
option. `edgar.py` files a 10-K as `investor_material`, which was EXTERNAL but
not INDEPENDENT, and the gate had only those two tiers.

The fix is not to call a filing independent -- it is management-authored. It is
to give accountability its own tier.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.strategic_intelligence import evidence_classes as EC

FILING = "investor_material"      # what edgar.py assigns to a 10-K/10-Q/8-K
MARKETING = "company_owned"
REPORTING = "independent_reporting"
CUSTOMER = "customer_voice"
COMPETITOR = "competitor"
EXEC = "executive_statement"


# --- the three tiers --------------------------------------------------------
@pytest.mark.parametrize("coverage,expected", [
    ({MARKETING}, "asserted"),
    ({EXEC}, "asserted"),
    ({FILING}, "accountable"),
    ({FILING, MARKETING}, "accountable"),
    ({REPORTING}, "independent"),
    ({CUSTOMER}, "independent"),
    ({COMPETITOR}, "independent"),
    ({FILING, REPORTING}, "independent"),
    ({FILING, CUSTOMER}, "independent"),
    (set(), "none"),
])
def test_evidence_standing(coverage, expected):
    assert EC.evidence_standing(coverage) == expected


def test_a_filing_is_not_ordinary_marketing():
    """The defect. A filing is made under securities law; a marketing page is
    not, and grouping them withheld the whole recommendation."""
    assert EC.evidence_standing({FILING}) != EC.evidence_standing({MARKETING})
    assert EC.has_accountable({FILING})
    assert not EC.has_accountable({MARKETING})


def test_a_filing_is_not_independent_confirmation():
    """The opposite error, which would be worse. Management wrote it."""
    assert not EC.has_independent({FILING})
    assert EC.evidence_standing({FILING}) != "independent"


def test_a_filing_does_not_silence_the_limitation():
    """A filing raises what a reading can support; it never closes the gap."""
    limit = EC.standing_limitation({FILING})
    assert limit
    assert "outside account" in limit


def test_independent_evidence_is_the_only_state_with_no_limitation():
    assert EC.standing_limitation({REPORTING}) == ""
    for coverage in ({FILING}, {MARKETING}, set()):
        assert EC.standing_limitation(coverage) != ""


def test_the_three_limitations_are_distinct():
    """Each tier has to say something different, or the tier is decorative."""
    said = {EC.standing_limitation(c)
            for c in ({FILING}, {MARKETING}, set())}
    assert len(said) == 3


def test_marketing_only_keeps_its_original_wording():
    """Unchanged behaviour where the old rule was already right."""
    assert ("published by the company itself"
            in EC.standing_limitation({MARKETING}))


def test_website_only_names_what_would_test_it():
    assert "would be needed to test" in EC.standing_limitation(set())


# --- backward compatibility and unknown input -------------------------------
def test_an_unknown_source_class_does_not_raise_and_grants_nothing():
    assert EC.evidence_standing({"a_class_added_next_year"}) == "none"
    assert not EC.has_independent({"a_class_added_next_year"})
    assert not EC.has_accountable({"a_class_added_next_year"})


def test_external_still_means_anything_beyond_the_website():
    assert EC.has_external({FILING})
    assert EC.has_external({REPORTING})
    assert not EC.has_external({MARKETING})


def test_a_list_works_as_well_as_a_set():
    """Callers pass whatever `coverage` happens to be."""
    assert EC.evidence_standing([FILING, MARKETING]) == "accountable"


# --- the structural point ---------------------------------------------------
def test_the_independence_rule_is_defined_exactly_once():
    """It was five tuples across the package, which is how the defect
    survived: correcting one corrected nothing."""
    pkg = pathlib.Path(EC.__file__).parent
    literal = '("independent_reporting", "customer_voice", "competitor")'
    offenders = [p.name for p in pkg.glob("*.py")
                 if p.name != "evidence_classes.py"
                 and literal in p.read_text()]
    assert offenders == [], f"independence redefined in {offenders}"


def test_every_consumer_shares_one_definition():
    from intent_engine.strategic_intelligence import (
        insights, model, quality, reasoning, render,
    )
    for mod, attr in ((model, "_INDEPENDENT"), (insights, "_INDEPENDENT"),
                      (render, "_INDEPENDENT"),
                      (quality, "_INDEPENDENT_CLASSES"),
                      (reasoning, "_INDEPENDENT_CLASSES")):
        assert tuple(getattr(mod, attr)) == tuple(EC.INDEPENDENT_CLASSES)
