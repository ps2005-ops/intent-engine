"""A run that never reached the analyst must not be explained as thin evidence.

FOUND BY THE FIRST BREAKER WAVE. The Anthropic balance was exhausted, so
`analyse()` returned FAILED — and the founder was shown "every source here is
the company's own account. Independent reporting ... would strengthen this."

That reader goes and collects more sources. It cannot help: nothing was wrong
with the evidence. The code three lines above the defect already says why this
matters — a founder told the wrong reason acts on the wrong thing — but the
branch was keyed on `!= COMPLETE`, so it caught every failure including the
ones that are about us rather than about the company.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.analyst.contract import ResultState


def test_only_evidence_caused_states_are_explained_by_evidence():
    assert ResultState.EVIDENCE_EXPLAINED == (
        ResultState.EVIDENCE_LIMITED, ResultState.STRATEGICALLY_INSUFFICIENT)


@pytest.mark.parametrize("state", [ResultState.FAILED,
                                   ResultState.RETRIEVAL_BLOCKED,
                                   ResultState.ENTITY_AMBIGUOUS])
def test_a_state_that_is_about_us_is_not_an_evidence_shortfall(state):
    """These three mean the analysis did not get to look, or looked at the
    wrong company. None of them is a statement about how much evidence the
    company has published."""
    assert state not in ResultState.EVIDENCE_EXPLAINED


@pytest.mark.parametrize("state", ResultState.ALL)
def test_every_state_still_has_an_honest_explanation(state):
    text = ResultState.EXPLANATION.get(state, "")
    assert text, state


def test_the_failed_explanation_does_not_blame_the_sources():
    text = ResultState.EXPLANATION[ResultState.FAILED].lower()
    for misleading in ("source", "evidence", "independent", "retrieved"):
        assert misleading not in text, (
            f"the FAILED explanation mentions {misleading!r}; a run that "
            f"never completed is not a statement about the evidence")


def test_the_call_site_gates_on_the_set_and_not_on_not_complete():
    """The guard is a SET MEMBERSHIP at the call site, and this reads the
    code to prove it.

    A monkeypatch asserting `explain` was not called would pass whether or
    not the branch was fixed, because the state under test never reaches it
    either way — a test that cannot fail. The AST is what actually changed.
    """
    import ast
    import pathlib

    import intent_engine.company_ingestion.service as service

    tree = ast.parse(pathlib.Path(service.__file__).read_text())
    gates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body = ast.dump(node)
        if "withheld_explanation" in body or "WX" in body:
            gates.append(ast.dump(node.test))
    assert gates, "the withheld-explanation branch was not found"
    assert any("EVIDENCE_EXPLAINED" in g for g in gates), (
        "the evidence explanation is not gated on ResultState."
        "EVIDENCE_EXPLAINED; a non-evidence failure will be blamed on the "
        f"sources again: {gates}")
