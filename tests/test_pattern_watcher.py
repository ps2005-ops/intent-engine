from datetime import datetime, timedelta, timezone

from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter
from intent_engine.core.pattern_watcher import (
    _calibrate_confidence,
    _content_similarity_consistent,
    _extract_recipient,
    _timing_consistent,
    detect_recurring_message_patterns,
)


def _voice_record(entity_id, decision_text, timestamp):
    return EntityMemoryRecord(
        entity_id=entity_id,
        source="voice",
        decision_text=decision_text,
        goals=[],
        constraints=[],
        timestamp=timestamp,
        salience="low",
    )


def _iso(days_ago, hour, minute=0):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


# --- Recipient extraction -----------------------------------------------


def test_extract_recipient_requires_explicit_communication_verb():
    assert _extract_recipient("email Sarah about the deck") == "sarah"
    assert _extract_recipient("message Sarah the update") == "sarah"
    assert _extract_recipient("text the team the daily numbers") == "the team"
    assert _extract_recipient("tell the group standup notes") == "the group"


def test_extract_recipient_does_not_false_positive_on_bare_to():
    """The whole point of requiring an explicit verb: "remind me to buy milk"
    must NOT extract "buy" as a fake recipient."""
    assert _extract_recipient("remind me to buy milk") is None
    assert _extract_recipient("I need to follow up with Sarah") is None


def test_extract_recipient_catches_realistic_phrasing_variety():
    """Regression test for the measured 83% miss rate on the original narrow
    verb list -- these phrasings must all now be caught, case-insensitively,
    without depending on capitalization."""
    assert _extract_recipient("let Sarah know the standup notes are ready") == "sarah"
    assert _extract_recipient("shoot sarah a note about today standup") == "sarah"
    assert _extract_recipient("ping Sarah about the daily update") == "sarah"
    assert _extract_recipient("send sarah the standup summary") == "sarah"
    assert _extract_recipient("give Sarah the daily update") == "sarah"
    assert _extract_recipient("update sarah on today standup") == "sarah"
    assert _extract_recipient("fill Sarah in on the standup") == "sarah"
    assert _extract_recipient("drop sarah a line about the standup notes") == "sarah"


def test_extract_recipient_does_not_false_positive_on_everyday_phrasal_verbs():
    """The broadened verb list ("send"/"give"/"update"/"drop"/"fill" etc.) is
    common in ordinary phrases that have nothing to do with messaging a
    person -- these must not extract a fake recipient."""
    assert _extract_recipient("update the roadmap") is None
    assert _extract_recipient("send the report to accounting") is None
    assert _extract_recipient("drop the meeting from my calendar") is None
    assert _extract_recipient("give the presentation a look") is None
    assert _extract_recipient("fill out the expense report") is None


def test_extract_recipient_does_not_false_positive_on_recurring_capitalized_nouns():
    """A capitalized word (a month, a day, a topic) recurring across
    unrelated noise utterances must never be mistaken for a recipient --
    this must stay gated on an actual communication-like verb."""
    assert _extract_recipient("block off Thursday afternoon for the board meeting") is None
    assert _extract_recipient("note that the vendor contract renews in March") is None
    assert _extract_recipient("look up Alex contact information") is None


# --- Content similarity ---------------------------------------------------


def test_content_similarity_consistent_for_near_identical_wording():
    texts = [
        "email Sarah the daily standup notes",
        "email Sarah the standup notes for today",
        "email Sarah today's standup notes",
    ]
    consistent, score = _content_similarity_consistent(texts)
    assert consistent is True
    assert score > 0.25


def test_content_similarity_not_consistent_for_unrelated_texts():
    texts = [
        "email Sarah the daily standup notes",
        "message Sarah about the vacation schedule next month",
        "text Sarah asking if she saw the game last night",
    ]
    consistent, score = _content_similarity_consistent(texts)
    assert consistent is False
    assert score < 0.25


# --- Timing consistency ---------------------------------------------------


def test_timing_consistent_within_2_hour_band():
    consistent, window = _timing_consistent([19, 19, 20, 19, 20])
    assert consistent is True
    assert window is not None


def test_timing_not_consistent_when_scattered():
    consistent, _ = _timing_consistent([6, 12, 19, 2, 15])
    assert consistent is False


def test_timing_consistent_handles_midnight_wraparound():
    consistent, window = _timing_consistent([23, 0, 23, 0, 23])
    assert consistent is True


# --- Confidence calibration -------------------------------------------------


def test_confidence_defaults_to_low_unless_genuinely_earned():
    assert _calibrate_confidence(2, content_consistent=True, timing_consistent=True) == "low"
    assert _calibrate_confidence(3, content_consistent=True, timing_consistent=True) == "low"
    assert _calibrate_confidence(5, content_consistent=False, timing_consistent=True) == "low"
    assert _calibrate_confidence(10, content_consistent=False, timing_consistent=False) == "low"


def test_confidence_medium_requires_4_to_6_and_consistency():
    assert _calibrate_confidence(4, content_consistent=True, timing_consistent=True) == "medium"
    assert _calibrate_confidence(6, content_consistent=True, timing_consistent=True) == "medium"


