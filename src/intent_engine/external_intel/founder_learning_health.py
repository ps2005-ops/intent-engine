"""Is Founder Intelligence getting better because Market Intelligence is?

THE COUNTERPART, AND ITS HONEST LIMIT
-------------------------------------
`MarketLearningHealth` asks whether the engine is learning. This asks whether
the product is getting better at turning that learning into decisions — the
other half of the loop, and the half nobody was measuring.

It is built on the consumption ledger, because that is the only append-only
founder-side record that exists. There is no run store: founder analyses are
session-scoped and nothing persists a per-run outcome. So the metrics that
would need one — how many analyses were full vs bounded vs withheld, how many
failed, how many carried a wrong subject — are reported `UNMEASURABLE` with
the reason, not as zero.

That is a real gap and it is named rather than papered over. Building a run
store to make the numbers appear would be a bigger change than this cycle can
verify, and a health report whose inputs are invented is worse than one that
says what it cannot see.

WHAT IT CAN SEE, IT SEES EXACTLY
--------------------------------
Every dossier that reached this side, how far it got, why it stopped, and
whether it changed a decision field. That is enough to answer the question
this module exists for, which is not "did more tests pass" but "is market
learning arriving, and is it doing anything when it does".
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.external_intel import consumption_receipt as CR

CONTRACT = "founder_learning_health.v1"

UNMEASURABLE = "UNMEASURABLE"

# --- where the product is currently limited ---------------------------------
SOURCE_COVERAGE = "SOURCE_COVERAGE"
IDENTITY = "IDENTITY"
EVIDENCE_QUALITY = "EVIDENCE_QUALITY"
REASONING = "REASONING"
MARKET_CONSUMPTION = "MARKET_CONSUMPTION"
DECISION_IMPACT = "DECISION_IMPACT"
PRESENTATION = "PRESENTATION"
RELIABILITY = "RELIABILITY"
NOT_LIMITED = "NOT_LIMITED"

BOTTLENECKS = frozenset({
    SOURCE_COVERAGE, IDENTITY, EVIDENCE_QUALITY, REASONING,
    MARKET_CONSUMPTION, DECISION_IMPACT, PRESENTATION, RELIABILITY,
    NOT_LIMITED})

#: A rate over fewer analyses than this is not a rate. Same discipline as the
#: market side, and deliberately the same number, so the two reports cannot
#: disagree about what counts as measurable.
MIN_ANALYSES_FOR_RATE = 3

WINDOWS = (7, 20)


def _rate(numerator: int, denominator: int) -> object:
    if denominator < MIN_ANALYSES_FOR_RATE:
        return UNMEASURABLE
    return numerator / denominator


def _pairs(events: Sequence[dict]) -> Dict[str, dict]:
    """Furthest stage each (analysis, dossier) pairing reached.

    Counting rows would count one consumption up to nine times, once per
    stage. The unit is the pairing and its value is how far it got.
    """
    best: Dict[str, dict] = {}
    order = _ORDER
    for row in events:
        key = f"{row.get('founder_analysis_id')}|{row.get('dossier_id')}"
        current = best.get(key)
        if current is None or order.get(str(row.get("stage")), -1) > \
                order.get(str(current.get("stage")), -1):
            best[key] = row
    return best


#: Read from the producer's own declaration rather than restated here. Two
#: copies of a ladder is two things that can disagree about how far a dossier
#: got, and the disagreement is silent: a stage this module has not heard of
#: ranks below every other and vanishes from the health view.
_ORDER = {name: i for i, name in enumerate(CR.LADDER)}


def _reached(row: dict, stage: str) -> bool:
    order = _ORDER
    got, want = order.get(str(row.get("stage"))), order.get(stage)
    return got is not None and want is not None and got >= want


def read_events(root, path: str = CR.LEDGER_PATH) -> Tuple[dict, ...]:
    target = pathlib.Path(root) / path
    if not target.exists():
        return ()
    out: List[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == CR.SCHEMA:
            out.append(row)
    return tuple(out)


def assess(root, *, window: Optional[int] = None) -> Dict[str, object]:
    """Founder-side health over the most recent `window` analyses."""
    events = read_events(root)
    pairs = _pairs(events)

    ordered = sorted(pairs.values(),
                     key=lambda r: str(r.get("consumed_at") or ""))
    if window:
        ordered = ordered[-window:]

    analyses = {r.get("founder_analysis_id") for r in ordered}
    companies = {r.get("company_id") for r in ordered}
    refusals = collections.Counter(
        r.get("refusal_code") for r in events if r.get("refusal_code"))

    received = sum(1 for r in ordered if _reached(r, CR.RECEIVED))
    used = sum(1 for r in ordered if _reached(r, CR.USED_IN_REASONING))
    rendered = sum(1 for r in ordered if _reached(r, CR.RENDERED_TO_FOUNDER))
    decisive = sum(1 for r in ordered if _reached(r, CR.DECISION_RELEVANT))
    # Reasoned from occurrences rather than from a row count. Counted over
    # pairings that reached at least this rung, so a dossier consumed by an
    # older path — or by a producer that never normalized — is not credited.
    normalized = sum(1 for r in ordered if _reached(r, CR.TRUST_NORMALIZED))

    materialities = collections.Counter(
        r.get("founder_surface_rendered") for r in events
        if r.get("stage") == CR.DECISION_RELEVANT
        and r.get("founder_surface_rendered"))

    health: Dict[str, object] = {
        "contract": CONTRACT,
        "window": window or "all",
        "analyses_seen": len(analyses),
        "companies_seen": len(companies),

        # --- what the ledger genuinely shows --------------------------------
        "market_dossiers_available": len(ordered),
        "market_dossiers_used": used,
        "market_learning_rendered": rendered,
        "market_learning_decision_relevant": decisive,
        "consumption_rate": _rate(used, len(ordered)),
        "decision_impact_rate": _rate(decisive, len(ordered)),
        "materiality_distribution": dict(materialities),
        "graph_provenance_reads": rendered,

        # --- was the evidence normalized, or merely counted? ----------------
        # The question §14 asks. `normalized_rate` below 1.0 with a healthy
        # consumption rate means dossiers are being read by a path that still
        # counts rows — which is the failure that looks most like success.
        "trust_normalized_consumptions": normalized,
        "normalized_rate": _rate(normalized, used),

        # --- refusals, by cause ---------------------------------------------
        "identity_failures": refusals.get(CR.IDENTITY_MISMATCH, 0),
        "schema_refusals": refusals.get(CR.SCHEMA_REJECTED, 0),
        "stale_dossier_refusals": refusals.get(CR.STALE_DOSSIER, 0),
        "no_material_refusals": refusals.get(CR.NO_MATERIAL, 0),

        # --- what needs a run store this side does not have -----------------
        "companies_attempted": UNMEASURABLE,
        "analyses_full": UNMEASURABLE,
        "analyses_bounded": UNMEASURABLE,
        "analyses_withheld": UNMEASURABLE,
        "analyses_failed": UNMEASURABLE,
        "wrong_subject_defects": UNMEASURABLE,
        "false_competitors": UNMEASURABLE,
        "unsupported_claims": UNMEASURABLE,
        "generic_reasoning": UNMEASURABLE,
        "acceptance_rate": UNMEASURABLE,
        "unmeasurable_because": (
            "founder analyses are session-scoped and nothing persists a "
            "per-run outcome, so these need a run store that does not exist "
            "yet; reported unmeasured rather than as zero"),
    }
    health["bottleneck"] = bottleneck_of(health)
    return health


def bottleneck_of(health: Dict[str, object]) -> Dict[str, object]:
    """Where the product is currently limited, and why.

    Ordered by which failure starves the most downstream of it, so the answer
    names the first thing that must be fixed rather than the loudest number.
    """
    available = int(health.get("market_dossiers_available") or 0)
    used = int(health.get("market_dossiers_used") or 0)
    rendered = int(health.get("market_learning_rendered") or 0)
    decisive = int(health.get("market_learning_decision_relevant") or 0)

    if int(health.get("schema_refusals") or 0) and not used:
        return {"stage": MARKET_CONSUMPTION,
                "because": "dossiers are arriving and being refused by the "
                           "contract; nothing downstream can run"}
    if int(health.get("identity_failures") or 0):
        return {"stage": IDENTITY,
                "because": "dossiers are being refused on company identity"}
    if not available:
        return {"stage": SOURCE_COVERAGE,
                "because": "no market dossier has reached this side at all"}
    if not used:
        return {"stage": MARKET_CONSUMPTION,
                "because": "dossiers arrive but none enters reasoning"}
    if not rendered:
        return {"stage": PRESENTATION,
                "because": "dossiers enter reasoning but nothing reaches a "
                           "founder-facing surface"}
    if not decisive:
        return {"stage": DECISION_IMPACT,
                "because": "market learning is rendered and changes no "
                           "decision field; it is visible but not yet useful"}
    return {"stage": NOT_LIMITED,
            "because": "market learning is arriving, rendering and changing "
                       "decision fields; the limit is now upstream of this "
                       "side"}


def render(health: Dict[str, object]) -> str:
    """Operator view. Not a founder surface."""
    b = health.get("bottleneck") or {}
    lines = [
        f"# Founder learning health — window {health.get('window')}",
        "",
        f"**Bottleneck: {b.get('stage')}** — {b.get('because')}",
        "",
        f"- Analyses seen: {health.get('analyses_seen')} across "
        f"{health.get('companies_seen')} companies",
        f"- Market dossiers available: "
        f"{health.get('market_dossiers_available')}",
        f"- Used in reasoning: {health.get('market_dossiers_used')}",
        f"- Rendered: {health.get('market_learning_rendered')}",
        f"- Changed a decision field: "
        f"{health.get('market_learning_decision_relevant')}",
        f"- Decision impact rate: {health.get('decision_impact_rate')}",
        "",
        "## Refusals",
        f"- identity {health.get('identity_failures')} · "
        f"schema {health.get('schema_refusals')} · "
        f"stale {health.get('stale_dossier_refusals')} · "
        f"no-material {health.get('no_material_refusals')}",
        "",
        "## Not observable from here",
        f"_{health.get('unmeasurable_because')}_",
    ]
    return "\n".join(lines)
