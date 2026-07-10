import inspect

from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter, read_records
from intent_engine.core.mom_fitness_captions import (
    ENTITY_ID,
    PILLAR_SEED_CAPTIONS,
    build_cold_start_spec,
    seed_cold_start_pillars,
    start_mom_fitness_captions,
)
from intent_engine.core.pattern_watcher import _extract_recipient
from intent_engine.core.suggestion import TaskAgentSpecStub

import intent_engine.core.mom_fitness_captions as mom_module


def _voice_record(entity_id, decision_text):
    return EntityMemoryRecord(entity_id=entity_id, source="voice", decision_text=decision_text, goals=[], constraints=[])


# --- Reuse discipline: no new mechanism, no copies of the correction loop --


def test_mom_fitness_captions_module_defines_no_draft_generation_logic_of_its_own():
    """The shadow-guess-and-correct loop (generate_draft/classify_draft_reply/
    process_draft_reply/DraftAttempt) and the suggestion layer
    (generate_suggestion/accept_suggestion/decline_suggestion) must be reused
    EXACTLY as already built -- this module must not define, copy, or shadow
    any of it. Checked by introspecting which functions are actually DEFINED
    in this module's own namespace (via __module__), not just whether the
    names happen to be importable."""
    own_functions = {
        name for name, obj in inspect.getmembers(mom_module, inspect.isfunction)
        if obj.__module__ == mom_module.__name__
    }
    forbidden = {
        "generate_draft", "classify_draft_reply", "process_draft_reply",
        "generate_suggestion", "accept_suggestion", "decline_suggestion",
        "detect_recurring_message_patterns", "detect_recurring_patterns",
    }
    assert own_functions.isdisjoint(forbidden)


def test_mom_fitness_captions_module_only_defines_cold_start_seeding_functions():
    """Positive check to complement the above: the only functions this
    module actually defines are the cold-start seeding ones -- nothing
    else, no surprise extra mechanism."""
    own_functions = {
        name for name, obj in inspect.getmembers(mom_module, inspect.isfunction)
        if obj.__module__ == mom_module.__name__
    }
    assert own_functions == {"seed_cold_start_pillars", "build_cold_start_spec", "start_mom_fitness_captions"}


# --- Pillar seed content: exactly 3, flagged as placeholders ---------------


def test_pillar_seed_captions_has_exactly_the_three_stated_pillars():
    assert set(PILLAR_SEED_CAPTIONS.keys()) == {
        "authority_education", "transformation_social_proof", "personal_story",
    }


def test_pillar_seed_captions_flagged_as_placeholder_content():
    """The seed content must be explicitly, honestly flagged as generic
    placeholder text pending real specifics -- not silently presented as
    real business detail."""
    assert "PLACEHOLDER" in mom_module.__doc__
    assert "generic placeholder" in mom_module.__doc__.lower()


def test_pillar_seed_captions_all_extract_instagram_as_recipient():
    """Recipient-framing check: every seed caption must be phrased so the
    UNMODIFIED pattern_watcher._extract_recipient groups it under
    "instagram" -- this is the one deliberate phrasing adaptation this
    domain needed, not a change to the extraction mechanism itself."""
    for pillar, text in PILLAR_SEED_CAPTIONS.items():
        assert _extract_recipient(text) == "instagram", pillar


# --- seed_cold_start_pillars -------------------------------------------------


def test_seed_cold_start_pillars_writes_exactly_3_records(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    records = seed_cold_start_pillars(entity_id="Test Mom Account", path=path)

    assert len(records) == 3
    stored = read_records("Test Mom Account", path=path)
    assert len(stored) == 3
    assert {r.source for r in stored} == {"voice"}


def test_seed_cold_start_pillars_records_match_pillar_seed_captions_text(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    records = seed_cold_start_pillars(entity_id="Test Mom Account", path=path)

    stored_texts = {r.decision_text for r in records}
    assert stored_texts == set(PILLAR_SEED_CAPTIONS.values())


# --- build_cold_start_spec --------------------------------------------------


def test_build_cold_start_spec_produces_valid_task_agent_spec_stub(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    seed_records = seed_cold_start_pillars(entity_id="Test Mom Account", path=path)

    spec = build_cold_start_spec("Test Mom Account", seed_records)

    assert isinstance(spec, TaskAgentSpecStub)
    assert spec.action == "draft_only"
    assert spec.gated is True
    assert set(spec.supporting_record_ids) == {r.record_id for r in seed_records}
    assert "3-pillar" in spec.trigger_hint
    assert "day-one" in spec.trigger_hint.lower()


def test_build_cold_start_spec_never_references_a_real_detected_pattern():
    """source_pattern_id must be visibly distinct from a real DetectedPattern
    id (a fresh uuid4 elsewhere in this codebase) -- this spec was never
    produced by detect_recurring_message_patterns(), and its provenance
    should say so plainly rather than looking indistinguishable from an
    organically detected one."""
    spec = build_cold_start_spec("Test Mom Account", [])
    assert "cold-start" in spec.source_pattern_id.lower()


# --- start_mom_fitness_captions: idempotent, real-history-aware ------------


def test_start_mom_fitness_captions_seeds_on_first_call(tmp_path):
    path = tmp_path / "entity_memory.jsonl"

    spec = start_mom_fitness_captions(entity_id="Test Mom Account", path=path)

    stored = read_records("Test Mom Account", path=path)
    assert len(stored) == 3
    assert set(spec.supporting_record_ids) == {r.record_id for r in stored}


def test_start_mom_fitness_captions_does_not_duplicate_seeds_on_second_call(tmp_path):
    path = tmp_path / "entity_memory.jsonl"

    first_spec = start_mom_fitness_captions(entity_id="Test Mom Account", path=path)
    second_spec = start_mom_fitness_captions(entity_id="Test Mom Account", path=path)

    stored = read_records("Test Mom Account", path=path)
    assert len(stored) == 3  # not 6 -- second call must not re-seed
    assert set(first_spec.supporting_record_ids) == set(second_spec.supporting_record_ids)


def test_start_mom_fitness_captions_reuses_existing_real_history_instead_of_seeding(tmp_path):
    """If real history already exists for this entity (e.g. a prior real
    caption was already logged), start_mom_fitness_captions() must build the
    spec from that real history, never silently injecting placeholder seed
    captions on top of or instead of it."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    real_record = _voice_record("Test Mom Account", "Update Instagram with today's caption: a real one, already posted")
    writer.write(real_record)

    spec = start_mom_fitness_captions(entity_id="Test Mom Account", path=path)

    stored = read_records("Test Mom Account", path=path)
    assert len(stored) == 1  # no seeds added
    assert spec.supporting_record_ids == [real_record.record_id]


def test_start_mom_fitness_captions_defaults_to_the_real_entity_id(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    start_mom_fitness_captions(path=path)
    stored = read_records(ENTITY_ID, path=path)
    assert len(stored) == 3
