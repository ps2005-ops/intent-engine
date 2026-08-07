"""Refusing to assert is not the same as finding the opposite.

WHERE THIS CAME FROM. Gating `product_to_platform` on third-party dependence
made Stripe stop qualifying. Stripe is, in the world, infrastructure thousands
of businesses depend on — the run's retrieved sources simply never said so.
Refusing was right. Reporting it as though the evidence argued against it
would have been a different error, and the product could not tell the two
apart.

`sufficiency.py` separates them, and this file holds the boundary — including
the one that matters most: a reasoning layer may ask retrieval for a missing
FACT and may never ask it to prove a named conclusion.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from intent_engine.strategic_intelligence import sufficiency as S
from intent_engine.strategic_intelligence.observations import derive_observations
from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY
from intent_engine.strategic_intelligence.records import StrategicObservation

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
P2P = PATTERNS["product_to_platform"]
GATED = [p for p in PATTERN_LIBRARY
         if p.required_signals or p.required_any_signals]


def _obs(oid, signals, excerpt="x", source_class="company_owned"):
    return StrategicObservation(
        observation_id=oid, text="Acme shows a signal.",
        observation_type="product_surface",
        source_refs=[{"artifact_id": oid}], signals=tuple(signals),
        source_class=source_class, excerpt=excerpt, source_title="t",
        origin="https://acme.example/")


# --- the five states ---------------------------------------------------------

def test_a_mechanism_that_is_evidenced_is_supported():
    d = S.classify(P2P, [_obs("o1", ("third_party_builds_on",))])
    assert d["state"] == S.SUPPORTED
    assert not S.explain("Acme", P2P, d), "nothing to explain when supported"


def test_a_thin_run_is_a_retrieval_gap_not_a_finding():
    """THE STRIPE CASE. One homepage, no mechanism. The run was never in a
    position to observe it, so its silence says nothing about the company."""
    d = S.classify(P2P, [_obs("o1", ("infrastructure_positioning",),
                              excerpt="short")])
    assert d["state"] == S.RETRIEVAL_MISSING
    text = S.explain("Stripe", P2P, d)
    assert "did not verify" in text
    assert "not the same as finding it untrue" in text
    assert "usually appear in" in text, "tell the reader where to look"


def test_a_deep_run_that_still_shows_nothing_is_informative():
    """Several kinds of source, one of them substantial, and still no
    mechanism. That absence is worth something."""
    d = S.classify(P2P, [
        _obs("o1", ("infrastructure_positioning",), excerpt="x" * 500),
        _obs("o2", ("product_breadth",), source_class="investor_material")])
    assert d["state"] == S.REASONING_NOT_SUPPORTED
    assert "informative rather than incidental" in S.explain("Acme", P2P, d)


def test_one_weak_disconfirmer_is_not_a_contradiction():
    """MEASURED LIVE ON CLOUDFLARE. Publishing a price list made the page
    say "the public record argues against" the reading. Pricing is
    `tool_to_system_of_record`'s disconfirmer and that pattern's own note
    says why it is weak: a company can publish prices and still hold the
    record. One weak signal is noise."""
    d = S.classify(P2P, [_obs("o1", ("storefront_creation",))])
    assert d["state"] != S.MECHANISM_CONTRADICTED
    assert "argues against" not in S.explain("Acme", P2P, d)


def test_evidence_pointing_the_other_way_is_a_contradiction():
    """A second disconfirmer is a direction rather than noise."""
    d = S.classify(P2P, [_obs("o1", ("storefront_creation",
                                     "smb_simplicity"))])
    assert d["state"] == S.MECHANISM_CONTRADICTED
    assert "argues against" in S.explain("Acme", P2P, d)


def test_a_refused_source_is_neither_absence_nor_contradiction():
    d = S.classify(P2P, [_obs("o1", ("infrastructure_positioning",))],
                   blocked_families=("developer_docs",))
    assert d["state"] == S.RETRIEVAL_BLOCKED
    assert "unavailable to this run" in S.explain("Acme", P2P, d)


def test_the_four_unsupported_states_read_differently_to_a_reader():
    """If two diagnoses produce the same sentence, the distinction is
    internal bookkeeping and the founder gains nothing."""
    said = {
        S.explain("Acme", P2P, S.classify(
            P2P, [_obs("o1", ("infrastructure_positioning",))])),
        S.explain("Acme", P2P, S.classify(
            P2P, [_obs("o1", ("infrastructure_positioning",), "x" * 500),
                  _obs("o2", ("product_breadth",), source_class="investor_material")])),
        S.explain("Acme", P2P, S.classify(
            P2P, [_obs("o1", ("storefront_creation",
                              "smb_simplicity"))])),
        S.explain("Acme", P2P, S.classify(
            P2P, [_obs("o1", ("infrastructure_positioning",))],
            blocked_families=("x",))),
    }
    assert len(said) == 4, said


# --- an ungated pattern has nothing to be insufficient about ------------------

def test_an_ungated_pattern_is_not_diagnosed():
    ungated = next(p for p in PATTERN_LIBRARY
                   if not (p.required_signals or p.required_any_signals))
    assert S.classify(ungated, [_obs("o1", ())])["state"] is None


# --- the confirmation-bias boundary ------------------------------------------

@pytest.mark.parametrize("pattern", GATED, ids=lambda p: p.pattern_id)
def test_retrieval_is_never_asked_to_prove_a_named_hypothesis(pattern):
    """THE RULE THAT KEEPS THIS HONEST.

    A retrieval layer told which CONCLUSION to support will find support for
    it. One told which FACT is missing can come back empty — and coming back
    empty has to stay possible, or the gate is theatre.
    """
    asked = " ".join(S.mechanism_request(pattern)).lower()
    for pid in PATTERNS:
        assert pid not in asked, f"asked retrieval to prove {pid}"
        assert pid.replace("_", " ") not in asked
    for word in ("prove", "confirm that", "show that the company is",
                 "hypothesis", "pattern"):
        assert word not in asked, f"{word!r} turns a fact request into a brief"


def test_a_mechanism_request_names_a_fact_and_where_it_lives():
    asked = S.mechanism_request(P2P)
    assert asked
    assert any("third party builds on" in a for a in asked)
    assert any("marketplace" in a or "developer documentation" in a
               for a in asked)


def test_no_module_asks_retrieval_for_a_named_pattern():
    """Guard the boundary at the source, not only in this module."""
    src = pathlib.Path(__file__).resolve().parents[1] / "src/intent_engine"
    offenders = []
    for path in src.rglob("*.py"):
        if path.name in ("patterns.py", "sufficiency.py"):
            continue
        text = path.read_text()
        for pid in PATTERNS:
            if re.search(rf"(retriev|fetch|search|query|discover)\w*"
                         rf"[^\n]{{0,60}}{re.escape(pid)}", text, re.I):
                offenders.append(f"{path.name}: {pid}")
    assert not offenders, offenders


# --- it composes with the real pipeline --------------------------------------

def test_the_stripe_shape_end_to_end():
    """A company that positions as infrastructure and never evidences
    dependence gets a refusal AND an explanation of what was missing."""
    obs = derive_observations([{
        "source_id": "s1", "source_type": "product", "title": "Acme",
        "final_url": "https://acme.example/", "meta_description": "",
        "text_content": "Acme is payments infrastructure. One platform for "
                        "billing and payouts.",
        "retrieval_status": "OK", "freshness": "CURRENT", "content_hash": "s1",
        "retrieved_at": "2026-08-07", "parser_version": "p1"}], company="Acme")
    d = S.classify(P2P, obs)
    assert d["state"] in (S.RETRIEVAL_MISSING, S.REASONING_NOT_SUPPORTED)
    assert d["missing"], "the diagnosis must name what was absent"
    assert "third_party_builds_on" in d["missing"]
