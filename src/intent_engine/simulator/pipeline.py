"""Composes the Week 1 pipeline: raw input -> intent -> risk audit, with timing.

Uses the combined PremortemAnalyzer stage by default (one Claude call, ~7-8s) rather than
chaining the separate IntentClassifier + RiskAuditGenerator stages (two calls, ~20s+),
which blew the spec's <10s budget. Pass an `analyzer=` override to use a different
implementation (e.g. the two-stage version) for comparison or future domains with a
looser latency budget.
"""

import time
from typing import NamedTuple, Optional

from ..core.llm_client import LLMClient
from ..core.schemas import RiskAudit, StructuredIntent
from .analysis import PremortemAnalyzer
from .context_schema import BusinessContext
from .schemas import ScenarioSet


class PremortemResult(NamedTuple):
    intent: StructuredIntent
    risk_audit: RiskAudit
    scenario_set: ScenarioSet
    elapsed_seconds: float
    # T005 additive field (docs/TASK4_SPEC_PROPOSAL.md): None when the
    # mechanism section wasn't requested; [] when requested but nothing
    # matched (correct silence); populated list otherwise. Defaulted, so
    # every existing caller/unpacking site is unaffected.
    ranked_mechanisms: Optional[list] = None


def run_premortem(
    decision_text: str,
    context: BusinessContext,
    client: Optional[LLMClient] = None,
    analyzer: Optional[PremortemAnalyzer] = None,
    mechanism_client: Optional[LLMClient] = None,
) -> PremortemResult:
    """`mechanism_client` (T005): when provided, ONE additional isolated
    extraction call computes the structural-mechanisms read (see
    simulator/mechanism_section.py) -- the combined-call analyzer prompt is
    untouched either way (hard wall A3; LuckTest isolation pattern).
    Default None: zero new calls, zero behavior change."""
    analyzer = analyzer or PremortemAnalyzer(client=client)

    start = time.monotonic()
    result = analyzer.run(decision_text, context)

    ranked_mechanisms = None
    if mechanism_client is not None:
        from .mechanism_section import compute_ranked_mechanisms
        ranked_mechanisms = compute_ranked_mechanisms(decision_text, client=mechanism_client)
    elapsed = time.monotonic() - start

    return PremortemResult(
        intent=result.intent,
        risk_audit=result.risk_audit,
        scenario_set=result.scenario_set,
        elapsed_seconds=elapsed,
        ranked_mechanisms=ranked_mechanisms,
    )
