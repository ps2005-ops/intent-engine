"""Live end-to-end test of estimate_scrap_lot() against REAL scrap-metal
photos from the actual target user (tests/fixtures/scrap_metal/), not
synthetic Pillow renders. This distinction matters: rendered flat-color
shapes could never meaningfully test real visual grading (no real texture,
oxidation variation, or clutter) -- these real photos can.

Skipped automatically unless a minimal live Anthropic API call actually
succeeds, checked directly at collection time (credits were confirmed
exhausted as of this file's creation) -- same "skip cleanly so the main
suite stays green regardless of what this environment allows" discipline as
test_calendar_live.py / test_speech_to_text_live.py.

IMPORTANT, stated plainly, same standard as the checkpoint that authorized
this file: this test does NOT validate grading accuracy. Neither we nor the
model has independent ground truth for these lots' actual condition or
composition. What this DOES prove: the model produces coherent, honestly-
hedged, non-fabricated output on real material, and the entity-memory-backed
comparison_note logic behaves sensibly across a genuine sequential run of
real photos -- not that the grades themselves are correct.
"""

import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scrap_metal"
LOT_PHOTOS = [FIXTURES / f"scrap_lot_{i}.jpeg" for i in range(1, 10)]
NO_PRIOR_LOTS_MESSAGE = "No prior lots on record yet for this entity."
_YIELD_NOTE_SOURCES = ("okon recycling", "scrapmonster", "taylor's junkyard", "taylors junkyard")


def _credits_available():
    try:
        from intent_engine.core.llm_client import LLMClient

        client = LLMClient()
        client.call_tool(
            system="Reply with a single word.",
            user_message="Say hello.",
            tool_name="reply",
            tool_description="Record a one-word reply.",
            input_schema={"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]},
            max_tokens=64,  # must be >= the tool_use block's real overhead, not just the word itself --
            # a too-low value here previously caused a truncation RuntimeError that looked
            # exactly like a credit-exhaustion failure and skipped this test incorrectly.
        )
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _credits_available(),
    reason="Anthropic API credits unavailable (checked via a minimal live call) -- "
    "verify locally once credits exist. See PROGRESS.md's scrap-metal checkpoint.",
)


def test_real_sequential_photos_comparison_note_behaves_correctly(tmp_path):
    from intent_engine.core.scrap_estimate import estimate_scrap_lot

    entity_id = "Live Scrap Test Entity"
    entity_memory_path = tmp_path / "entity_memory.jsonl"

    estimates = [
        estimate_scrap_lot(photo, entity_id, path=entity_memory_path) for photo in LOT_PHOTOS
    ]

    # First photo: no prior lots exist yet -- must be the deterministic message,
    # never a fabricated comparison.
    assert estimates[0].comparison_note == NO_PRIOR_LOTS_MESSAGE

    # By the 3rd/4th photo, comparison_note must reference something real from
    # THIS run, not the "no prior lots" placeholder -- proving the
    # entity-memory-backed comparison logic actually engaged with genuine
    # sequential history, not just repeating the cold-start case.
    for estimate in estimates[2:]:
        assert estimate.comparison_note is not None
        assert estimate.comparison_note != NO_PRIOR_LOTS_MESSAGE

    # No estimate anywhere should ever state a material purity/alloy
    # percentage claim -- the honesty ceiling this domain is built around.
    # Deliberately NOT a bare word-ban: a first real run showed the model
    # using "composition" in a completely benign sense ("similar composition
    # of automotive electrical components," meaning "mixture of part types"),
    # and a bare percentage alone can legitimately describe a visual
    # proportion ("most units show..."), not a material claim. The real
    # violation is a percentage figure tied to a purity/alloy/material claim
    # specifically -- that's what this regex targets, not ordinary language.
    _composition_violation = re.compile(
        r"\d+(\.\d+)?\s*%\s*(pure|purity|copper|steel|aluminum|iron|zinc|brass|alloy)"
        r"|(purity|alloy grade)\s+of\s+\d+(\.\d+)?\s*%",
        re.IGNORECASE,
    )
    for estimate in estimates:
        combined_text = f"{estimate.reasoning} {estimate.comparison_note or ''}"
        match = _composition_violation.search(combined_text)
        assert match is None, f"Possible purity/alloy percentage claim found: {combined_text!r}"

    # category_typical_yield_note is the one deliberate exception -- IF the
    # model populates it, it must cite one of the given real sources, never
    # present a bare figure as if self-derived.
    for estimate in estimates:
        if estimate.category_typical_yield_note:
            lowered = estimate.category_typical_yield_note.lower()
            assert any(source in lowered for source in _YIELD_NOTE_SOURCES), (
                f"category_typical_yield_note populated without citing a source: {estimate.category_typical_yield_note!r}"
            )

    # is_scrap_metal_lot=False must never carry a computed scrap_score --
    # there's no scrap grade to score for something that isn't scrap.
    for estimate in estimates:
        if not estimate.is_scrap_metal_lot:
            assert estimate.scrap_score is None
