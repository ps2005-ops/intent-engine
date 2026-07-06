import random
from pathlib import Path
from unittest.mock import MagicMock

from intent_engine.core.entity_memory import JsonlEntityMemoryWriter, read_records
from intent_engine.core.scrap_estimate import (
    GENERIC_YIELD_EXPECTATION_NOTE,
    RICHNESS_SYSTEM_PROMPT,
    MaterialComposite,
    ScrapEstimate,
    WeighInRecord,
    YieldAssessment,
    _BIN_NUMERIC_RANGES,
    _CATEGORY_MATERIAL_PROFILES,
    _MOTOR_SUBTYPE_PROFILES,
    _SCRAP_CHECK_MARKER,
    _WEIGHIN_MARKER,
    _aggregate_category_votes,
    _compute_calibrated_yields,
    _compute_deterministic_comparison,
    _enforce_richness_evidence_rule,
    _normalize_category_shares,
    _read_prior_scrap_estimates,
    _refine_unanimous_category,
    _resolve_category_range,
    _resolve_profile_type,
    _tertile_to_range,
    _vote_modal_or_fallback,
    aggregate_shipment_estimates,
    aggregate_shipment_yield_assessments,
    apply_richness_trim,
    compute_coherence_note,
    compute_condition_note,
    compute_deviation_from_richness,
    compute_material_composite,
    compute_scrap_score,
    compute_track_record_note,
    compute_yield_assessment,
    estimate_scrap_lot,
    record_actual_weighin,
    render_scrap_estimate_as_text,
    vote_copper_richness,
    vote_lot_type,
    vote_motor_subtype,
)

# Real photos from the actual target user (not synthetic renders) -- these
# tests are mocked-client, so file CONTENT is never actually read by the code
# under test, but pointing at real files keeps the suite honestly
# representative of real usage rather than a placeholder path.
REAL_FIXTURES = Path(__file__).parent / "fixtures" / "scrap_metal"
REAL_LOT_1 = REAL_FIXTURES / "scrap_lot_1.jpeg"

# Kept specifically for the "no prior lots" test below: that logic is pure
# entity-memory bookkeeping and doesn't depend on real texture at all.
SYNTHETIC_FIXTURES = Path(__file__).parent / "fixtures" / "scrap_estimate"
SYNTHETIC_LOT = SYNTHETIC_FIXTURES / "clean_metal.png"


def _richness_dict(vote):
    """Normalizes a richness_votes entry into a full schema-valid dict --
    accepts either a plain verdict string or an already-complete dict (for
    tests needing custom evidence/reasoning)."""
    if isinstance(vote, dict):
        return vote
    evidence = ["mock visible evidence"] if vote in ("unusually_copper_rich", "unusually_copper_poor") else []
    return {"visible_copper_richness": vote, "visible_evidence": evidence, "reasoning": "mock reasoning"}


def _fake_client(main_result, lot_type_votes=None, subtype_votes=None, richness_votes=None, tertile_result="middle"):
    """Smart mock dispatching on tool_name -- estimate_scrap_lot() now makes
    up to FOUR kinds of calls, each a real production call this mock must
    answer: the main isolated judgment call (no longer includes lot_type);
    5 isolated lot_type votes (for any real scrap lot); 5 isolated motor-
    subtype votes (only when lot_type resolves to
    sealed_motors_alternators_starters); one isolated within-range
    refinement call (only when the subtype vote comes back genuinely
    unanimous on a real, non-"mixed" subtype); and 5 isolated richness
    votes (for any lot with a real resolved lot_type).

    Defaults are chosen so existing coarse-range assertions keep working
    unchanged unless a test explicitly asks for narrowing:
    - lot_type_votes: 5x "sealed_motors_alternators_starters" (unanimous).
    - subtype_votes: 5x "mixed_sealed_motors" (unanimous, but harmless --
      "mixed" never triggers refinement).
    - richness_votes: 4x "typical_mixed_scrap" + 1x "unusually_copper_poor"
      -- a clear MODAL winner ("typical_mixed_scrap", the honest default)
      but deliberately NOT unanimous, so the richness-conditioned trim does
      not fire by default. Tests that want the trim to fire pass an
      explicit 5-identical list."""
    if lot_type_votes is None:
        lot_type_votes = ["sealed_motors_alternators_starters"] * 5
    if subtype_votes is None:
        subtype_votes = ["mixed_sealed_motors"] * 5
    if richness_votes is None:
        richness_votes = ["typical_mixed_scrap"] * 4 + ["unusually_copper_poor"]
    richness_votes = [_richness_dict(v) for v in richness_votes]

    state = {"lot_type_idx": 0, "subtype_idx": 0, "richness_idx": 0}

    def side_effect(*args, **kwargs):
        tool_name = kwargs.get("tool_name")
        if tool_name == "record_scrap_estimate":
            return main_result
        if tool_name == "record_lot_type":
            idx = state["lot_type_idx"] % len(lot_type_votes)
            state["lot_type_idx"] += 1
            return {"lot_type": lot_type_votes[idx], "reasoning": "mock reasoning"}
        if tool_name == "record_motor_subtype":
            idx = state["subtype_idx"] % len(subtype_votes)
            state["subtype_idx"] += 1
            return {"subtype": subtype_votes[idx], "reasoning": "mock reasoning"}
        if tool_name == "record_richness_assessment":
            idx = state["richness_idx"] % len(richness_votes)
            state["richness_idx"] += 1
            return richness_votes[idx]
        if tool_name == "record_subtype_tertile_refinement":
            return {"tertile": tertile_result}
        raise AssertionError(f"Unexpected tool_name: {tool_name}")

    client = MagicMock()
    client.call_tool.side_effect = side_effect
    return client


def _base_result(**overrides):
    """A fully-populated, schema-valid mocked tool result for the ISOLATED
    judgment call. lot_type is no longer part of this call -- it's now a
    separate, 5-voted classification (see vote_lot_type / _fake_client's
    lot_type_votes)."""
    result = {
        "is_scrap_metal_lot": True,
        "category_note": "",
        "grade_impression": "looks_average",
        "oxidation_level": "moderate",
        "visible_contamination": [],
        "copper_exposure": "enclosed_housing",
        "confidence": "medium",
        "reasoning": "moderate rust visible across the lot",
    }
    result.update(overrides)
    return result


def _write_prior_estimate(path, entity_id, **overrides):
    """Writes a prior ScrapEstimate directly to entity memory in the real,
    current JSON-behind-the-marker format."""
    from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter

    defaults = dict(
        is_scrap_metal_lot=True, category_note=None, grade_impression="looks_weak",
        oxidation_level="heavy", visible_contamination=[], copper_exposure="enclosed_housing",
        comparison_note="No prior lots on record yet for this entity.",
        scrap_score=1, confidence="high", reasoning="heavily rusted, thin material",
    )
    defaults.update(overrides)
    estimate = ScrapEstimate(**defaults)
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(EntityMemoryRecord(
        entity_id=entity_id, source="voice",
        decision_text=f"{_SCRAP_CHECK_MARKER}{estimate.model_dump_json()}",
        goals=[], constraints=[],
    ))
    return estimate


def test_estimate_scrap_lot_returns_typed_result(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(
        grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=["plastic housing"],
    ))

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert isinstance(estimate, ScrapEstimate)
    assert estimate.grade_impression == "looks_average"
    assert estimate.oxidation_level == "moderate"
    assert estimate.visible_contamination == ["plastic housing"]


def test_estimate_scrap_lot_never_produces_per_lot_composition_field():
    """Structural guarantee: ScrapEstimate has no top-level field that could
    ever carry a PER-LOT composition percentage. yield_assessment is
    excluded by name -- it's a table-lookup base rate + evidence-gated
    deviation flag, never a per-lot measurement claim."""
    fields = set(ScrapEstimate.model_fields.keys()) - {"yield_assessment"}
    for forbidden in ("composition", "purity", "alloy", "percentage"):
        assert not any(forbidden in f.lower() for f in fields)


