"""CRM and Customer Intelligence (T014) — the first real consumer of the
Company Event System.

Ownership boundary (load-bearing):

    DecisionService       owns decision identity + lifecycle
    Prediction Ledger     owns prediction claims + outcomes
    Company Event System  owns integration delivery
    CRM (this package)    owns prospect/customer relationship history and
                          the signals DERIVED from it

The CRM references decision_id / decision_key / company event ids; it
never allocates decision ids, never infers or mutates decision state,
never rewrites company events, never sends outreach, and never approves
anything. History is append-only (`marketing/crm/crm.jsonl`); every
current state is a fold; health and conversion are computed by versioned
code rules, never stored as opinions and never asked of a model.

Canonical CRM contract: `events.py` (envelope + taxonomy). Docs
cross-reference it; nothing restates it.
"""
from intent_engine.crm.events import (  # noqa: F401
    CRM_EVENT_TYPES, CRMEvent, CRMEnvelopeError,
)
from intent_engine.crm.state import (  # noqa: F401
    CRMState, CRMTransitionError, fold_crm,
)
from intent_engine.crm.service import CRMService, DEFAULT_CRM_PATH  # noqa: F401
from intent_engine.crm.signals import (  # noqa: F401
    CONVERSION_RULE_VERSION, HEALTH_RULE_VERSION, conversion_signal,
    health_signal,
)
from intent_engine.crm.consumer import CRMCompanyEventConsumer  # noqa: F401
