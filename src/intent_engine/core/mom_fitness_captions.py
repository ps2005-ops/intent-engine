"""Part 2 of the four-part domain queue: mom's fitness Instagram caption
generator. Reuses core/pattern_watcher.py's recurring-pattern machinery and
core/draft_generator.py's shadow-guess-and-correct loop as already built --
no new mechanism, no schema change, no prompt change to either module, and
no change at all to the recipient verb-gate (pattern_watcher._extract_recipient).
classify_draft_reply() and process_draft_reply() are called here completely
unmodified. generate_draft() gained two small, additive, backward-compatible
optional parameters (example_text_transform/output_text_transform, both
default None/no-op -- every other caller, including recurring_message, is
unaffected) specifically to fix a real bug this domain's own live
verification found: see PREFIX-STRIP FIX below.

PREFIX-STRIP FIX (found by real, live verification, not theorized): the
recipient-framing phrasing adaptation (see below) means every seed/example
caption's STORED decision_text starts with "Update Instagram with today's
caption:" -- scaffolding needed only so _extract_recipient can find
"instagram" as the recipient. A live generate -> correct -> regenerate
cycle showed this literal prefix leaking into 2 of 3 real generated
captions verbatim, because it appears often enough across gathered
examples to register as its own "recurring content element" the model then
imitates -- exactly the kind of scaffolding-as-content leak the
prior-lot-narrative-anchoring fix (core/scrap_estimate.py) and the
label/baseline information-hiding fix (same file) were built to prevent,
just discovered in a new domain. Fixed the same way: information hiding
applied to the seed scaffolding -- generate_caption_draft() (below) strips
the prefix from every example BEFORE it enters the prompt
(example_text_transform) and from the model's own output before display
(output_text_transform), while _gather_supporting_records/
_correction_record_ids inside the UNMODIFIED generate_draft() still match
against the RAW stored text, prefix included -- the verb-gate itself is
untouched, per the explicit instruction that this is the data-foundation
pass's question, not this fix's.

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

from .draft_generator import DEFAULT_DRAFT_ATTEMPTS_PATH, DraftAttempt, generate_draft
from .entity_memory import (
    DEFAULT_PATH,
    EntityMemoryRecord,
    EntityMemoryWriter,
    SqliteEntityMemoryWriter,
    read_records,
)
from .llm_client import LLMClient
from .suggestion import TaskAgentSpecStub

ENTITY_ID = "Mom's Fitness Instagram"

# Scaffolding needed ONLY so pattern_watcher._extract_recipient can find
# "instagram" as the recipient when STORING a record -- never meant to be
# seen by the model or a real person. See PREFIX-STRIP FIX above.
_SCAFFOLD_PREFIX = "Update Instagram with today's caption:"

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
    writer = writer or SqliteEntityMemoryWriter(path=path)
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


def _strip_scaffold_prefix(text: str) -> str:
    """Strips the "Update Instagram with today's caption:" scaffolding
    prefix if present -- case-insensitive match, any immediately-following
    whitespace also removed. A real caption (from the model, or a real
    person editing one) should never contain this phrase; it exists only
    so the STORED record satisfies the recipient verb-gate. A no-op on any
    text that doesn't start with it, so this is safe to apply broadly
    (e.g. to model output that already omits the prefix)."""
    stripped = text.strip()
    if stripped.lower().startswith(_SCAFFOLD_PREFIX.lower()):
        return stripped[len(_SCAFFOLD_PREFIX):].strip()
    return stripped


def generate_caption_draft(
    spec: TaskAgentSpecStub,
    entity_id: str,
    client: Optional[LLMClient] = None,
    path: Union[str, Path] = DEFAULT_PATH,
    attempts_path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH,
    min_occurrences_for_confidence: int = 3,
) -> DraftAttempt:
    """Thin wrapper over the UNMODIFIED generate_draft() -- reuses it
    exactly, only supplying this domain's scaffolding-prefix strip via the
    two optional transform hooks (see PREFIX-STRIP FIX in the module
    docstring). Gathering/matching (the recipient verb-gate included)
    still runs inside generate_draft() against the RAW stored text,
    completely untouched by either transform."""
    return generate_draft(
        spec, entity_id, client=client, path=path, attempts_path=attempts_path,
        min_occurrences_for_confidence=min_occurrences_for_confidence,
        example_text_transform=_strip_scaffold_prefix,
        output_text_transform=_strip_scaffold_prefix,
    )
