"""Media Generation (§7) — vendor-neutral, provider-abstracted.

The provider interface covers storyboard/image/video/shot-planning/narration/
caption/thumbnail generation, status polling, asset retrieval, cost + usage
recording and failure handling. Real adapters (e.g. a Higgsfield adapter) are
added ONLY when a supported API is confirmed; until then the system produces an
export-ready production package and marks execution ACCOUNT_OWNER_MANUAL,
preserving the abstraction. Media never fabricates customer outcomes or
testimonials — the `result` beat must reference real, provenanced evidence.
"""
from intent_engine.growth_os.media.records import (  # noqa: F401
    ACCOUNT_OWNER_MANUAL,
    FACELESS_FORMATS,
    JOB_STATES,
    MEDIA_STREAM,
    STORY_BEATS,
    ProductionPackage,
    StoryBeat,
)
from intent_engine.growth_os.media.providers import (  # noqa: F401
    FakeMediaProvider,
    ManualExportProvider,
    MediaJob,
    MediaProvider,
)
from intent_engine.growth_os.media.service import MediaGenerationService  # noqa: F401

__all__ = [
    "ACCOUNT_OWNER_MANUAL", "FACELESS_FORMATS", "JOB_STATES", "MEDIA_STREAM",
    "STORY_BEATS", "ProductionPackage", "StoryBeat", "MediaProvider",
    "FakeMediaProvider", "ManualExportProvider", "MediaJob",
    "MediaGenerationService",
]
