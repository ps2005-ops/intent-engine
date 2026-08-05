"""The founder side of `strategic_market_intel.v1`: what it renders, and what
it refuses.

The producer lives in a package this branch does not contain, so every test
here works from a payload rather than from an import. That is the boundary
being tested: the founder product must be correct about a file it did not
write and cannot verify by construction.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.external_intel import pack as ep
from intent_engine.external_intel import strategic_contract as sc


def dossier(**overrides) -> dict:
    """A minimal valid dossier. Overrides replace whole top-level keys."""
    payload = {
        "export_version": sc.SCHEMA_VERSION,
        "generated_at": "2026-08-05T00:00:00+00:00",
        "company_id": "palantir",
        "as_of": "2026-08-05",
        "freshness": {"status": "observed", "as_of": "2026-08-05",
                      "age_days": 0, "stale": False, "note": "current"},
        "strategic_beliefs": [{
            "proposition": "Palantir is productising its delivery model",
            "subject": "Palantir", "confidence": 0.54,
            "direction_of_last_change": "WEAKENED",
            "last_updated": "2026-08-05",
            "basis": "a preregistered expectation was contradicted",
            "update_method": "CALIBRATED_HEURISTIC",
            "evidence_ids": ["ev-1"], "limitations": [],
        }],
        "hidden_states": [], "interactions": [],
        "pricing_actions": [], "causal_pathways": [],
        "expectation_mismatches": [], "competitor_reactions": [],
        "information_priorities": [],
        "limitations": [], "evidence_ids": ["ev-1"],
        "disclaimer": sc.DISCLAIMER,
        "interpretation_allowed": [], "interpretation_forbidden": [],
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------- it works
def test_a_valid_dossier_is_read():
    intel = sc.consume(dossier(), expected_company="palantir",
                       today="2026-08-05")
    assert intel.available is True
    assert intel.has_material is True
    assert intel.beliefs[0]["confidence"] == 0.54
    assert intel.age_days == 0 and intel.stale is False


def test_the_dossier_never_promotes_a_reading():
    """Break proof 20: a bounded result must not become rich because a
    strategic dossier exists."""
    intel = sc.consume(dossier(), expected_company="palantir",
                       today="2026-08-05")
    assert intel.changes_readiness is False


# --------------------------------------------------- break proof 19: allowlist
def test_an_unknown_field_fails_closed():
    payload = dossier()
    payload["shadow_policy_performance"] = {"strict": 1.4}
    intel = sc.consume(payload, expected_company="palantir",
                       today="2026-08-05")
    assert intel.available is False
    assert "shadow_policy_performance" in intel.reason


def test_an_unknown_field_nested_inside_a_list_fails_closed():
    """The leak that matters is the one added six months from now, deep in a
    row nobody re-reads."""
    payload = dossier()
    payload["strategic_beliefs"][0]["realised_pnl"] = 12.5
    intel = sc.consume(payload, expected_company="palantir",
                       today="2026-08-05")
    assert intel.available is False
    assert "realised_pnl" in intel.reason


def test_an_object_where_a_leaf_is_declared_fails_closed():
    payload = dossier()
    payload["strategic_beliefs"][0]["basis"] = {"strategy": "momentum"}
    intel = sc.consume(payload, expected_company="palantir",
                       today="2026-08-05")
    assert intel.available is False


# ------------------------------------------ break proof 15: a leak in prose
@pytest.mark.parametrize("leak", [
    "the strategy's win rate improved",
    "Sharpe rose over the window",
    "we cut the long position",
    "our price target moved",
])
def test_a_trading_internal_inside_permitted_free_text_is_refused(leak):
    """Structure alone cannot catch this: `basis` accepts prose by design."""
    payload = dossier()
    payload["strategic_beliefs"][0]["basis"] = leak
    intel = sc.consume(payload, expected_company="palantir",
                       today="2026-08-05")
    assert intel.available is False, f"{leak!r} was rendered"
    assert "trading internal" in intel.reason


def test_the_ordinary_disclaimer_is_not_mistaken_for_a_leak():
    """The disclaimer says "not a statement about any investment position".

    A substring scan that fires on its own boilerplate would refuse every
    dossier ever published, so this pins that it does not.
    """
    intel = sc.consume(dossier(), expected_company="palantir",
                       today="2026-08-05")
    assert intel.available is True


# ------------------------------------------------------------ fail-closed reads
def test_a_wrong_schema_version_is_refused():
    intel = sc.consume(dossier(export_version="strategic_market_intel.v2"),
                       expected_company="palantir", today="2026-08-05")
    assert intel.available is False
    assert "v2" in intel.reason


def test_a_dossier_for_another_company_is_refused():
    intel = sc.consume(dossier(company_id="shopify"),
                       expected_company="palantir", today="2026-08-05")
    assert intel.available is False
    assert "shopify" in intel.reason


def test_a_stale_dossier_is_refused_with_its_age():
    intel = sc.consume(dossier(as_of="2026-06-01"),
                       expected_company="palantir", today="2026-08-05")
    assert intel.available is False
    assert "65 days old" in intel.reason


def test_a_missing_file_is_a_reason_not_a_crash(tmp_path):
    intel = sc.load(tmp_path / "nothing.json", expected_company="palantir")
    assert intel.available is False
    assert intel.reason and "No strategic reading" in intel.reason


def test_a_corrupt_file_is_a_reason_not_a_crash(tmp_path):
    path = tmp_path / "palantir.json"
    path.write_text("{not json")
    intel = sc.load(path, expected_company="palantir")
    assert intel.available is False
    assert intel.available is False and intel.reason


def test_a_real_file_round_trips(tmp_path):
    path = tmp_path / "palantir.json"
    path.write_text(json.dumps(dossier()))
    intel = sc.load(path, expected_company="palantir", today="2026-08-05")
    assert intel.available is True and intel.beliefs


# --------------------------------------------------------------- the filename
@pytest.mark.parametrize("name,key", [
    ("Palantir", "palantir"),
    ("Palantir Technologies", "palantir-technologies"),
    ("  Shopify  ", "shopify"),
    ("Berkshire Hathaway Inc.", "berkshire-hathaway-inc"),
    ("AT&T", "at-t"),
    ("", ""),
])
def test_company_key_is_pinned_on_both_sides(name, key):
    """The producer derives this key independently.

    If the two implementations drift the failure is SILENT — no file is found
    and "no dossier published" is a legitimate state, so nothing reports an
    error. This table is what both sides are checked against.
    """
    assert sc.company_key(name) == key


# ------------------------------------------------------- relevance in the pack
def test_an_absent_dossier_adds_no_section():
    """Most runs have no dossier. That is our deployment topology, not
    intelligence about the company, so it must not print."""
    context = ep.build_context(strategic=sc.unavailable("nothing published"))
    assert context.has_strategic is False
    assert ep.STRATEGIC not in context.relevant_sections()


def test_a_valid_but_empty_dossier_adds_no_section():
    empty = sc.consume(dossier(strategic_beliefs=[], evidence_ids=[]),
                       expected_company="palantir", today="2026-08-05")
    assert empty.available is True and empty.has_material is False
    context = ep.build_context(strategic=empty)
    assert context.has_strategic is False


def test_a_dossier_with_material_earns_its_section():
    intel = sc.consume(dossier(), expected_company="palantir",
                       today="2026-08-05")
    context = ep.build_context(strategic=intel)
    assert context.has_strategic is True
    assert ep.STRATEGIC in context.relevant_sections()


# --------------------------------------------- what the reasoning layer sees
def test_a_posture_always_carries_its_live_alternatives():
    """Break proof 5: a hidden state must never be asserted as certain."""
    intel = sc.consume(dossier(hidden_states=[{
        "subject": "Palantir", "leading_state": "PRODUCTIZING",
        "leading_probability": 0.56,
        "alternatives": [{"state": "SERVICES_DEPENDENT", "probability": 0.25}],
        "moved": [{"state": "PRODUCTIZING", "from": 0.31, "to": 0.56}],
        "as_of": "2026-08-05", "evidence_ids": ["ev-1"],
        "certainty_note": "Posture is inferred and is never certain.",
    }]), expected_company="palantir", today="2026-08-05")
    blocks = ep.reasoning_pack(ep.build_context(strategic=intel))["blocks"]
    posture = [b for b in blocks if "leading reading" in " ".join(b["facts"])]
    assert posture, blocks
    text = " ".join(posture[0]["facts"])
    assert "SERVICES_DEPENDENT" in text, "alternatives must travel with it"
    assert "31% → 56%" in text
    assert posture[0]["limitations"], "the certainty note must survive"


def test_an_inferred_objective_never_becomes_a_known_motive():
    """Break proof 6: a competitor's motive is inferred, never proven."""
    intel = sc.consume(dossier(interactions=[{
        "focal_actor": "Rival A", "responding_actor": "Palantir",
        "initial_action": "cut list price 15%", "response": "matched",
        "at": "2026-07-20", "response_lag_days": 6,
        "payoff_change": "NEGATIVE", "payoff_note": "margin pressure",
        "inferred_objective": "buying share",
        "alternative_explanations": ["excess capacity", "weak demand"],
        "evidence_ids": ["ev-2"], "status": "OBSERVED",
    }]), expected_company="palantir", today="2026-08-05")
    blocks = ep.reasoning_pack(ep.build_context(strategic=intel))["blocks"]
    interaction = [b for b in blocks if "Rival A" in " ".join(b["facts"])]
    assert interaction, blocks
    limits = " ".join(interaction[0]["limitations"])
    assert "excess capacity" in limits and "weak demand" in limits
    assert "inferred" in limits.lower()


