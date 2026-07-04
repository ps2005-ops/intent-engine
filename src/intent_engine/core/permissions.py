"""Stage B: permission / scope registry, per docs/weekly/intent-engine-v2-entity-memory.md.

Deliberately minimal for this pass: no persistence, no integration-specific logic --
there's nothing to gate yet (confirmed in the Weeks 1-4 audit: the current codebase
takes zero actions against anything external). This exists so the gate is in place
before Stage C's real integrations are built, not retrofitted after.

Domain-string convention, locked in with the Calendar stub (voice/calendar.py) and
binding for every integration after it: "{integration}_read" and "{integration}_act",
two separate domain strings per integration, never a single domain covering both.
is_authorized() itself stays single-arg (domain: str) -> bool -- the read/act
distinction is expressed entirely through which string gets checked, not through a
second method parameter. E.g. Gmail (when it's built) must use "gmail_read"/
"gmail_act", not "gmail" alone or a bespoke scheme -- reading someone's email and
sending on their behalf are different authorization decisions and must never share
one grant.
"""

from typing import Dict, Optional


class PermissionRegistry:
    """Deny-by-default: unknown or ungranted domains return False, not True."""

    def __init__(self, grants: Optional[Dict[str, bool]] = None):
        self._grants = grants or {}

    def is_authorized(self, domain: str) -> bool:
        return self._grants.get(domain, False)