def test_estimate_scrap_lot_isolated_call_never_receives_prior_lot_text(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", reasoning="a very distinctive prior reasoning string")

    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    judgment_call = next(c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_scrap_estimate")
    assert "distinctive prior reasoning" not in judgment_call.kwargs["user_message"]
    assert "prior" not in judgment_call.kwargs["user_message"].lower()


def test_estimate_scrap_lot_richness_call_also_never_receives_prior_lot_text(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", reasoning="a very distinctive prior reasoning string")

    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    richness_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_richness_assessment"]
    assert len(richness_calls) == 5  # now a 5-vote classification, not a single call
    for call in richness_calls:
        assert "prior" not in call.kwargs["user_message"].lower()
        assert "distinctive prior reasoning" not in call.kwargs["system"]


def test_estimate_scrap_lot_richness_call_never_receives_lot_type_or_baseline(tmp_path):
    """The structural information-hiding guarantee this redesign depends
    on: the richness call must never see the classified lot_type, its
    numeric baseline, or any category name -- that's the whole fix for the
    label-anchoring failure found in the first (rejected) design."""
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(), lot_type_votes=["exposed_copper_windings_stators"] * 5)
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    richness_call = next(c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_richness_assessment")
    system_text = richness_call.kwargs["system"].lower()
    for leaked in ("exposed_copper_windings_stators", "sealed_motors", "20-40", "7-18", "9-10", "15-18"):
        assert leaked not in system_text


def test_richness_system_prompt_never_mentions_lot_type_or_numeric_baseline():
    lowered = RICHNESS_SYSTEM_PROMPT.lower()
    for forbidden in ("sealed_motors", "exposed_copper_windings", "large_industrial_machinery",
                      "aluminum_dominant_items", "loose_mixed_steel", "7-18", "20-40", "9-10", "15-18"):
        assert forbidden not in lowered


def test_estimate_scrap_lot_lot_type_call_never_receives_prior_lot_text(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", reasoning="a very distinctive prior reasoning string")

    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    lot_type_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_lot_type"]
    assert len(lot_type_calls) == 5  # 5-vote classification
    for call in lot_type_calls:
        assert "prior" not in call.kwargs["user_message"].lower()
        assert "distinctive prior reasoning" not in call.kwargs["system"]


def test_estimate_scrap_lot_sets_deterministic_no_prior_lots_message(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))

    estimate = estimate_scrap_lot(SYNTHETIC_LOT, "New Supplier Co", client=client, path=entity_path)

    assert estimate.comparison_note == "No prior lots on record yet for this entity."


def test_estimate_scrap_lot_uses_deterministic_comparison_when_prior_lots_exist(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", grade_impression="looks_weak", oxidation_level="heavy")

    client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))
    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert "less oxidized than the prior lot" in estimate.comparison_note
    assert "grade impression better than the prior lot" in estimate.comparison_note


def test_estimate_scrap_lot_writes_marked_entity_memory_record(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result())

    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    records = read_records("Acme Scrap Yard", path=entity_path)
    assert len(records) == 1
    assert records[0].source == "voice"
    assert records[0].decision_text.startswith(_SCRAP_CHECK_MARKER)


def test_estimate_scrap_lot_second_call_sees_first_as_prior_lot(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"

    first_client = _fake_client(_base_result(grade_impression="looks_weak", oxidation_level="heavy"))
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=first_client, path=entity_path)

    second_client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))
    second_estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=second_client, path=entity_path)

    judgment_call = next(c for c in second_client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_scrap_estimate")
    assert "prior" not in judgment_call.kwargs["user_message"].lower()
    assert "less oxidized than the prior lot" in second_estimate.comparison_note

    records = read_records("Acme Scrap Yard", path=entity_path)
    assert len(records) == 2


def test_estimate_scrap_lot_not_scrap_metal_sets_not_applicable_grade_and_no_yield_assessment(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(
        is_scrap_metal_lot=False,
        category_note="appears to be intact, new equipment on pallets, not deteriorated scrap",
        grade_impression="not_applicable", oxidation_level="not_applicable", copper_exposure="not_applicable",
        confidence="high", reasoning="units appear new/unused, boxed and palletized",
    ))

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert estimate.is_scrap_metal_lot is False
    assert estimate.grade_impression == "not_applicable"
    assert estimate.scrap_score is None
    assert estimate.yield_assessment is None  # no yield assessment for a non-scrap lot
    assert "not deteriorated scrap" in estimate.category_note
    # lot_type/richness must never even be called for a non-scrap lot.
    lot_type_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_lot_type"]
    assert lot_type_calls == []
    richness_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_richness_assessment"]
    assert richness_calls == []


def test_estimate_scrap_lot_unclear_lot_type_sets_no_yield_assessment(tmp_path):
    """A genuinely mixed/unclassifiable lot IS scrap metal, but has no
    single type to look a base rate up for -- yield_assessment stays None
    and the richness call is skipped entirely (nothing to join it with)."""
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(), lot_type_votes=["unclear"] * 5)

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert estimate.is_scrap_metal_lot is True
    assert estimate.yield_assessment is None
    richness_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_richness_assessment"]
    assert richness_calls == []


def test_estimate_scrap_lot_comparison_skipped_when_categories_differ(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(
        entity_path, "Acme Scrap Yard",
        is_scrap_metal_lot=False, category_note="intact equipment", grade_impression="not_applicable",
        oxidation_level="not_applicable", copper_exposure="not_applicable", scrap_score=None,
    )

    client = _fake_client(_base_result(is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate"))
    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert "different category" in estimate.comparison_note


def test_render_scrap_estimate_as_text_handles_empty_contamination_and_no_comparison():
    estimate = ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=[], copper_exposure="enclosed_housing", comparison_note=None,
        scrap_score=5, confidence="medium", reasoning="moderate rust",
    )

    text = render_scrap_estimate_as_text(estimate)

    assert "none visible" in text
    assert "no comparison available" in text
    assert "5/10" in text


def test_render_scrap_estimate_as_text_handles_non_scrap_case():
    estimate = ScrapEstimate(
        is_scrap_metal_lot=False, category_note="looks like new equipment, not scrap",
        grade_impression="not_applicable", oxidation_level="not_applicable",
        visible_contamination=[], copper_exposure="not_applicable",
        comparison_note=None, scrap_score=None, confidence="high", reasoning="units appear new",
    )

    text = render_scrap_estimate_as_text(estimate)

    assert "Not identified as scrap metal" in text
    assert "looks like new equipment" in text


# --- _read_prior_scrap_estimates (parses real stored structured fields) ----


def test_read_prior_scrap_estimates_parses_real_stored_json(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", grade_impression="looks_weak")

    prior = _read_prior_scrap_estimates("Acme Scrap Yard", path=entity_path)

    assert len(prior) == 1
    assert isinstance(prior[0], ScrapEstimate)
    assert prior[0].grade_impression == "looks_weak"


def test_read_prior_scrap_estimates_skips_unparseable_legacy_records(tmp_path):
    from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter

    entity_path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=entity_path)
    writer.write(EntityMemoryRecord(
        entity_id="Acme Scrap Yard", source="voice",
        decision_text=f"{_SCRAP_CHECK_MARKER}Grade impression: looks_weak. Oxidation: heavy. Reasoning: old format.",
        goals=[], constraints=[],
    ))
    _write_prior_estimate(entity_path, "Acme Scrap Yard", grade_impression="looks_strong")

    prior = _read_prior_scrap_estimates("Acme Scrap Yard", path=entity_path)

    assert len(prior) == 1
    assert prior[0].grade_impression == "looks_strong"


# --- _compute_deterministic_comparison (fully deterministic, no LLM) ------


def test_compute_deterministic_comparison_detects_more_oxidized():
    prior = [ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=[], copper_exposure="enclosed_housing", confidence="medium", reasoning="x",
    )]
    note = _compute_deterministic_comparison(True, "looks_average", "heavy", "enclosed_housing", prior)
    assert "more oxidized than the prior lot (moderate -> heavy)" in note


def test_compute_deterministic_comparison_detects_less_oxidized():
    prior = [ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="heavy",
        visible_contamination=[], copper_exposure="enclosed_housing", confidence="medium", reasoning="x",
    )]
    note = _compute_deterministic_comparison(True, "looks_average", "low", "enclosed_housing", prior)
    assert "less oxidized than the prior lot (heavy -> low)" in note


def test_compute_deterministic_comparison_skips_different_categories():
    prior = [ScrapEstimate(
        is_scrap_metal_lot=False, category_note="intact equipment", grade_impression="not_applicable",
        oxidation_level="not_applicable", visible_contamination=[], copper_exposure="not_applicable",
        confidence="high", reasoning="x",
    )]
    note = _compute_deterministic_comparison(True, "looks_average", "moderate", "enclosed_housing", prior)
    assert "different category" in note


def test_compute_deterministic_comparison_handles_copper_exposure_change():
    prior = [ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=[], copper_exposure="enclosed_housing", confidence="medium", reasoning="x",
    )]
    note = _compute_deterministic_comparison(True, "looks_average", "moderate", "exposed_stripped", prior)
    assert "copper exposure differs from the prior lot (enclosed_housing -> exposed_stripped)" in note


# --- compute_scrap_score (deterministic, never LLM-asserted) ---------------


def test_compute_scrap_score_returns_none_when_not_scrap_metal():
    assert compute_scrap_score("not_applicable", "not_applicable", 0, is_scrap_metal_lot=False) is None


def test_compute_scrap_score_strong_low_oxidation_no_contamination_scores_high():
    score = compute_scrap_score("looks_strong", "low", 0, is_scrap_metal_lot=True)
    assert score == 9


def test_compute_scrap_score_weak_heavy_oxidation_with_contamination_scores_low():
    score = compute_scrap_score("looks_weak", "heavy", 3, is_scrap_metal_lot=True)
    assert score == 1  # clamped to the floor, not negative


