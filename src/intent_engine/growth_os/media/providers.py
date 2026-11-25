"""Media provider interface + injected fakes (§7, §16).

`MediaProvider` is the vendor-neutral surface. `FakeMediaProvider` drives the
full submit→poll→retrieve flow deterministically (and can simulate a failure)
with no network. `ManualExportProvider` is the honest default when no supported
programmatic API is confirmed: it never pretends to generate — it returns
ACCOUNT_OWNER_MANUAL with the export-ready package for a human to run in the
vendor tool. A real Higgsfield adapter slots in here ONLY once its supported API
is confirmed (see docs/GROWTH_OS_INTEGRATIONS.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

from intent_engine.growth_os.media.records import (
    ACCOUNT_OWNER_MANUAL,
    JOB_FAILED,
    JOB_GENERATING,
    JOB_READY,
    JOB_REQUESTED,
    ProductionPackage,
)


@dataclass
class MediaJob:
    job_id: str
    provider: str
    state: str = JOB_REQUESTED
    asset_uri: Optional[str] = None
    cost_cad: float = 0.0
    error: Optional[str] = None
    usage: dict = field(default_factory=dict)


@runtime_checkable
class MediaProvider(Protocol):
    name: str
    supports_api: bool

    def submit(self, package: ProductionPackage) -> MediaJob: ...
    def poll(self, job_id: str) -> MediaJob: ...
    def retrieve(self, job_id: str) -> MediaJob: ...


class ManualExportProvider:
    """No programmatic API — the honest default. Never fabricates generation."""
    name = "manual_export"
    supports_api = False

    def submit(self, package: ProductionPackage) -> MediaJob:
        return MediaJob(job_id=f"manual-{abs(hash(package.title)) % 10_000_000}",
                        provider=self.name, state=ACCOUNT_OWNER_MANUAL,
                        usage={"note": "export-ready package; run in the vendor tool"})

    def poll(self, job_id: str) -> MediaJob:
        return MediaJob(job_id=job_id, provider=self.name, state=ACCOUNT_OWNER_MANUAL)

    def retrieve(self, job_id: str) -> MediaJob:
        return MediaJob(job_id=job_id, provider=self.name, state=ACCOUNT_OWNER_MANUAL)


class FakeMediaProvider:
    """Deterministic API-style provider for tests/demos. submit -> generating,
    poll -> ready (or a configured failure), retrieve -> asset + recorded cost."""
    supports_api = True

    def __init__(self, name: str = "fake_media", *, fail: bool = False,
                 cost_cad: float = 1.25):
        self.name = name
        self._fail = fail
        self._cost = cost_cad
        self._jobs: dict = {}

    def submit(self, package: ProductionPackage) -> MediaJob:
        jid = f"{self.name}-{len(self._jobs) + 1}"
        self._jobs[jid] = MediaJob(job_id=jid, provider=self.name, state=JOB_GENERATING)
        return self._jobs[jid]

    def poll(self, job_id: str) -> MediaJob:
        job = self._jobs[job_id]
        if self._fail:
            job.state, job.error = JOB_FAILED, "provider rejected the render (simulated)"
        else:
            job.state = JOB_READY
        return job

    def retrieve(self, job_id: str) -> MediaJob:
        job = self._jobs[job_id]
        if job.state == JOB_READY and not job.asset_uri:
            job.asset_uri = f"https://assets.example/{job_id}.mp4"
            job.cost_cad = self._cost
            job.usage = {"seconds": 30, "provider": self.name}
        return job