def test_a_predicted_reaction_is_labelled_as_not_yet_happened():
    """Break proof 13: a fabricated actor response must be distinguishable
    from an observed one."""
    intel = sc.consume(dossier(competitor_reactions=[{
        "responder": "Rival B", "response": "bundles the adjacent product",
        "confidence": "plausible", "payoff_effect": "switching cost rises",
        "rationale": "it has the adjacent product already",
        "precedents": "", "second_order": "", "evidence_ids": ["ev-3"],
        "is_prediction": True,
    }]), expected_company="palantir", today="2026-08-05")
    blocks = ep.reasoning_pack(ep.build_context(strategic=intel))["blocks"]
    reaction = [b for b in blocks if "Rival B" in " ".join(b["facts"])]
    assert reaction, blocks
    limits = " ".join(reaction[0]["limitations"])
    assert "has NOT happened" in limits
    assert "no precedent" in limits.lower()


def test_a_mismatch_carries_the_falsifier_stated_in_advance():
    intel = sc.consume(dossier(expectation_mismatches=[{
        "subject": "Palantir", "expected_event": "shares outperform",
        "expected_direction": "UP", "observed_direction": "DOWN",
        "outcome": "CONTRADICTED",
        "rationale": "observed the opposite direction over the window",
        "evaluated_at": "2026-08-05", "preregistered_at": "2026-07-01",
        "falsifier": "shares underperform over the window",
        "evidence_ids": ["ev-4"],
    }]), expected_company="palantir", today="2026-08-05")
    blocks = ep.reasoning_pack(ep.build_context(strategic=intel))["blocks"]
    mismatch = [b for b in blocks if "expected" in " ".join(b["facts"])]
    assert mismatch, blocks
    assert "Falsifier stated in advance" in " ".join(mismatch[0]["limitations"])


def test_strategic_blocks_are_tagged_as_strategic():
    intel = sc.consume(dossier(), expected_company="palantir",
                       today="2026-08-05")
    context = ep.build_context(strategic=intel)
    pack = ep.reasoning_pack(context)
    assert ep.STRATEGIC in pack["sections"]
