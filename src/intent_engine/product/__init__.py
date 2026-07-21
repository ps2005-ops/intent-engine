"""Product Strategy & Roadmap Intelligence Platform (T020).

This subsystem owns PROPOSALS. The founder owns decisions.

    Problem  ->  Opportunity  ->  Proposal  ->  Spec Draft  ->  Founder Review
                                                            ->  Decision Record
                                                            ->  Execution Candidate

The Problem Index and the Opportunity Index (`index.py`) are the product
memory that later agents read instead of rebuilding, exactly as the
Evidence Index is for research. Neither is ever written by a model.

Load-bearing properties:
    every artifact begins with a problem, its evidence, why now, and what
        changes if it is ignored — before any solution exists
    a problem with zero evidence references is rejected
    one problem may carry several competing opportunities and proposals;
        the founder chooses among a solution set
    `merged_into` and `deferred` are first-class founder answers, because
        a system that models only accept/reject distorts the real choice
    known, unknown, and assumptions are mandatory and separately stored
    a dimension with no recorded input is UNAVAILABLE, not zero
    strategic alignment comes from a human declaration; an agent does not
        infer strategy
    uncertainty travels: an unsettled origin cannot yield a confident
        opportunity
    priority, sequencing, blocking, and readiness are four questions, not
        one
    `ROADMAP.md` is never written here — a diff is emitted for a person to
        apply
    nothing executes automatically

Canonical product contract: `records.py`.
"""
from intent_engine.product.records import (  # noqa: F401
    PRODUCT_PRINCIPLES, PROPOSAL_EDGES, REFERENCE_KINDS, SPEC_SECTIONS,
    TERMINAL_PROPOSAL_STATUSES, WORK_CATEGORIES, ProductError, ProductEvent,
    scan_banned_language,
)
from intent_engine.product.store import (  # noqa: F401
    DEFAULT_PRODUCT_PATH, ProductCorruptLogError, ProductStore,
)
from intent_engine.product.state import (  # noqa: F401
    ProductState, fold_product,
)
from intent_engine.product.problems import (  # noqa: F401
    build_problem_statement, normalize_problem, problem_dedup_key,
    validate_reference,
)
from intent_engine.product.graph import (  # noqa: F401
    ProposalGraph, assert_graph_invariants, build_graph, detect_cycles,
    sequence,
)
from intent_engine.product.index import (  # noqa: F401
    OpportunityIndex, ProblemIndex, build_index,
)
from intent_engine.product.scoring import (  # noqa: F401
    SCORE_VERSIONS, assert_not_score_shaped, cost_of_delay, score_block,
)
from intent_engine.product.proposals import (  # noqa: F401
    build_proposal, solution_set_report,
)
from intent_engine.product.specs import (  # noqa: F401
    build_spec_draft, derive_spec_debt, spec_debt_report,
)
from intent_engine.product.intake import (  # noqa: F401
    intake_candidates_from_crm, intake_candidates_from_growth,
    intake_candidates_from_research_debt,
)
from intent_engine.product.portfolio import (  # noqa: F401
    balance_report, executive_summary, portfolio_rollup, readiness_report,
)
from intent_engine.product.bundles import assemble_bundle  # noqa: F401
from intent_engine.product.roadmap_diff import (  # noqa: F401
    build_roadmap_candidate, render_roadmap_diff,
)
from intent_engine.product.service import ProductService  # noqa: F401
from intent_engine.product.snapshots import (  # noqa: F401
    capture_portfolio_snapshot, capture_proposal_snapshot,
)
from intent_engine.product.consumer import (  # noqa: F401
    ProductCompanyEventConsumer,
)
