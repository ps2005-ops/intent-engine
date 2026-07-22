"""Executive Decision Intelligence Platform (T021).

This subsystem answers a triage question — *given everything we know, what
decision deserves the founder's attention next?* — so its primary artifact
is a queue of decision CANDIDATES, and a decision package is what opening
one yields.

    Candidate -> Context -> Package -> Founder Review -> Decision Record
                                                      -> Outcome
                                                      -> Knowledge

The Decision Index (`index.py`) is the executive memory, the third
canonical index, completing the layering:

    Evidence Index      (T019)  what is known
    Problem + Opportunity Index (T020)  what could be built
    Decision Index      (T021)  what deserves a decision next

Load-bearing properties:
    it owns exactly one thing — decision candidates
    the Decision Index folds from the executive log alone and resolves
        decision state through DecisionService; it never mirrors it
    a disagreement is typed and stated, never averaged into one number
    six readiness dimensions, never one overall score; financial
        readiness is UNAVAILABLE without a human declaration
    reversibility is declared per option; impact is computed from scope
    a decision expires when a load-bearing input changed, never on a clock
    every recommendation carries alternatives; approve/reject is not a
        choice, and "no recommendation" is a legitimate outcome
    the founder's override and the recorded preference both survive
    every recommendation traces to a TERMINAL state; declining is an
        answer, not a dead end
    nothing executes automatically

Canonical executive contract: `records.py`.
"""
from intent_engine.executive.records import (  # noqa: F401
    CONFLICT_KINDS, DECISION_CLASSES, DECISION_DEBT_KINDS, DECISION_HORIZONS,
    DECISION_PRINCIPLES, ESCALATION_LEVELS, IMPACT_LEVELS, QUEUES,
    REFERENCE_KINDS, REVERSIBILITY_LEVELS, ExecutiveError, ExecutiveEvent,
    scan_banned_language,
)
from intent_engine.executive.store import (  # noqa: F401
    DEFAULT_EXECUTIVE_PATH, ExecutiveCorruptLogError, ExecutiveStore,
)
from intent_engine.executive.state import (  # noqa: F401
    ExecutiveState, fold_executive,
)
from intent_engine.executive.graph import (  # noqa: F401
    DecisionGraph, assert_graph_invariants, build_graph, detect_cycles,
    order_by_dependency,
)
from intent_engine.executive.index import (  # noqa: F401
    DecisionIndex, build_index,
)
from intent_engine.executive.context import (  # noqa: F401
    build_context, decision_age, expiry_check,
)
from intent_engine.executive.conflicts import (  # noqa: F401
    conflict_summary, detect_conflicts,
)
from intent_engine.executive.debt import (  # noqa: F401
    debt_report, derive_decision_debt,
)
from intent_engine.executive.readiness import (  # noqa: F401
    aggregate_reversibility, assert_not_readiness_shaped, decision_impact,
    readiness_block,
)
from intent_engine.executive.intake import (  # noqa: F401
    candidate_from_accepted_proposal, candidate_from_decision_debt,
    candidate_from_expired_decision,
)
from intent_engine.executive.packages import (  # noqa: F401
    assign_escalation, build_no_recommendation, build_option, build_package,
)
from intent_engine.executive.queue import build_queues  # noqa: F401
from intent_engine.executive.portfolio import (  # noqa: F401
    executive_portfolio, health_dashboard,
)
from intent_engine.executive.traceability import (  # noqa: F401
    assert_no_dead_ends, trace_package,
)
from intent_engine.executive.service import (  # noqa: F401
    ExecutiveService, ModelOverreach,
)
from intent_engine.executive.snapshots import capture_snapshot  # noqa: F401
from intent_engine.executive.consumer import (  # noqa: F401
    ExecutiveCompanyEventConsumer,
)
