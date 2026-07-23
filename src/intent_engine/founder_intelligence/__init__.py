"""Founder Intelligence Experience (T023.5) — the first sellable product.

A founder enters a company name + website and receives an evidence-backed
executive experience that earns trust in one order:

    prove knowledge -> reveal perspective -> invite investigation ->
        enable conversation

It is an evidence-backed executive analyst, not an AI consultant that
invents advice and not an autonomous operator. Every conclusion resolves to
an exact source artifact, replay id, and freshness state (reusing the T023
`SourceRef` / `SourceClaim` contract). It computes no business
intelligence, holds no action surface, invents no competitor and no
statistic, asserts no unsupported causality, and preserves disagreement,
staleness, and unavailability. There is no company master score.

Live company ingestion, authentication, public deployment, and a real-
browser pass are recorded dependency gaps
(`docs/T0235_DEPENDENCY_GAPS.md`); T023.5 is PRODUCT BUILT / CONTROLLED
DEMO READY, not deployed and not launched.

Canonical contract: `records.py`.
"""
from intent_engine.founder_intelligence.records import (  # noqa: F401
    CompanyIdentity, CompanyInput, FounderIntelligenceError,
    FounderIntelligenceEvent, InsightCard, IntelligenceSection, RUN_STATES,
    SecretRejected, SourceClaim, SourceRef, TRUST_SEQUENCE, UnsafeURLRejected,
    assert_trust_sequence, validate_public_url,
)
from intent_engine.founder_intelligence.store import (  # noqa: F401
    DEFAULT_FI_PATH, FounderIntelligenceCorruptLogError,
    FounderIntelligenceStore,
)
from intent_engine.founder_intelligence.state import (  # noqa: F401
    WorkspaceRuns, fold_runs,
)
from intent_engine.founder_intelligence.identity import (  # noqa: F401
    is_duplicate, resolve_identity,
)
from intent_engine.founder_intelligence.intake import (  # noqa: F401
    CONSENT_STATEMENT, validate_input,
)
from intent_engine.founder_intelligence.ingestion import (  # noqa: F401
    ingest_approved_text, retrieval_gap,
)
from intent_engine.founder_intelligence.hooks import select_hook  # noqa: F401
from intent_engine.founder_intelligence.fixtures import (  # noqa: F401
    DEMO_COMPANY_NAME, DEMO_DOMAIN, demo_claims,
)
from intent_engine.founder_intelligence.service import (  # noqa: F401
    FounderIntelligenceService,
)
from intent_engine.founder_intelligence.snapshots import (  # noqa: F401
    capture_snapshot,
)
from intent_engine.founder_intelligence.presentation import (  # noqa: F401
    render_landing_html, render_report_preview, render_result_html,
    result_view_model,
)