def test_compute_scrap_score_always_within_1_to_10():
    for grade in ("looks_strong", "looks_average", "looks_weak", "unclear"):
        for oxidation in ("low", "moderate", "heavy", "unclear"):
            for contamination_count in (0, 1, 5, 10):
                score = compute_scrap_score(grade, oxidation, contamination_count, is_scrap_metal_lot=True)
                assert 1 <= score <= 10


# --- compute_condition_note (deterministic, industry-recognizable) --------


def test_compute_condition_note_returns_none_when_not_scrap_metal():
    assert compute_condition_note("not_applicable", "not_applicable", [], is_scrap_metal_lot=False) is None


def test_compute_condition_note_mentions_contamination_and_sorting():
    note = compute_condition_note("looks_weak", "heavy", ["grease/oil residue", "dirt/debris"], is_scrap_metal_lot=True)
    assert "heavy oxidation" in note
    assert "significantly degraded" in note
    assert "would need sorting before processing" in note
    assert "grease/oil residue" in note


def test_compute_condition_note_states_no_contamination_when_none_visible():
    note = compute_condition_note("looks_strong", "low", [], is_scrap_metal_lot=True)
    assert "no non-metal attachments visible" in note


def test_compute_condition_note_never_mentions_isri_or_hms():
    for grade in ("looks_strong", "looks_average", "looks_weak", "unclear"):
        for oxidation in ("low", "moderate", "heavy", "unclear"):
            note = compute_condition_note(grade, oxidation, ["plastic", "dirt"], is_scrap_metal_lot=True)
            assert "isri" not in note.lower()
            assert "hms" not in note.lower()


# --- render_scrap_estimate_as_text: yield note surfaced prominently --------


def test_render_scrap_estimate_as_text_surfaces_yield_note_prominently():
    yield_assessment = YieldAssessment(
        lot_type="sealed_motors_alternators_starters", copper_pct_range=[7.0, 18.0],
        aluminum_pct_range=[0.0, 3.0], ferrous_pct_range=[79.0, 93.0],
        yield_source="cited industry range (no weigh-ins yet)",
        deviation="looks_typical", visible_evidence=[],
        note=(
            "Base rate for sealed motors alternators starters: 7-18% Cu (cited industry range "
            "(no weigh-ins yet)). No visible anomalies; expect a typical lot."
        ),
    )
    estimate = ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=[], copper_exposure="enclosed_housing",
        condition_note="moderate oxidation, average condition, no non-metal attachments visible.",
        yield_assessment=yield_assessment,
        comparison_note="No prior lots on record yet for this entity.",
        scrap_score=5, confidence="medium", reasoning="moderate rust",
    )

    text = render_scrap_estimate_as_text(estimate)
    lines = text.splitlines()

    yield_line_index = next(i for i, line in enumerate(lines) if "Base rate for" in line)
    reasoning_line_index = next(i for i, line in enumerate(lines) if line.startswith("Reasoning"))
    comparison_line_index = next(i for i, line in enumerate(lines) if line.startswith("Comparison"))

    assert "7-18% Cu" in lines[yield_line_index]
    assert yield_line_index < comparison_line_index
    assert yield_line_index < reasoning_line_index


# --- _resolve_category_range (bin-wobble -> honest width) -- ARCHIVED ------
# (still tested -- see module docstring's ARCHITECTURAL REPLACEMENT section)


def test_resolve_category_range_stable_bin_uses_its_own_range():
    assert _resolve_category_range(["some", "some", "some"]) == (5, 15)


def test_resolve_category_range_wobble_uses_union_of_observed_bins():
    result = _resolve_category_range(["minimal", "some", "minimal"])
    assert result == (0, 15)  # union of minimal (0-5) and some (5-15)


def test_resolve_category_range_majority_unclear_returns_none():
    assert _resolve_category_range(["unclear", "unclear", "some"]) is None


def test_resolve_category_range_minority_unclear_ignored():
    # 1 of 3 unclear -- not a majority, ignored; concrete bins used.
    assert _resolve_category_range(["some", "some", "unclear"]) == (5, 15)


# --- _aggregate_category_votes -- ARCHIVED ---------------------------------


def test_aggregate_category_votes_drops_categories_below_inclusion_threshold():
    votes = [
        {"sealed_motors_alternators_starters": "majority", "aluminum_dominant_items": "minimal"},
        {"sealed_motors_alternators_starters": "majority"},
        {"sealed_motors_alternators_starters": "majority"},
        {"sealed_motors_alternators_starters": "majority"},
        {"sealed_motors_alternators_starters": "majority"},
    ]
    modal_bins, share_ranges, excluded, unanimous = _aggregate_category_votes(votes)
    # aluminum_dominant_items appeared in only 1 of 5 votes -- below the
    # 3-of-5 inclusion threshold, dropped entirely (not in any output).
    assert "aluminum_dominant_items" not in modal_bins
    assert "aluminum_dominant_items" not in share_ranges
    assert "aluminum_dominant_items" not in excluded
    assert modal_bins["sealed_motors_alternators_starters"] == "majority"
    # unanimous across all 5 identical votes.
    assert unanimous["sealed_motors_alternators_starters"] == "majority"


def test_aggregate_category_votes_includes_category_meeting_threshold():
    votes = [
        {"sealed_motors_alternators_starters": "majority", "exposed_copper_windings_stators": "some"},
        {"sealed_motors_alternators_starters": "majority", "exposed_copper_windings_stators": "some"},
        {"sealed_motors_alternators_starters": "majority", "exposed_copper_windings_stators": "minimal"},
        {"sealed_motors_alternators_starters": "majority"},
        {"sealed_motors_alternators_starters": "majority"},
    ]
    modal_bins, share_ranges, excluded, unanimous = _aggregate_category_votes(votes)
    assert "exposed_copper_windings_stators" in share_ranges
    # wobbled between "some" and "minimal" -- honest union width.
    assert share_ranges["exposed_copper_windings_stators"] == (0, 15)
    # sealed_motors_alternators_starters agreed in all 5 votes -- unanimous.
    assert unanimous["sealed_motors_alternators_starters"] == "majority"
    # exposed_copper_windings_stators wobbled -- not unanimous.
    assert "exposed_copper_windings_stators" not in unanimous


def test_aggregate_category_votes_not_unanimous_when_category_missing_from_some_votes():
    votes = [
        {"sealed_motors_alternators_starters": "majority"},
        {"sealed_motors_alternators_starters": "majority"},
        {"sealed_motors_alternators_starters": "majority"},
        {},
        {},
    ]
    modal_bins, share_ranges, excluded, unanimous = _aggregate_category_votes(votes)
    # present in only 3 of 5 votes -- meets inclusion threshold, but is NOT
    # unanimous (2 of 5 votes didn't even mention it).
    assert "sealed_motors_alternators_starters" in share_ranges
    assert "sealed_motors_alternators_starters" not in unanimous


# --- _normalize_category_shares -- ARCHIVED ---------------------------------


def test_normalize_category_shares_empty_input_returns_empty():
    assert _normalize_category_shares({}) == {}


def test_normalize_category_shares_leaves_already_consistent_ranges_unscaled():
    # sum(lows)=60 <= 100 <= sum(highs)=110 already -- no correction needed.
    shares = {"a": (40, 60), "b": (20, 50)}
    normalized = _normalize_category_shares(shares)
    assert normalized == {"a": (40, 60), "b": (20, 50)}


def test_normalize_category_shares_shrinks_lows_when_they_jointly_overclaim():
    # sum(lows) = 80 + 60 = 140 > 100 -- must shrink both lows by one scalar.
    shares = {"a": (80, 100), "b": (60, 100)}
    normalized = _normalize_category_shares(shares)
    assert sum(lo for lo, _ in normalized.values()) <= 100.001
    # highs are untouched (already >= 100 jointly, no correction needed there).
    assert normalized["a"][1] == 100
    assert normalized["b"][1] == 100
    # ordering preserved.
    assert normalized["a"][0] <= normalized["a"][1]
    assert normalized["b"][0] <= normalized["b"][1]


def test_normalize_category_shares_grows_highs_when_they_jointly_underclaim():
    # sum(highs) = 15 + 20 = 35 < 100 -- must grow both highs by one scalar.
    shares = {"a": (5, 15), "b": (10, 20)}
    normalized = _normalize_category_shares(shares)
    assert sum(hi for _, hi in normalized.values()) >= 99.999
    assert normalized["a"][0] == 5
    assert normalized["b"][0] == 10
    assert normalized["a"][0] <= normalized["a"][1]
    assert normalized["b"][0] <= normalized["b"][1]


def test_normalize_category_shares_never_produces_out_of_bounds_values():
    # a single dominant category with a wide raw range near the top of the
    # scale is exactly the case that produced the >100% defect in the old
    # midpoint-forcing normalization (e.g. share (80, 100), old factor
    # 100/90=1.111 -> old broken high of 111.1).
    shares = {"a": (80, 100)}
    normalized = _normalize_category_shares(shares)
    assert 0 <= normalized["a"][0] <= 100
    assert 0 <= normalized["a"][1] <= 100
    assert normalized["a"][0] <= normalized["a"][1]


