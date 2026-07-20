"""Knowledge Promotion and Feedback (T016).

Feedback is evidence, not automatically knowledge. An insight is a
proposal until a human validates it. Knowledge must be cited, scoped,
limited, and versioned. Quotes require exact, explicit human consent.
Mechanism proposals go to review — the frozen library
(core/data/mechanisms.json) is NEVER written by this package.

Canonical knowledge contract: `records.py`. Docs cross-reference it.
"""
from intent_engine.knowledge.records import (  # noqa: F401
    BANNED_CLAIM_LANGUAGE, KNOWLEDGE_CATEGORIES, KnowledgeError, Row,
)
from intent_engine.knowledge.service import (  # noqa: F401
    DEFAULT_FEEDBACK_PATH, DEFAULT_KNOWLEDGE_PATH, KnowledgeService,
)
from intent_engine.knowledge.consumer import (  # noqa: F401
    KnowledgeCompanyEventConsumer,
)
