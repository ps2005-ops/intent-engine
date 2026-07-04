"""Voice-domain-specific output shapes, following the simulator/schemas.py pattern:
kept out of core/ since these are voice-specific concepts, not domain-agnostic ones.
"""

from typing import Optional

from pydantic import BaseModel

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

VoiceIntentType = Literal[
    "reminder",
    "email_draft",
    "calendar_block",
    "task_creation",
    "context_retrieval",
    "note_capture",
    "follow_up",
    "status_update",
    "priority_flag",
    "contact_lookup",
    "information_request",
    "general_query",
]

Salience = Literal["low", "medium", "high"]


class VoiceIntent(BaseModel):
    intent_type: VoiceIntentType
    target: Optional[str] = None   # who/what this is about
    when: Optional[str] = None     # raw time phrase, unparsed -- parsing is downstream
    content: Optional[str] = None  # the substance of the request

    # Not optional: every interaction gets classified, no "skip this" state --
    # entity memory writes every voice interaction (source: "voice"), no filtering
    # at write time. salience is the signal Stage D queries/weights by later.
    salience: Salience