def test_normalize_category_shares_property_fuzz_never_leaves_0_100_or_inverts_ordering():
    """Property test required when this normalization was fixed: no random
    combination of category share ranges (mimicking real bin-derived and
    union-derived ranges) may produce a normalized bound outside [0, 100],
    and every category's low must remain <= its high. 2000 random trials,
    stdlib `random` only (no new dependency)."""
    rng = random.Random(20260702)
    bin_ranges = list(_BIN_NUMERIC_RANGES.values())

    for _ in range(2000):
        num_categories = rng.randint(1, 7)
        shares = {}
        for i in range(num_categories):
            # mimic real inputs: either a single bin's range, or a union of
            # 2 random bins' ranges (the two shapes _resolve_category_range
            # actually produces).
            if rng.random() < 0.5:
                lo, hi = rng.choice(bin_ranges)
            else:
                r1, r2 = rng.choice(bin_ranges), rng.choice(bin_ranges)
                lo, hi = min(r1[0], r2[0]), max(r1[1], r2[1])
            shares[f"cat_{i}"] = (lo, hi)

        normalized = _normalize_category_shares(shares)

        for category, (lo, hi) in normalized.items():
            assert -0.001 <= lo <= 100.001, (shares, normalized)
            assert -0.001 <= hi <= 100.001, (shares, normalized)
            assert lo <= hi + 0.001, (shares, normalized)


# --- compute_material_composite -- ARCHIVED (cited vs. assumption) --------


def test_compute_material_composite_returns_none_when_no_shares():
    assert compute_material_composite({}, {}, []) is None


def test_compute_material_composite_sealed_motors_only():
    modal_bins = {"sealed_motors_alternators_starters": "nearly_all"}
    share_ranges = {"sealed_motors_alternators_starters": (80, 100)}
    composite = compute_material_composite(modal_bins, share_ranges, [])

    assert composite is not None
    # ~80-100% share x 7-18% copper assumption -> roughly 5.6-18%
    assert composite.copper_pct_range[0] < composite.copper_pct_range[1]
    assert composite.hms_ferrous_pct_range[0] > composite.copper_pct_range[0]
    assert composite.hedge  # mandatory hedge always present


def test_compute_material_composite_excludes_non_metal_and_unidentified():
    modal_bins = {"sealed_motors_alternators_starters": "majority", "non_metal_contamination": "some"}
    share_ranges = {"sealed_motors_alternators_starters": (60, 80), "non_metal_contamination": (5, 15)}
    composite = compute_material_composite(modal_bins, share_ranges, [])

    assert composite.non_metal_excluded_pct_range[0] > 0
    # non_metal_contamination must not leak into copper/aluminum/ferrous.
    assert composite is not None


def test_compute_material_composite_records_excluded_unclear_categories():
    modal_bins = {"sealed_motors_alternators_starters": "majority"}
    share_ranges = {"sealed_motors_alternators_starters": (60, 80)}
    composite = compute_material_composite(modal_bins, share_ranges, ["large_industrial_machinery"])

    assert "large_industrial_machinery" in composite.excluded_categories


def test_compute_material_composite_never_exceeds_100_even_for_a_single_dominant_wide_share():
    """The exact input shape that produced the real >100% defect (up to
    143.2%) in the old midpoint-forcing normalization: a single dominant
    category with a wide raw share near the top of the scale."""
    modal_bins = {"loose_mixed_steel": "nearly_all"}
    share_ranges = {"loose_mixed_steel": (80, 100)}
    composite = compute_material_composite(modal_bins, share_ranges, [])

    for r in (composite.copper_pct_range, composite.aluminum_pct_range,
              composite.hms_ferrous_pct_range, composite.non_metal_excluded_pct_range):
        assert 0 <= r[0] <= 100
        assert 0 <= r[1] <= 100
        assert r[0] <= r[1]


def test_compute_material_composite_property_fuzz_all_four_ranges_bounded():
    """Property test: across many random category-share combinations (the
    same shapes real _resolve_category_range output can take), every one of
    the four derived ranges (copper/aluminum/ferrous/excluded) must land
    within [0, 100], as an arithmetic consequence of the weighted-average
    formula -- never a clamp."""
    rng = random.Random(20260702)
    bin_ranges = list(_BIN_NUMERIC_RANGES.values())
    all_categories = list(_CATEGORY_MATERIAL_PROFILES.keys())

    for _ in range(1000):
        chosen = rng.sample(all_categories, rng.randint(1, len(all_categories)))
        modal_bins, share_ranges = {}, {}
        for c in chosen:
            lo, hi = rng.choice(bin_ranges)
            share_ranges[c] = (lo, hi)
            modal_bins[c] = "some"
        composite = compute_material_composite(modal_bins, share_ranges, [])
        for r in (composite.copper_pct_range, composite.aluminum_pct_range,
                  composite.hms_ferrous_pct_range, composite.non_metal_excluded_pct_range):
            assert -0.001 <= r[0] <= 100.001, (share_ranges, r)
            assert -0.001 <= r[1] <= 100.001, (share_ranges, r)
            assert r[0] <= r[1] + 0.001, (share_ranges, r)


def test_compute_material_composite_labels_generic_yield_sources():
    modal_bins = {"sealed_motors_alternators_starters": "majority"}
    share_ranges = {"sealed_motors_alternators_starters": (60, 80)}
    composite = compute_material_composite(modal_bins, share_ranges, [])

    assert composite.category_yield_sources["sealed_motors_alternators_starters"] == "cited industry range (no weigh-ins yet)"
    assert composite.used_any_generic_yield is True


def test_compute_material_composite_labels_assumption_yield_sources():
    modal_bins = {"exposed_copper_windings_stators": "majority"}
    share_ranges = {"exposed_copper_windings_stators": (60, 80)}
    composite = compute_material_composite(modal_bins, share_ranges, [])

    assert composite.category_yield_sources["exposed_copper_windings_stators"] == "generic assumption (no weigh-ins yet)"


def test_compute_material_composite_uses_calibrated_yields_when_provided():
    modal_bins = {"sealed_motors_alternators_starters": "nearly_all"}
    share_ranges = {"sealed_motors_alternators_starters": (80, 100)}
    generic = compute_material_composite(modal_bins, share_ranges, [])

    calibrated_yields = {
        "sealed_motors_alternators_starters": {"_count": 4, "copper": (11.0, 13.0), "aluminum": (0.0, 1.0), "ferrous": (85.0, 88.0)},
    }
    calibrated = compute_material_composite(modal_bins, share_ranges, [], calibrated_yields)

    assert calibrated.category_yield_sources["sealed_motors_alternators_starters"] == "calibrated from 4 real weigh-ins for this supplier"
    assert calibrated.used_any_generic_yield is False
    # calibrated range must be narrower than the generic 7-18% range scaled by the same share.
    generic_width = generic.copper_pct_range[1] - generic.copper_pct_range[0]
    calibrated_width = calibrated.copper_pct_range[1] - calibrated.copper_pct_range[0]
    assert calibrated_width < generic_width


def test_compute_material_composite_copper_higher_for_exposed_windings_than_sealed():
    """Sanity-relevant unit test: given the SAME share, exposed copper
    windings must produce a higher copper range than sealed motors."""
    sealed = compute_material_composite(
        {"sealed_motors_alternators_starters": "nearly_all"},
        {"sealed_motors_alternators_starters": (80, 100)}, [],
    )
    exposed = compute_material_composite(
        {"exposed_copper_windings_stators": "nearly_all"},
        {"exposed_copper_windings_stators": (80, 100)}, [],
    )
    assert exposed.copper_pct_range[0] > sealed.copper_pct_range[0]
    assert exposed.copper_pct_range[1] > sealed.copper_pct_range[1]


# --- _refine_unanimous_category -- ARCHIVED (within-bin refinement) -------


def test_refine_unanimous_category_maps_tertile_to_third_of_bin_range():
    client = MagicMock()
    client.call_tool.return_value = {"tertile": "upper"}

    result = _refine_unanimous_category(REAL_LOT_1, client, "sealed_motors_alternators_starters", "majority")

    # "majority" bin is (50, 80); upper third is (70, 80).
    assert result == (70.0, 80.0)
    assert client.call_tool.call_args.kwargs["tool_name"] == "record_tertile_refinement"


def test_refine_unanimous_category_lower_and_middle_tertiles():
    client = MagicMock()
    client.call_tool.return_value = {"tertile": "lower"}
    assert _refine_unanimous_category(REAL_LOT_1, client, "x", "majority") == (50.0, 60.0)

    client.call_tool.return_value = {"tertile": "middle"}
    assert _refine_unanimous_category(REAL_LOT_1, client, "x", "majority") == (60.0, 70.0)


# --- aggregate_shipment_estimates -- ARCHIVED (shipment-level combining) ---
# Takes MaterialComposite objects directly now (ScrapEstimate no longer
# carries a material_composite field in the live schema).


