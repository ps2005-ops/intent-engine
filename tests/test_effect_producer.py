"""Batch 15: the lifecycle Batch 14 could not exercise, because nothing wrote.

Every case here runs through the REAL producer, the REAL semantic comparison
in `decision_impact`, and the REAL append-only persistence. Nothing is mocked;
the evidence is synthetic and marked so, and it drives the production seam
rather than standing in for it.

The cases that must NOT produce learning outnumber the ones that must. That
ratio is deliberate: the easiest broken implementation turns every evidence
row into an effect and reports enormous velocity.
"""
import pytest

from intent_engine.company_ingestion.learning_attribution import (
    CHANGING, CONTRADICTED, CREATED, FIRST_OBSERVATION, NO_CHANGE, NON_CHANGING,
    REFUSED, RETIRED, SUPPORTED, UNMEASURABLE,
)
from intent_engine.external_intel import decision_impact as di
from intent_engine.external_intel import effect_producer as ep

#: SYNTHETIC. Drives the deterministic seam; never stands in for a live run.
_COMPANY = "acme"


def _state(**fields):
    """A semantic state over canonical impact types."""
    return {field: list(fields.get(field, ())) for field in di.IMPACT_TYPES}


def _impact(before, after, *, company=_COMPANY, analysis="run-1"):
    return di.assess(analysis_id=analysis, company_id=company,
                     before=before, after=after, provenance=("obs-1",))


# --- CASE A: first observation ----------------------------------------------
def test_case_a_first_observation_is_a_baseline_not_an_improvement(tmp_path):
    impact = di.assess_against_prior(
        tmp_path, analysis_id="run-1", company_id=_COMPANY,
        after=_state(RECOMMENDATION=("hold capacity",)),
        provenance=("obs-1",))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-1"])
    assert [e.effect_type for e in effects] == [FIRST_OBSERVATION]
    assert effects[0].effect_type not in CHANGING
    assert effects[0].effect_type in NON_CHANGING


# --- CASE B: semantically identical second observation ----------------------
def test_case_b_identical_second_observation_is_a_confirmation(tmp_path):
    before = _state(RECOMMENDATION=("hold capacity",))
    impact = _impact(before, dict(before))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-2"])
    assert {e.effect_type for e in effects} == {NO_CHANGE}
    assert all(e.effect_type not in CHANGING for e in effects)


def test_case_b2_a_reread_that_could_not_test_earns_no_confirmation(tmp_path):
    """THE CHEAPEST CONFIRMATION RATE IN THE SYSTEM, refused.

    Re-fetch the same page daily and every field "holds". A confirmation is
    only earned when the evidence could have moved the state.
    """
    before = _state(RECOMMENDATION=("hold capacity",))
    impact = _impact(before, dict(before))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-2"],
                                     testable=False)
    assert {e.effect_type for e in effects} == {UNMEASURABLE}
    assert NO_CHANGE not in {e.effect_type for e in effects}


# --- CASE C: meaningful revision --------------------------------------------
def test_case_c_a_material_change_produces_a_changing_effect():
    impact = _impact(_state(RECOMMENDATION=("hold capacity",)),
                     _state(RECOMMENDATION=("expand capacity in ohio",)))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-3"])
    changing = [e for e in effects if e.effect_type in CHANGING]
    assert changing, "a replaced recommendation must produce a changing effect"
    assert changing[0].effect_type == CONTRADICTED
    assert changing[0].before_state != changing[0].after_state


def test_a_new_field_reads_created_and_a_dropped_item_reads_retired():
    """Matched to the ENGINE's semantics, not to what the names suggest.

    `compare_field` grades a field emptied entirely as WEAKENED and one that
    lost an item while keeping others as REMOVED. An earlier version of this
    test asserted the reverse and was wrong about the code, not the code about
    itself.
    """
    created = ep.effects_from_impact(
        _impact(_state(), _state(RISK=("supplier concentration",))),
        evidence_ids=["obs-4"])
    assert CREATED in {e.effect_type for e in created}
    retired = ep.effects_from_impact(
        _impact(_state(RISK=("supplier concentration", "fx exposure")),
                _state(RISK=("supplier concentration",))),
        evidence_ids=["obs-5"])
    assert RETIRED in {e.effect_type for e in retired}


def test_a_field_emptied_entirely_reads_weakened():
    from intent_engine.company_ingestion.learning_attribution import WEAKENED
    effects = ep.effects_from_impact(
        _impact(_state(RISK=("supplier concentration",)), _state()),
        evidence_ids=["obs-5b"])
    assert WEAKENED in {e.effect_type for e in effects}


