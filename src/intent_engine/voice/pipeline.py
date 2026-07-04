"""Composes VoiceIntentClassifier + the entity-memory write, mirroring
simulator/cli.py's pattern: the write call lives outside the classifier stage,
not inside it. VoiceIntentClassifier.run() stays classification-only (Stage
contract: compute-and-return), same reasoning as why the memory writer is a
Protocol, not a Stage, in the first place.

Every voice interaction gets written to entity memory, no filtering -- salience
is a signal for Stage D to query/weight by later, not a write-time gate.
"""

from typing import Optional

from ..core.entity_memory import EntityMemoryRecord, EntityMemoryWriter, JsonlEntityMemoryWriter
from .classifier import VoiceIntentClassifier
from .context_schema import PersonalContext
from .schemas import VoiceIntent


def process_voice_interaction(
    entity_id: str,
    utterance: str,
    context: Optional[PersonalContext] = None,
    classifier: Optional[VoiceIntentClassifier] = None,
    writer: Optional[EntityMemoryWriter] = None,
) -> VoiceIntent:
    classifier = classifier or VoiceIntentClassifier()
    writer = writer or JsonlEntityMemoryWriter()

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

    return voice_intent