def _composite(copper_range, aluminum_range, ferrous_range, excluded_range=(0.0, 0.0)):
    return MaterialComposite(
        category_proportions={}, raw_category_shares_pct={}, normalized_category_shares_pct={},
        excluded_categories=[], copper_pct_range=list(copper_range), aluminum_pct_range=list(aluminum_range),
        hms_ferrous_pct_range=list(ferrous_range), non_metal_excluded_pct_range=list(excluded_range),
    )


def test_aggregate_shipment_estimates_returns_none_for_no_composites():
    assert aggregate_shipment_estimates([]) is None


def test_aggregate_shipment_estimates_narrows_width_vs_any_single_estimate():
    composites = [
        _composite((10, 20), (0, 2), (78, 90)),
        _composite((12, 22), (0, 2), (76, 88)),
        _composite((8, 18), (0, 2), (80, 92)),
        _composite((11, 21), (0, 2), (77, 89)),
    ]
    combined = aggregate_shipment_estimates(composites)

    combined_width = combined.copper_pct_range[1] - combined.copper_pct_range[0]
    single_widths = [c.copper_pct_range[1] - c.copper_pct_range[0] for c in composites]
    assert combined_width < min(single_widths)
    assert "4 photos" in combined.hedge
    assert "independent" in combined.hedge


def test_aggregate_shipment_estimates_stays_within_0_100():
    composites = [_composite((90, 100), (0, 1), (0, 5)) for _ in range(3)]
    combined = aggregate_shipment_estimates(composites)
    for r in (combined.copper_pct_range, combined.aluminum_pct_range, combined.hms_ferrous_pct_range):
        assert 0 <= r[0] <= 100
        assert 0 <= r[1] <= 100


# --- _enforce_richness_evidence_rule ---------------------------------------


def test_enforce_richness_evidence_rule_downgrades_unsupported_rich_claim():
    assert _enforce_richness_evidence_rule("unusually_copper_rich", []) == "typical_mixed_scrap"


def test_enforce_richness_evidence_rule_downgrades_unsupported_poor_claim():
    assert _enforce_richness_evidence_rule("unusually_copper_poor", []) == "typical_mixed_scrap"


def test_enforce_richness_evidence_rule_leaves_supported_claims_alone():
    assert _enforce_richness_evidence_rule("unusually_copper_rich", ["exposed copper visible"]) == "unusually_copper_rich"
    assert _enforce_richness_evidence_rule("unusually_copper_poor", ["plain steel only"]) == "unusually_copper_poor"


def test_enforce_richness_evidence_rule_leaves_typical_and_cannot_assess_alone():
    assert _enforce_richness_evidence_rule("typical_mixed_scrap", []) == "typical_mixed_scrap"
    assert _enforce_richness_evidence_rule("cannot_assess", []) == "cannot_assess"


# --- compute_deviation_from_richness (the code-level join, no API calls) --


def test_compute_deviation_from_richness_cannot_assess_always_cannot_assess():
    deviation, _ = compute_deviation_from_richness("sealed_motors_alternators_starters", "cannot_assess")
    assert deviation == "cannot_assess"
    deviation, _ = compute_deviation_from_richness("exposed_copper_windings_stators", "cannot_assess")
    assert deviation == "cannot_assess"


def test_compute_deviation_from_richness_typical_always_looks_typical():
    for lot_type in ("sealed_motors_alternators_starters", "exposed_copper_windings_stators",
                      "large_industrial_machinery", "aluminum_dominant_items", "loose_mixed_steel"):
        deviation, _ = compute_deviation_from_richness(lot_type, "typical_mixed_scrap")
        assert deviation == "looks_typical", lot_type


def test_compute_deviation_from_richness_rich_flags_better_for_low_baseline_types():
    """The photo-5-shaped case: a low-baseline type showing unusually rich
    visible copper is a genuine upside surprise."""
    for lot_type in ("sealed_motors_alternators_starters", "large_industrial_machinery",
                      "aluminum_dominant_items", "loose_mixed_steel"):
        deviation, reason = compute_deviation_from_richness(lot_type, "unusually_copper_rich")
        assert deviation == "looks_better_than_typical", lot_type
        assert reason


def test_compute_deviation_from_richness_rich_is_consistent_for_exposed_copper_type():
    """exposed_copper_windings_stators' OWN base rate is already copper-rich
    -- "rich" there is expected, not a deviation."""
    deviation, reason = compute_deviation_from_richness("exposed_copper_windings_stators", "unusually_copper_rich")
    assert deviation == "looks_typical"
    assert reason


def test_compute_deviation_from_richness_poor_flags_worse_only_for_exposed_copper_type():
    deviation, reason = compute_deviation_from_richness("exposed_copper_windings_stators", "unusually_copper_poor")
    assert deviation == "looks_worse_than_typical"
    assert reason

    for lot_type in ("sealed_motors_alternators_starters", "large_industrial_machinery",
                      "aluminum_dominant_items", "loose_mixed_steel"):
        deviation, reason = compute_deviation_from_richness(lot_type, "unusually_copper_poor")
        assert deviation == "looks_typical", lot_type
        assert reason


# --- compute_yield_assessment (live replacement for compute_material_composite) --


def test_compute_yield_assessment_none_for_unclear_or_not_applicable():
    assert compute_yield_assessment("unclear", "typical_mixed_scrap", []) is None
    assert compute_yield_assessment("not_applicable", "typical_mixed_scrap", []) is None


def test_compute_yield_assessment_typical_note_and_base_rate():
    ya = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [])
    assert ya.deviation == "looks_typical"
    assert ya.copper_pct_range == [7.0, 18.0]
    assert ya.aluminum_pct_range == [0.0, 3.0]
    assert ya.ferrous_pct_range == [79.0, 93.0]
    assert "No visible anomalies" in ya.note
    assert "Base rate for sealed motors alternators starters" in ya.note
    assert "cited industry range" in ya.yield_source
    assert "Okon Recycling" in ya.yield_source


def test_compute_yield_assessment_flags_better_with_evidence_in_note():
    ya = compute_yield_assessment(
        "sealed_motors_alternators_starters", "unusually_copper_rich",
        ["exposed copper windings visibly dominant"],
    )
    assert ya.deviation == "looks_better_than_typical"
    assert "Flagged:" in ya.note
    assert "exposed copper windings visibly dominant" in ya.note
    assert "above typical" in ya.note


def test_compute_yield_assessment_flags_worse_for_exposed_copper_type_gone_poor():
    ya = compute_yield_assessment(
        "exposed_copper_windings_stators", "unusually_copper_poor",
        ["entirely plain steel, no copper visible"],
    )
    assert ya.deviation == "looks_worse_than_typical"
    assert "Flagged:" in ya.note
    assert "below typical" in ya.note


def test_compute_yield_assessment_cannot_assess_note():
    ya = compute_yield_assessment("sealed_motors_alternators_starters", "cannot_assess", [])
    assert ya.deviation == "cannot_assess"
    assert "does not show enough" in ya.note


def test_compute_yield_assessment_downgrades_unsupported_rich_claim_before_computing():
    ya = compute_yield_assessment("sealed_motors_alternators_starters", "unusually_copper_rich", [])
    assert ya.deviation == "looks_typical"  # enforced downgrade -- no evidence given


def test_compute_yield_assessment_uses_calibrated_yields_when_provided():
    generic = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [])
    calibrated_yields = {
        "sealed_motors_alternators_starters": {"_count": 4, "copper": (11.0, 13.0), "aluminum": (0.0, 1.0), "ferrous": (85.0, 88.0)},
    }
    calibrated = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [], calibrated_yields)

    assert "calibrated from 4 real weigh-ins" in calibrated.yield_source
    generic_width = generic.copper_pct_range[1] - generic.copper_pct_range[0]
    calibrated_width = calibrated.copper_pct_range[1] - calibrated.copper_pct_range[0]
    assert calibrated_width < generic_width


