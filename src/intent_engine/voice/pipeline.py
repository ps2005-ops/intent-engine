"""Composes VoiceIntentClassifier + the entity-memory write + permission-gated
domain actions (calendar_block -> Calendar, email_draft -> Gmail), mirroring
simulator/cli.py's pattern: the write call lives outside the classifier stage,
not inside it. VoiceIntentClassifier.run() stays classification-only (Stage
contract: compute-and-return), same reasoning as why the memory writer is a
Protocol, not a Stage, in the first place.

Every voice interaction gets written to entity memory, no filtering -- salience
is a signal for Stage D to query/weight by later, not a write-time gate. Order
matters here: the entity-memory write happens BEFORE any permission check/
domain action, unconditionally -- a denied action must still leave a durable
record that it was requested. Checking permission first and only writing on
success would silently drop the record of a refused request, which breaks
"every interaction written, no filtering."

email_draft is wired FRESH-COMPOSE ONLY. Known, documented limitation: there is
currently no field distinguishing "compose a new email" from "reply to an
existing one," so every email_draft intent is treated as fresh-compose --
including reply-style utterances, which this pipeline cannot yet detect or
handle correctly. This is deliberate, not an oversight: reply-to-existing needs
the compound-action mechanism (an act domain depending on a read domain's
content), which is explicitly tabled -- see
docs/weekly/intent-engine-v2-entity-memory.md's compound-action section for why
a concrete field/mechanism wasn't locked in from this one case alone.
"""

from typing import NamedTuple, Optional

from ..core.entity_memory import EntityMemoryRecord, EntityMemoryWriter, JsonlEntityMemoryWriter
from ..core.permissions import PermissionRegistry
from .calendar import CalendarActResult, StubCalendarActor
from .classifier import VoiceIntentClassifier
from .context_schema import PersonalContext
from .gmail import GmailActResult, StubGmailActor
from .schemas import VoiceIntent


class VoiceInteractionResult(NamedTuple):
    voice_intent: VoiceIntent
    calendar_action: Optional[CalendarActResult]  # populated only for calendar_block intents
    gmail_action: Optional[GmailActResult]  # populated only for email_draft intents (fresh-compose only)


def process_voice_interaction(
    entity_id: str,
    utterance: str,
    context: Optional[PersonalContext] = None,
    classifier: Optional[VoiceIntentClassifier] = None,
    writer: Optional[EntityMemoryWriter] = None,
    permission_registry: Optional[PermissionRegistry] = None,
    calendar_actor: Optional[StubCalendarActor] = None,
    gmail_actor: Optional[StubGmailActor] = None,
) -> VoiceInteractionResult:
    classifier = classifier or VoiceIntentClassifier()
    writer = writer or JsonlEntityMemoryWriter()
    registry = permission_registry or PermissionRegistry()  # deny-by-default if not supplied
    calendar_actor = calendar_actor or StubCalendarActor(registry)
    gmail_actor = gmail_actor or StubGmailActor(registry)

    voice_intent = classifier.run(utterance, context=context)

    record = EntityMemoryRecord(
        entity_id=entity_id,
        source="voice",
        decision_text=utterance,
        goals=[],
        constraints=[],
        risk_tolerance=None,
        primary_priority=None,
        salience=voice_intent.salience,
    )
    writer.write(record)

    calendar_action = None
    if voice_intent.intent_type == "calendar_block":
        calendar_action = calendar_actor.create_event(
            title=voice_intent.target or voice_intent.content or "Untitled event",
            when=voice_intent.when or "unspecified time",
        )

    gmail_action = None
    if voice_intent.intent_type == "email_draft":
        gmail_action = gmail_actor.create_draft(
            recipient=voice_intent.target or "unspecified recipient",
            subject=voice_intent.content or "Untitled draft",
        )

    return VoiceInteractionResult(voice_intent=voice_intent, calendar_action=calendar_action, gmail_action=gmail_action)