def test_an_extended_field_reads_supported():
    impact = _impact(_state(RISK=("supplier concentration",)),
                     _state(RISK=("supplier concentration", "fx exposure")))
    assert SUPPORTED in {e.effect_type
                         for e in ep.effects_from_impact(
                             impact, evidence_ids=["obs-6"])}


def test_an_untested_component_produces_no_effect():
    """THE INFLATION THIS BATCH CAUGHT IN ITS OWN LIVE PROOF.

    `assess` returns a delta for every one of the twelve impact types, so one
    effect per delta produced TWELVE effects per cycle — eleven of them
    confirmations of components that have never held any content. The ledger
    would have filled with undisputable confirmations and the conversion rate
    would have looked excellent.

    A component with no state on either side was not tested. Silence is not
    an event.
    """
    impact = _impact(_state(RECOMMENDATION=("hold capacity",)),
                     _state(RECOMMENDATION=("expand capacity",)))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-16"])
    assert len(effects) == 1, (
        f"one component moved; got {[e.target_id for e in effects]}")
    assert effects[0].target_id.endswith(":RECOMMENDATION")


def test_the_effect_count_tracks_components_not_evidence_rows():
    """Ten evidence rows behind one movement is ONE effect, not ten."""
    impact = _impact(_state(RECOMMENDATION=("a",)), _state(RECOMMENDATION=("b",)))
    effects = ep.effects_from_impact(
        impact, evidence_ids=[f"obs-{i}" for i in range(10)])
    assert len(effects) == 1


# --- CASE D/E: wording-only and timestamp-only ------------------------------
def test_case_d_wording_only_change_produces_no_changing_effect():
    """TWO RENDERINGS OF ONE CLAIM. Casing and a trailing full stop.

    This graded REVERSED — the strongest change signal there is — because
    `_norm` lowercased and collapsed whitespace but left punctuation on. A
    model that ends a sentence with a period on one run and not the next
    would have manufactured a CONTRADICTED effect on every rerun.
    """
    impact = _impact(_state(RECOMMENDATION=("Hold capacity.",)),
                     _state(RECOMMENDATION=("hold capacity",)))
    assert not [e for e in ep.effects_from_impact(impact,
                                                  evidence_ids=["obs-7"])
                if e.effect_type in CHANGING]


def test_internal_punctuation_still_distinguishes_two_claims():
    """NEGATIVE CONTROL for the normalisation fix: only the ends are trimmed.

    Stripping punctuation everywhere would merge genuinely different claims,
    which trades a false positive for a false negative — and a missed
    contradiction is the worse of the two.
    """
    impact = _impact(_state(RECOMMENDATION=("profit, then scale",)),
                     _state(RECOMMENDATION=("profit then scale",)))
    assert [e for e in ep.effects_from_impact(impact, evidence_ids=["obs-7b"])
            if e.effect_type in CHANGING]


def test_case_e_a_timestamp_only_change_produces_no_changing_effect():
    """`generated_at` is not part of the semantic state at all."""
    before = _state(RECOMMENDATION=("hold capacity",))
    a = _impact(before, dict(before), analysis="run-1")
    b = _impact(before, dict(before), analysis="run-2")
    assert not [e for e in ep.effects_from_impact(a, evidence_ids=["o"])
                if e.effect_type in CHANGING]
    assert not [e for e in ep.effects_from_impact(b, evidence_ids=["o"])
                if e.effect_type in CHANGING]


# --- CASE F/G/H: refusals ---------------------------------------------------
def test_case_f_an_incomparable_window_is_refused_not_scored():
    impact = _impact(_state(RECOMMENDATION=("a",)),
                     _state(RECOMMENDATION=("b",)))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-8"],
                                     comparability=di.UNKNOWN_WINDOW)
    assert [e.effect_type for e in effects] == [REFUSED]
    assert "INCOMPARABLE_WINDOW" in effects[0].reason


def test_case_g_a_change_with_no_provenance_earns_no_learning():
    impact = _impact(_state(RECOMMENDATION=("a",)),
                     _state(RECOMMENDATION=("b",)))
    effects = ep.effects_from_impact(impact, evidence_ids=[])
    assert [e.effect_type for e in effects] == [REFUSED]
    assert "NO_PROVENANCE" in effects[0].reason


