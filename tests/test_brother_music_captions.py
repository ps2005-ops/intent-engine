import inspect
from unittest.mock import MagicMock

from intent_engine.core.brother_music_captions import (
    ENTITY_ID,
    PILLAR_SEED_CAPTIONS,
    _SCAFFOLD_PREFIX,
    _strip_scaffold_prefix,
    build_cold_start_spec,
    generate_caption_draft,
    seed_cold_start_pillars,
    start_brother_music_captions,
)
from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter, read_records
from intent_engine.core.pattern_watcher import _extract_recipient
from intent_engine.core.suggestion import TaskAgentSpecStub

import intent_engine.core.brother_music_captions as brother_module


def _voice_record(entity_id, decision_text):
    return EntityMemoryRecord(entity_id=entity_id, source="voice", decision_text=decision_text, goals=[], constraints=[])


# --- Reuse discipline: no new mechanism, no copies of the correction loop --


def test_brother_music_captions_module_defines_no_draft_generation_logic_of_its_own():
    """Same reuse-discipline check as Part 2: the shadow-guess-and-correct
    loop and the suggestion layer must be reused EXACTLY as already built
    -- this module must not define, copy, or shadow any of it."""
    own_functions = {
        name for name, obj in inspect.getmembers(brother_module, inspect.isfunction)
        if obj.__module__ == brother_module.__name__
    }
    forbidden = {
        "generate_draft", "classify_draft_reply", "process_draft_reply",
        "generate_suggestion", "accept_suggestion", "decline_suggestion",
        "detect_recurring_message_patterns", "detect_recurring_patterns",
    }
    assert own_functions.isdisjoint(forbidden)


def test_brother_music_captions_module_only_defines_cold_start_seeding_functions():
    """Positive check: the only functions this module defines are cold-start
    seeding and the scaffolding-prefix strip -- applied from day one this
    time (Lesson 1), not added after a live leak, but still the same
    minimal function set as Part 2."""
    own_functions = {
        name for name, obj in inspect.getmembers(brother_module, inspect.isfunction)
        if obj.__module__ == brother_module.__name__
    }
    assert own_functions == {
        "seed_cold_start_pillars", "build_cold_start_spec", "start_brother_music_captions",
        "_strip_scaffold_prefix", "generate_caption_draft",
    }


def test_generate_caption_draft_calls_the_real_unmodified_generate_draft():
    """generate_caption_draft must be a thin wrapper, not a reimplementation
    -- checked by confirming it's the exact same function object
    draft_generator.py defines, imported and called through, not copied."""
    import intent_engine.core.draft_generator as draft_generator_module
    assert brother_module.generate_draft is draft_generator_module.generate_draft


# --- Pillar seed content: exactly 3, weighted, flagged as placeholders -----


def test_pillar_seed_captions_has_exactly_the_three_stated_pillars():
    assert set(PILLAR_SEED_CAPTIONS.keys()) == {
        "original_music_performance", "behind_the_scenes_process", "personal_connection",
    }


def test_pillar_seed_captions_flagged_as_placeholder_content():
    """The seed content must be explicitly, honestly flagged as generic
    placeholder text pending real specifics -- not silently presented as
    real details about the actual musician."""
    assert "PLACEHOLDER" in brother_module.__doc__
    assert "generic placeholder" in brother_module.__doc__.lower()


def test_pillar_seed_captions_all_extract_instagram_as_recipient():
    """Recipient-framing check: every seed caption must be phrased so the
    UNMODIFIED pattern_watcher._extract_recipient groups it under
    "instagram" -- the one deliberate phrasing adaptation this domain
    needs, not a change to the extraction mechanism itself."""
    for pillar, text in PILLAR_SEED_CAPTIONS.items():
        assert _extract_recipient(text) == "instagram", pillar


def test_pillar_seed_captions_weighting_is_stated_in_the_docstring():
    """The 40/30/20 weighting is a stated intent, not silently implied --
    checked directly rather than assumed present."""
    doc = brother_module.__doc__
    assert "40/30/20" in doc


# --- seed_cold_start_pillars -------------------------------------------------


def test_seed_cold_start_pillars_writes_exactly_3_records(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    records = seed_cold_start_pillars(entity_id="Test Brother Account", path=path)

    assert len(records) == 3
    stored = read_records("Test Brother Account", path=path)
    assert len(stored) == 3
    assert {r.source for r in stored} == {"voice"}


def test_seed_cold_start_pillars_records_match_pillar_seed_captions_text(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    records = seed_cold_start_pillars(entity_id="Test Brother Account", path=path)

    stored_texts = {r.decision_text for r in records}
    assert stored_texts == set(PILLAR_SEED_CAPTIONS.values())


# --- build_cold_start_spec --------------------------------------------------


def test_build_cold_start_spec_produces_valid_task_agent_spec_stub(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    seed_records = seed_cold_start_pillars(entity_id="Test Brother Account", path=path)

    spec = build_cold_start_spec("Test Brother Account", seed_records)

    assert isinstance(spec, TaskAgentSpecStub)
    assert spec.action == "draft_only"
    assert spec.gated is True
    assert set(spec.supporting_record_ids) == {r.record_id for r in seed_records}
    assert "40/30/20" in spec.trigger_hint
    assert "day-one" in spec.trigger_hint.lower()


def test_build_cold_start_spec_states_the_no_rotation_expectation_up_front():
    """Lesson 2: the no-cross-pillar-rotation property must be stated in
    the spec's own trigger_hint, not just the module docstring -- so
    anything reading the spec directly (not just the source file) sees
    the expectation too."""
    spec = build_cold_start_spec("Test Brother Account", [])
    assert "rotate" in spec.trigger_hint.lower()


def test_build_cold_start_spec_never_references_a_real_detected_pattern():
    """source_pattern_id must be visibly distinct from a real DetectedPattern
    id -- this spec was never produced by detect_recurring_message_patterns()."""
    spec = build_cold_start_spec("Test Brother Account", [])
    assert "cold-start" in spec.source_pattern_id.lower()


# --- start_brother_music_captions: idempotent, real-history-aware ----------


def test_start_brother_music_captions_seeds_on_first_call(tmp_path):
    path = tmp_path / "entity_memory.jsonl"

    spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)

    stored = read_records("Test Brother Account", path=path)
    assert len(stored) == 3
    assert set(spec.supporting_record_ids) == {r.record_id for r in stored}


def test_start_brother_music_captions_does_not_duplicate_seeds_on_second_call(tmp_path):
    path = tmp_path / "entity_memory.jsonl"

    first_spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)
    second_spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)

    stored = read_records("Test Brother Account", path=path)
    assert len(stored) == 3  # not 6 -- second call must not re-seed
    assert set(first_spec.supporting_record_ids) == set(second_spec.supporting_record_ids)


