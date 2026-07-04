"""Voice intent classification stage. Own prompt, own schema, own LLMClient
instance -- physically separate from simulator/, sharing only core/llm_client.py
and core/pipeline.py, per the Weeks 1-4 audit's Question 1 answer. Unlike the
entity-memory writer, this genuinely fits the Stage contract: input (an utterance
+ personal context) in, a computed VoiceIntent out.

Latency measured before this was built as a permanent module (throwaway script,
not committed): 4 sample utterances across the salience spectrum, in two configs.
Config 1 (no PersonalContext): 0.71-1.04s. Config 2 (with PersonalContext):
0.74-1.39s, +0.14s average injection cost. Both comfortably under the <3s voice
target -- but that measurement was the LLM call in isolation, no Deepgram STT or
TTS synthesis yet, so it's not the full voice pipeline's latency, only this stage's.
"""

from typing import Optional

from ..core.llm_client import LLMClient
from ..core.pipeline import Stage
from .context_schema import PersonalContext
from .schemas import VoiceIntent

FAST_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a personal assistant intent classifier. Given a spoken \
command (transcribed to text), classify it.

intent_type: exactly one of reminder, email_draft, calendar_block, task_creation, \
context_retrieval, note_capture, follow_up, status_update, priority_flag, \
contact_lookup, information_request, general_query.

target: who/what this is about, if any (a name, a document, a topic) -- omit if \
not applicable.
when: the RAW time phrase from the utterance if any (e.g. "Thursday afternoon", \
"in 5 days") -- do not parse it into a date, just extract the phrase.
content: the substance of the request in a few words.

salience: classify how much this reveals about the person's goals, priorities, or \
strategic thinking, versus routine logistics. "remind me to buy milk" is low -- \
pure logistics, reveals nothing about goals. "we should reconsider pricing" is \
high -- a strategic reconsideration, reveals active priority-shifting. Most \
reminders/calendar/task requests are low; anything touching strategy, a major \
decision, or a stated priority is high; ambiguous cases are medium."""

# OPEN CALIBRATION QUESTION, partially characterized, still not resolved -- do
# not treat context-injected salience as validated. Follow-up measurement (10
# runs each, both configs, 2 utterances -- an ambiguous one and a low-salience
# control) replaced the original 4-sample anecdote with a real distribution:
#
#   "what did I say about the Q3 roadmap last month" (ambiguous)
#     without context: {'medium': 9, 'high': 1}
#     with context:    {'high': 9, 'medium': 1}
#   "remind me to buy milk" (low-end control)
#     without context: {'low': 10}
#     with context:    {'low': 10}
#
# intent_type was perfectly stable (10/10) in every case -- variance is
# salience-specific. The control utterance showed zero variance in either
# config, so the noise isn't uniform across the salience spectrum, it's
# concentrated on ambiguous cases. The context-correlated shift (9/10 medium ->
# 9/10 high) is strong and consistent, not random scatter -- more consistent
# with a systematic effect of context injection on salience judgment for
# ambiguous utterances specifically than with pure sampling noise. This still
# does NOT resolve whether that shift is increased accuracy or a bias toward
# higher salience under context -- both remain equally consistent with this
# data. Unresolved; better-characterized than before, not settled.
VOICE_INTENT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "intent_type": {
            "type": "string",
            "enum": [
                "reminder", "email_draft", "calendar_block", "task_creation",
                "context_retrieval", "note_capture", "follow_up", "status_update",
                "priority_flag", "contact_lookup", "information_request", "general_query",
            ],
        },
        "target": {"type": "string"},
        "when": {"type": "string"},
        "content": {"type": "string"},
        "salience": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["intent_type", "content", "salience"],
}


class VoiceIntentClassifier(Stage):
    name = "voice_intent_classifier"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient(model=FAST_MODEL)

    def run(self, utterance: str, context: Optional[PersonalContext] = None) -> VoiceIntent:
        user_message = f"Utterance: {utterance}"
        if context is not None:
            user_message += f"\n\nContext about this person:\n{context.to_prompt_text()}"

        result = self.client.call_tool(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            tool_name="record_voice_intent",
            tool_description="Record the classified voice intent.",
            input_schema=VOICE_INTENT_TOOL_SCHEMA,
            max_tokens=512,
        )
        return VoiceIntent(**result)
