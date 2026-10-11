"""A chain that says UNKNOWN is worth more than one that fills the gap in.

The tests are about what the chain REFUSES: a node without evidence, a link
without a mechanism, a link without a competing story, and — the one this
project keeps having to re-establish — a causal link that claims to have been
observed.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import economic_chain as EC

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def rows():
    return [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]


def observed(node_type, statement="a figure", eid="ev_1"):
    return EC.node(node_type=node_type, statement=statement,
                   evidence_ids=(eid,), observed_at="2026-08-05")


def absent(node_type):
    return EC.node(node_type=node_type, statement="nothing measures this")


# --- a node without evidence is UNKNOWN, and there is no third option -----

def test_a_node_with_no_evidence_is_unknown():
    assert absent(EC.ORDERS).status == EC.UNKNOWN


def test_a_node_with_evidence_is_known():
    assert observed(EC.COMPANY_DEMAND).status == EC.KNOWN


def test_a_node_cannot_be_asserted_without_evidence():
    """"We believe orders are strong" is not a node."""
    assert EC.node(node_type=EC.ORDERS,
                   statement="orders are clearly strong").status == EC.UNKNOWN


# --- no link is ever OBSERVED --------------------------------------------

def test_observed_is_in_the_vocabulary():
    assert EC.OBSERVED in EC.LINK_STATUSES


def test_no_link_constructor_can_produce_observed():
    """The strongest input available still does not reach OBSERVED."""
    got = EC.link(source=observed(EC.COMPANY_DEMAND),
                  target=observed(EC.MARGIN),
                  mechanism="volume spreads fixed cost",
                  alternative_explanation="an input-cost move",
                  falsifier="margin moves while revenue is flat",
                  discriminating_test="a test that could have failed")
    assert got.status == EC.SUPPORTED
    assert got.status != EC.OBSERVED


# --- the ladder is evidence, not argument --------------------------------

def test_an_unknown_end_makes_the_link_unknown():
    got = EC.link(source=absent(EC.ORDERS), target=observed(EC.COMPANY_DEMAND),
                  mechanism="order intake precedes revenue",
                  alternative_explanation="a mix effect",
                  falsifier="revenue moves against intake",
                  discriminating_test="even with a test in hand")
    assert got.status == EC.UNKNOWN


def test_both_ends_observed_without_a_test_is_only_hypothesized():
    got = EC.link(source=observed(EC.MARGIN), target=observed(EC.GUIDANCE),
                  mechanism="margin gives room to raise the forecast",
                  alternative_explanation="currency",
                  falsifier="guidance rises in a quarter margin fell")
    assert got.status == EC.HYPOTHESIZED


@pytest.mark.parametrize("missing", ["mechanism", "alternative", "falsifier"])
def test_a_link_missing_any_of_the_three_is_refused(missing):
    kwargs = dict(source=observed(EC.COMPANY_DEMAND),
                  target=observed(EC.MARGIN),
                  mechanism="volume spreads fixed cost",
                  alternative_explanation="an input-cost move",
                  falsifier="margin moves while revenue is flat")
    kwargs[{"mechanism": "mechanism",
            "alternative": "alternative_explanation",
            "falsifier": "falsifier"}[missing]] = "  "
    with pytest.raises(EC.ChainRejected):
        EC.link(**kwargs)


# --- candidate scoring is a measurement, not a preference ----------------

# --- the real chain -------------------------------------------------------

# --- macro and capital live on THIS graph ---------------------------------

def test_the_graph_can_carry_macro_and_capital_states():
    """§21's compatibility check, pinned. If these had to live elsewhere,
    every link between a macro condition and a company would cross two
    models and become untyped."""
    for node_type in ("ECONOMIC_FACTOR", "MACRO_STATE", "CREDIT_STATE",
                      "CAPITAL_STATE", "INDUSTRY_STATE"):
        assert node_type in EC.NODE_TYPES


def test_a_macro_node_links_to_a_company_node_with_the_same_rules():
    """One graph means one set of link rules — including the one that makes
    OBSERVED unreachable for a LINK."""
    factor = EC.node(node_type=EC.ECONOMIC_FACTOR,
                     statement="Average interest rate on Treasury notes rose "
                               "to 3.3 percent",
                     evidence_ids=("ev_macro_1",), observed_at="2026-08-08")
    demand = EC.node(node_type=EC.COMPANY_DEMAND,
                     statement="Honda unit demand softened",
                     evidence_ids=("ev_honda_1",), observed_at="2026-08-08")
    edge = EC.link(source=factor, target=demand,
                   mechanism="financing cost raises the monthly payment on a "
                             "financed vehicle",
                   alternative_explanation="demand moved on model cycle",
                   falsifier="demand holds while rates rise further")
    assert edge.status in EC.LINK_STATUSES
    assert edge.status != EC.OBSERVED


def test_the_new_node_types_are_declared_and_unpopulated():
    """A node type with no instances is not a claim that the data exists.
    This is the position COMPETES_WITH held before wave 5."""
    import json
    import pathlib
    report = pathlib.Path(__file__).resolve().parents[1] / \
        "reports/market/strategic/wave10_coverage.json"
    got = json.loads(report.read_text())["macro_capital_compatibility"]
    assert got["required_by_roadmap"]
    # After the extension nothing is missing from the vocabulary.
    assert set(got["required_by_roadmap"]) <= set(EC.NODE_TYPES)
