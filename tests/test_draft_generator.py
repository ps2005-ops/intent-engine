from unittest.mock import MagicMock

import pytest

from datetime import datetime, timedelta, timezone

from intent_engine.core.draft_generator import (
    DraftAttempt,
    _gather_supporting_records,
    _hour_in_window,
    _learned_hour_window,
    _name_and_timing_fallback,
    classify_draft_reply,
    generate_draft,
    process_draft_reply,
)
from intent_engine.core.entity_memory import EntityMemoryRecord, SqliteEntityMemoryWriter, read_records
from intent_engine.core.suggestion import TaskAgentSpecStub


def _voice_record(entity_id, decision_text, timestamp=None):
    kwargs = dict(entity_id=entity_id, source="voice", decision_text=decision_text, goals=[], constraints=[])
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    return EntityMemoryRecord(**kwargs)


def _iso(days_ago, hour, minute=0):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def _fake_client(tool_input):
    client = MagicMock()
    client.call_tool.return_value = tool_input
    return client


# --- _gather_supporting_records ---------------------------------------------


def test_gather_supporting_records_re_scans_fresh_not_just_the_frozen_snapshot(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)

    for _ in range(3):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes"))
    original_records = read_records("Acme Inc", path=path)
    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in original_records],
    )

    # A NEW matching record appears after the spec was created (e.g. a fresh
    # daily occurrence, or a correction) -- must be picked up on re-scan.
    writer.write(_voice_record("Acme Inc", "email sarah today's standup notes"))

    gathered = _gather_supporting_records(spec, "Acme Inc", path=path)
    assert len(gathered) == 4


def test_gather_supporting_records_falls_back_to_frozen_snapshot_if_recipient_unrecoverable(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_voice_record("Acme Inc", "just a note with no communication verb at all"))
    original_records = read_records("Acme Inc", path=path)

    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="no verb here either",
        supporting_record_ids=[r.record_id for r in original_records],
    )

    gathered = _gather_supporting_records(spec, "Acme Inc", path=path)
    assert len(gathered) == 1
    assert gathered[0].record_id == original_records[0].record_id


# --- name+timing fallback (closes the "blind to casual new occurrences" gap) -


def test_hour_in_window_handles_midnight_wraparound():
    assert _hour_in_window(23, (23, 1)) is True
    assert _hour_in_window(0, (23, 1)) is True
    assert _hour_in_window(12, (23, 1)) is False


def test_learned_hour_window_derives_from_originally_consistent_evidence():
    records = [_voice_record("Acme Inc", "email Sarah standup notes", _iso(d, hour=19)) for d in (5, 4, 3)]
    window = _learned_hour_window(records)
    assert window is not None


def test_learned_hour_window_none_when_original_evidence_not_timing_consistent():
    records = [_voice_record("Acme Inc", "email Sarah standup notes", _iso(d, hour=h)) for d, h in [(5, 6), (4, 12), (3, 20)]]
    assert _learned_hour_window(records) is None


def test_name_and_timing_fallback_matches_name_within_learned_window():
    candidates = [_voice_record("Acme Inc", "hey sarah, standup notes are up", _iso(1, hour=19, minute=15))]
    matches = _name_and_timing_fallback("sarah", (19, 21), candidates)
    assert len(matches) == 1


def test_name_and_timing_fallback_excludes_unrelated_mention_outside_learned_window():
    """The false-positive guard: an unrelated mention of the recipient's name
    OUTSIDE the pattern's learned hour-band must not be pulled in."""
    candidates = [_voice_record("Acme Inc", "sarah asked about the office lease renewal", _iso(1, hour=11))]
    matches = _name_and_timing_fallback("sarah", (19, 21), candidates)
    assert matches == []


def test_name_and_timing_fallback_returns_nothing_without_a_learned_window():
    candidates = [_voice_record("Acme Inc", "hey sarah, standup notes are up", _iso(1, hour=19))]
    assert _name_and_timing_fallback("sarah", None, candidates) == []


def test_gather_supporting_records_picks_up_casual_new_occurrence_within_hour_band(tmp_path):
    """The actual gap found by live verification: a genuine new (non-
    correction) occurrence in a casual, verb-less register must now be
    picked up via the name+timing fallback."""
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    for d in (5, 4, 3):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(d, hour=19)))
    original_records = read_records("Acme Inc", path=path)
    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in original_records],
    )

    # No gating verb, but same recipient name, within the learned 7pm-ish band.
    writer.write(_voice_record("Acme Inc", "hey sarah, standup notes are up, finished the migration early", _iso(1, hour=19, minute=10)))

    gathered = _gather_supporting_records(spec, "Acme Inc", path=path)
    assert len(gathered) == 4


