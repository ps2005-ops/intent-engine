"""Marketing Automation C3–C8 (T017).

Marketing owns workflow artifacts: campaigns, audience selections,
briefs, drafts, review packages, publishing handoffs, and performance
observations. It reuses — and never reimplements — the CRM approval wall
(T014), the quote-consent gate (T016), the claim gate (T013 company
events), the analytics honesty markers (T015), and the C1 content
engine's claim audit.

Drafting may be automated. Approval and publication may not. This
subsystem never publishes or sends anything externally; a publication is
an OBSERVED fact supplied from outside.

Canonical marketing contract: `records.py`.
"""
from intent_engine.marketing.records import (  # noqa: F401
    CLAIMS_REQUIRING_REVIEW, MARKETING_EVENT_TYPES, MarketingError,
    MarketingRow, claim_identity, scan_banned_language,
)
from intent_engine.marketing.state import (  # noqa: F401
    MarketingState, fold_marketing,
)
from intent_engine.marketing.service import (  # noqa: F401
    DEFAULT_MARKETING_PATH, MarketingService,
)
from intent_engine.marketing.audience import (  # noqa: F401
    AUDIENCE_RULE_VERSION, select_audience,
)
from intent_engine.marketing.drafts import (  # noqa: F401
    VALIDATOR_VERSION, detect_claims, validate_draft,
)
from intent_engine.marketing.consumer import (  # noqa: F401
    MarketingCompanyEventConsumer,
)
