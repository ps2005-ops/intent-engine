"""Read adapters — the anti-corruption boundary (T023).

Each adapter wraps ONE subsystem's public read surface and translates its
output into the workspace's `SourceClaim` shape. The adapters exist so the
router and the rest of `personal/` never import a pile of unrelated
service modules directly, and so the workspace has one replaceable seam
when public APIs (T024) arrive.

The standing rule, asserted by test:

    an adapter may normalize field names and absence states.
    an adapter may NOT derive, score, rank, reinterpret, or enrich domain
    output.

An adapter reads; it never writes; it computes no domain intelligence. If
a subsystem cannot answer, the adapter returns an honest UNAVAILABLE /
OUT_OF_SCOPE claim — it never fabricates the missing result.
"""
from intent_engine.personal.adapters.base import (  # noqa: F401
    Adapter, out_of_scope_claim, unavailable_claim,
)
from intent_engine.personal.adapters.research import ResearchAdapter  # noqa: F401
from intent_engine.personal.adapters.product import ProductAdapter  # noqa: F401
from intent_engine.personal.adapters.executive import ExecutiveAdapter  # noqa: F401
from intent_engine.personal.adapters.crm import CRMAdapter  # noqa: F401
from intent_engine.personal.adapters.analytics import AnalyticsAdapter  # noqa: F401
from intent_engine.personal.adapters.knowledge import KnowledgeAdapter  # noqa: F401
from intent_engine.personal.adapters.decisions import DecisionsAdapter  # noqa: F401
