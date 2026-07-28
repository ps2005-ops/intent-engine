"""Grounded strategic analyst.

The deterministic pipeline in the package above this one is good at what it is
for: retrieving evidence, classifying whose account it is, resolving citations,
and refusing to overstate confidence. It is structurally incapable of one
thing, which is the thing a reader actually wants -- saying something about
THIS company that a competent executive did not already know.

A pattern library can only emit sentences an author wrote in advance. Written
generically enough to fire on many companies, those sentences say nothing;
written specifically enough to say something, they fire on almost nobody. That
is not a tuning problem, and no number of additional scaffolds resolves it.
Sony Interactive Entertainment being told it was "turning a people-delivered
service into a repeatable product" is what the failure looks like from the
generic end.

So reasoning moves to a model, and the deterministic layer keeps the jobs it
is genuinely better at:

    evidence acquisition  ->  deterministic   (retrieval, EDGAR, provenance)
    reasoning             ->  the analyst     (grounded, cited, structured)
    verification          ->  deterministic   (the critic, below)

The critic is not a formality. The analyst's output is rejected outright if a
citation does not resolve, if a number appears that is in no source, if the
claim would read identically for an unrelated company, or if a subsidiary is
described using its parent's facts. A rejected analysis does NOT fall back to
the generic scaffolds -- it produces an honest evidence-limited result.
"""
from intent_engine.strategic_intelligence.analyst.contract import (
    ANALYSIS_SCHEMA, PROMPT_VERSION, AnalysisRejected, ResultState,
    StrategicAnalysis,
)
from intent_engine.strategic_intelligence.analyst.critic import (
    CriticFinding, verify_analysis,
)
from intent_engine.strategic_intelligence.analyst.runner import (
    AnalystUnavailable, analyse,
)

__all__ = [
    "ANALYSIS_SCHEMA", "PROMPT_VERSION", "AnalysisRejected", "ResultState",
    "StrategicAnalysis", "CriticFinding", "verify_analysis",
    "AnalystUnavailable", "analyse",
]
