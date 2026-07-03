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


def run_premortem(
    decision_text: str,
    context: BusinessContext,
    client: Optional[LLMClient] = None,
    analyzer: Optional[PremortemAnalyzer] = None,
) -> PremortemResult:
    analyzer = analyzer or PremortemAnalyzer(client=client)

    start = time.monotonic()
    result = analyzer.run(decision_text, context)
    elapsed = time.monotonic() - start

    return PremortemResult(
        intent=result.intent,
        risk_audit=result.risk_audit,
        scenario_set=result.scenario_set,
        elapsed_seconds=elapsed,
    )
