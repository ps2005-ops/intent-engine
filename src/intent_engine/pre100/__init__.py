"""Capture once, replay locally, audit mechanically.

WHY THIS PACKAGE EXISTS. Three sessions were spent on one batch of eight
companies, and the cost was not the work — it was paying full price for the
same evidence repeatedly: a deploy and a live run to discover that a field
never crossed a projection, a second run to look at a different section of a
page already rendered, a six-minute suite to land a paragraph of prose.

The loop this package makes possible:

    LIVE CAPTURE -> LOCAL REPLAY -> CLUSTER -> BATCH REPAIR
                 -> ONE GUARD -> ONE DEPLOY -> CANARY REPROOF

The live UI remains the final authority on whether the product is right. It
stops being the debugger. A defect that reproduces from a captured artifact
is diagnosed in seconds; one that does not is itself a finding
(RUNTIME_ONLY_DEFECT) and is the only kind that earns another live run.
"""
from __future__ import annotations

__all__ = ["capture", "audit", "replay"]
