"""V2.0 channel policy walls — drafts must already comply, even though
the Studio never publishes. Reuses the existing banned-language scan for
brand/claim integrity and adds channel-specific checks."""
from __future__ import annotations

from intent_engine.growth_studio.records import (
    CHANNELS, CLAIM_CLASSES, StudioError,
)

_SEO_SPAM = ("best best", "top top", "#1 #1")


def check_draft(*, channel: str, body: str, statements: list) -> list:
    """Returns a list of violations (empty = compliant). Raises on an
    unknown channel or malformed statement classification."""
    if channel not in CHANNELS:
        raise StudioError(f"unknown channel {channel!r}")
    lowered = " ".join(body.lower().split())
    violations = []

    for statement in statements:
        cls = statement.get("class")
        if cls not in CLAIM_CLASSES:
            raise StudioError(f"statement class must be one of "
                              f"{CLAIM_CLASSES}, got {cls!r}")
        if cls == "UNSUPPORTED_REJECT":
            violations.append(
                f"unsupported statement must be removed: "
                f"{statement.get('text', '')[:60]!r}")
        if cls == "CUSTOMER_QUOTE" and not statement.get("consented"):
            violations.append("customer quote without recorded consent")

    # universal brand integrity
    for marker in ("testimonial", "customers say", "users report"):
        if marker in lowered and not any(
                s["class"] == "CUSTOMER_QUOTE" and s.get("consented")
                for s in statements):
            violations.append(f"implied testimonial without a consented "
                              f"quote ({marker!r})")
    for marker in ("guaranteed", "definitely the best", "better than"):
        if marker in lowered and not any(
                s["class"] in ("SUPPORTED_PRODUCT_FACT",
                               "SUPPORTED_MARKET_OBSERVATION")
                and marker in s.get("text", "").lower()
                for s in statements):
            violations.append(f"unsupported superiority claim ({marker!r})")

    # channel-specific
    if channel == "reddit":
        if not lowered.startswith("disclosure:") and \
                "i built" not in lowered and "we built" not in lowered:
            violations.append("reddit: promotion must be disclosed in "
                              "community context (no disguised promotion)")
    if channel == "hackernews":
        if "click here" in lowered or "limited time" in lowered:
            violations.append("hackernews: no engagement-bait language")
        if not any(s["class"] == "SUPPORTED_PRODUCT_FACT"
                   for s in statements):
            violations.append("hackernews: technical substance required "
                              "(at least one supported product fact)")
    if channel == "newsletter":
        if "unsubscribe" not in lowered:
            violations.append("newsletter: unsubscribe notice required "
                              "before any future execution")
    if channel == "producthunt":
        if "vote for us" in lowered or "upvote" in lowered:
            violations.append("producthunt: no vote solicitation")
    if channel == "seo":
        words = lowered.split()
        if words:
            top = max(set(words), key=words.count)
            if len(top) > 3 and words.count(top) / len(words) > 0.12:
                violations.append(f"seo: keyword stuffing ({top!r})")
        if any(s in lowered for s in _SEO_SPAM):
            violations.append("seo: spam pattern")
    return violations