def test_estimate_scrap_lot_surfaces_better_than_typical_deviation(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    richness_dict = {
        "visible_copper_richness": "unusually_copper_rich",
        "visible_evidence": ["exposed copper windings visibly dominant across the lot"],
        "reasoning": "much more exposed copper than typical",
    }
    # 4 of 5 agree (a clear plurality, not full unanimity) -- deviation
    # flag fires regardless of unanimity; the richness TRIM (a separate
    # mechanism) specifically requires full unanimity, tested elsewhere.
    client = _fake_client(_base_result(), richness_votes=[richness_dict] * 4 + ["typical_mixed_scrap"])

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert estimate.yield_assessment.deviation == "looks_better_than_typical"
    assert "Flagged:" in estimate.yield_assessment.note
    text = render_scrap_estimate_as_text(estimate)
    assert "Flagged:" in text


# --- Motor sub-type classification (width reduction #1) --------------------


def test_resolve_profile_type_uses_subtype_for_sealed_motors_when_confident():
    assert _resolve_profile_type("sealed_motors_alternators_starters", "automotive_alternators_starters") == "automotive_alternators_starters"
    assert _resolve_profile_type("sealed_motors_alternators_starters", "small_fractional_motors") == "small_fractional_motors"
    assert _resolve_profile_type("sealed_motors_alternators_starters", "dc_motors") == "dc_motors"


def test_resolve_profile_type_falls_back_to_coarse_when_subtype_is_mixed_or_missing():
    assert _resolve_profile_type("sealed_motors_alternators_starters", "mixed_sealed_motors") == "sealed_motors_alternators_starters"
    assert _resolve_profile_type("sealed_motors_alternators_starters", None) == "sealed_motors_alternators_starters"


def test_resolve_profile_type_ignores_subtype_for_non_sealed_motor_coarse_types():
    # a sub-type value should never apply to a coarse type it wasn't
    # classified for -- structurally impossible in practice (subtype is
    # only ever requested for sealed_motors_alternators_starters), but the
    # resolver itself must not silently misapply it either.
    assert _resolve_profile_type("large_industrial_machinery", "automotive_alternators_starters") == "large_industrial_machinery"


def test_motor_subtype_profiles_are_narrower_than_the_coarse_range():
    coarse_width = _CATEGORY_MATERIAL_PROFILES["sealed_motors_alternators_starters"]["copper"][1] - \
        _CATEGORY_MATERIAL_PROFILES["sealed_motors_alternators_starters"]["copper"][0]
    for subtype, profile in _MOTOR_SUBTYPE_PROFILES.items():
        width = profile["copper"][1] - profile["copper"][0]
        assert width < coarse_width, subtype


def test_compute_yield_assessment_uses_subtype_for_narrower_cited_range():
    coarse = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [])
    subtyped = compute_yield_assessment(
        "sealed_motors_alternators_starters", "typical_mixed_scrap", [], subtype="automotive_alternators_starters",
    )

    assert subtyped.lot_type == "automotive_alternators_starters"
    assert subtyped.copper_pct_range == [10.0, 14.0]
    assert "cited industry range" in subtyped.yield_source
    coarse_width = coarse.copper_pct_range[1] - coarse.copper_pct_range[0]
    subtyped_width = subtyped.copper_pct_range[1] - subtyped.copper_pct_range[0]
    assert subtyped_width < coarse_width


def test_compute_yield_assessment_falls_back_to_coarse_when_subtype_is_mixed():
    ya = compute_yield_assessment(
        "sealed_motors_alternators_starters", "typical_mixed_scrap", [], subtype="mixed_sealed_motors",
    )
    assert ya.lot_type == "sealed_motors_alternators_starters"
    assert ya.copper_pct_range == [7.0, 18.0]


def test_estimate_scrap_lot_calls_subtype_classification_only_for_sealed_motors(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(), lot_type_votes=["large_industrial_machinery"] * 5)

    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    subtype_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_motor_subtype"]
    assert subtype_calls == []


def test_estimate_scrap_lot_subtype_call_never_receives_prior_lot_text(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", reasoning="a very distinctive prior reasoning string")

    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    subtype_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_motor_subtype"]
    assert len(subtype_calls) == 5  # now a 5-vote classification, not a single call
    for call in subtype_calls:
        assert "prior" not in call.kwargs["user_message"].lower()
        assert "distinctive prior reasoning" not in call.kwargs["system"]


def test_estimate_scrap_lot_narrows_range_when_subtype_resolves_confidently(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(), subtype_votes=["automotive_alternators_starters"] * 5)

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    ya = estimate.yield_assessment
    assert ya.lot_type == "automotive_alternators_starters"
    # unanimous subtype -> within-range refinement also fires (reliability-
    # gated, shipped -- see module docstring) -- range narrows to a third
    # of the cited 10-14% range, not the full 4pp.
    assert 10.0 <= ya.copper_pct_range[0] <= ya.copper_pct_range[1] <= 14.0
    assert ya.copper_pct_range[1] - ya.copper_pct_range[0] < 4.0


def test_yield_source_marks_uncited_profiles_visibly(tmp_path):
    """Whatever isn't citably sourced must say so plainly in the rendered
    output -- a literal "(uncited estimate)" tag, not just an implicit
    label a reader has to already know to interpret."""
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(), lot_type_votes=["large_industrial_machinery"] * 5)

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert "(uncited estimate)" in estimate.yield_assessment.yield_source
    text = render_scrap_estimate_as_text(estimate)
    assert "(uncited estimate)" in text


def test_yield_source_never_marks_cited_profiles_as_uncited():
    ya = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [])
    assert "(uncited estimate)" not in ya.yield_source


# --- _vote_modal_or_fallback (generic voting helper) ------------------------


def test_vote_modal_or_fallback_strict_plurality_wins_even_without_unanimity():
    # 3 of 5 vs. 2 of 5 -- a clear plurality, NOT a tie, so it must NOT hit
    # the fallback (this is exactly the photo-4-shaped case).
    votes = ["small_fractional_motors"] * 3 + ["mixed_sealed_motors"] * 2
    resolved, is_unanimous = _vote_modal_or_fallback(votes, fallback="mixed_sealed_motors")
    assert resolved == "small_fractional_motors"
    assert is_unanimous is False


def test_vote_modal_or_fallback_tie_falls_back_to_conservative_value():
    votes = ["small_fractional_motors", "small_fractional_motors", "dc_motors", "dc_motors", "mixed_sealed_motors"]
    resolved, is_unanimous = _vote_modal_or_fallback(votes, fallback="mixed_sealed_motors")
    assert resolved == "mixed_sealed_motors"
    assert is_unanimous is False


def test_vote_modal_or_fallback_unanimous_detected_correctly():
    votes = ["automotive_alternators_starters"] * 5
    resolved, is_unanimous = _vote_modal_or_fallback(votes, fallback="mixed_sealed_motors")
    assert resolved == "automotive_alternators_starters"
    assert is_unanimous is True


# --- vote_lot_type / vote_motor_subtype / vote_copper_richness -------------


def test_vote_lot_type_modal_resolution():
    client = MagicMock()
    client.call_tool.side_effect = [
        {"lot_type": "sealed_motors_alternators_starters", "reasoning": "x"},
        {"lot_type": "sealed_motors_alternators_starters", "reasoning": "x"},
        {"lot_type": "sealed_motors_alternators_starters", "reasoning": "x"},
        {"lot_type": "exposed_copper_windings_stators", "reasoning": "x"},
        {"lot_type": "exposed_copper_windings_stators", "reasoning": "x"},
    ]
    resolved, is_unanimous, raw = vote_lot_type(REAL_LOT_1, client)
    assert resolved == "sealed_motors_alternators_starters"
    assert is_unanimous is False
    assert len(raw) == 5
    assert client.call_tool.call_count == 5


def test_vote_motor_subtype_modal_resolution():
    client = MagicMock()
    client.call_tool.side_effect = [
        {"subtype": "small_fractional_motors", "reasoning": "x"},
        {"subtype": "small_fractional_motors", "reasoning": "x"},
        {"subtype": "small_fractional_motors", "reasoning": "x"},
        {"subtype": "mixed_sealed_motors", "reasoning": "x"},
        {"subtype": "mixed_sealed_motors", "reasoning": "x"},
    ]
    resolved, is_unanimous, raw = vote_motor_subtype(REAL_LOT_1, client)
    assert resolved == "small_fractional_motors"
    assert is_unanimous is False
    assert len(raw) == 5


def test_vote_copper_richness_evidence_only_from_agreeing_votes():
    client = MagicMock()
    client.call_tool.side_effect = [
        {"visible_copper_richness": "unusually_copper_rich", "visible_evidence": ["evidence A"], "reasoning": "x"},
        {"visible_copper_richness": "unusually_copper_rich", "visible_evidence": ["evidence B"], "reasoning": "x"},
        {"visible_copper_richness": "unusually_copper_rich", "visible_evidence": ["evidence A"], "reasoning": "x"},
        {"visible_copper_richness": "typical_mixed_scrap", "visible_evidence": ["should not appear"], "reasoning": "x"},
        {"visible_copper_richness": "typical_mixed_scrap", "visible_evidence": ["should not appear either"], "reasoning": "x"},
    ]
    resolved, is_unanimous, evidence, raw = vote_copper_richness(REAL_LOT_1, client)
    assert resolved == "unusually_copper_rich"
    assert is_unanimous is False
    assert "should not appear" not in evidence
    assert "should not appear either" not in evidence
    assert "evidence A" in evidence and "evidence B" in evidence
    assert len(evidence) == 2  # deduplicated -- "evidence A" appeared twice


# --- Within-range refinement: _tertile_to_range (deterministic mapping) ---


def test_tertile_to_range_maps_thirds_correctly():
    # 10-14% range, width 4, third = 1.333...
    assert _tertile_to_range((10.0, 14.0), "lower") == (10.0, 10.0 + 4 / 3)
    assert _tertile_to_range((10.0, 14.0), "upper") == (14.0 - 4 / 3, 14.0)
    middle = _tertile_to_range((10.0, 14.0), "middle")
    assert middle == (10.0 + 4 / 3, 14.0 - 4 / 3)


