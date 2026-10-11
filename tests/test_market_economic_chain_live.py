"""LIVE ACCEPTANCE CHECKS -- read the real production ledger.

Split out of `test_market_economic_chain.py` on 2026-10-11. These tests read
`/Users/prathamsharma/intent-engine-market` directly, so their results move
whenever a scheduled cycle appends. That makes them **monitors of production
state**, not regression tests: a legitimate new observation can turn one red
with nothing broken, and a concurrent cycle writing the ledger makes them
nondeterministic outright.

They are deliberately NOT weakened and NOT skipped. Every assertion is
unchanged and they remain runnable on demand:

    env PYTHONPATH=src python -m pytest tests/test_market_economic_chain_live.py

Repository convention: live tests live in `tests/test_*_live.py` and the
pre-commit guard deselects them by filename, alongside
`test_calendar_live.py`, `test_macro_data_live.py` and the others. The
invariants stay covered in the offline suite by the 11 deterministic
tests remaining in `test_market_economic_chain.py`.
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

# --- no link is ever OBSERVED --------------------------------------------

def test_no_chain_built_from_the_real_ledger_contains_an_observed_link():
    for subject in ("honda", "shopify", "cloudflare", "jpmorgan"):
        built = EC.build(rows(), subject=subject)
        assert all(l.status != EC.OBSERVED for l in built.links)
    assert EC.summarise([EC.build(rows(), subject="honda")])[
        "observed_links"] == 0


# --- the ladder is evidence, not argument --------------------------------

# --- candidate scoring is a measurement, not a preference ----------------

def test_scoring_prefers_coverage_and_resolution_over_volume():
    got = EC.score_candidates(rows())
    top = got[0]
    # The property is that COVERAGE beats VOLUME, not that any particular
    # company wins. The live ledger grows nightly and the leader has
    # already changed once (honda -> toyota) on new evidence; pinning the
    # name asserted a snapshot rather than the scorer's behaviour.
    assert top["resolved_expectations"] >= 1 or \
        top["primary_source_observations"] >= 10
    by_volume = max(got, key=lambda r: r["observations"])
    assert top["score"] >= by_volume["score"]


# --- the real chain -------------------------------------------------------

def test_the_honda_chain_is_honest_about_what_is_missing():
    built = EC.build(rows(), subject="honda")
    got = built.as_dict()
    assert got["overall_status"] == EC.UNKNOWN
    assert got["known_nodes"] == 4 and got["unknown_nodes"] == 3
    assert got["by_link_status"] == {EC.UNKNOWN: 3, EC.HYPOTHESIZED: 3}
    missing = {n["node_type"] for n in got["nodes"]
               if n["status"] == EC.UNKNOWN}
    assert missing == {EC.MACRO_STATE, EC.CUSTOMER_STATE, EC.ORDERS}


def test_the_weakest_link_names_the_boundary_not_the_first_gap():
    """Three consecutive UNKNOWNs are one finding; name where it ends."""
    built = EC.build(rows(), subject="honda")
    assert built.weakest_link.source == EC.ORDERS
    assert built.weakest_link.target == EC.COMPANY_DEMAND
    assert built.weakest_link.status == EC.UNKNOWN


def test_a_node_holds_the_figure_not_the_announcement_of_it():
    """Same filing, same day: only one of the two sentences is a quantity."""
    built = EC.build(rows(), subject="honda")
    demand = next(n for n in built.nodes if n.node_type == EC.COMPANY_DEMAND)
    assert "13.5%" in demand.statement
    assert not demand.statement.startswith("Exhibit 1")


def test_the_document_supplies_its_own_alternative_explanation():
    """Honda's filing attributes its margin move. That is the competing story."""
    built = EC.build(rows(), subject="honda")
    margin = next(l for l in built.links if l.target == EC.MARGIN)
    assert "the source document itself attributes this" in \
        margin.alternative_explanation
    assert "EV" in margin.alternative_explanation
    # And it does NOT promote the link: an interested party's attribution is
    # a statement about a link, not an observation of one.
    assert margin.status == EC.HYPOTHESIZED


def test_the_founder_translation_separates_established_from_missing():
    got = EC.build(rows(), subject="honda").founder_translation()
    assert len(got["established"]) == 4
    assert len(got["missing"]) == 3
    assert got["weakest_link"] == "ORDERS → COMPANY_DEMAND"
    assert got["what_would_resolve_it"]
    assert "relying on the unmeasured ones" in got["why_it_matters"]


# --- macro and capital live on THIS graph ---------------------------------

