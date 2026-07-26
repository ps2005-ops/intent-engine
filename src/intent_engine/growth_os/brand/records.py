"""Brand Memory taxonomy (§6). Pure constants, no I/O."""
from __future__ import annotations

BRAND_STREAM = "brand_memory"

# Everything the brand model remembers (§6).
BRAND_FACT_KINDS = {
    "voice", "tone", "messaging", "value", "positioning", "claim", "proof",
    "case_study", "customer_story", "quote", "visual_style",
}

# Kinds that constrain outbound copy — content is checked against the ACTIVE
# facts of these kinds so it never contradicts approved messaging.
CONSISTENCY_GATED_KINDS = {"messaging", "positioning", "claim", "value"}

# event types on the brand stream
BRAND_PROPOSED = "brand.fact_proposed"
BRAND_APPROVED = "brand.fact_approved"     # HUMAN ONLY
BRAND_RETIRED = "brand.fact_retired"       # HUMAN ONLY

# Only humans may approve or retire brand facts — agents can only propose.
HUMAN_ONLY_BRAND_EVENTS = {BRAND_APPROVED, BRAND_RETIRED}
