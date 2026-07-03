"""Stage B: permission / scope registry, per docs/weekly/intent-engine-v2-entity-memory.md.

Deliberately minimal for this pass: no persistence, no integration-specific logic --
there's nothing to gate yet (confirmed in the Weeks 1-4 audit: the current codebase
takes zero actions against anything external). This exists so the gate is in place
before Stage C's real integrations are built, not retrofitted after.
"""

from typing import Dict, Optional


class PermissionRegistry:
    """Deny-by-default: unknown or ungranted domains return False, not True."""

    def __init__(self, grants: Optional[Dict[str, bool]] = None):
        self._grants = grants or {}

    def is_authorized(self, domain: str) -> bool:
        return self._grants.get(domain, False)
