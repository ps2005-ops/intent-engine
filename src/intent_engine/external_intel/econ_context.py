"""The founder engine's end of the canonical economic core.

WHAT CHANGES FOR A COMPANY ANALYSIS
------------------------------------
Before this, a company report's macro picture came from whatever the company
itself happened to publish. Rates, enterprise demand, security consolidation,
hyperscaler pricing, cloud optimisation -- each was re-derived per run from
retrieved documents, and the far better picture the market-learning engine
holds was structurally unreachable.

This reads that picture. The company system's job stops being "work out what
the economy is doing" and becomes "work out what it means for THIS company",
which is the only one of the two it is equipped to do.

THE IMPORT WALL IS INTACT
--------------------------
This module imports `intent_engine.econ` and NEVER `intent_engine.market`.
`econ` is neutral: it imports neither product. So the guarantee that trading
internals cannot reach a founder's screen is still a property of the import
graph -- `tests/test_market_intel_contract.py` asserts the absence of the
edge and continues to pass -- while the economics both sides need is shared.

The state on disk is UNTRUSTED INPUT, exactly as the strategic dossier is. It
may have been written by an older producer, a newer one, or a hand edit. So
it is re-validated on the way in against `econ.state.ALLOWED`, which is the
same allowlist the producer validated against and is declared independently
here for the same reason `strategic_contract` declares its own.

ABSENCE IS A READING
--------------------
On a deployment where no market engine has ever run, this returns
`available: False` with a reason a founder can act on. It is never an empty
heading, never a zero, and never a silently skipped section -- and it never
promotes a bounded analysis into a confident one, because economic context
qualifies a decision the company's own evidence drives.

WHAT THIS WILL NOT DO
---------------------
Recompute macro. There is no fallback in this module that derives an economic
condition from company documents when the shared state is missing. That
fallback is what created two disagreeing macro pictures; if the state is
absent, the honest output is that it is absent.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from intent_engine.econ import state as ES
from intent_engine.econ import store as EST
from intent_engine.econ import shock as SH

CONTRACT = "econ_context.v1"


@dataclass(frozen=True)
class EconContext:
    """The shared economic state, as one company analysis reads it."""

    available: bool
    as_of: str = ""
    area: str = ""
    reason: str = ""
    conditions: Dict[str, dict] = field(default_factory=dict)
    beliefs: Tuple[dict, ...] = ()
    shocks: Tuple[dict, ...] = ()
    uncertainty: Dict[str, object] = field(default_factory=dict)
    provenance: Dict[str, object] = field(default_factory=dict)

    #: Permanently False, matching every other external context in this
    #: package. Economic context cannot turn a bounded reading into a
    #: confident one however rich it is.
    changes_readiness: bool = field(default=False, init=False)

    def reading(self, kind: str) -> Optional[dict]:
        row = self.conditions.get(kind)
        return row if row and row.get("known") else None

    def known_kinds(self) -> List[str]:
        return sorted(k for k, v in self.conditions.items() if v.get("known"))

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "available": self.available,
                "as_of": self.as_of, "area": self.area,
                "reason": self.reason,
                "conditions": dict(self.conditions),
                "beliefs": [dict(b) for b in self.beliefs],
                "shocks": [dict(s) for s in self.shocks],
                "uncertainty": dict(self.uncertainty),
                "provenance": dict(self.provenance),
                "changes_readiness": self.changes_readiness}


def unavailable(reason: str) -> EconContext:
    return EconContext(available=False, reason=reason)


def load(runtime_root, *, as_of: str = "") -> EconContext:
    """Read the shared economic state, or say why there is none."""
    try:
        rows = EST.load(runtime_root, "state_snapshot", upto=as_of)
    except Exception as exc:                       # noqa: BLE001
        return unavailable(
            f"the shared economic state could not be read ({exc}); the "
            "company analysis continues on its own evidence and this "
            "section states what is missing")
    if not rows:
        return unavailable(
            "no economic state has been published to this deployment. The "
            "market-learning engine writes it; on a deployment where that "
            "engine has never run there is nothing to read, and the "
            "company's own evidence is the whole basis for this analysis.")
    payload = rows[-1]
    try:
        # Re-validated on the way in. The file is untrusted input, and a
        # consumer that trusts the producer's validation is a consumer that
        # renders whatever the file happens to contain.
        ES.validate(payload)
    except ES.StateViolation as exc:
        return unavailable(
            f"the published economic state failed the shared contract on the "
            f"way in ({exc}). It is refused rather than rendered: a state "
            "carrying a field this side does not recognise may be carrying "
            "anything.")
    return EconContext(
        available=True, as_of=str(payload.get("as_of", "")),
        area=str(payload.get("area", "")),
        conditions=dict(payload.get("conditions") or {}),
        beliefs=tuple(payload.get("beliefs") or ()),
        shocks=tuple(payload.get("shocks") or ()),
        uncertainty=dict(payload.get("uncertainty") or {}),
        provenance=dict(payload.get("provenance") or {}),
        reason="")


def relevant_to(context: EconContext, *,
                exposures: Sequence[str]) -> List[dict]:
    """The economic readings this company is actually exposed to.

    `exposures` comes from the company's OWN evidence -- see
    `econ.company.MacroExposure`, which refuses an exposure that does not name
    the observation establishing it. This function never widens that: a
    condition the company has no evidenced exposure to is not returned,
    however interesting it is.

    An exposure the shared state does not measure comes back with
    `measured: False` rather than being dropped. "This company is exposed to
    real yields and nothing here measures them" is a research priority, and
    dropping it would make the company look less exposed than it is.
    """
    if not context.available:
        return []
    out: List[dict] = []
    for quantity in exposures:
        row = context.conditions.get(quantity)
        if row and row.get("known"):
            out.append({"quantity": quantity, "measured": True,
                        "standing": row.get("standing"),
                        "direction": row.get("direction"),
                        "moved": row.get("moved"),
                        "value": row.get("value"), "unit": row.get("unit"),
                        "as_of": row.get("as_of"),
                        "prior_value": row.get("prior_value"),
                        "prior_as_of": row.get("prior_as_of"),
                        "publisher": row.get("publisher"),
                        "node_id": row.get("node_id")})
        else:
            out.append({"quantity": quantity, "measured": False,
                        "reason": ((row or {}).get("reason")
                                   or "the shared economic state does not "
                                      "measure this condition")})
    return out


def beliefs_touching(context: EconContext, *, terms: Sequence[str],
                     limit: int = 3) -> List[dict]:
    """Market-learned beliefs whose proposition names one of `terms`.

    Matched on the company's own vocabulary rather than on a sector code, for
    the same reason exposures are evidence-bound: a sector map says a payroll
    company and a chip designer are both technology.
    """
    if not context.available:
        return []
    lowered = [t.lower() for t in terms if t and len(t) > 3]
    hits = []
    for b in context.beliefs:
        text = str(b.get("proposition", "")).lower()
        if any(t in text for t in lowered):
            hits.append(b)
    return sorted(hits, key=lambda b: -float(b.get("fragility", 0)))[:limit]


def transmission_note(context: EconContext, *, exposures: Sequence[str],
                      ) -> str:
    """One sentence a founder surface can render, or an empty string.

    Empty rather than a placeholder. A section that renders "no significant
    macro transmission identified" on every run teaches its reader to stop
    reading it, and an empty string lets the surface omit the section
    entirely -- which is what `pack.relevant_sections` already does.
    """
    if not context.available:
        return ""
    live = [r for r in relevant_to(context, exposures=exposures)
            if r.get("measured")]
    if not live:
        return ""
    parts = []
    for r in live[:3]:
        direction = str(r.get("direction", "")).upper()
        moving = {"UP": "rising", "DOWN": "falling", "FLAT": "unchanged",
                  "NO_PRIOR": "at a level with no earlier observation to "
                              "compare against"}.get(direction, "unchanged")
        parts.append(f"{r['quantity'].replace('_', ' ')} {moving}")
    return (f"As of {context.as_of}, the shared economic state reads "
            + "; ".join(parts) + ". This company has evidenced exposure to "
            "each of those, and what they mean for it is the question the "
            "rest of this analysis answers.")
