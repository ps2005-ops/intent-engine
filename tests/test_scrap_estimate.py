import random
from pathlib import Path
from unittest.mock import MagicMock

from intent_engine.core.entity_memory import JsonlEntityMemoryWriter, read_records
from intent_engine.core.scrap_estimate import (
    GENERIC_YIELD_EXPECTATION_NOTE,
    MaterialComposite,
    ScrapEstimate,
    WeighInRecord,
    _BIN_NUMERIC_RANGES,
    _CATEGORY_MATERIAL_PROFILES,
    _SCRAP_CHECK_MARKER,
    _WEIGHIN_MARKER,
    _aggregate_category_votes,
    _compute_calibrated_yields,
    _compute_deterministic_comparison,
    _dominant_material_category,
    _normalize_category_shares,
    _read_prior_scrap_estimates,
    _refine_unanimous_category,
    _resolve_category_range,
    aggregate_shipment_estimates,
    compute_coherence_note,
    compute_condition_note,
    compute_material_composite,
    compute_scrap_score,
    compute_track_record_note,
    estimate_scrap_lot,
    record_actual_weighin,
    render_scrap_estimate_as_text,
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


def _fake_client(main_result, category_votes=None, tertile="middle"):
    """Smart mock dispatching on tool_name, since estimate_scrap_lot() now
    makes up to THREE different kinds of calls: one main judgment call, 5
    category_proportions votes (for real scrap lots), and -- ONLY when a
    category was unanimous across all 5 votes -- one additional tertile-
    refinement call per unanimous category. category_votes defaults to a
    single stable category repeated 5x (a unanimous case) if the test
    doesn't care about category-proportion specifics; tertile controls the
    mocked answer for any refinement call triggered by that unanimity."""
    if category_votes is None:
        category_votes = [{"sealed_motors_alternators_starters": "majority"}] * 5

    state = {"category_call_index": 0}

    def side_effect(*args, **kwargs):
        if kwargs.get("tool_name") == "record_scrap_estimate":
            return main_result
        if kwargs.get("tool_name") == "record_category_proportions":
            idx = state["category_call_index"] % len(category_votes)
            state["category_call_index"] += 1
            return {"category_proportions": category_votes[idx]}
        if kwargs.get("tool_name") == "record_tertile_refinement":
            return {"tertile": tertile}
        raise AssertionError(f"Unexpected tool_name: {kwargs.get('tool_name')}")

    client = MagicMock()
    client.call_tool.side_effect = side_effect
    return client


def _base_result(**overrides):
    """A fully-populated, schema-valid mocked tool result for the ISOLATED
    judgment call."""
    result = {
        "is_scrap_metal_lot": True,
        "category_note": "",
        "grade_impression": "looks_average",
        "oxidation_level": "moderate",
        "visible_contamination": [],
        "copper_exposure": "enclosed_housing",
        "category_typical_yield_note": "",
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
        category_typical_yield_note=None, comparison_note="No prior lots on record yet for this entity.",
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
    ever carry a PER-LOT composition percentage. category_typical_yield_note
    and material_composite are both excluded by name -- the former is the
    already-approved cited-category exception, the latter is the checked,
    hedged sample-based composite, not a per-lot measurement claim."""
    fields = set(ScrapEstimate.model_fields.keys()) - {"category_typical_yield_note", "material_composite"}
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


def test_estimate_scrap_lot_category_proportions_call_also_never_receives_prior_lot_text(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    _write_prior_estimate(entity_path, "Acme Scrap Yard", reasoning="a very distinctive prior reasoning string")

    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    category_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_category_proportions"]
    assert len(category_calls) == 5
    for call in category_calls:
        assert "prior" not in call.kwargs["user_message"].lower()


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


def test_estimate_scrap_lot_not_scrap_metal_sets_not_applicable_grade_and_no_composite(tmp_path):
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
    assert estimate.material_composite is None  # no composite for a non-scrap lot
    assert "not deteriorated scrap" in estimate.category_note
    # category_proportions must never even be called for a non-scrap lot.
    category_calls = [c for c in client.call_tool.call_args_list if c.kwargs["tool_name"] == "record_category_proportions"]
    assert category_calls == []


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


def test_render_scrap_estimate_as_text_surfaces_yield_note_near_top_not_buried():
    estimate = ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=[], copper_exposure="enclosed_housing",
        category_typical_yield_note="Small motors typically run 9-10% copper (industry sources: Okon Recycling).",
        condition_note="moderate oxidation, average condition, no non-metal attachments visible.",
        comparison_note="No prior lots on record yet for this entity.",
        scrap_score=5, confidence="medium", reasoning="moderate rust",
    )

    text = render_scrap_estimate_as_text(estimate)
    lines = text.splitlines()

    yield_line_index = next(i for i, line in enumerate(lines) if "Typical yield reference" in line)
    reasoning_line_index = next(i for i, line in enumerate(lines) if line.startswith("Reasoning"))
    comparison_line_index = next(i for i, line in enumerate(lines) if line.startswith("Comparison"))

    assert "9-10% copper" in lines[yield_line_index]
    assert yield_line_index < comparison_line_index
    assert yield_line_index < reasoning_line_index


# --- _resolve_category_range (bin-wobble -> honest width) ------------------


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


# --- _aggregate_category_votes ---------------------------------------------


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


# --- _normalize_category_shares ---------------------------------------------


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
    """Property test required by the checkpoint: no random combination of
    category share ranges (mimicking real bin-derived and union-derived
    ranges) may produce a normalized bound outside [0, 100], and every
    category's low must remain <= its high. 2000 random trials, stdlib
    `random` only (no new dependency)."""
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


# --- compute_material_composite (deterministic, cited vs. assumption) -----


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


# --- _dominant_material_category ------------------------------------------


def test_dominant_material_category_picks_highest_midpoint():
    shares = {
        "sealed_motors_alternators_starters": [10.0, 20.0],
        "exposed_copper_windings_stators": [60.0, 80.0],
    }
    category, midpoint = _dominant_material_category(shares)
    assert category == "exposed_copper_windings_stators"
    assert midpoint == 70.0


def test_dominant_material_category_ignores_non_metal_and_unidentified():
    shares = {
        "non_metal_contamination": [90.0, 100.0],
        "sealed_motors_alternators_starters": [5.0, 10.0],
    }
    category, _ = _dominant_material_category(shares)
    assert category == "sealed_motors_alternators_starters"


def test_dominant_material_category_none_when_no_material_categories():
    category, midpoint = _dominant_material_category({"non_metal_contamination": [90.0, 100.0]})
    assert category is None
    assert midpoint is None


# --- _refine_unanimous_category (within-bin refinement) --------------------


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


# --- aggregate_shipment_estimates (shipment-level, independent samples) ----


def _estimate_with_composite(copper_range, aluminum_range, ferrous_range, excluded_range=(0.0, 0.0)):
    composite = MaterialComposite(
        category_proportions={}, raw_category_shares_pct={}, normalized_category_shares_pct={},
        excluded_categories=[], copper_pct_range=list(copper_range), aluminum_pct_range=list(aluminum_range),
        hms_ferrous_pct_range=list(ferrous_range), non_metal_excluded_pct_range=list(excluded_range),
    )
    return ScrapEstimate(
        is_scrap_metal_lot=True, grade_impression="looks_average", oxidation_level="moderate",
        visible_contamination=[], copper_exposure="enclosed_housing", material_composite=composite,
        confidence="medium", reasoning="x",
    )


def test_aggregate_shipment_estimates_returns_none_for_no_composites():
    assert aggregate_shipment_estimates([]) is None


def test_aggregate_shipment_estimates_narrows_width_vs_any_single_estimate():
    estimates = [
        _estimate_with_composite((10, 20), (0, 2), (78, 90)),
        _estimate_with_composite((12, 22), (0, 2), (76, 88)),
        _estimate_with_composite((8, 18), (0, 2), (80, 92)),
        _estimate_with_composite((11, 21), (0, 2), (77, 89)),
    ]
    combined = aggregate_shipment_estimates(estimates)

    combined_width = combined.copper_pct_range[1] - combined.copper_pct_range[0]
    single_widths = [e.material_composite.copper_pct_range[1] - e.material_composite.copper_pct_range[0] for e in estimates]
    assert combined_width < min(single_widths)
    assert "4 photos" in combined.hedge
    assert "independent" in combined.hedge


def test_aggregate_shipment_estimates_stays_within_0_100():
    estimates = [_estimate_with_composite((90, 100), (0, 1), (0, 5)) for _ in range(3)]
    combined = aggregate_shipment_estimates(estimates)
    for r in (combined.copper_pct_range, combined.aluminum_pct_range, combined.hms_ferrous_pct_range):
        assert 0 <= r[0] <= 100
        assert 0 <= r[1] <= 100


def test_compute_material_composite_copper_higher_for_exposed_windings_than_sealed():
    """Sanity-relevant unit test: given the SAME share, exposed copper
    windings must produce a higher copper range than sealed motors -- this
    is the deterministic math the full 9-photo sanity check depends on."""
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


# --- compute_coherence_note (cross-field physical coherence) --------------


def test_compute_coherence_note_none_when_no_conflict():
    modal_bins = {"sealed_motors_alternators_starters": "majority"}
    composite = compute_material_composite(modal_bins, {"sealed_motors_alternators_starters": (60, 80)}, [])
    assert compute_coherence_note("enclosed_housing", True, modal_bins, composite) is None


def test_compute_coherence_note_none_when_not_scrap_metal():
    assert compute_coherence_note("not_applicable", False, {}, None) is None


def test_compute_coherence_note_asserts_composite_never_present_for_non_scrap_lot():
    composite = compute_material_composite(
        {"sealed_motors_alternators_starters": "majority"}, {"sealed_motors_alternators_starters": (60, 80)}, [],
    )
    try:
        compute_coherence_note("not_applicable", False, {}, composite)
        assert False, "expected AssertionError"
    except AssertionError:
        pass


def test_compute_coherence_note_flags_exposed_copper_with_absent_category():
    modal_bins = {"sealed_motors_alternators_starters": "majority"}
    composite = compute_material_composite(modal_bins, {"sealed_motors_alternators_starters": (60, 80)}, [])
    note = compute_coherence_note("exposed_stripped", True, modal_bins, composite)
    assert note is not None
    assert "no significant exposed-copper-windings share" in note


def test_compute_coherence_note_flags_exposed_copper_with_minimal_category():
    modal_bins = {"sealed_motors_alternators_starters": "majority", "exposed_copper_windings_stators": "minimal"}
    composite = compute_material_composite(
        modal_bins,
        {"sealed_motors_alternators_starters": (60, 80), "exposed_copper_windings_stators": (0, 5)},
        [],
    )
    note = compute_coherence_note("exposed_stripped", True, modal_bins, composite)
    assert note is not None
    assert "only a minimal exposed-copper-windings share" in note


def test_compute_coherence_note_does_not_flag_exposed_copper_with_real_share():
    modal_bins = {"exposed_copper_windings_stators": "majority"}
    composite = compute_material_composite(modal_bins, {"exposed_copper_windings_stators": (60, 80)}, [])
    assert compute_coherence_note("exposed_stripped", True, modal_bins, composite) is None


def test_compute_coherence_note_flags_sealed_motor_dominance_exceeding_ceiling():
    # sealed_motors dominates the share (80-90%), but a small high-copper
    # exposed-windings share drags the composite's copper HIGH end above
    # the sealed-motor cited ceiling (~18%).
    modal_bins = {"sealed_motors_alternators_starters": "nearly_all", "exposed_copper_windings_stators": "some"}
    share_ranges = {"sealed_motors_alternators_starters": (80, 90), "exposed_copper_windings_stators": (10, 20)}
    composite = compute_material_composite(modal_bins, share_ranges, [])
    note = compute_coherence_note("mixed", True, modal_bins, composite)
    assert note is not None
    assert "exceeds that ceiling" in note


def test_compute_coherence_note_does_not_flag_when_sealed_motor_composite_within_ceiling():
    modal_bins = {"sealed_motors_alternators_starters": "nearly_all"}
    composite = compute_material_composite(modal_bins, {"sealed_motors_alternators_starters": (80, 100)}, [])
    assert compute_coherence_note("enclosed_housing", True, modal_bins, composite) is None


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


def test_record_actual_weighin_captures_dominant_category_and_share(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    client = _fake_client(_base_result())
    estimate_scrap_lot(REAL_LOT_1, "Acme Scrap Yard", client=client, path=entity_path)

    record = record_actual_weighin("Acme Scrap Yard", "lot_1_photo.jpg", 10.0, 2.0, 85.0, path=entity_path)

    assert record.dominant_category == "sealed_motors_alternators_starters"
    assert record.dominant_category_share_pct is not None


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

    calibrated_mc = calibrated_estimate.material_composite
    generic_mc = generic_estimate.material_composite

    assert "calibrated from 3 real weigh-ins" in calibrated_mc.category_yield_sources["sealed_motors_alternators_starters"]
    assert generic_mc.category_yield_sources["sealed_motors_alternators_starters"] == "cited industry range (no weigh-ins yet)"

    calibrated_width = calibrated_mc.copper_pct_range[1] - calibrated_mc.copper_pct_range[0]
    generic_width = generic_mc.copper_pct_range[1] - generic_mc.copper_pct_range[0]
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
