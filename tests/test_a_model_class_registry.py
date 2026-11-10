"""A business-model class added tomorrow may not be invisible to these tables.

MEASURED LIVE. Three classes were added one cycle ago — ADVERTISING_PLATFORM,
MULTI_ENGINE_PLATFORM, SCALE_RETAIL — and `MODEL_CLASSES`, the tuple that was
supposed to be the registry, was not updated. Nothing read it, so nothing
noticed, and three separate producers keyed on model class silently disagreed
about which classes exist:

    patterns_for                      filtered by an EXCLUSION list, so the
                                      three new classes qualified for 12 of 12
                                      patterns while every older class was
                                      filtered to 5-11
    strategic_read._METRICS           no entry: three companies were judged on
                                      no model-specific metric at all
    competitive_ground._MODEL_ALTERNATIVES
                                      no entry: Meta's whole competitive
                                      ground was one row until repaired

The customer-visible result of the first was measured through the deployed
Q&A on three companies: Meta (an advertising auction), Caterpillar (an
equipment maker) and Exxon (an oil major) answered NINE OF TEN board
questions with the identical sentence — "committing capital to capacity ahead
of uncertain demand" — and all three were offered "Memory and sensor
fabrication cycles" as the historical analogy. `capacity_ahead_of_demand`'s
own `when_it_does_not_apply` says "demand is spread across many independent
buyers", which is exactly what an advertising auction has.

A denylist cannot exclude a class that did not exist when it was written.
These tests make the registry load-bearing: adding a thirteenth class turns
the suite red until every table below has decided about it.
"""
from __future__ import annotations

import pytest

from intent_engine.executive.company_profile import (
    MODEL_CLASSES, missing_model_classes,
)


# ===========================================================================
# The registry itself
# ===========================================================================
def test_the_registry_holds_every_class_the_classifier_can_produce():
    """Every class any producer can assign must be registered. The SIC table
    and the revenue/segment hints are what actually assign them."""
    from intent_engine.executive import company_profile as CP
    assigned = {cls for cls, _sector in CP._SIC_CLASS.values()} \
        if hasattr(CP, "_SIC_CLASS") else set()
    assigned |= {"ADVERTISING_PLATFORM", "MULTI_ENGINE_PLATFORM"}
    unregistered = sorted(assigned - set(MODEL_CLASSES))
    assert not unregistered, f"assignable but unregistered: {unregistered}"


def test_the_registry_has_no_duplicates():
    assert len(MODEL_CLASSES) == len(set(MODEL_CLASSES))


def test_missing_model_classes_reports_in_registry_order():
    assert missing_model_classes(MODEL_CLASSES[:9]) == list(MODEL_CLASSES[9:])
    assert missing_model_classes(MODEL_CLASSES) == []


# ===========================================================================
# Every model-keyed table must cover the registry
# ===========================================================================
#: Modules that make a decision keyed on business-model class. A module is
#: listed here; its TABLES are discovered, not named — the previous version
#: named two of eleven, and the nine it did not name were exactly the ones
#: with no entry for the three newest classes.
_MODEL_KEYED_MODULES = (
    "intent_engine.company_ingestion.xbrl",              # metric selection
    "intent_engine.product_eval.defect_taxonomy",        # foreign-language
    "intent_engine.executive.competitive_ground",        # mechanism / rivals
    "intent_engine.executive.belief_engine",             # market belief
    "intent_engine.executive.strategic_read",            # metrics, mechanisms
    "intent_engine.executive.history_simulator",         # history + rewind
    "intent_engine.executive.company_profile",           # economics, history
    "intent_engine.executive.analysis_selection",        # decision candidates
)

#: A table is model-keyed if it is a dict whose keys include at least this
#: many REGISTERED classes. Three is enough to distinguish a model table from
#: a dict that happens to contain one class name, and low enough that a table
#: covering only the nine older classes is still caught.
_MODEL_KEYED_THRESHOLD = 3


