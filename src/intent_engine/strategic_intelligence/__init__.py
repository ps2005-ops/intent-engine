"""V1.2 Strategic Intelligence — an evidence-backed, outside-in strategic
reasoning layer that sits AFTER ingestion and claim extraction.

It does not claim private/internal knowledge and it never "trains live" on a
company. It retrieves approved public sources, derives structured
observations, matches them against a curated, auditable historical-pattern
library, and produces evidence-backed strategic hypotheses — each with its
reasoning chain, supporting evidence, counter-evidence, an alternative
explanation, calibrated confidence, evidence gaps, a decision implication, and
a falsification test.

Public surface:
    build_strategic_report(...)      -> StrategicReport   (reasoning.py)
    evaluate_report(report)          -> (status, findings) (quality.py)
    render_strategic_report(report)  -> str (HTML)         (render.py)
    answer_strategic(question, ...)  -> dict               (conversation.py)
    PATTERN_LIBRARY                                          (patterns.py)
"""
from intent_engine.strategic_intelligence.records import (  # noqa: F401
    EVIDENCE_KINDS, OBSERVATION_TYPES, SOURCE_CLASSES, ComparablePattern,
    StrategicHypothesis, StrategicObservation, StrategicQuestion,
    StrategicReport,
)
from intent_engine.strategic_intelligence.patterns import (  # noqa: F401
    PATTERN_LIBRARY, TENSIONS,
)
from intent_engine.strategic_intelligence.reasoning import (  # noqa: F401
    build_strategic_report,
)
from intent_engine.strategic_intelligence.quality import (  # noqa: F401
    STRATEGIC_STATUSES, evaluate_report, looks_low_value,
)
