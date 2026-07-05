"""Image-verification: a second real domain, deliberately different-shaped
from recurring_message (image input, not voice-transcribed text; a
criterion-shaped verdict, not a text draft) -- built specifically to convert
the architecture-generalization audit's two open uncertainties from paper
speculation into real evidence. See
docs/weekly/intent-engine-v2-entity-memory.md's imitation-vs-criterion
limitation and pattern_watcher.py's SimilarityStrategy seam.

verify_image() makes ONE minimal, separate Claude vision call, mirroring
LuckTestAnalyzer's isolation pattern (simulator/luck_test.py) -- not folded
into any existing pipeline. VerificationResult is the dict-shaped payload
proposed in the architecture audit's Β§3 (the lighter alternative to a full
OutputArtifact class hierarchy) -- deliberately NOT a new class hierarchy,
since there is still only one real domain needing a non-text-draft shape.

Uses Claude's own vision capability via LLMClient.call_tool's new
image_path parameter (core/llm_client.py) -- no new API vendor, only an
additive extension of the existing Anthropic client wrapper.

Deliberately out of scope this pass (see the checkpoint that authorized this
build): no SimilarityStrategy/Pattern-Watcher integration for images --
content-similarity for images stays an open, undecided dependency question,
not computed anywhere here; no real multi-round refinement loop, only a
one-shot correction-reply probe (see tests/test_image_verification.py); no
CLI/voice wiring.
"""

from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from .llm_client import LLMClient

FAST_MODEL = "claude-haiku-4-5-20251001"

Verdict = Literal["complete", "incomplete", "illegible"]
Confidence = Literal["low", "medium", "high"]


class VerificationResult(BaseModel):
    verdict: Verdict
    missing: List[str]
    reasoning: str
    confidence: Confidence


VERIFICATION_SYSTEM_PROMPT = """You are checking whether a photo shows a complete, \
legible document against a fixed checklist of required fields. For each checklist \
item, judge only whether it is CLEARLY VISIBLE AND LEGIBLE in the image -- not \
whether you can guess or infer it from context, only whether it is actually visible.

verdict: "complete" if every checklist item is clearly visible and legible in the \
image. "incomplete" if the image is otherwise readable but at least one checklist \
item is missing, cut off, or out of frame. "illegible" if the image itself is too \
blurry, dark, or low-quality to reliably read ANY of the checklist items, \
regardless of framing.

missing: the checklist items (using their exact wording) that are NOT clearly \
visible and legible. Empty list if verdict is "complete". If verdict is \
"illegible", list every checklist item, since none can be reliably confirmed.

confidence: "low" if the image is borderline or ambiguous, "high" only if the \
verdict is unambiguous from what is actually visible, "medium" otherwise.

reasoning: one or two sentences grounded in what you actually observe in the \
image -- which specific fields you found, and where any missing or illegible \
field would be expected to appear."""

VERIFICATION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["complete", "incomplete", "illegible"]},
        "missing": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string", "maxLength": 300},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["verdict", "missing", "reasoning", "confidence"],
}


def verify_image(
    image_path: Union[str, Path],
    checklist: List[str],
    client: Optional[LLMClient] = None,
) -> VerificationResult:
    client = client or LLMClient(model=FAST_MODEL)
    checklist_text = "\n".join(f"- {item}" for item in checklist)
    user_message = f"Checklist:\n{checklist_text}\n\nCheck the attached image against this checklist."

    result = client.call_tool(
        system=VERIFICATION_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="record_verification",
        tool_description="Record the verification judgment for this image.",
        input_schema=VERIFICATION_TOOL_SCHEMA,
        max_tokens=400,
        image_path=image_path,
    )
    return VerificationResult(**result)


def render_verification_as_text(result: VerificationResult) -> str:
    """Renders a VerificationResult as a flat text summary -- used ONLY to
    probe classify_draft_reply() (draft_generator.py), which takes a plain
    draft_text: str. This function exists purely for that one-shot
    correction-reply experiment; it is not a real "draft" and nothing here
    claims verification results are draft text in general."""
    missing_text = ", ".join(result.missing) if result.missing else "none"
    return f"Verdict: {result.verdict}. Missing: {missing_text}. Reasoning: {result.reasoning}"