def test_gather_supporting_records_excludes_unrelated_mention_outside_hour_band(tmp_path):
    """The false-positive guard integrated end-to-end: an unrelated record
    mentioning "sarah" at 11am (outside the learned ~7pm band) must NOT be
    pulled into this spec's supporting set."""
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    for d in (5, 4, 3):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(d, hour=19)))
    original_records = read_records("Acme Inc", path=path)
    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in original_records],
    )

    writer.write(_voice_record("Acme Inc", "sarah asked about the office lease renewal", _iso(1, hour=11)))

    gathered = _gather_supporting_records(spec, "Acme Inc", path=path)
    assert len(gathered) == 3  # unrelated 11am mention excluded
    assert all("lease" not in r.decision_text for r in gathered)


# --- generate_draft -----------------------------------------------------------


def test_generate_draft_produces_pending_review_attempt(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    for _ in range(5):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes"))
    records = read_records("Acme Inc", path=path)

    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in records],
    )
    client = _fake_client({"draft_text": "email Sarah the daily standup notes"})

    attempt = generate_draft(spec, "Acme Inc", client=client, path=path)

    assert attempt.status == "pending_review"
    assert attempt.spec_id == spec.spec_id
    assert attempt.entity_id == "Acme Inc"
    assert set(attempt.based_on_record_ids) == {r.record_id for r in records}
    assert "email Sarah the daily standup notes" in attempt.generated_text
    assert "Early days" not in attempt.generated_text  # 5 >= default threshold of 3


def test_generate_draft_flags_thin_evidence_explicitly(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes"))
    records = read_records("Acme Inc", path=path)

    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in records],
    )
    client = _fake_client({"draft_text": "email Sarah the daily standup notes"})

    attempt = generate_draft(spec, "Acme Inc", client=client, path=path, min_occurrences_for_confidence=3)

    assert "Early days" in attempt.generated_text
    assert "rough first attempt" in attempt.generated_text


def test_generate_draft_tags_correction_examples_explicitly_in_the_prompt(tmp_path):
    """The fix for the position-dependence bug found by live verification:
    the prompt must explicitly label which example is a stated correction,
    not rely on the model inferring it from list position."""
    entity_path = tmp_path / "entity_memory.jsonl"
    attempts_path = tmp_path / "draft_attempts.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)
    for d in (5, 4, 3):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(d, hour=19)))
    original_records = read_records("Acme Inc", path=entity_path)

    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in original_records],
    )

    correction_record = _voice_record("Acme Inc", "hey sarah, standup notes attached", _iso(2, hour=19))
    writer.write(correction_record)
    correction_record_id = read_records("Acme Inc", path=entity_path)[-1].record_id

    fake_attempt = DraftAttempt(
        attempt_id="a1", spec_id=spec.spec_id, entity_id="Acme Inc",
        generated_text="email Sarah the daily standup notes", based_on_record_ids=[],
        timestamp=_iso(2, hour=19), status="corrected",
        correction_text="hey sarah, standup notes attached", correction_record_id=correction_record_id,
    )
    from intent_engine.core.draft_generator import _append_draft_attempt
    _append_draft_attempt(fake_attempt, path=attempts_path)

    # A LATER plain occurrence, after the correction -- must NOT be tagged.
    writer.write(_voice_record("Acme Inc", "sarah - notes are up, thanks", _iso(1, hour=19)))

    client = _fake_client({"draft_text": "whatever"})
    generate_draft(spec, "Acme Inc", client=client, path=entity_path, attempts_path=attempts_path)

    user_message = client.call_tool.call_args.kwargs["user_message"]
    assert "CORRECTED STYLE" in user_message
    assert "hey sarah, standup notes attached" in user_message
    correction_line = next(line for line in user_message.splitlines() if "hey sarah, standup notes attached" in line)
    assert "CORRECTED STYLE" in correction_line
    plain_line = next(line for line in user_message.splitlines() if "notes are up, thanks" in line)
    assert "CORRECTED STYLE" not in plain_line
    assert "Past occurrence" in plain_line


# --- classify_draft_reply / process_draft_reply -----------------------------


