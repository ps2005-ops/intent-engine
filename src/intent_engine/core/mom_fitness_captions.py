"""Part 2 of the four-part domain queue: mom's fitness Instagram caption
generator. Reuses core/pattern_watcher.py's recurring-pattern machinery and
core/draft_generator.py's shadow-guess-and-correct loop EXACTLY as already
built -- no new mechanism, no schema change, no prompt change to either
module. generate_draft(), classify_draft_reply(), and process_draft_reply()
are called here completely unmodified.

The one genuinely new thing in this file is COLD-START SEEDING. The
existing recurring_message flow (detect_recurring_message_patterns() ->
generate_suggestion() -> accept_suggestion() -> generate_draft()) requires
~3+ real organic occurrences already sitting in entity memory before it can
detect anything -- there is no such history on day one for a brand-new
Instagram account. Rather than waiting weeks for organic history to
accumulate before the first real draft can be produced, this seeds THREE
example captions representing an explicit, STATED 3-pillar content
framework (authority/education, transformation/social-proof,
personal-story) directly into entity memory as the day-one supporting
evidence, then builds a TaskAgentSpecStub directly -- bypassing
DetectedPattern/PatternSuggestion entirely, since there is no organically
detected pattern to declare here; this is a stated, declared starting
point, not an observation of real repeated behavior. From that point
forward, generate_draft()/process_draft_reply() run exactly as they already
do for recurring_message: real corrections and real new captions refine
future drafts the same way, with no code path here able to tell the
difference between this spec and one accept_suggestion() produced.

PLACEHOLDER CONTENT, flagged explicitly, not glossed over: the 3 seed
captions below are generic placeholder text illustrating each pillar's
SHAPE (what an authority/education post looks like, structurally), not
real specifics about the actual business -- I don't have, and have not
fabricated, real details about this Instagram account's actual niche,
brand voice, or audience. Replace PILLAR_SEED_CAPTIONS with real example
captions in mom's own voice before this is used for anything beyond this
session's own real correction-cycle verification.

Recipient framing, a deliberate minimal PHRASING adaptation, not a
mechanism change: pattern_watcher._extract_recipient requires a
communication-verb + name/group match (e.g. "update X") to group records as
"the same recurring thing" -- unchanged here. Every seed caption's
decision_text is phrased "Update Instagram with today's caption: ..." so
_extract_recipient finds "instagram" as the recipient, grouping these
records the same way a recurring text message would group under a
person's name. The verb list (email/message/text/tell/let/shoot/ping/send/
give/update/fill/drop) doesn't include "post" -- "update" was chosen
because "update Instagram with ..." reads naturally, not because anything
about the extraction logic was changed to accommodate this domain.
"""

from pathlib import Path
from typing import List, Optional, Union

from .entity_memory import (
    DEFAULT_PATH,
    EntityMemoryRecord,
    EntityMemoryWriter,
    JsonlEntityMemoryWriter,
    read_records,
)
from .suggestion import TaskAgentSpecStub

ENTITY_ID = "Mom's Fitness Instagram"

# Explicit, stated cold-start baseline -- see module docstring. Content is a
# generic placeholder illustrating each pillar's SHAPE, not real business
# specifics. All three are phrased "Update Instagram with today's caption:"
# so pattern_watcher._extract_recipient groups them under "instagram".
PILLAR_SEED_CAPTIONS = {
    "authority_education": (
        "Update Instagram with today's caption: Did you know your body needs about 48 hours to fully "
        "recover muscle fibers after a strength session? That's why we alternate push/pull days in the "
        "program -- recovery IS training, not time off. Save this post for the next time you're tempted "
        "to skip a rest day. #fitnesstips #strengthtraining"
    ),
    "transformation_social_proof": (
        "Update Instagram with today's caption: 12 weeks ago she couldn't do a single unassisted push-up. "
        "Today? 3 sets of 8, full range of motion, no knees down. This is what consistent, unglamorous "
        "Tuesday-morning workouts add up to. So proud of this progress. #transformationtuesday #realresults"
    ),
    "personal_story": (
        "Update Instagram with today's caption: Not going to lie, today's workout almost didn't happen -- "
        "woke up sore, tired, and ready to skip it. Showed up anyway, and 20 minutes in I remembered why "
        "I always feel better after, never before. Some days motivation doesn't show up and you do the "
        "work anyway. That's the whole secret, honestly. #showupanyway"
    ),
}


def seed_cold_start_pillars(
    entity_id: str = ENTITY_ID,
    path: Union[str, Path] = DEFAULT_PATH,
    writer: Optional[EntityMemoryWriter] = None,
) -> List[EntityMemoryRecord]:
    """Writes the 3 pillar-seed captions to entity memory as real
    EntityMemoryRecords (source="voice", same as any other real occurrence)
    -- this is what gives generate_draft() something concrete to imitate on
    day one, without changing generate_draft() itself at all. Not
    idempotent by itself (calling it twice writes 6 records, not 3) --
    start_mom_fitness_captions() is the safe, checked entrypoint; call this
    directly only if you specifically want to (re-)seed."""
    writer = writer or JsonlEntityMemoryWriter(path=path)
    records = []
    for text in PILLAR_SEED_CAPTIONS.values():
        record = EntityMemoryRecord(entity_id=entity_id, source="voice", decision_text=text, goals=[], constraints=[])
        writer.write(record)
        records.append(record)
    return records


def build_cold_start_spec(entity_id: str, seed_records: List[EntityMemoryRecord]) -> TaskAgentSpecStub:
    """Builds a TaskAgentSpecStub directly, bypassing DetectedPattern/
    PatternSuggestion entirely -- there is no organically-detected pattern
    to declare here; this is a stated, declared starting point (the
    3-pillar framework), not an observation from real repeated behavior.
    Everything downstream (generate_draft, process_draft_reply) is
    unmodified and cannot tell the difference between this spec and one
    that came from a real accept_suggestion() call -- same
    TaskAgentSpecStub shape, same fields, same guarantees
    (action="draft_only", gated=True)."""
    return TaskAgentSpecStub(
        source_pattern_id=f"cold-start-3-pillar-seed:{entity_id}",
        trigger_hint=(
            "Recurring: write today's fitness Instagram caption for mom's account. Seeded day-one with an "
            "explicit 3-pillar content framework (authority/education, transformation/social-proof, "
            "personal-story) rather than waiting for organic history to accumulate -- see "
            "core/mom_fitness_captions.py's module docstring."
        ),
        supporting_record_ids=[r.record_id for r in seed_records],
    )


def start_mom_fitness_captions(
    entity_id: str = ENTITY_ID,
    path: Union[str, Path] = DEFAULT_PATH,
    writer: Optional[EntityMemoryWriter] = None,
) -> TaskAgentSpecStub:
    """One-shot cold-start entrypoint: seeds the 3 pillar captions ONLY if
    this entity has no voice-sourced entity-memory records yet (checked
    directly, so calling this more than once is safe and never duplicates
    seeds or overwrites real accumulated history), then returns a
    ready-to-draft TaskAgentSpecStub. Everything after this call uses
    generate_draft()/process_draft_reply() completely unmodified, exactly
    as recurring_message already does."""
    existing = [r for r in read_records(entity_id, path=path) if r.source == "voice"]
    seed_records = existing if existing else seed_cold_start_pillars(entity_id, path=path, writer=writer)
    return build_cold_start_spec(entity_id, seed_records)
