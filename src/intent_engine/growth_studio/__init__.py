"""V2.0 — Founder Growth Studio: bounded continuous planning around one
client (Founder Intelligence). Orchestrates existing Marketing, Growth,
Research, Analytics, CRM, Personal AI, and AgentOS capability through
references. No external execution surface exists in this package.
"""
from intent_engine.growth_studio.adapters import (
    funnel_metrics_from_fi_store, growth_experiment_refs,
    marketing_portfolio,
)
from intent_engine.growth_studio.briefing import (
    BRIEF_SECTIONS, CONFIDENCE_BANDS, compose_brief, statement,
)
from intent_engine.growth_studio.channels import check_draft
from intent_engine.growth_studio.fixtures import FIXTURE_NOTE, build_fixture
from intent_engine.growth_studio.learning import (
    CANDIDATE_REQUIRED, MIN_SAMPLE, validate_candidate,
)
from intent_engine.growth_studio.records import (
    BRAND_RESEARCH_EXPERIMENT, CHANNELS, CLAIM_CLASSES, FUNNEL,
    FUNNEL_TRANSITIONS, LOOP_STATES, LOOP_TRANSITIONS,
    MANUAL_PUBLICATION_ACTORS, PRODUCT_ID, RECORD_KINDS, StudioError,
    StudioEvent, require_scope,
)
from intent_engine.growth_studio.service import (
    EXPERIMENT_PLAN_REQUIRED, MAX_MODEL_CALLS_PER_RUN, GrowthStudioService,
)
from intent_engine.growth_studio.store import (
    DEFAULT_STUDIO_PATH, StudioCorruptLogError, StudioStore,
)

__all__ = [
    "BRAND_RESEARCH_EXPERIMENT", "BRIEF_SECTIONS", "CANDIDATE_REQUIRED",
    "CHANNELS", "CLAIM_CLASSES", "CONFIDENCE_BANDS", "DEFAULT_STUDIO_PATH",
    "EXPERIMENT_PLAN_REQUIRED", "FIXTURE_NOTE", "FUNNEL",
    "FUNNEL_TRANSITIONS", "GrowthStudioService", "LOOP_STATES",
    "LOOP_TRANSITIONS", "MANUAL_PUBLICATION_ACTORS",
    "MAX_MODEL_CALLS_PER_RUN", "MIN_SAMPLE", "PRODUCT_ID", "RECORD_KINDS",
    "StudioCorruptLogError", "StudioError", "StudioEvent", "StudioStore",
    "build_fixture", "check_draft", "compose_brief",
    "funnel_metrics_from_fi_store", "growth_experiment_refs",
    "marketing_portfolio", "require_scope", "statement",
    "validate_candidate",
]
