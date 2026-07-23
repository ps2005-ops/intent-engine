"""V2.0 learning acceptance — the wall between "a post did well" and
"we now believe X".

Only a human-accepted LearningCandidate becomes AcceptedLearning in the
append-only growth memory. The metric-gaming prohibitions live here and
are enforced, not advisory.
"""
from __future__ import annotations

from intent_engine.growth_studio.records import StudioError

CANDIDATE_REQUIRED = (
    "statement",            # the proposed learning
    "success_metric",       # predefined, from the experiment plan
    "baseline",             # what it is compared against
    "observation_window",   # {start, end}
    "sample_size",          # or evidence sufficiency statement
    "confounders",          # list, may be empty but must be considered
    "channel_context",      # which channel, which audience
    "confidence",           # qualitative band
    "counterevidence",      # what cuts against it (may be "none found")
)

MIN_SAMPLE = 2   # one post never proves a pattern


def validate_candidate(candidate: dict, *, experiment: dict) -> None:
    """Raises StudioError unless the candidate meets the acceptance bar."""
    missing = [f for f in CANDIDATE_REQUIRED if candidate.get(f) in (None, "")]
    if missing:
        raise StudioError(f"LearningCandidate missing: {missing}")

    # metric predefined and unchanged after results
    planned = experiment.get("success_metric")
    if candidate["success_metric"] != planned:
        raise StudioError(
            "metric gaming: the success metric "
            f"({candidate['success_metric']!r}) differs from the "
            f"predefined experiment metric ({planned!r}) — no changing "
            "the metric after seeing results")

    # impressions are not conversions
    if "impression" in str(candidate["success_metric"]).lower() and \
            "conver" in str(candidate["statement"]).lower():
        raise StudioError("metric gaming: impressions treated as conversions")

    # equal observation windows
    window = candidate["observation_window"]
    baseline_window = candidate.get("baseline_window")
    if isinstance(window, dict) and isinstance(baseline_window, dict):
        span = _span(window)
        base_span = _span(baseline_window)
        if span is not None and base_span is not None and span != base_span:
            raise StudioError(
                "metric gaming: unequal time windows compared silently "
                f"({span} days vs {base_span} days)")

    # sample sufficiency
    sample = candidate["sample_size"]
    if isinstance(sample, int) and sample < MIN_SAMPLE:
        raise StudioError(
            f"insufficient evidence: sample_size {sample} < {MIN_SAMPLE} — "
            "one observation never proves a pattern")

    # no winner from unavailable data
    if candidate.get("data_availability") == "UNAVAILABLE":
        raise StudioError("no winner may be declared from unavailable data")

    # no causality from correlation alone
    statement = str(candidate["statement"]).lower()
    causal_markers = ("caused", "because of", "due to", "drove", "led to")
    if any(m in statement for m in causal_markers) and \
            not experiment.get("randomized"):
        raise StudioError(
            "no causal claim from correlation alone: the statement asserts "
            "causality but the experiment was not a randomized design")

    # attribution requires an experiment design
    if not experiment.get("experiment_id"):
        raise StudioError(
            "no attributing changes to a campaign without an experiment "
            "design (missing experiment_id)")


def _span(window: dict):
    try:
        from datetime import date
        start = date.fromisoformat(str(window["start"])[:10])
        end = date.fromisoformat(str(window["end"])[:10])
        return (end - start).days
    except (KeyError, ValueError):
        return None
