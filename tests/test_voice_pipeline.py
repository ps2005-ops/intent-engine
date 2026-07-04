from intent_engine.core.entity_memory import JsonlEntityMemoryWriter, read_records
from intent_engine.voice.classifier import VoiceIntentClassifier
from intent_engine.voice.pipeline import process_voice_interaction


class FakeLLMClient:
    """Stands in for LLMClient so this test never touches the network or needs an API key."""

    def __init__(self, canned_response):
        self.canned_response = canned_response

    def call_tool(self, **kwargs):
        return self.canned_response


def test_process_voice_interaction_writes_every_interaction_regardless_of_salience(tmp_path):
    """No filtering: both a low-salience and a high-salience interaction for the
    same entity must both land in entity memory -- salience is a signal for
    Stage D to query/weight by later, not a write-time gate."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    low_client = VoiceIntentClassifier(
        client=FakeLLMClient(
            {"intent_type": "reminder", "target": "milk", "when": None, "content": "buy milk", "salience": "low"}
        )
    )
    high_client = VoiceIntentClassifier(
        client=FakeLLMClient(
            {
                "intent_type": "priority_flag",
                "target": "pricing",
                "when": None,
                "content": "reconsider pricing",
                "salience": "high",
            }
        )
    )

    low_result = process_voice_interaction(
        entity_id="Acme Inc", utterance="remind me to buy milk", classifier=low_client, writer=writer
    )
    high_result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="we should reconsider our pricing strategy",
        classifier=high_client,
        writer=writer,
    )

    assert low_result.salience == "low"
    assert high_result.salience == "high"

    records = read_records("Acme Inc", path=path)
    assert len(records) == 2  # both written -- neither filtered out
    assert {r.salience for r in records} == {"low", "high"}
    assert all(r.source == "voice" for r in records)
    assert all(r.goals == [] and r.constraints == [] for r in records)
    assert all(r.primary_priority is None for r in records)

    decision_texts = {r.decision_text for r in records}
    assert decision_texts == {"remind me to buy milk", "we should reconsider our pricing strategy"}
