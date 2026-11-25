"""MediaGenerationService (§7) — provider-agnostic generation, event-sourced.

Builds an export-ready production package (refusing to fabricate a customer
outcome), optionally runs it through the Brand Memory gate, enforces a daily
budget ceiling (§14), submits to a provider, and records every job transition as
a foundation IntelRecord (recoverable on failure; ACCOUNT_OWNER_MANUAL when no
API). No network — the provider is injected.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from intent_engine.growth_os.foundation import (
    Confidence,
    GrowthOSError,
    IntelRecord,
    IntelStore,
    Provenance,
)
from intent_engine.growth_os.media.providers import MediaJob, MediaProvider
from intent_engine.growth_os.media.records import (
    ACCOUNT_OWNER_MANUAL,
    JOB_FAILED,
    JOB_READY,
    MEDIA_STREAM,
    ProductionPackage,
    StoryBeat,
)

MEDIA_REQUESTED = "media.requested"
MEDIA_READY = "media.ready"
MEDIA_FAILED = "media.failed"
MEDIA_MANUAL = "media.account_owner_manual"
MEDIA_BLOCKED_BRAND = "media.blocked_brand"
MEDIA_BUDGET_SKIPPED = "media.budget_skipped"


class MediaGenerationService:
    def __init__(self, store: IntelStore, *, brand_service=None,
                 daily_budget_cad: Optional[float] = None):
        self.store = store
        self.brand = brand_service
        self.daily_budget_cad = daily_budget_cad

    # -- package builder (never fabricates outcomes) ------------------------
    @staticmethod
    def build_package(*, fmt: str, title: str, beats: list, **kw) -> ProductionPackage:
        pkg = ProductionPackage(fmt=fmt, title=title, beats=list(beats), **kw)
        return pkg.validate()      # StoryBeat.validate refuses evidence-free results

    # -- generate -----------------------------------------------------------
    def generate(self, package: ProductionPackage, provider: MediaProvider, *,
                 actor: str = "agent", expected_cost_cad: float = 0.0) -> IntelRecord:
        package.validate()

        # brand gate: narration + captions must not contradict approved messaging
        if self.brand is not None:
            text = package.narration_script + " " + " ".join(package.captions)
            conflicts = self.brand.check_consistency(text)
            if conflicts:
                return self._event(MEDIA_BLOCKED_BRAND, package.title, actor,
                                   {"conflicts": [c.contradicting_phrase for c in conflicts]},
                                   provider="brand_gate")

        # budget ceiling (§14): stop safely, keep the package, report the reason
        if self.daily_budget_cad is not None:
            if self.daily_cost() + expected_cost_cad > self.daily_budget_cad:
                return self._event(MEDIA_BUDGET_SKIPPED, package.title, actor,
                                   {"reason": "daily media budget reached",
                                    "package": package.as_dict()}, provider="budget")

        job = provider.submit(package)
        if job.state == ACCOUNT_OWNER_MANUAL:
            return self._event(MEDIA_MANUAL, package.title, actor,
                               {"job": job.job_id, "package": package.as_dict(),
                                "instructions": "run this package in the vendor tool"},
                               provider=job.provider)
        job = provider.poll(job.job_id)
        if job.state == JOB_FAILED:
            # recoverable: the package is retained on the failure event
            return self._event(MEDIA_FAILED, package.title, actor,
                               {"job": job.job_id, "error": job.error,
                                "package": package.as_dict()}, provider=job.provider)
        job = provider.retrieve(job.job_id) if job.state == JOB_READY else job
        return self._event(MEDIA_READY, package.title, actor,
                           {"job": job.job_id, "asset_uri": job.asset_uri,
                            "cost_cad": job.cost_cad, "usage": job.usage},
                           provider=job.provider, cost_cad=job.cost_cad)

    # -- cost tracking ------------------------------------------------------
    def daily_cost(self, *, day: Optional[str] = None) -> float:
        day = day or datetime.now(timezone.utc).date().isoformat()
        return round(sum(
            r.payload.get("cost_cad", 0.0) or 0.0
            for r in self.store.for_event_type(MEDIA_READY)
            if r.recorded_at[:10] == day), 4)

    # -- event write --------------------------------------------------------
    def _event(self, event_type: str, title: str, actor: str, payload: dict, *,
               provider: str, cost_cad: float = 0.0) -> IntelRecord:
        method = "manual" if event_type == MEDIA_MANUAL else "derived"
        rec = IntelRecord(
            stream=MEDIA_STREAM, event_type=event_type, actor=actor,
            provenance=Provenance(source=provider, method=method),
            confidence=Confidence(0.8, basis=f"media job via {provider}"),
            payload={"title": title, "cost_cad": cost_cad, **payload})
        return self.store.append(rec)