def test_classify_draft_reply_approval():
    client = _fake_client({"classification": "approval", "correction_text": ""})
    classification, correction = classify_draft_reply("draft text", "looks good", client=client)
    assert classification == "approval"
    assert correction == ""


def test_classify_draft_reply_correction():
    client = _fake_client({"classification": "correction", "correction_text": "just tell sarah standup's done"})
    classification, correction = classify_draft_reply(
        "email Sarah the daily standup notes", "make it shorter, just say standup's done", client=client
    )
    assert classification == "correction"
    assert correction == "just tell sarah standup's done"


def test_process_draft_reply_approval_records_no_phantom_correction(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    attempts_path = tmp_path / "draft_attempts.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)
    writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes"))

    attempt = DraftAttempt(
        attempt_id="a1",
        spec_id="s1",
        entity_id="Acme Inc",
        generated_text="email Sarah the daily standup notes",
        based_on_record_ids=[],
        timestamp="2026-01-01T00:00:00+00:00",
        status="pending_review",
    )
    from intent_engine.core.draft_generator import _append_draft_attempt

    _append_draft_attempt(attempt, path=attempts_path)

    client = _fake_client({"classification": "approval", "correction_text": ""})
    updated = process_draft_reply(
        "a1", "Acme Inc", "looks good", client=client, attempts_path=attempts_path, entity_memory_path=entity_path
    )

    assert updated.status == "approved_as_is"
    assert updated.correction_text is None
    # No new entity_memory record should have been written for an approval.
    assert len(read_records("Acme Inc", path=entity_path)) == 1


def test_process_draft_reply_correction_persists_correction_text_and_new_entity_memory_record(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    attempts_path = tmp_path / "draft_attempts.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)
    writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes"))

    attempt = DraftAttempt(
        attempt_id="a1",
        spec_id="s1",
        entity_id="Acme Inc",
        generated_text="email Sarah the daily standup notes",
        based_on_record_ids=[],
        timestamp="2026-01-01T00:00:00+00:00",
        status="pending_review",
    )
    from intent_engine.core.draft_generator import _append_draft_attempt

    _append_draft_attempt(attempt, path=attempts_path)

    client = _fake_client({"classification": "correction", "correction_text": "just tell sarah standup's done"})
    updated = process_draft_reply(
        "a1",
        "Acme Inc",
        "make it shorter",
        client=client,
        attempts_path=attempts_path,
        entity_memory_path=entity_path,
    )

    assert updated.status == "corrected"
    assert updated.correction_text == "just tell sarah standup's done"

    all_records = read_records("Acme Inc", path=entity_path)
    assert len(all_records) == 2
    assert any(r.decision_text == "just tell sarah standup's done" and r.source == "voice" for r in all_records)


def test_process_draft_reply_rejection_records_no_phantom_correction(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    attempts_path = tmp_path / "draft_attempts.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)
    writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes"))

    attempt = DraftAttempt(
        attempt_id="a1",
        spec_id="s1",
        entity_id="Acme Inc",
        generated_text="email Sarah the daily standup notes",
        based_on_record_ids=[],
        timestamp="2026-01-01T00:00:00+00:00",
        status="pending_review",
    )
    from intent_engine.core.draft_generator import _append_draft_attempt

    _append_draft_attempt(attempt, path=attempts_path)

    client = _fake_client({"classification": "rejection", "correction_text": ""})
    updated = process_draft_reply(
        "a1", "Acme Inc", "no, don't bother", client=client, attempts_path=attempts_path, entity_memory_path=entity_path
    )

    assert updated.status == "rejected"
    assert updated.correction_text is None
    assert len(read_records("Acme Inc", path=entity_path)) == 1


def test_process_draft_reply_raises_if_not_pending_review(tmp_path):
    attempts_path = tmp_path / "draft_attempts.jsonl"
    entity_path = tmp_path / "entity_memory.jsonl"

    attempt = DraftAttempt(
        attempt_id="a1",
        spec_id="s1",
        entity_id="Acme Inc",
        generated_text="email Sarah the daily standup notes",
        based_on_record_ids=[],
        timestamp="2026-01-01T00:00:00+00:00",
        status="approved_as_is",
    )
    from intent_engine.core.draft_generator import _append_draft_attempt

    _append_draft_attempt(attempt, path=attempts_path)

    client = _fake_client({"classification": "approval", "correction_text": ""})
    with pytest.raises(ValueError):
        process_draft_reply(
            "a1", "Acme Inc", "looks good", client=client, attempts_path=attempts_path, entity_memory_path=entity_path
        )


# --- Refinement loop proof (mocked LLM, real entity-memory plumbing) -------


def test_refinement_loop_next_draft_includes_correction_record(tmp_path):
    """PROVES (not just logs) that after a correction is recorded, the next
    generate_draft() call's based_on_record_ids includes the correction's
    resulting record -- the mechanical half of the refinement-loop
    requirement. Real text-quality movement is proven separately in the live
    verification script (needs a real LLM call to be meaningful)."""
    entity_path = tmp_path / "entity_memory.jsonl"
    attempts_path = tmp_path / "draft_attempts.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)
    for _ in range(5):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes, please find attached"))
    records = read_records("Acme Inc", path=entity_path)

    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in records],
    )

    draft_client = _fake_client({"draft_text": "email Sarah the daily standup notes, please find attached"})
    first_attempt = generate_draft(spec, "Acme Inc", client=draft_client, path=entity_path)
    from intent_engine.core.draft_generator import _append_draft_attempt

    _append_draft_attempt(first_attempt, path=attempts_path)

    correction_client = _fake_client({"classification": "correction", "correction_text": "email sarah standup notes"})
    process_draft_reply(
        first_attempt.attempt_id,
        "Acme Inc",
        "make it much shorter and less formal",
        client=correction_client,
        attempts_path=attempts_path,
        entity_memory_path=entity_path,
    )

    second_draft_client = _fake_client({"draft_text": "email sarah standup notes"})
    second_attempt = generate_draft(spec, "Acme Inc", client=second_draft_client, path=entity_path, attempts_path=attempts_path)

    assert len(second_attempt.based_on_record_ids) == 6  # original 5 + the correction record
    correction_records = read_records("Acme Inc", path=entity_path)
    correction_record_id = next(r.record_id for r in correction_records if r.decision_text == "email sarah standup notes")
    assert correction_record_id in second_attempt.based_on_record_ids


def test_refinement_loop_includes_correction_even_without_a_trigger_verb(tmp_path):
    """Regression test for a real gap found during live verification: a
    correction's own phrasing is often casual ("hey sarah, standup notes
    attached") and contains none of _extract_recipient's gating verbs, so a
    pure recipient re-scan silently drops it. correction_record_id tracking
    (via spec_id) must include it regardless."""
    entity_path = tmp_path / "entity_memory.jsonl"
    attempts_path = tmp_path / "draft_attempts.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)
    for _ in range(5):
        writer.write(_voice_record("Acme Inc", "please email Sarah the daily standup notes for her review"))
    records = read_records("Acme Inc", path=entity_path)

    spec = TaskAgentSpecStub(
        source_pattern_id="p1",
        trigger_hint="You send a similar message to Sarah.",
        supporting_record_ids=[r.record_id for r in records],
    )

    draft_client = _fake_client({"draft_text": "please email Sarah the daily standup notes for her review"})
    first_attempt = generate_draft(spec, "Acme Inc", client=draft_client, path=entity_path, attempts_path=attempts_path)
    from intent_engine.core.draft_generator import _append_draft_attempt

    _append_draft_attempt(first_attempt, path=attempts_path)

    # No trigger verb ("email"/"send"/"tell"/etc.) anywhere in this text --
    # _extract_recipient would return None for it.
    correction_client = _fake_client({"classification": "correction", "correction_text": "hey sarah, standup notes attached"})
    process_draft_reply(
        first_attempt.attempt_id,
        "Acme Inc",
        "way too formal, make it casual",
        client=correction_client,
        attempts_path=attempts_path,
        entity_memory_path=entity_path,
    )

    from intent_engine.core.pattern_watcher import _extract_recipient

    assert _extract_recipient("hey sarah, standup notes attached") is None  # confirms the heuristic really would miss it

    second_draft_client = _fake_client({"draft_text": "hey sarah, standup notes attached"})
    second_attempt = generate_draft(spec, "Acme Inc", client=second_draft_client, path=entity_path, attempts_path=attempts_path)

    correction_records = read_records("Acme Inc", path=entity_path)
    correction_record_id = next(r.record_id for r in correction_records if r.decision_text == "hey sarah, standup notes attached")
    assert correction_record_id in second_attempt.based_on_record_ids
    assert len(second_attempt.based_on_record_ids) == 6
