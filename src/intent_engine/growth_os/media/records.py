"""Media taxonomy + the export-ready production package (§7). Pure, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from intent_engine.growth_os.foundation.records import GrowthOSError

MEDIA_STREAM = "growth_media"

# Faceless formats the system supports (§7) — none impersonates a real person.
FACELESS_FORMATS = {
    "cinematic_product_story", "narrated_screen_recording", "motion_graphics",
    "data_story", "founder_style_explainer", "before_after_workflow",
    "case_study_video",
}

# The narrative beats every asset should communicate (§7), in order.
STORY_BEATS = (
    "user_problem", "costly_current_workflow", "reasoning_process", "evidence",
    "product_interaction", "measurable_result", "cta",
)

# Job lifecycle. ACCOUNT_OWNER_MANUAL = no supported programmatic interface; the
# package is export-ready and a human runs it in the vendor tool.
JOB_REQUESTED = "requested"
JOB_GENERATING = "generating"
JOB_READY = "ready"
JOB_FAILED = "failed"
ACCOUNT_OWNER_MANUAL = "account_owner_manual"
JOB_STATES = (JOB_REQUESTED, JOB_GENERATING, JOB_READY, JOB_FAILED, ACCOUNT_OWNER_MANUAL)


@dataclass
class StoryBeat:
    beat: str
    text: str
    # `result`/evidence beats must reference real, provenanced evidence — never
    # a fabricated customer outcome or testimonial.
    evidence_ref: Optional[str] = None

    def validate(self) -> "StoryBeat":
        if self.beat not in STORY_BEATS:
            raise GrowthOSError(f"unknown story beat {self.beat!r}")
        if self.beat in ("measurable_result", "evidence") and not self.evidence_ref:
            raise GrowthOSError(
                f"the {self.beat!r} beat needs an evidence_ref — never fabricate "
                "a customer outcome or testimonial")
        return self


@dataclass
class ProductionPackage:
    """Provider-agnostic, export-ready package: everything a human OR a real
    provider API needs to produce the asset."""
    fmt: str
    title: str
    beats: list                       # list[StoryBeat]
    shot_list: list = field(default_factory=list)
    narration_script: str = ""
    captions: list = field(default_factory=list)
    thumbnail_concept: str = ""
    prompts: dict = field(default_factory=dict)   # provider prompt inputs
    b_roll_suggestions: list = field(default_factory=list)

    def validate(self) -> "ProductionPackage":
        if self.fmt not in FACELESS_FORMATS:
            raise GrowthOSError(f"format {self.fmt!r} not in {sorted(FACELESS_FORMATS)}")
        if not self.beats:
            raise GrowthOSError("a production package needs story beats")
        for b in self.beats:
            b.validate()
        return self

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)
