"""There is one graph. A second one would be a second truth.

Preventive, and cheap to keep: the moment macro or capital state gets its own
store, every edge between a macro condition and a company crosses two models
and becomes untyped — which is how a "temporary parallel store" becomes
permanent.
"""
from __future__ import annotations

import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "intent_engine"

#: Names that would announce a parallel truth store.
FORBIDDEN_MODULES = ("macro_graph", "economic_graph_v2", "capital_graph",
                     "world_model_v2", "graph_v2")

FORBIDDEN_CLASSES = ("MacroGraph", "EconomicGraphV2", "CapitalGraph",
                     "WorldModelV2")


def test_no_parallel_graph_module_exists():
    for name in FORBIDDEN_MODULES:
        assert not list(SRC.rglob(f"{name}.py")), name


def test_no_parallel_graph_class_is_defined():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in FORBIDDEN_CLASSES:
            assert f"class {name}" not in text, f"{name} in {path.name}"


def test_macro_and_capital_states_live_on_the_canonical_graph():
    """They are node types in the one economic chain vocabulary, not a
    separate model with its own edges."""
    from intent_engine.market import economic_chain as EC
    for node_type in ("ECONOMIC_FACTOR", "MACRO_STATE", "CREDIT_STATE",
                      "CAPITAL_STATE", "INDUSTRY_STATE"):
        assert node_type in EC.NODE_TYPES


def test_a_macro_node_uses_the_same_link_rules_as_a_company_node():
    """One graph means one set of rules — including the one that keeps
    OBSERVED unreachable for a link."""
    from intent_engine.market import economic_chain as EC
    credit = EC.node(node_type=EC.CREDIT_STATE,
                     statement="investment-grade spreads widened 40bp",
                     evidence_ids=("ev_credit_1",), observed_at="2026-08-08")
    capex = EC.node(node_type=EC.CAPEX,
                    statement="the company deferred a plant expansion",
                    evidence_ids=("ev_capex_1",), observed_at="2026-08-08")
    edge = EC.link(source=credit, target=capex,
                   mechanism="a higher cost of debt raises the hurdle rate "
                             "on discretionary capacity",
                   alternative_explanation="the deferral was demand-led",
                   falsifier="capex proceeds while spreads widen further")
    assert edge.status in EC.LINK_STATUSES
    assert edge.status != EC.OBSERVED
