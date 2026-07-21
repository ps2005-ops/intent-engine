"""Growth & Experiment Intelligence (T018).

An experiment is a PRE-REGISTERED COMMITMENT, not a query run against
data that already exists. This package is built so the dishonest version
is impossible rather than merely discouraged:

    there is no `winner` field to populate
    a stopping rule being satisfied is a FACT, not an ACTION
    nothing rolls out, rolls back, launches, or reassigns itself
    an experiment without a control arm is permanently OBSERVATIONAL ONLY
    a statistic whose assumptions fail is UNAVAILABLE, with the assumption named
    survivorship counts travel with every result
    peeking is allowed; hiding that you peeked is not
    synthetic and production experiments can never be mixed

Canonical growth contract: `records.py`.
"""
from intent_engine.growth.records import (  # noqa: F401
    GROWTH_EVENT_TYPES, LABEL_DIFFERENCE, LABEL_INCONCLUSIVE,
    LABEL_OBSERVATIONAL, LABEL_TOO_FEW, MODIFIER_NO_CAUSAL_CLAIM,
    MODIFIER_REVIEW_REQUIRED, NAMESPACE_PRODUCTION, NAMESPACE_SYNTHETIC,
    GrowthError, GrowthEvent, scan_banned_language,
)
from intent_engine.growth.state import (  # noqa: F401
    ExperimentState, fold_experiment,
)
from intent_engine.growth.randomization import (  # noqa: F401
    RANDOMIZATION_METHOD, assign,
)
from intent_engine.growth.statistics import (  # noqa: F401
    arm_counts, difference_in_proportions,
)
from intent_engine.growth.results import (  # noqa: F401
    LABEL_RULE_VERSION, compute_result, participation_funnel,
)
from intent_engine.growth.service import GrowthService  # noqa: F401
from intent_engine.growth.snapshots import (  # noqa: F401
    capture_snapshot, get_snapshot,
)
from intent_engine.growth.consumer import (  # noqa: F401
    GrowthCompanyEventConsumer,
)
