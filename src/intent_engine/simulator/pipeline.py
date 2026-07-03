"""Composes the Week 1 pipeline: raw input -> intent -> risk audit, with timing.

Kept as an explicit function rather than a generic chained Pipeline runner because the
outcome-simulation stage needs both the classifier's output AND the original context,
not just the previous stage's output. Each stage is still independently swappable and
unit-testable via the Stage classes in core.classifier / simulator.outcome_simulation.
"""

import time
from typing import NamedTuple, Optional

from ..core.classifier import IntentClassifier
from ..core.llm_client import LLMClient
from ..core.schemas import RawInput, RiskAudit, StructuredIntent
from .context_schema import BusinessContext
from .outcome_simulation import RiskAuditGenerator


class PremortemResult(NamedTuple):
    intent: StructuredIntent
    risk_audit: RiskAudit
    elapsed_seconds: float


def run_premortem(
    decision_text: str,
    context: BusinessContext,
    client: Optional[LLMClient] = None,
    classifier: Optional[IntentClassifier] = None,
    audit_generator: Optional[RiskAuditGenerator] = None,
) -> PremortemResult:
    classifier = classifier or IntentClassifier(client=client)
    audit_generator = audit_generator or RiskAuditGenerator(client=client)

    start = time.monotonic()

    raw_input = RawInput(decision_text=decision_text, context_text=context.to_prompt_text())
    intent = classifier.run(raw_input)
    risk_audit = audit_generator.run(decision_text, context, intent)

    elapsed = time.monotonic() - start
    return PremortemResult(intent=intent, risk_audit=risk_audit, elapsed_seconds=elapsed)
