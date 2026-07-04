"""Stage C: stub Gmail integration. Mirrors voice/calendar.py's shape exactly,
per the locked-in action-domain pattern (docs/weekly/intent-engine-v2-entity-memory.md)
-- gated by the real PermissionRegistry, canned data, no real Gmail API calls,
no OAuth, no new dependencies.

The "act" tier is create_draft(), not send_email() -- drafting is the safer
default for something acting on someone's behalf than an irreversible send,
same caution this project has applied to action-taking throughout. It also
maps directly onto VoiceIntentType's existing "email_draft" value, unlike
gmail_read, which has no natural intent_type trigger -- see pipeline.py (not
yet wired) for why that still matters.
"""

from typing import List, Optional

from pydantic import BaseModel

from ..core.permissions import PermissionRegistry

GMAIL_READ_DOMAIN = "gmail_read"
GMAIL_ACT_DOMAIN = "gmail_act"


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
    # Additive, defaults False so every existing stub-produced result is
    # unaffected: distinguishes "not_authorized" (authorized=False, failed=False
    # -- a permission decision) from "read_failed" (authorized=False,
    # failed=True -- an operational failure: expired token, rate limit, network
    # error, malformed response). No real Gmail reader produces failed=True yet
    # (StubGmailReader never fails) -- kept symmetric with CalendarReadResult
    # for when one exists.
    failed: bool = False


class StubGmailReader:
    """Fake Gmail reader -- returns hardcoded messages, gated by "gmail_read"."""

    def __init__(self, registry: PermissionRegistry):
        self.registry = registry

    def read_messages(self) -> GmailReadResult:
        if not self.registry.is_authorized(GMAIL_READ_DOMAIN):
            return GmailReadResult(authorized=False, message="Not authorized to read Gmail.")
        return GmailReadResult(authorized=True, messages=list(_CANNED_MESSAGES))


class GmailActResult(BaseModel):
    authorized: bool
    confirmation: Optional[str] = None
    message: Optional[str] = None


class StubGmailActor:
    """Fake Gmail actor -- create_draft() doesn't actually create or send
    anything, just returns a canned confirmation, gated by "gmail_act"
    specifically -- separate from "gmail_read" so a read grant never implies
    an act grant."""

    def __init__(self, registry: PermissionRegistry):
        self.registry = registry

    def create_draft(self, recipient: str, subject: str) -> GmailActResult:
        if not self.registry.is_authorized(GMAIL_ACT_DOMAIN):
            return GmailActResult(authorized=False, message="Not authorized to create Gmail drafts.")
        return GmailActResult(
            authorized=True,
            confirmation=f"Created draft to {recipient} with subject '{subject}' (stub -- nothing actually sent).",
        )