def test_start_brother_music_captions_reuses_existing_real_history_instead_of_seeding(tmp_path):
    """If real history already exists for this entity, start_brother_music_captions()
    must build the spec from that real history, never silently injecting
    placeholder seed captions on top of or instead of it."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    real_record = _voice_record("Test Brother Account", "Update Instagram with today's caption: a real one, already posted")
    writer.write(real_record)

    spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)

    stored = read_records("Test Brother Account", path=path)
    assert len(stored) == 1  # no seeds added
    assert spec.supporting_record_ids == [real_record.record_id]


def test_start_brother_music_captions_defaults_to_the_real_entity_id(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    start_brother_music_captions(path=path)
    stored = read_records(ENTITY_ID, path=path)
    assert len(stored) == 3


# --- Prefix-strip, applied from day one (Lesson 1) --------------------------


def test_strip_scaffold_prefix_removes_the_exact_phrase():
    text = _SCAFFOLD_PREFIX + " New clip from tonight's set. #originalmusic"
    assert _strip_scaffold_prefix(text) == "New clip from tonight's set. #originalmusic"


def test_strip_scaffold_prefix_case_insensitive():
    text = "update instagram with today's caption: shorter one here"
    assert _strip_scaffold_prefix(text) == "shorter one here"


def test_strip_scaffold_prefix_is_a_noop_when_prefix_absent():
    text = "Just played the new song live for the first time. #musiclife"
    assert _strip_scaffold_prefix(text) == text


def test_generate_caption_draft_strips_prefix_from_examples_before_the_prompt(tmp_path):
    """The verb-gate (_extract_recipient) still needs the prefix in the
    STORED record to find "instagram" as the recipient -- gathering is
    unaffected. But the prompt the model actually sees must never contain
    it."""
    path = tmp_path / "entity_memory.jsonl"
    spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)

    client = MagicMock()
    client.call_tool.return_value = {"draft_text": "a mocked draft, no prefix here"}

    generate_caption_draft(spec, "Test Brother Account", client=client, path=path)

    user_message = client.call_tool.call_args.kwargs["user_message"]
    assert _SCAFFOLD_PREFIX.lower() not in user_message.lower()
    # sanity: the real pillar content itself IS still present -- only the
    # scaffolding prefix was stripped, not the actual example text.
    assert "clip" in user_message.lower() or "riff" in user_message.lower() or "show" in user_message.lower()


def test_generate_caption_draft_strips_prefix_from_model_output_if_present(tmp_path):
    """Render-time safety net, wired up from day one this time: even if the
    model's own output still contains the scaffolding phrase, the final
    generated_text a person sees must never contain it."""
    path = tmp_path / "entity_memory.jsonl"
    spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)

    client = MagicMock()
    client.call_tool.return_value = {
        "draft_text": f"{_SCAFFOLD_PREFIX} a caption the model generated, prefix and all"
    }

    attempt = generate_caption_draft(spec, "Test Brother Account", client=client, path=path)

    assert _SCAFFOLD_PREFIX.lower() not in attempt.generated_text.lower()
    assert attempt.generated_text == "a caption the model generated, prefix and all"


def test_generate_caption_draft_never_produces_prefix_across_realistic_mocked_outputs(tmp_path):
    """Broader confirmation: across several plausible mocked model outputs
    (with prefix, without prefix, different casing), generated captions
    never contain the scaffolding prefix."""
    path = tmp_path / "entity_memory.jsonl"
    spec = start_brother_music_captions(entity_id="Test Brother Account", path=path)

    mocked_outputs = [
        f"{_SCAFFOLD_PREFIX} new clip from tonight's set",
        "already-clean caption, no prefix",
        f"{_SCAFFOLD_PREFIX.lower()} lowercase variant of the prefix",
    ]
    for mocked_text in mocked_outputs:
        client = MagicMock()
        client.call_tool.return_value = {"draft_text": mocked_text}
        attempt = generate_caption_draft(spec, "Test Brother Account", client=client, path=path)
        assert _SCAFFOLD_PREFIX.lower() not in attempt.generated_text.lower(), mocked_text