def test_tertile_to_range_always_narrower_than_original_and_within_bounds():
    for tertile in ("lower", "middle", "upper"):
        lo, hi = _tertile_to_range((10.0, 14.0), tertile)
        assert 10.0 <= lo <= hi <= 14.0
        assert (hi - lo) < 4.0


# --- Richness-conditioned tail trim (apply_richness_trim) ------------------


def test_apply_richness_trim_unanimous_typical_trims_top_20_percent():
    trimmed, note = apply_richness_trim((10.0, 14.0), "typical_mixed_scrap", is_unanimous=True)
    assert trimmed == (10.0, 14.0 - 0.2 * 4.0)
    assert "upper tail" in note


def test_apply_richness_trim_unanimous_rich_trims_bottom_20_percent():
    trimmed, note = apply_richness_trim((10.0, 14.0), "unusually_copper_rich", is_unanimous=True)
    assert trimmed == (10.0 + 0.2 * 4.0, 14.0)
    assert "lower tail" in note


def test_apply_richness_trim_unanimous_poor_deliberately_not_trimmed():
    """No rule was specified for unanimous unusually_copper_poor in the
    checkpoint that requested this trim -- deliberately NOT extended,
    rather than inventing a rule (see module docstring)."""
    trimmed, note = apply_richness_trim((10.0, 14.0), "unusually_copper_poor", is_unanimous=True)
    assert trimmed == (10.0, 14.0)
    assert note is None


def test_apply_richness_trim_no_trim_on_split_vote_or_cannot_assess():
    for verdict in ("typical_mixed_scrap", "unusually_copper_rich", "unusually_copper_poor", "cannot_assess"):
        trimmed, note = apply_richness_trim((10.0, 14.0), verdict, is_unanimous=False)
        assert trimmed == (10.0, 14.0)
        assert note is None

    trimmed, note = apply_richness_trim((10.0, 14.0), "cannot_assess", is_unanimous=True)
    assert trimmed == (10.0, 14.0)
    assert note is None


def test_apply_richness_trim_never_widens_or_inverts():
    for verdict in ("typical_mixed_scrap", "unusually_copper_rich", "unusually_copper_poor", "cannot_assess"):
        for unanimous in (True, False):
            trimmed, _ = apply_richness_trim((7.0, 18.0), verdict, unanimous)
            assert 7.0 <= trimmed[0] <= trimmed[1] <= 18.0


# --- Ferrous is the arithmetic complement, never independently narrowed ---


def test_compute_yield_assessment_ferrous_is_arithmetic_complement():
    ya = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [])
    expected_lo = round(100.0 - ya.copper_pct_range[1] - ya.aluminum_pct_range[1], 1)
    expected_hi = round(100.0 - ya.copper_pct_range[0] - ya.aluminum_pct_range[0], 1)
    assert ya.ferrous_pct_range == [expected_lo, expected_hi]
    assert "arithmetic complement" in ya.note


def test_compute_yield_assessment_ferrous_narrows_when_copper_narrows_via_refinement():
    wide = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [], subtype="mixed_sealed_motors")
    narrowed = compute_yield_assessment(
        "sealed_motors_alternators_starters", "typical_mixed_scrap", [],
        subtype="automotive_alternators_starters", refined_subtype_range=(11.3, 12.7),
    )
    wide_ferrous_width = wide.ferrous_pct_range[1] - wide.ferrous_pct_range[0]
    narrowed_ferrous_width = narrowed.ferrous_pct_range[1] - narrowed.ferrous_pct_range[0]
    assert narrowed_ferrous_width < wide_ferrous_width


def test_compute_yield_assessment_richness_trim_applies_to_both_copper_and_aluminum():
    untrimmed = compute_yield_assessment("sealed_motors_alternators_starters", "typical_mixed_scrap", [])
    trimmed = compute_yield_assessment(
        "sealed_motors_alternators_starters", "typical_mixed_scrap", [], richness_is_unanimous=True,
    )
    assert trimmed.copper_pct_range[1] < untrimmed.copper_pct_range[1]
    assert trimmed.aluminum_pct_range[1] < untrimmed.aluminum_pct_range[1]
    assert "copper" in " ".join(trimmed.trim_notes)
    assert "aluminum" in " ".join(trimmed.trim_notes)


def test_compute_yield_assessment_no_trim_when_richness_not_unanimous():
    ya = compute_yield_assessment(
        "sealed_motors_alternators_starters", "typical_mixed_scrap", [], richness_is_unanimous=False,
    )
    assert ya.copper_pct_range == [7.0, 18.0]
    assert ya.trim_notes == []


# --- Full pipeline stacking: refinement + trim + ferrous complement -------


def test_estimate_scrap_lot_stacks_refinement_and_trim_never_widens(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(
        _base_result(),
        subtype_votes=["automotive_alternators_starters"] * 5,
        richness_votes=["typical_mixed_scrap"] * 5,  # unanimous -> trim fires too
    )

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
    ya = estimate.yield_assessment

    # Stacked: refinement narrows 10-14 to a ~1.3pp third, then the
    # unanimous-typical trim removes another 20% off the top of THAT third.
    assert 10.0 <= ya.copper_pct_range[0] <= ya.copper_pct_range[1] <= 14.0
    assert ya.copper_pct_range[1] - ya.copper_pct_range[0] < 4 / 3 + 0.01
    assert len(ya.trim_notes) == 2  # both copper and aluminum trimmed
    # ferrous is still the arithmetic complement of whatever copper/aluminum ended up as.
    expected_ferrous = [
        round(100.0 - ya.copper_pct_range[1] - ya.aluminum_pct_range[1], 1),
        round(100.0 - ya.copper_pct_range[0] - ya.aluminum_pct_range[0], 1),
    ]
    assert ya.ferrous_pct_range == expected_ferrous


# --- aggregate_shipment_yield_assessments (live shipment-level combining) --


def _ya(lot_type, copper_range, aluminum_range=(0.0, 3.0)):
    return YieldAssessment(
        lot_type=lot_type, copper_pct_range=list(copper_range), aluminum_pct_range=list(aluminum_range),
        ferrous_pct_range=[round(100 - copper_range[1] - aluminum_range[1], 1), round(100 - copper_range[0] - aluminum_range[0], 1)],
        yield_source="cited industry range (no weigh-ins yet)", deviation="looks_typical", visible_evidence=[],
        note="mock",
    )


def test_aggregate_shipment_yield_assessments_returns_none_for_empty():
    assert aggregate_shipment_yield_assessments([]) is None


def test_aggregate_shipment_yield_assessments_same_type_intersects_and_narrows():
    assessments = [
        _ya("automotive_alternators_starters", (10.0, 14.0)),
        _ya("automotive_alternators_starters", (11.0, 13.0)),
    ]
    combined = aggregate_shipment_yield_assessments(assessments)
    # intersection of (10,14) and (11,13) is (11,13) -- narrower than either.
    assert combined.copper_pct_range == [11.0, 13.0]
    assert "same classified type" in combined.note


def test_aggregate_shipment_yield_assessments_non_overlapping_falls_back_to_union():
    assessments = [
        _ya("automotive_alternators_starters", (10.0, 12.0)),
        _ya("automotive_alternators_starters", (13.0, 15.0)),
    ]
    combined = aggregate_shipment_yield_assessments(assessments)
    # ranges don't overlap -- intersection would be inverted (12 > 13), so
    # this falls back to the union (10, 15), an honest signal of disagreement.
    assert combined.copper_pct_range == [10.0, 15.0]


def test_aggregate_shipment_yield_assessments_mixed_type_blends_with_label():
    assessments = [
        _ya("automotive_alternators_starters", (10.0, 14.0)),
        _ya("large_industrial_machinery", (2.0, 6.0)),
    ]
    combined = aggregate_shipment_yield_assessments(assessments)
    assert combined.copper_pct_range == [6.0, 10.0]  # equal-weight blend of (10,14) and (2,6)
    assert "MIXED-type" in combined.note
    assert combined.lot_type == "mixed"


def test_aggregate_shipment_yield_assessments_ferrous_is_complement_not_combined_directly():
    assessments = [
        _ya("automotive_alternators_starters", (10.0, 14.0)),
        _ya("automotive_alternators_starters", (11.0, 13.0)),
    ]
    combined = aggregate_shipment_yield_assessments(assessments)
    expected_ferrous = [
        round(100.0 - combined.copper_pct_range[1] - combined.aluminum_pct_range[1], 1),
        round(100.0 - combined.copper_pct_range[0] - combined.aluminum_pct_range[0], 1),
    ]
    assert combined.ferrous_pct_range == expected_ferrous


def test_estimate_scrap_lot_photos_1_and_2_shipment_aggregation_demo(tmp_path):
    """Photos 1 and 2 (the same real alternator lot) run through the full
    stacked pipeline, then combined -- single-photo vs. aggregate width
    side by side, real mechanism, no live API calls (mocked client)."""
    entity_path = tmp_path / "entity_memory.jsonl"

    client1 = _fake_client(_base_result(), subtype_votes=["automotive_alternators_starters"] * 5)
    estimate1 = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client1, path=entity_path)

    client2 = _fake_client(_base_result(), subtype_votes=["automotive_alternators_starters"] * 5, tertile_result="upper")
    estimate2 = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client2, path=entity_path)

    combined = aggregate_shipment_yield_assessments([estimate1.yield_assessment, estimate2.yield_assessment])

    single_widths = [
        estimate1.yield_assessment.copper_pct_range[1] - estimate1.yield_assessment.copper_pct_range[0],
        estimate2.yield_assessment.copper_pct_range[1] - estimate2.yield_assessment.copper_pct_range[0],
    ]
    combined_width = combined.copper_pct_range[1] - combined.copper_pct_range[0]
    assert combined_width <= min(single_widths)


