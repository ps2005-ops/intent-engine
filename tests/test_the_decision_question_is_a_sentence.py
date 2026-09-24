"""The central question must read as English, on every company.

MEASURED LIVE at 591041b0, on the captured X-Ray of the twenty-five. Four
companies established something of their own and had it substituted into the
pricing question. THREE OF THE FOUR came out broken:

    Procore       "...without losing more customer count among vital role in
                   our customers' operations than the price gains?"
    ServiceTitan  "...among experience their own rapid technological changes
                   than the price gains?"
    NinjaOne      "...without losing more device than the price gains?"
    Okta          "...among human users than the price gains?"   <- correct

The first two are the BUYER slot accepting something that is not a
population. The third is the BILLING UNIT slot landing a singular count noun
after "more". Okta is the control: the repair must leave it alone, because a
rule that refuses everything buys differentiation at the price of truth --
and §11 says downgrade, not manufacture.

NOTE ON DIRECTION. Repairing this REDUCES measured differentiation: Procore
and ServiceTitan fall back to the class constant. That is the correct
direction. Two of the five "distinct" questions in this cohort were garbage,
and a distinct-question count that counts them is measuring noise.
"""
import pytest

from intent_engine.executive import analysis_selection as AS
from intent_engine.executive import decision_object as DO

#: Verbatim from the captured pages at 591041b0.
PROCORE = "vital role in our customers' operations"
SERVICETITAN = "experience their own rapid technological changes"
OKTA = "human users"


def _why(phrase, kind="BUYER"):
    return DO._acceptable(phrase, "Acme Corp", kind)


# ------------------------------------------------------------------ buyer
def test_the_live_procore_buyer_is_refused():
    why = _why(PROCORE)
    assert why, f"{PROCORE!r} was accepted as a population"
    assert "population" in why


def test_the_live_servicetitan_buyer_is_refused():
    why = _why(SERVICETITAN)
    assert why, f"{SERVICETITAN!r} was accepted as a population"
    assert "points back" in why


def test_the_live_okta_buyer_still_passes():
    """THE CONTROL. A repair that also refuses this one has not worked."""
    assert _why(OKTA) == "", _why(OKTA)


@pytest.mark.parametrize("phrase", [
    "mid-market enterprises across north america",
    "security teams",
    "managed service providers",
    "general contractors",
    "hospitals",
    "law firms",
    "fleets of vehicles",
])
def test_a_real_population_is_not_refused_by_the_new_rules(phrase):
    """The head cut and the possessive rule must not eat good buyers."""
    why = _why(phrase)
    assert "population" not in why and "points back" not in why, \
        f"{phrase!r}: {why}"


def test_the_head_is_taken_before_the_preposition_not_at_the_end():
    """The module's own comment promised this cut; the code did not do it."""
    assert DO._head_noun(PROCORE) == "role"
    assert DO._head_noun("mid-market enterprises across north america") \
        == "enterprises"
    assert DO._head_noun("security teams") == "teams"


@pytest.mark.parametrize("possessive", sorted(DO._POSSESSIVE))
def test_no_possessive_determiner_survives_in_a_buyer(possessive):
    """A population is NAMED, never referred back to -- for every one of a
    genuinely closed class, not the three that happened to be measured."""
    assert _why(f"the {possessive} own regional operators"), possessive


# ----------------------------------------------------------- billing unit
@pytest.mark.parametrize("unit,expected", [
    ("device", "device count"),
    ("seat", "seat count"),
    ("endpoint", "endpoint count"),
    ("human users", "human users"),
    ("managed endpoints", "managed endpoints"),
    ("capacity", "capacity"),
    ("customer count", "customer count"),
    ("", ""),
])
def test_a_unit_can_follow_the_word_more(unit, expected):
    assert AS._countable(unit) == expected


@pytest.mark.parametrize("unit", ["device", "seat", "capacity",
                                  "customer count", "human users"])
def test_the_countable_rule_is_idempotent(unit):
    """"customer count count" is what a non-idempotent version produced."""
    once = AS._countable(unit)
    assert AS._countable(once) == once


def test_the_class_constant_is_already_in_the_shape_the_rule_produces():
    """Why "count" and not a guessed plural: the product already says it."""
    assert AS._countable("customer") == "customer count"
    assert AS._countable("customer count") == "customer count"
