"""Learning & Promotion Ledger (unified-learning platform).

The platform-wide primitive the founder's architecture calls the "brain":
every subsystem that learns — paper trading, synthetic worlds, calibration,
marketing — proposes improvement *candidates* here, evidence accrues as
*evaluations*, and only a human-authorized, criteria-met *promotion* ever
changes production. It generalizes the acceptance wall first proven in
`growth_studio/learning.py` so no subsystem reinvents it.

Cadence (founder's "learn every day, promote on evidence"):
    DAILY    propose candidates      (LearningLedger.propose)
    WEEKLY   evaluate vs current     (LearningLedger.evaluate)
    MONTHLY  promote / reject        (LearningLedger.promote — HUMAN wall)
"""
from intent_engine.learning.records import (  # noqa: F401
    Candidate, CandidateSource, Evaluation, EvaluationKind,
    EvaluationVerdict, LearningError, PromotionDecision, SuccessCriterion,
    beats_baseline, clears,
)
from intent_engine.learning.ledger import (  # noqa: F401
    DEFAULT_LEARNING_PATH, LearningStore,
)
from intent_engine.learning.service import (  # noqa: F401
    MIN_EVALUATIONS_TO_PROMOTE, PRODUCER, LearningLedger,
)
