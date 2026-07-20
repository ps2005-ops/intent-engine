"""T009 bars as tests — synthetic-world reasoning eval (founder-approved
2026-07-19, HIGH priority). All offline, zero model calls: (a) generator
determinism, (b) planted-condition enum validity, (c) leakage walls incl.
negative cases, (d) offline-eval invariants + expressiveness cross-check,
(e) fictional-entity wall incl. negative case, (f) report language walls,
(g) live-harness guards (frozen-prompt hash, call cap) with a fake client
— no call escapes the guards."""

import sys
from pathlib import Path
from typing import get_args
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import run_synthetic_world_eval as runner  # noqa: E402

from intent_engine.core import synthetic_worlds as sw  # noqa: E402
from intent_engine.core.mechanism_library import TriggerCondition, load_mechanisms  # noqa: E402


def _worlds():
    return sw.generate_worlds()


# --- (a) determinism --------------------------------------------------------

def test_generation_is_deterministic_and_seed_sensitive():
    assert sw.generate_worlds() == sw.generate_worlds()
    assert sw.generate_worlds(seed=1) != sw.generate_worlds(seed=2)


def test_world_counts_and_types():
    worlds = _worlds()
    by_type = {t: [w for w in worlds if w.world_type == t]
               for t in ("single", "mixed", "control")}
    assert len(by_type["single"]) == 23 * 3
    assert len(by_type["mixed"]) == 12
    assert len(by_type["control"]) == 8
    assert len(worlds) == 89


# --- (b) planted conditions are frozen-enum members -------------------------

def test_planted_conditions_are_valid_enum_members():
    declared = set(get_args(TriggerCondition))
    for w in _worlds():
        assert set(w.planted_conditions) <= declared, w.world_id


def test_single_worlds_plant_exactly_the_mechanism_trigger_set():
    sets = {m.mechanism_id: tuple(sorted(m.trigger_conditions)) for m in load_mechanisms()}
    for w in _worlds():
        if w.world_type == "single":
            (gt,) = w.ground_truth_mechanisms
            assert w.planted_conditions == sets[gt], w.world_id


# --- (c) leakage walls ------------------------------------------------------

def test_leakage_walls_pass_on_the_default_set():
    sw.assert_leakage_walls(_worlds())  # raises on violation


def test_leakage_wall_trips_on_enum_token():
    w = _worlds()[0]
    bad = w._replace(narrative=w.narrative + " drawdown_gt_20pct")
    with pytest.raises(ValueError, match="enum token"):
        sw.assert_leakage_walls([bad])


def test_leakage_wall_trips_on_real_anchor():
    w = _worlds()[0]
    bad = w._replace(narrative=w.narrative + " The board studied what Lehman did.")
    with pytest.raises(ValueError, match="real-world anchor"):
        sw.assert_leakage_walls([bad])


def test_leakage_wall_trips_on_library_shingle():
    chain_sentence = load_mechanisms()[0].causal_chain[1]
    w = _worlds()[0]
    bad = w._replace(narrative=w.narrative + " " + chain_sentence)
    with pytest.raises(ValueError, match="shingle"):
        sw.assert_leakage_walls([bad])


# --- (e) fictional entities -------------------------------------------------

def test_fictional_entity_wall_passes_and_trips():
    worlds = _worlds()
    sw.assert_fictional_entities(worlds)
    bad = worlds[0]._replace(company="Volcker Systems")
    with pytest.raises(ValueError, match="collides with library text"):
        sw.assert_fictional_entities([bad])


# --- (d) offline eval invariants -------------------------------------------

def test_offline_eval_recovers_constructed_truth_everywhere():
    worlds = _worlds()
    results = sw.run_offline_eval(worlds)
    assert all(r.identified for r in results)
    controls = [r for r in results if r.world_type == "control"]
    assert all(r.tier_size == 0 for r in controls)  # constructed silence


def test_unique_top_singles_cross_check_expressiveness_map():
    """33/69 unique-top singles must equal 3 x (uniquely identifiable
    mechanisms) — two independent computations of the same fact."""
    results = sw.run_offline_eval(_worlds())
    unique_singles = sum(1 for r in results if r.world_type == "single" and r.unique_top)
    emap = sw.enum_expressiveness_map()
    unique_mechs = [k for k, v in emap.items() if len(v) == 1]
    assert unique_singles == 3 * len(unique_mechs)