def _tables():
    """Every model-class-keyed table in the product, discovered.

    NAMING THE TABLES IS THE BUG. Two were named and eleven exist; the nine
    unnamed ones had no row for ADVERTISING_PLATFORM, MULTI_ENGINE_PLATFORM
    or SCALE_RETAIL, so Meta got no model-specific financial index, no
    market-belief engine, no competitive mechanism, no history economics and
    no counterfactual — and, worst, no entry in the very table that detects
    take-or-pay language in a business that has no order book.

    A table added tomorrow is discovered by the same rule, so this cannot
    silently go stale again.
    """
    import importlib
    registry = set(MODEL_CLASSES)
    found = {}
    for module_name in _MODEL_KEYED_MODULES:
        module = importlib.import_module(module_name)
        short = module_name.rsplit(".", 1)[-1]
        for attr in dir(module):
            value = getattr(module, attr, None)
            if not isinstance(value, dict) or not value:
                continue
            keys = {k for k in value if isinstance(k, str)}
            if len(keys & registry) >= _MODEL_KEYED_THRESHOLD:
                found[f"{short}.{attr}"] = value
    assert found, "no model-keyed table was discovered at all"
    return found


def test_the_discovery_finds_more_than_the_two_that_used_to_be_named():
    """A guard that discovers nothing is a guard that passes for free."""
    discovered = set(_tables())
    assert {"strategic_read._METRICS",
            "competitive_ground._MODEL_ALTERNATIVES"} <= discovered
    assert len(discovered) >= 10, sorted(discovered)


@pytest.mark.parametrize("table_name", sorted(_tables()))
def test_every_model_keyed_table_covers_the_registry(table_name):
    table = _tables()[table_name]
    missing = missing_model_classes(table)
    assert not missing, (
        f"{table_name} has no entry for {missing}. A class the registry knows "
        f"about and this table does not is a company judged by a default.")


# ===========================================================================
# Pattern applicability must be POSITIVE, not merely un-excluded
# ===========================================================================
def test_every_pattern_has_considered_every_registered_class():
    """THE DEFECT, DIRECTLY. A pattern that has not ruled on a class must not
    be offered for it — and a pattern that has ruled on none of them would
    accept all of them."""
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY
    undecided = {}
    for pattern in PATTERN_LIBRARY:
        missing = missing_model_classes(
            tuple(pattern.considered_model_classes or ()))
        if missing:
            undecided[pattern.pattern_id] = missing
    assert not undecided, f"patterns that have not ruled on a class: {undecided}"


def test_a_pattern_is_not_offered_for_a_class_it_never_considered():
    from intent_engine.strategic_intelligence.records import ComparablePattern
    p = ComparablePattern(
        pattern_id="probe", name="p", description="d", mechanism="m",
        historical_examples=[{"name": "x", "note": "n", "source": "s"}],
        when_it_applies="a", when_it_does_not_apply="b",
        qualifying_signals=("multi_product",),
        considered_model_classes=("SUBSCRIPTION_SOFTWARE",))
    assert p.applies_to_model("SUBSCRIPTION_SOFTWARE")
    assert not p.applies_to_model("SCALE_RETAIL")
    # An unclassified company still gets the whole library, unchanged.
    assert p.applies_to_model("")
    assert p.applies_to_model("UNKNOWN")


def test_an_exclusion_still_wins_over_consideration():
    from intent_engine.strategic_intelligence.records import ComparablePattern
    p = ComparablePattern(
        pattern_id="probe2", name="p", description="d", mechanism="m",
        historical_examples=[{"name": "x", "note": "n", "source": "s"}],
        when_it_applies="a", when_it_does_not_apply="b",
        qualifying_signals=("multi_product",),
        considered_model_classes=("SCALE_RETAIL",),
        excluded_model_classes=("SCALE_RETAIL",))
    assert not p.applies_to_model("SCALE_RETAIL")


# ===========================================================================
# The measured collapse, as a regression control
# ===========================================================================
def test_a_capacity_thesis_is_not_offered_to_an_advertising_auction():
    """Meta's buyers are millions of independent advertisers, which is the
    pattern's own stated non-applicability."""
    from intent_engine.strategic_intelligence.patterns import patterns_for
    offered = {p.pattern_id for p in patterns_for("ADVERTISING_PLATFORM")}
    assert "capacity_ahead_of_demand" not in offered


def test_a_capacity_thesis_is_still_offered_to_a_manufacturer():
    """The repair must not empty the library for the businesses the pattern
    was written for."""
    from intent_engine.strategic_intelligence.patterns import patterns_for
    for model in ("DESIGN_AND_MANUFACTURE", "MANUFACTURE_AND_AFTERMARKET"):
        offered = {p.pattern_id for p in patterns_for(model)}
        assert "capacity_ahead_of_demand" in offered, model


