"""Part 3 of the four-part domain queue: brother's music Instagram caption
generator. Reuses core/pattern_watcher.py's recurring-pattern machinery and
core/draft_generator.py's shadow-guess-and-correct loop exactly as already
built -- no new mechanism, no schema change, no prompt change to either
module, no change to the recipient verb-gate
(pattern_watcher._extract_recipient). classify_draft_reply() and
process_draft_reply() are called here completely unmodified.

This module is a near-exact structural copy of core/mom_fitness_captions.py
(Part 2), with that part's two real, live-verified lessons applied from day
one instead of discovered after the fact:

LESSON 1 (prefix-strip from day one): Part 2 found, only after a live
generate cycle, that the recipient-framing scaffolding prefix ("Update
Instagram with today's caption:") leaked into real generated captions,
because it recurs across enough gathered examples to register as its own
"recurring content element." generate_draft() already has the
example_text_transform/output_text_transform hooks Part 2 added to fix
this (both additive, both default None/no-op, every other caller
including recurring_message and mom_fitness_captions is unaffected) --
this module wires both hooks up from the start, in
generate_caption_draft() below, rather than shipping the leak first.

LESSON 2 (stated, not rediscovered): Part 2's live cross-pillar test found
that a cold-start spec's content does not rotate across pillars after a
correction, because each of the 3 seed pillars is a distinct one-off
example, never repeated 3+ times -- the "recurring content elements (3+)"
mechanism inside generate_draft()'s own prompt has nothing to grab onto
across a 3-pillar, 1-example-each seed. This is a real, structural
property of cold-start seeding as designed (not a defect in
draft_generator.py, and not something this module works around) -- stated
here up front so it's an expected property from day one, not a surprise
found by a live test. It resolves itself naturally once real organic
history accumulates and any single detail repeats 3+ times, same as any
other recurring_message pattern.

The one genuinely new thing in this file, same as Part 2, is COLD-START
SEEDING: PILLAR_SEED_CAPTIONS declares 3 pillars with a stated,
WEIGHTED 40/30/20 intended content mix (original music/performance is the
primary pillar; behind-the-scenes/process second; personal-connection
third) -- the weighting is a stated intent for the account's long-term
content strategy, recorded in the module docstring and trigger_hint for
whoever curates future real captions; it does NOT change cold-start
seeding itself, which still writes exactly one example per pillar (3
records total), for the same reason Part 2 did: seeding proportionally
more copies of the 40%-weighted pillar would itself manufacture a
"recurring content element (3+)" out of placeholder text, which is
exactly the kind of scaffolding-as-content leak Lesson 1 above exists to
prevent, just via a different path (over-seeding instead of a leaked
prefix).

PLACEHOLDER CONTENT, flagged explicitly, not glossed over: the 3 seed
captions below are generic placeholder text illustrating each pillar's
SHAPE, not real specifics about the actual musician, songs, or brand
voice -- I don't have, and have not fabricated, real details about this
account. Replace PILLAR_SEED_CAPTIONS with real example captions in his
own voice before this is used for anything beyond this session's own real
correction-cycle verification.

Recipient framing, the same deliberate minimal PHRASING adaptation as
Part 2, not a mechanism change: every seed caption's decision_text is
phrased "Update Instagram with today's caption: ..." so
pattern_watcher._extract_recipient finds "instagram" as the recipient,
grouping these records the same way a recurring text message would group
under a person's name.
"""

from pathlib import Path
from typing import List, Optional, Union

from .draft_generator import DEFAULT_DRAFT_ATTEMPTS_PATH, DraftAttempt, generate_draft
from .entity_memory import (
    DEFAULT_PATH,
    EntityMemoryRecord,
    EntityMemoryWriter,
    JsonlEntityMemoryWriter,
    read_records,
)
from .llm_client import LLMClient
from .suggestion import TaskAgentSpecStub

ENTITY_ID = "Brother's Music Instagram"

# Scaffolding needed ONLY so pattern_watcher._extract_recipient can find
# "instagram" as the recipient when STORING a record -- never meant to be
# seen by the model or a real person. See LESSON 1 in the module docstring;
# stripped by generate_caption_draft() below from day one.
_SCAFFOLD_PREFIX = "Update Instagram with today's caption:"

# Explicit, stated cold-start baseline -- see module docstring. Content is a
# generic placeholder illustrating each pillar's SHAPE, not real musical or
# personal specifics. Weighted 40/30/20 as a stated intended content-mix
# for future real captions; cold-start seeding still writes exactly one
# example per pillar regardless of weight (see LESSON 2). All three are
# phrased "Update Instagram with today's caption:" so
# pattern_watcher._extract_recipient groups them under "instagram".
PILLAR_SEED_CAPTIONS = {
    "original_music_performance": (  # 40% -- primary pillar
        "Update Instagram with today's caption: New clip from tonight's set -- this one's still unreleased, "
        "but it's been the closer for the last three shows and it keeps landing the same way every time. "
        "Full version's coming, but wanted you to hear this part first. #originalmusic #liveperformance"
    ),
    "behind_the_scenes_process": (  # 30%
        "Update Instagram with today's caption: This riff went through four completely different versions "
        "before it became what you heard on the record. Some days writing a song feels like sculpting, "
        "some days it feels like getting out of its way. Today was the second kind. #songwriting #studio"
    ),
    "personal_connection": (  # 20%
        "Update Instagram with today's caption: Someone came up after the show tonight and told me a song "
        "got them through something hard this year. That's the whole reason I do this -- not the stage, "
        "not the numbers, moments like that one. Thank you for being here. #gratitude #musiclife"
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
    start_brother_music_captions() is the safe, checked entrypoint; call
    this directly only if you specifically want to (re-)seed."""
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
    weighted 3-pillar framework), not an observation from real repeated
    behavior. Everything downstream (generate_draft, process_draft_reply)
    is unmodified and cannot tell the difference between this spec and one
    that came from a real accept_suggestion() call -- same
    TaskAgentSpecStub shape, same fields, same guarantees
    (action="draft_only", gated=True)."""
    return TaskAgentSpecStub(
        source_pattern_id=f"cold-start-3-pillar-seed:{entity_id}",
        trigger_hint=(
            "Recurring: write today's music Instagram caption for brother's account. Seeded day-one with an "
            "explicit, weighted 40/30/20 content framework (original-music/performance primary, "
            "behind-the-scenes/process second, personal-connection third) rather than waiting for organic "
            "history to accumulate -- see core/brother_music_captions.py's module docstring. Content will "
            "not yet rotate across pillars on corrections until real usage accumulates 3+ repeats of some "
            "detail (a stated, expected property of cold-start seeding, not a defect -- see LESSON 2 in the "
            "module docstring)."
        ),
        supporting_record_ids=[r.record_id for r in seed_records],
    )


def start_brother_music_captions(
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
    (e.g. to model output that already omits the prefix). Applied from day
    one here (LESSON 1), not added after a live leak was found."""
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
    two optional transform hooks generate_draft() already exposes (added
    in Part 2's prefix-strip fix). Gathering/matching (the recipient
    verb-gate included) still runs inside generate_draft() against the RAW
    stored text, completely untouched by either transform."""
    return generate_draft(
        spec, entity_id, client=client, path=path, attempts_path=attempts_path,
        min_occurrences_for_confidence=min_occurrences_for_confidence,
        example_text_transform=_strip_scaffold_prefix,
        output_text_transform=_strip_scaffold_prefix,
    )