def test_case_h_another_companys_prior_is_never_this_companys_before():
    impact = _impact(_state(RECOMMENDATION=("a",)),
                     _state(RECOMMENDATION=("b",)))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-9"],
                                     prior_company_id="globex")
    assert [e.effect_type for e in effects] == [REFUSED]
    assert "CROSS_COMPANY_PRIOR" in effects[0].reason


def test_an_effect_must_name_the_company_and_the_analysis():
    assert ep.eligibility(company_id="", analysis_id="r", impact=None,
                          evidence_ids=["x"]).reason == ep.NO_COMPANY
    assert ep.eligibility(company_id="c", analysis_id="", impact=None,
                          evidence_ids=["x"]).reason == ep.NO_ANALYSIS


# --- persistence, reload, idempotency (§6) ----------------------------------
def test_the_same_semantic_comparison_appends_once(tmp_path):
    impact = _impact(_state(RECOMMENDATION=("a",)),
                     _state(RECOMMENDATION=("b",)))
    effects = ep.effects_from_impact(impact, evidence_ids=["obs-10"])
    assert ep.record_effects(tmp_path, effects) == len(effects)
    assert ep.record_effects(tmp_path, effects) == 0


def test_idempotency_survives_a_fresh_read_of_the_file(tmp_path):
    """RELOAD IS PART OF THE PROOF. An in-memory set would pass without it."""
    impact = _impact(_state(RECOMMENDATION=("a",)),
                     _state(RECOMMENDATION=("b",)))
    ep.record_effects(tmp_path, ep.effects_from_impact(
        impact, evidence_ids=["obs-11"]))
    reloaded = ep.load_effects(tmp_path)
    assert reloaded, "effects must survive to disk"
    rebuilt = ep.effects_from_impact(impact, evidence_ids=["obs-11"])
    assert ep.record_effects(tmp_path, rebuilt) == 0


def test_a_genuinely_new_movement_is_a_second_row(tmp_path):
    first = _impact(_state(RECOMMENDATION=("a",)),
                    _state(RECOMMENDATION=("b",)))
    second = _impact(_state(RECOMMENDATION=("b",)),
                     _state(RECOMMENDATION=("c",)))
    ep.record_effects(tmp_path, ep.effects_from_impact(
        first, evidence_ids=["obs-12"]))
    added = ep.record_effects(tmp_path, ep.effects_from_impact(
        second, evidence_ids=["obs-13"]))
    assert added > 0


def test_effect_identity_does_not_include_the_time_of_day():
    """A digest over the full timestamp duplicates on every rerun.

    The identity deliberately carries the DATE — the market ledger's own
    convention, so the same evidence moving the same object again TOMORROW is
    a second, real record — but not the time. An earlier version of this test
    built both effects from one impact, so `created_at` was identical either
    way and the assertion held with the wall clock fully in the key.
    """
    from intent_engine.company_ingestion.learning_attribution import (
        FOUNDER_DECISION_COMPONENT, SUPPORTED, KnowledgeEffect,
    )
    common = dict(evidence_id="obs-14", target_type=FOUNDER_DECISION_COMPONENT,
                  target_id="acme:RECOMMENDATION", effect_type=SUPPORTED,
                  before_state="a", after_state="b", reason="same movement")
    morning = KnowledgeEffect(created_at="2026-08-13T06:00:00+00:00", **common)
    evening = KnowledgeEffect(created_at="2026-08-13T22:30:00+00:00", **common)
    assert morning.effect_id == evening.effect_id

    tomorrow = KnowledgeEffect(created_at="2026-08-14T06:00:00+00:00",
                               **common)
    assert tomorrow.effect_id != morning.effect_id


def test_a_corrupt_line_is_skipped_and_never_repaired(tmp_path):
    path = tmp_path / ep.EFFECT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"effect_id": "ke-1"}\nnot json at all\n')
    assert [r["effect_id"] for r in ep.load_effects(tmp_path)] == ["ke-1"]


def test_effects_are_scoped_by_company_on_read(tmp_path):
    ep.record_effects(tmp_path, ep.effects_from_impact(
        _impact(_state(RISK=("a",)), _state(RISK=("b",))),
        evidence_ids=["obs-15"]))
    assert ep.load_effects(tmp_path, company_id="globex") == []
    assert ep.load_effects(tmp_path, company_id=_COMPANY)


@pytest.mark.parametrize("change,expected", sorted(
    ep._CHANGE_TO_EFFECT.items()))
def test_every_semantic_change_maps_to_an_effect(change, expected):
    """An unmapped change would raise KeyError in production."""
    assert expected in (CHANGING | NON_CHANGING)