# --- Headline calibration promise (width reduction #3) ---------------------


def test_generic_yield_expectation_note_is_the_headline_promise():
    assert "~3 real weigh-ins" in GENERIC_YIELD_EXPECTATION_NOTE
    assert "narrows" in GENERIC_YIELD_EXPECTATION_NOTE


def test_calibration_narrows_to_realistic_cluster_spread_under_5pp(tmp_path):
    """Simulates 3 real weigh-ins with realistic clustering (11.2%, 12.1%,
    11.8%) and confirms the rendered range tightens to that cluster's
    spread -- well under the generic 11pp-wide range -- with the
    "calibrated from N-ins" label."""
    entity_path = tmp_path / "entity_memory.jsonl"
    for actual_copper in (11.2, 12.1, 11.8):
        client = _fake_client(_base_result())
        estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
        record_actual_weighin("Acme Scrap Yard", "weighin", actual_copper, 1.0, 86.0, path=entity_path)

    fresh_client = _fake_client(_base_result())
    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=fresh_client, path=entity_path)

    ya = estimate.yield_assessment
    assert "calibrated from 3 real weigh-ins" in ya.yield_source
    width = ya.copper_pct_range[1] - ya.copper_pct_range[0]
    assert width < 5.0, ya.copper_pct_range
    text = render_scrap_estimate_as_text(estimate)
    assert "calibrated from 3 real weigh-ins" in text
    assert GENERIC_YIELD_EXPECTATION_NOTE not in text


# --- compute_coherence_note (cross-field physical coherence) --------------


def test_compute_coherence_note_none_when_no_conflict():
    assert compute_coherence_note("enclosed_housing", True, "sealed_motors_alternators_starters") is None


def test_compute_coherence_note_none_when_not_scrap_metal():
    assert compute_coherence_note("not_applicable", False, "not_applicable") is None


def test_compute_coherence_note_flags_exposed_copper_vs_non_exposed_lot_type():
    for lot_type in ("sealed_motors_alternators_starters", "large_industrial_machinery",
                      "aluminum_dominant_items", "loose_mixed_steel"):
        note = compute_coherence_note("exposed_stripped", True, lot_type)
        assert note is not None, lot_type
        assert lot_type.replace("_", " ") in note


def test_compute_coherence_note_does_not_flag_exposed_copper_for_its_own_type():
    assert compute_coherence_note("exposed_stripped", True, "exposed_copper_windings_stators") is None


def test_compute_coherence_note_does_not_flag_for_unclear_or_missing_lot_type():
    assert compute_coherence_note("exposed_stripped", True, "unclear") is None
    assert compute_coherence_note("exposed_stripped", True, None) is None


def test_estimate_scrap_lot_surfaces_coherence_conflict_and_downgrades_confidence(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(copper_exposure="exposed_stripped", confidence="high"))

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert estimate.coherence_note is not None
    assert "copper exposure suggests" in estimate.coherence_note
    assert estimate.confidence == "medium"  # downgraded one level from high
    text = render_scrap_estimate_as_text(estimate)
    assert "Note:" in text
    assert estimate.coherence_note in text


def test_estimate_scrap_lot_no_coherence_conflict_on_default_coherent_case(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(confidence="high"))

    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    assert estimate.coherence_note is None
    assert estimate.confidence == "high"  # unchanged -- no conflict to downgrade for


# --- Calibration loop: record_actual_weighin / compute_track_record_note --


def test_record_actual_weighin_writes_marked_record(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"

    record = record_actual_weighin("Acme Scrap Yard", "lot_7_photo.jpg", 12.0, 3.0, 80.0, path=entity_path)

    assert isinstance(record, WeighInRecord)
    records = read_records("Acme Scrap Yard", path=entity_path)
    assert len(records) == 1
    assert records[0].decision_text.startswith(_WEIGHIN_MARKER)


def test_record_actual_weighin_captures_matched_prior_estimate(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    record = record_actual_weighin("Acme Scrap Yard", "lot_1_photo.jpg", 10.0, 2.0, 85.0, path=entity_path)

    assert record.estimated_copper_pct_range is not None


def test_compute_track_record_note_none_when_no_weighins(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    assert compute_track_record_note("Acme Scrap Yard", path=entity_path) is None


def test_compute_track_record_note_surfaces_real_gap(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
    record_actual_weighin("Acme Scrap Yard", "lot_1_photo.jpg", 5.0, 0.0, 90.0, path=entity_path)

    note = compute_track_record_note("Acme Scrap Yard", path=entity_path)

    assert note is not None
    assert "Not auto-adjusted" in note


def test_estimate_scrap_lot_surfaces_track_record_note_after_weighin(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
    record_actual_weighin("Acme Scrap Yard", "lot_1_photo.jpg", 5.0, 0.0, 90.0, path=entity_path)

    second_client = _fake_client(_base_result(grade_impression="looks_strong", oxidation_level="low"))
    second_estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=second_client, path=entity_path)

    assert second_estimate.track_record_note is not None
    text = render_scrap_estimate_as_text(second_estimate)
    assert "Not auto-adjusted" in text


def test_record_actual_weighin_captures_lot_type(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    record = record_actual_weighin("Acme Scrap Yard", "lot_1_photo.jpg", 10.0, 2.0, 85.0, path=entity_path)

    assert record.lot_type == "sealed_motors_alternators_starters"


# --- Per-supplier calibrated yields (the real accuracy path) --------------


def test_compute_calibrated_yields_empty_below_minimum_weighins(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
    record_actual_weighin("Acme Scrap Yard", "p1", 10.0, 2.0, 85.0, path=entity_path)
    record_actual_weighin("Acme Scrap Yard", "p2", 11.0, 2.0, 84.0, path=entity_path)
    # only 2 weigh-ins -- below the 3-weighin minimum for calibration.
    assert _compute_calibrated_yields("Acme Scrap Yard", path=entity_path) == {}


def test_compute_calibrated_yields_switches_over_at_3_weighins(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    for i in range(3):
        client = _fake_client(_base_result())
        estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
        record_actual_weighin("Acme Scrap Yard", f"p{i}", 10.0 + i, 1.0, 85.0, path=entity_path)

    calibrated = _compute_calibrated_yields("Acme Scrap Yard", path=entity_path)

    assert "sealed_motors_alternators_starters" in calibrated
    assert calibrated["sealed_motors_alternators_starters"]["_count"] == 3


def test_estimate_scrap_lot_uses_calibrated_yields_and_narrower_range_after_3_weighins(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    for i in range(3):
        client = _fake_client(_base_result())
        estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
        record_actual_weighin("Acme Scrap Yard", f"p{i}", 12.0, 1.0, 87.0, path=entity_path)

    fresh_client = _fake_client(_base_result())
    calibrated_estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=fresh_client, path=entity_path)

    fresh_entity_path = entity_path.parent / "fresh_entity_memory.jsonl"
    generic_client = _fake_client(_base_result())
    generic_estimate = estimate_scrap_lot(REAL_LOT_1, "Brand New Supplier", client=generic_client, path=fresh_entity_path)

    calibrated_ya = calibrated_estimate.yield_assessment
    generic_ya = generic_estimate.yield_assessment

    assert "calibrated from 3 real weigh-ins" in calibrated_ya.yield_source
    assert "cited industry range" in generic_ya.yield_source
    assert "Okon Recycling" in generic_ya.yield_source

    calibrated_width = calibrated_ya.copper_pct_range[1] - calibrated_ya.copper_pct_range[0]
    generic_width = generic_ya.copper_pct_range[1] - generic_ya.copper_pct_range[0]
    assert calibrated_width < generic_width


def test_render_scrap_estimate_as_text_appends_expectation_note_for_generic_yields(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result())
    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    text = render_scrap_estimate_as_text(estimate)
    assert GENERIC_YIELD_EXPECTATION_NOTE in text


def test_render_scrap_estimate_as_text_omits_expectation_note_when_fully_calibrated(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    for i in range(3):
        client = _fake_client(_base_result())
        estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)
        record_actual_weighin("Acme Scrap Yard", f"p{i}", 12.0, 1.0, 87.0, path=entity_path)

    fresh_client = _fake_client(_base_result())
    estimate = estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=fresh_client, path=entity_path)

    text = render_scrap_estimate_as_text(estimate)
    assert GENERIC_YIELD_EXPECTATION_NOTE not in text