def test_no_class_qualifies_for_the_entire_library():
    """Qualifying for every pattern is the signature of being gated by
    nothing. The three new classes each qualified for 12 of 12."""
    from intent_engine.strategic_intelligence.patterns import (
        PATTERN_LIBRARY, patterns_for,
    )
    total = len(PATTERN_LIBRARY)
    for model in MODEL_CLASSES:
        assert len(patterns_for(model)) < total, (
            f"{model} qualifies for all {total} patterns, so nothing is "
            f"gating it")


def test_every_class_still_gets_a_reading():
    """The opposite failure: a class filtered down to nothing would trade a
    wrong reading for no reading, which is worse."""
    from intent_engine.strategic_intelligence.patterns import patterns_for
    for model in MODEL_CLASSES:
        assert len(patterns_for(model)) >= 4, model


# ===========================================================================
# THE DURABLE GUARD. Today's exclusions already filter today's classes, so a
# test over today's registry cannot tell a denylist from a considered list.
# The defect was about the class added TOMORROW, so the proof has to add one.
# ===========================================================================
def test_a_class_added_tomorrow_does_not_inherit_the_whole_library():
    """THE DEFECT, IN ITS GENERAL FORM.

    A denylist cannot exclude what did not exist when it was written. Simulate
    the next class exactly as the last three arrived — registered, assignable,
    and named in nobody's exclusion list — and require that it does NOT
    silently qualify for every pattern.
    """
    from intent_engine.strategic_intelligence.patterns import (
        PATTERN_LIBRARY, patterns_for,
    )
    tomorrow = "A_CLASS_NOBODY_HAS_RULED_ON_YET"
    assert all(tomorrow not in (p.excluded_model_classes or ())
               for p in PATTERN_LIBRARY), "fixture must be un-excluded"
    offered = patterns_for(tomorrow)
    assert len(offered) < len(PATTERN_LIBRARY), (
        f"an unconsidered class qualified for all {len(PATTERN_LIBRARY)} "
        f"patterns — applicability is being read off the denylist again")
    assert offered == [], (
        "a class no pattern has ruled on should be offered nothing, so the "
        "completeness guard is what admits it rather than silence")


def test_an_unclassified_company_still_gets_the_whole_library():
    """The opposite failure. Withholding every pattern from a company we
    could not classify trades a wrong reading for no reading, and no reading
    is the failure this module was reopened to fix."""
    from intent_engine.strategic_intelligence.patterns import (
        PATTERN_LIBRARY, patterns_for,
    )
    for unknown in ("", "UNKNOWN", None):
        assert len(patterns_for(unknown)) == len(PATTERN_LIBRARY), unknown


# ===========================================================================
# The thirteenth class
# ===========================================================================
def test_a_thirteenth_class_fails_every_model_keyed_system_closed():
    """THE POINT OF A REGISTRY. Today's three exclusions already mask
    today's symptom, so nothing above proves the next class will be caught.
    This simulates one and requires every discovered model-keyed table to
    report it missing — which is what turns the suite red until a human has
    decided what that class's metric, belief, mechanism, history and
    foreign-language set actually are.

    If this test ever passes with an EMPTY report, the registry has stopped
    being load-bearing and a fourteenth class will inherit generic logic in
    silence, exactly as the thirteenth's three predecessors did.
    """
    thirteenth = "NEW_MODEL_CLASS_13"
    assert thirteenth not in MODEL_CLASSES
    registry = tuple(MODEL_CLASSES) + (thirteenth,)
    uncovered = [name for name, table in _tables().items()
                 if thirteenth not in table]
    assert len(uncovered) == len(_tables()), (
        "a model-keyed table already answers for a class nobody defined: "
        f"{sorted(set(_tables()) - set(uncovered))}")

    # And the same must hold for the pattern library's applicability.
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY
    undecided = [p.pattern_id for p in PATTERN_LIBRARY
                 if thirteenth not in (p.considered_model_classes or ())]
    assert len(undecided) == len(PATTERN_LIBRARY), (
        "a pattern already claims to have considered an undefined class")

    # `missing_model_classes` is the mechanism each guard above uses, so it
    # must report the new class against every table.
    from intent_engine.executive.company_profile import missing_model_classes
    for name, table in _tables().items():
        assert thirteenth in missing_model_classes(table, registry=registry), \
            f"{name} would not report the thirteenth class as missing"
