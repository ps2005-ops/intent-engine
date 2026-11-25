"""Brand Memory (§6) — the persistent, versioned brand model.

Stores voice, tone, messaging, values, positioning, claims, proof, case studies,
customer stories, quotes and visual style. Every fact is human-approved before
it is `active` (agents may only propose). The load-bearing guarantee — never
contradict previously approved messaging — is enforced by `check_consistency`,
the gate the content modules call before a draft may advance.
"""
from intent_engine.growth_os.brand.records import (  # noqa: F401
    BRAND_FACT_KINDS,
    BRAND_STREAM,
    CONSISTENCY_GATED_KINDS,
)
from intent_engine.growth_os.brand.service import (  # noqa: F401
    BrandConflict,
    BrandMemoryService,
)

__all__ = [
    "BRAND_FACT_KINDS", "BRAND_STREAM", "CONSISTENCY_GATED_KINDS",
    "BrandConflict", "BrandMemoryService",
]
