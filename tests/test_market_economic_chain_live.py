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


def test_the_honda_chain_is_honest_about_what_is_missing():
    """COUNTS REPLACED BY THE STRUCTURE THEY WERE STANDING IN FOR.

    This asserted `known_nodes == 4`, `unknown_nodes == 3` and a missing set
    of exactly {MACRO_STATE, CUSTOMER_STATE, ORDERS}. All three were facts
    about the live ledger on the day they were written, and the ledger is a
    growing production artifact: measured 2026-08-27 the chain reads 5 known
    and 2 missing, because an orders observation for Honda arrived. The
    engine learned MORE and the suite went red.

    What the module's own docstring actually claims is STRUCTURAL, and it
    holds at every ledger size: the unknown nodes are a PREFIX of the chain.
    The engine knows a great deal about companies and little about the
    economy they sit in, so what is missing is always the top of the
    transmission, never a hole in the middle.
    """
    built = EC.build(rows(), subject="honda")
    got = built.as_dict()
    assert got["overall_status"] == EC.UNKNOWN
    assert got["known_nodes"] + got["unknown_nodes"] == len(got["nodes"])
    assert sum(got["by_link_status"].values()) == len(built.links)

    statuses = [n.status for n in built.nodes]
    unknown_indices = [i for i, st in enumerate(statuses)
                       if st == EC.UNKNOWN]
    assert unknown_indices, "nothing is unknown; the fixture is exhausted"
    assert unknown_indices == list(range(len(unknown_indices))), (
        f"the unknown nodes are not a prefix of the chain: {statuses}. A hole "
        "in the MIDDLE would be a different finding from an unmeasured "
        "economy, and this test exists to tell them apart.")
    assert built.nodes[0].node_type == EC.MACRO_STATE
    assert built.nodes[0].status == EC.UNKNOWN, (
        "MACRO_STATE became known without the shared economic core being "
        "wired into this chain; that is a real change and should be asserted "
        "deliberately rather than passing here by accident")


def test_the_weakest_link_names_the_boundary_not_the_first_gap():
    """Consecutive UNKNOWNs are one finding; name where the run ENDS.

    The node pair was pinned and moved when the ledger grew. The claim is
    relational: the weakest link starts at the LAST unknown node in chain
    order, not the first, because three consecutive gaps are one gap.
    """
    built = EC.build(rows(), subject="honda")
    order = [n.node_type for n in built.nodes]
    unknown = [n.node_type for n in built.nodes if n.status == EC.UNKNOWN]
    assert unknown, "nothing is unknown; the fixture is exhausted"
    assert built.weakest_link.status == EC.UNKNOWN
    assert built.weakest_link.source == unknown[-1], (
        f"the weakest link starts at {built.weakest_link.source}, which is "
        f"not the last unknown node ({unknown[-1]}); naming the FIRST gap "
        "reports a run of three as three separate findings")
    assert order.index(built.weakest_link.target) > \
        order.index(built.weakest_link.source)


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
    """The SPLIT is the claim; the two counts were the ledger's, not the code's."""
    built = EC.build(rows(), subject="honda")
    got = built.founder_translation()
    assert len(got["established"]) + len(got["missing"]) == len(built.nodes)
    assert got["missing"], "nothing is reported missing on a chain with gaps"
    assert got["weakest_link"] == (
        f"{built.weakest_link.source} \u2192 {built.weakest_link.target}")
    assert got["what_would_resolve_it"]
    assert "relying on the unmeasured ones" in got["why_it_matters"]
