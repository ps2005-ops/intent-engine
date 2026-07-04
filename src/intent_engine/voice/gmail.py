"""Stage C: stub Gmail integration, read-only for this pass. Mirrors
voice/calendar.py's shape exactly, per the locked-in action-domain pattern
(docs/weekly/intent-engine-v2-entity-memory.md) -- gated by the real
PermissionRegistry, canned data, no real Gmail API calls, no OAuth, no new
dependencies.

gmail_act (sending on someone's behalf) is deliberately not built in this pass
-- reading someone's email and sending on their behalf are different
authorization decisions per the domain-string convention, and only
"gmail_read" is being proven here.
"""

from typing import List, Optional

from pydantic import BaseModel

from ..core.permissions import PermissionRegistry

GMAIL_READ_DOMAIN = "gmail_read"


class GmailMessage(BaseModel):
    sender: str
    subject: str
    snippet: str


_CANNED_MESSAGES = [
    GmailMessage(
        sender="sarah@acme.example",
        subject="Re: board deck draft",
        snippet="Looks good, one number on slide 4 needs a refresh before Thursday.",
    ),
    GmailMessage(
        sender="billing@vendor.example",
        subject="Invoice #4471 due",
        snippet="Your invoice for last month's usage is now available.",
    ),
    GmailMessage(
        sender="alex@acme.example",
        subject="Investor intro",
        snippet="Following up on the intro you asked for -- call scheduled for next week.",
    ),
]


class GmailReadResult(BaseModel):
    # Same "state what it would do, don't silently skip" principle as
    # CalendarReadResult -- `authorized=False` must be distinguishable from
    # "authorized, zero messages," which an empty `messages` list alone can't do.
    authorized: bool
    messages: List[GmailMessage] = []
    message: Optional[str] = None


class StubGmailReader:
    """Fake Gmail reader -- returns hardcoded messages, gated by "gmail_read"."""

    def __init__(self, registry: PermissionRegistry):
        self.registry = registry

    def read_messages(self) -> GmailReadResult:
        if not self.registry.is_authorized(GMAIL_READ_DOMAIN):
            return GmailReadResult(authorized=False, message="Not authorized to read Gmail.")
        return GmailReadResult(authorized=True, messages=list(_CANNED_MESSAGES))