def test_expressiveness_map_matches_known_collision_structure():
    emap = sw.enum_expressiveness_map()
    # the founder-ratified drawdown dual-match class, plus the two
    # single-condition-superset members, tie on {drawdown_gt_20pct}:
    assert emap["margin_collateral_spiral"] == (
        "debt_deflation_spiral", "exogenous_activity_halt", "leverage_cycle_bust",
        "margin_collateral_spiral", "mechanical_feedback_liquidation",
    )
    # the credit-side identical pair:
    assert emap["money_market_contagion"] == ("money_market_contagion", "sovereign_debt_doom_loop")
    # a uniquely identifiable mechanism stays unique:
    assert emap["policy_tightening_demand_collapse"] == ("policy_tightening_demand_collapse",)


# --- (f) report language walls ----------------------------------------------

def test_offline_report_carries_disclaimer_and_walls(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OFFLINE_MD", tmp_path / "eval.md")
    monkeypatch.setattr(runner, "OFFLINE_JSON", tmp_path / "eval.json")
    monkeypatch.setattr(runner, "REPORT_DIR", tmp_path)
    assert runner.run_offline(sw.DEFAULT_SEED) == 0
    report = (tmp_path / "eval.md").read_text()
    assert sw.DIAGNOSTIC_DISCLAIMER in report
    with pytest.raises(ValueError, match="language wall"):
        sw.assert_report_language_walls(report + "\nThis proves a great track record.")


# --- (g) live-harness guards (fake client; nothing escapes the walls) -------

def test_live_leg_parks_on_prompt_hash_mismatch(monkeypatch, tmp_path):
    from intent_engine.simulator import mechanism_section as ms
    client = MagicMock()
    monkeypatch.setattr(ms, "EXTRACTION_SYSTEM_PROMPT", "tampered prompt")
    monkeypatch.setattr(runner, "LIVE_MD", tmp_path / "live.md")
    monkeypatch.setattr(runner, "LIVE_JSON", tmp_path / "live.json")
    assert runner.run_live(sw.DEFAULT_SEED, 100, client=client) == 1
    assert client.call_tool.call_count == 0  # parked BEFORE any call


def test_live_leg_parks_on_call_cap(monkeypatch, tmp_path):
    client = MagicMock()
    monkeypatch.setattr(runner, "LIVE_MD", tmp_path / "live.md")
    monkeypatch.setattr(runner, "LIVE_JSON", tmp_path / "live.json")
    assert runner.run_live(sw.DEFAULT_SEED, 10, client=client) == 1
    assert client.call_tool.call_count == 0


def test_live_leg_end_to_end_with_perfect_fake_extraction(monkeypatch, tmp_path):
    """Fake client echoes each world's planted conditions in world order —
    exercises the full live path (extraction -> scorer -> report) offline
    and confirms a perfect extractor recovers every constructed truth."""
    worlds = sw.generate_worlds()
    client = MagicMock()
    client.call_tool.side_effect = [
        {"trigger_conditions": list(w.planted_conditions)} for w in worlds
    ]
    monkeypatch.setattr(runner, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(runner, "LIVE_MD", tmp_path / "live.md")
    monkeypatch.setattr(runner, "LIVE_JSON", tmp_path / "live.json")
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runner, "RUN_HISTORY", tmp_path / "history.jsonl")
    assert runner.run_live(sw.DEFAULT_SEED, 100, client=client) == 0
    assert client.call_tool.call_count == len(worlds)
    import json
    # append-only run recording: one archived run + one history row
    assert len(list((tmp_path / "runs").glob("live_*.json"))) == 1
    history = (tmp_path / "history.jsonl").read_text().splitlines()
    assert len(history) == 1 and json.loads(history[0])["controls_clean"] == 8
    # conditional control wording: all-clean case has no stale "the rest"
    live_md = (tmp_path / "live.md").read_text()
    assert "no hallucinated conditions on any control this run" in live_md
    assert "on the rest" not in live_md
    rows = json.loads((tmp_path / "live.json").read_text())["rows"]
    assert all(r["identified"] for r in rows)
    controls = [r for r in rows if r["world_type"] == "control"]
    assert all(r["predicted"] == [] for r in controls)
    report = (tmp_path / "live.md").read_text()
    assert sw.DIAGNOSTIC_DISCLAIMER in report


# --- v1.1: conditional opener (live-run finding, 2026-07-20) ----------------

def test_v11_opener_is_conditional_on_the_oligopoly_condition():
    """v1.0's unconditional 'principal competitor' opener baited
    few_dominant_competitors 67 times in the first live run. v1.1: only
    worlds that PLANT the condition keep the concentrated phrasing;
    everything else (controls included) describes a broad field."""
    for w in _worlds():
        if "few_dominant_competitors" in w.planted_conditions:
            assert "principal competitor" in w.narrative, w.world_id
        else:
            assert "principal competitor" not in w.narrative, w.world_id
            assert "broad field" in w.narrative, w.world_id
