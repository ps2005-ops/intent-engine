"""Pattern-Watcher: Stage D-adjacent proactive-discovery over entity memory.
Reads across MANY existing entity_memory records looking for repetition --
nothing in entity_memory.py is modified, this is a new consumer, not a new
writer.

Every DetectedPattern is an observation, not an assertion. confidence exists
specifically so this stays honest: it's derived from actual occurrence_count
and measured consistency, never asserted independent of the data, same
discipline as scale_efficiency/leverage_type/demand_durability elsewhere in
this codebase. supporting_record_ids makes every pattern auditable against the
real records that grounded it -- not a black-box claim about "how you behave."

This pass implements ONLY "recurring_message" detection. "recurring_action"
and "recurring_check" are named in the enum now, unimplemented, so the schema
doesn't need to change when they're built -- same reserved-field discipline as
EntityMemoryRecord.outcome.

Known, deliberate limitations (flagged, not hidden):
- Recipient extraction is a conservative regex heuristic requiring an
  explicit communication verb (email/message/text/tell), not real NLP/NER.
  It will MISS genuine recurring messages phrased without one of those verbs
  (e.g. "let Sarah know...", "ping the team...") -- a real gap, not a
  guarantee of completeness, chosen to avoid false positives like "remind me
  TO buy milk" matching on a bare "to".
- Timing analysis operates on EntityMemoryRecord.timestamp, which is stored
  in UTC (core/entity_memory.py's _current_timestamp()). "Evenings around
  7-8pm" is inherently a LOCAL-time concept; nothing in this codebase
  captures the person's timezone anywhere, so a pattern's stated time window
  is genuinely in UTC, not the person's real local evening, unless they
  happen to be in UTC. Labeled explicitly in every description rather than
  silently presented as local time.
- Content-similarity thresholds and the timing-consistency fraction below are
  reasoned starting points, not empirically calibrated against a large real
  corpus -- unlike retrieval.py's _STRONG_MATCH_THRESHOLD, which WAS
  calibrated by eyeballing real matches. Flagged as an open, unvalidated
  choice, not presented as settled.
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union
from uuid import uuid4

from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from .entity_memory import DEFAULT_PATH, read_records

PatternType = Literal["recurring_message", "recurring_action", "recurring_check"]
Confidence = Literal["low", "medium", "high"]


class DetectedPattern(BaseModel):
    pattern_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str
    pattern_type: PatternType
    description: str
    occurrence_count: int
    first_seen: str  # ISO8601, earliest supporting record's timestamp
    last_seen: str  # ISO8601, most recent supporting record's timestamp
    confidence: Confidence
    supporting_record_ids: List[str]  # real EntityMemoryRecord.record_id values -- auditable, not a black-box claim


# --- Recipient extraction (heuristic, see module docstring for limitations) --
#
# REVISED after measuring a real 83% miss rate on the original narrow verb
# list ("email"/"message"/"text"/"tell") against realistic phrasing variety
# for the SAME recurring action ("let Sarah know...", "shoot Sarah a note...",
# "ping Sarah...", "send Sarah...", "give Sarah...", "update Sarah on...",
# "fill Sarah in...", "drop Sarah a line..." -- none matched the old list).
#
# A capitalization-based name-detection alternative was tried and measured
# first, NOT chosen: it closed the miss-rate gap (0% miss on the same
# corpus) but introduced two new, real problems, both measured, not assumed:
# (1) 100% miss rate the moment names aren't capitalized (a lowercase-only
# speech-to-text transcript would defeat it entirely), and (2) NEW false
# positives on pure noise data (4 spurious patterns detected -- "Thursday",
# "March", "Alex", "Api" -- from ordinary capitalized words recurring in
# unrelated sentences, since nothing gated candidacy on an actual
# communication-like verb anymore).
#
# Kept instead: broaden the verb list (fixes the real miss-rate problem) while
# keeping verb-gating (avoids the false-positive regression) and case
# insensitivity (avoids the capitalization dependency). A stopword exclusion
# guards the new, broader verbs' own false-positive risk: "update"/"send"/
# "give"/"drop" are common in everyday phrases NOT about messaging a person
# ("update the roadmap", "send the report to accounting") -- without excluding
# generic objects like "the"/"a"/"it", the broadened verb list would capture
# those as fake recipients. Measured against all three corpora (see
# PROGRESS.md for the real numbers): this closes the phrasing-variety gap
# without reintroducing false positives on noise or depending on
# capitalization -- a materially better result than the name-detection
# alternative on all three axes measured.
_RECIPIENT_TRIGGER = re.compile(
    r"\b(?:email|message|text|tell|let|shoot|ping|send|give|update|fill|drop)\s+(the team|the group|[a-zA-Z][\w'-]*)",
    re.IGNORECASE,
)
_NON_RECIPIENT_WORDS = {
    "the", "a", "an", "it", "this", "that", "me", "us", "them", "him", "her", "everyone", "someone",
    "out", "in", "up", "on", "off", "over", "back", "down",  # common phrasal-verb particles, e.g. "fill OUT the form"
}


def _extract_recipient(decision_text: str) -> Optional[str]:
    match = _RECIPIENT_TRIGGER.search(decision_text)
    if not match:
        return None
    candidate = match.group(1).strip().lower()
    if candidate in _NON_RECIPIENT_WORDS:
        return None
    return candidate


# --- Content similarity: TF-IDF + cosine, reusing retrieval.py's approach ---
# (already a dependency via scikit-learn -- no new ML dependency introduced) --

_CONTENT_SIMILARITY_THRESHOLD = 0.25  # reasoned starting point, NOT empirically
# validated against a large real corpus -- see module docstring.


def _content_similarity_consistent(texts: List[str]) -> Tuple[bool, float]:
    if len(texts) < 2:
        return False, 0.0
    vectorizer = TfidfVectorizer()
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # e.g. every text reduces to pure stopwords/empty after tokenization --
        # can't compute a meaningful similarity; treat as inconsistent rather
        # than crashing the whole detection pass.
        return False, 0.0
    sims = cosine_similarity(matrix)
    n = len(texts)
    pairwise = [sims[i][j] for i in range(n) for j in range(i + 1, n)]
    avg_similarity = float(sum(pairwise) / len(pairwise)) if pairwise else 0.0
    return bool(avg_similarity >= _CONTENT_SIMILARITY_THRESHOLD), avg_similarity


# --- Timing consistency: hour-of-day clustering, UTC (see module docstring) -

_TIMING_BAND_HOURS = 2  # "within a 2-hour band"
_TIMING_CONSISTENCY_FRACTION = 0.7  # "most days" -- reasoned choice, not validated


def _timing_consistent(hours: List[int]) -> Tuple[bool, Optional[Tuple[int, int]]]:
    """Finds the 2-hour band (wraparound-safe, e.g. 23:00-01:00) covering the
    most occurrences; consistent if that band covers >= 70% of them."""
    if not hours:
        return False, None
    best_coverage = 0
    best_window = None
    for start in range(24):
        window = {(start + i) % 24 for i in range(_TIMING_BAND_HOURS + 1)}
        coverage = sum(1 for h in hours if h in window)
        if coverage > best_coverage:
            best_coverage = coverage
            best_window = (start, (start + _TIMING_BAND_HOURS) % 24)
    fraction = best_coverage / len(hours)
    return fraction >= _TIMING_CONSISTENCY_FRACTION, best_window


def _format_hour_12h(hour: int) -> str:
    period = "am" if hour < 12 else "pm"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}{period}"


def _calibrate_confidence(occurrence_count: int, content_consistent: bool, timing_consistent: bool) -> Confidence:
    """MUST default to low unless genuinely earned -- same "don't fabricate
    confidence" requirement as leverage_type/demand_durability, applied to
    pattern detection instead of extraction. Bands per spec: low = 2-3
    occurrences (or anything short of full consistency); medium = 4-6 with
    consistent timing AND content; high = 7+ with consistent timing AND
    content (the third "same recipient signal" dimension is already
    guaranteed by grouping records under one extracted recipient before this
    function ever runs, so it isn't a separate check here)."""
    if occurrence_count >= 7 and content_consistent and timing_consistent:
        return "high"
    if occurrence_count >= 4 and content_consistent and timing_consistent:
        return "medium"
    return "low"


def _describe_pattern(
    recipient: str, occurrence_count: int, hour_window: Optional[Tuple[int, int]], avg_similarity: float
) -> str:
    recipient_label = recipient if recipient in ("the team", "the group") else recipient.title()
    if hour_window:
        time_phrase = f"around {_format_hour_12h(hour_window[0])}-{_format_hour_12h(hour_window[1])} (UTC)"
    else:
        time_phrase = "at no consistent time of day"
    return (
        f"You send a similar message to {recipient_label} on {occurrence_count} separate days, "
        f"typically {time_phrase}. Wording similarity across these instances: {avg_similarity:.0%}."
    )


def detect_recurring_message_patterns(
    entity_id: str,
    min_occurrences: int = 3,
    lookback_days: int = 30,
    path: Union[str, Path] = DEFAULT_PATH,
) -> List[DetectedPattern]:
    """Reads entity_memory.read_records(entity_id), looks for voice-sourced
    records with similar decision_text (recurring recipient signal + content
    similarity) occurring at similar times of day, across at least
    min_occurrences DISTINCT DAYS within lookback_days. confidence is always
    computed from the actual occurrence_count/consistency of the real
    supporting records -- never asserted independent of them.
    """
    records = read_records(entity_id, path=path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    groups: dict = defaultdict(list)
    for record in records:
        if record.source != "voice":
            continue
        try:
            ts = datetime.fromisoformat(record.timestamp)
        except ValueError:
            continue
        if ts < cutoff:
            continue
        recipient = _extract_recipient(record.decision_text)
        if recipient is None:
            continue
        groups[recipient].append((record, ts))

    patterns: List[DetectedPattern] = []
    for recipient, entries in groups.items():
        # Distinct calendar days only -- multiple utterances to the same
        # recipient on the SAME day shouldn't inflate occurrence_count; the
        # pattern being detected is "recurs across days," not "was said more
        # than once." Keep the earliest record per day as that day's
        # representative.
        by_day: dict = defaultdict(list)
        for record, ts in entries:
            by_day[ts.date()].append((record, ts))

        distinct_days = sorted(by_day.keys())
        if len(distinct_days) < min_occurrences:
            continue

        representative = [min(by_day[day], key=lambda pair: pair[1])[0] for day in distinct_days]

        texts = [r.decision_text for r in representative]
        content_consistent, avg_similarity = _content_similarity_consistent(texts)

        hours = [datetime.fromisoformat(r.timestamp).hour for r in representative]
        timing_consistent, hour_window = _timing_consistent(hours)

        occurrence_count = len(distinct_days)
        confidence = _calibrate_confidence(occurrence_count, content_consistent, timing_consistent)

        timestamps = [r.timestamp for r in representative]
        patterns.append(
            DetectedPattern(
                entity_id=entity_id,
                pattern_type="recurring_message",
                description=_describe_pattern(recipient, occurrence_count, hour_window, avg_similarity),
                occurrence_count=occurrence_count,
                first_seen=min(timestamps),
                last_seen=max(timestamps),
                confidence=confidence,
                supporting_record_ids=[r.record_id for r in representative],
            )
        )

    return patterns