def test_confidence_high_requires_7_plus_and_consistency():
    assert _calibrate_confidence(7, content_consistent=True, timing_consistent=True) == "high"
    assert _calibrate_confidence(15, content_consistent=True, timing_consistent=True) == "high"
    # 7+ occurrences alone, without consistency, must NOT be high -- confidence
    # is earned from consistency, not just raw count.
    assert _calibrate_confidence(15, content_consistent=False, timing_consistent=True) != "high"


# --- End-to-end detection ---------------------------------------------------


def test_detect_recurring_message_pattern_positive_case(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    for days_ago in range(7, 0, -1):
        writer.write(
            _voice_record(
                "Acme Inc",
                f"email Sarah the daily standup notes, day {days_ago}",
                _iso(days_ago, hour=19, minute=(days_ago % 3) * 10),
            )
        )

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=3, lookback_days=30, path=path)

    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern.pattern_type == "recurring_message"
    assert pattern.occurrence_count == 7
    assert pattern.confidence == "high"
    assert "Sarah" in pattern.description
    assert len(pattern.supporting_record_ids) == 7

    # supporting_record_ids must trace back to REAL records for this entity.
    from intent_engine.core.entity_memory import read_records

    real_ids = {r.record_id for r in read_records("Acme Inc", path=path)}
    assert set(pattern.supporting_record_ids).issubset(real_ids)


def test_detect_recurring_message_pattern_low_confidence_with_two_occurrences(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    for days_ago in (2, 1):
        writer.write(
            _voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(days_ago, hour=19))
        )

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=2, lookback_days=30, path=path)

    assert len(patterns) == 1
    assert patterns[0].occurrence_count == 2
    assert patterns[0].confidence == "low"


def test_detect_recurring_message_pattern_negative_case_no_false_positive_on_noise(tmp_path):
    """Unrelated, non-recurring voice interactions must NOT produce a
    recurring_message pattern -- a real negative, not just a positive case."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    noise = [
        "remind me to buy milk",
        "block off Thursday afternoon for the board meeting",
        "what's the status on the Q3 roadmap",
        "note that the vendor contract renews in March",
        "reconsider our pricing strategy for enterprise customers",
    ]
    for i, text in enumerate(noise):
        writer.write(_voice_record("Acme Inc", text, _iso(days_ago=i + 1, hour=(i * 3) % 24)))

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=2, lookback_days=30, path=path)

    assert patterns == []


def test_detect_recurring_message_pattern_ignores_multiple_same_day_utterances(tmp_path):
    """Several utterances to the same recipient on the SAME day must count as
    ONE occurrence (one day), not inflate occurrence_count."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    # 3 utterances on the same day.
    for hour in (19, 20, 21):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(1, hour=hour)))
    # 1 utterance on a second day.
    writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(2, hour=19)))

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=2, lookback_days=30, path=path)

    assert len(patterns) == 1
    assert patterns[0].occurrence_count == 2  # 2 distinct days, not 4 utterances


def test_detect_recurring_message_pattern_respects_lookback_days(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    # All occurrences are 60+ days old -- outside a 30-day lookback window.
    for days_ago in (65, 62, 60):
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", _iso(days_ago, hour=19)))

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=2, lookback_days=30, path=path)

    assert patterns == []


def test_detect_recurring_message_pattern_only_considers_voice_records(tmp_path):
    """Simulator-sourced records must never contribute to voice-behavior
    pattern detection, even if their decision_text happens to match the
    recipient heuristic."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    for days_ago in (3, 2, 1):
        writer.write(
            EntityMemoryRecord(
                entity_id="Acme Inc",
                source="simulator",
                decision_text="email Sarah the daily standup notes",
                goals=[],
                constraints=[],
                timestamp=_iso(days_ago, hour=19),
                primary_priority="growth",
            )
        )

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=2, lookback_days=30, path=path)

    assert patterns == []


def test_detect_recurring_message_pattern_catches_realistic_phrasing_variety_end_to_end(tmp_path):
    """The same recurring action described 12 genuinely different ways (not
    tailored to a specific verb list), lowercased throughout -- must still be
    detected as ONE pattern, all instances caught. Regression test for the
    measured 83% miss rate this fix closed."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    phrasings = [
        "let sarah know the standup notes are ready",
        "shoot sarah a note about today standup",
        "ping sarah about the daily update",
        "send sarah the standup summary",
        "give sarah the daily update",
        "update sarah on today standup",
        "fill sarah in on the standup",
        "drop sarah a line about the standup notes",
        "email sarah the daily standup notes",
        "message sarah with today update",
        "tell sarah the standup notes are done",
        "text sarah the standup summary",
    ]
    for days_ago, text in zip(range(len(phrasings), 0, -1), phrasings):
        writer.write(_voice_record("Acme Inc", text, _iso(days_ago, hour=19)))

    patterns = detect_recurring_message_patterns("Acme Inc", min_occurrences=3, lookback_days=30, path=path)

    assert len(patterns) == 1
    assert patterns[0].occurrence_count == len(phrasings)  # every instance caught, none missed
