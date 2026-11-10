"""Canonical PUBLIC state for a company, so a second run is not a first one.

WHY THIS EXISTS
---------------
MEASURED on the deployed preview at 517180e6:

    Microsoft   CORE 107.78s   discovery 27.7s + retrieval 40.5s = 63%
    Apple       CORE  72.2s /  84.5s, same shape

Every run rediscovers the company from nothing: the same candidate URLs are
proposed, the same filings are located, the same pages are fetched and parsed.
For one company that is merely slow. For a fifty-company cohort, and for the
same company looked at twice in a day, it is the dominant cost and none of it
is new information.

WHAT THIS IS NOT
----------------
NOT a cached answer. A snapshot holds what is PUBLIC and slow to find --
identity, where the documents are, what they hashed to -- and never a
recommendation, a thesis, a DecisionDelta or an observation. Those are
recomputed from current evidence and the current EconomicState on every run,
because a cached conclusion is how a product starts telling a reader something
it no longer believes.

The test for whether a field belongs here is: would a reader be misled if this
were three days old and labelled as such? A filing accession number, no. A
recommendation, yes.

DURABILITY IS NOT CLAIMED
-------------------------
This deployment's runtime root is writable and EPHEMERAL -- `/readyz` reports
`EPHEMERAL_LIKELY`, and there is no persistent disk. Snapshots therefore
survive within a deployment lifetime and are lost on redeploy. That is enough
to make a second analysis cheap and enough to prove the architecture; it is
NOT restart-survival evidence and is never reported as such. Every snapshot
carries `durability` so a reader of the file cannot mistake one for the other.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import time
from typing import Optional

SCHEMA = "public_company_snapshot.v1"

#: Written by a deployment that cannot promise survival across a restart.
EPHEMERAL = "EPHEMERAL"
DURABLE = "DURABLE_PROVEN"

#: How old a snapshot may be before its SOURCE LIST is re-derived. Identity
#: does not rot; where the documents live does, slowly. A day is chosen
#: because filings appear on a business-day cadence, not because it is round.
DEFAULT_MAX_AGE_S = 24 * 3600


@dataclasses.dataclass(frozen=True)
class SourceRecord:
    """One document this company published, as we last saw it."""
    url: str
    #: Content hash of the body we parsed. The ONLY reliable "did this
    #: change?" signal for a page that carries no validators.
    content_hash: str = ""
    #: HTTP validators, when the host offered them. Cheaper than a hash
    #: because a conditional request avoids the download entirely.
    etag: str = ""
    last_modified: str = ""
    #: EDGAR accession, when this is a filing. A filing is immutable once
    #: accessioned, so this is the strongest unchanged-signal there is.
    accession: str = ""
    form: str = ""
    source_class: str = ""
    fetched_at: float = 0.0
    bytes: int = 0

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class PublicCompanySnapshot:
    """What is public, canonical, and expensive to rediscover."""
    company_key: str
    canonical_name: str = ""
    aliases: tuple = ()
    ticker: str = ""
    cik: str = ""
    domains: tuple = ()
    #: The evidence index: where this company's documents were, and what they
    #: hashed to. NOT the documents themselves and NOT what they meant.
    sources: tuple = ()
    #: Structural facts a filing states about itself -- SIC code, segment
    #: names, business-model class. Descriptive, not concluded.
    structural: dict = dataclasses.field(default_factory=dict)
    provenance: dict = dataclasses.field(default_factory=dict)
    econ_state_version: str = ""
    created_at: float = 0.0
    refreshed_at: float = 0.0
    schema: str = SCHEMA
    #: EPHEMERAL on any deployment without a proven disk. Carried in the file
    #: so a snapshot can never be mistaken for restart-survival evidence.
    durability: str = EPHEMERAL

    def age_s(self, now: Optional[float] = None) -> float:
        return max(0.0, (now if now is not None else time.time())
                   - (self.refreshed_at or self.created_at or 0.0))

    def is_fresh(self, *, max_age_s: float = DEFAULT_MAX_AGE_S,
                 now: Optional[float] = None) -> bool:
        return bool(self.refreshed_at or self.created_at) and \
            self.age_s(now) <= max_age_s

    def source_for(self, url: str) -> Optional[SourceRecord]:
        for s in self.sources:
            if s.url == url:
                return s
        return None

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["sources"] = [s.as_dict() if isinstance(s, SourceRecord) else dict(s)
                        for s in self.sources]
        d["aliases"] = list(self.aliases)
        d["domains"] = list(self.domains)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PublicCompanySnapshot":
        d = dict(d or {})
        d["sources"] = tuple(SourceRecord(**s) for s in (d.get("sources") or ()))
        d["aliases"] = tuple(d.get("aliases") or ())
        d["domains"] = tuple(d.get("domains") or ())
        return cls(**{k: v for k, v in d.items()
                      if k in {f.name for f in dataclasses.fields(cls)}})


def company_key(name: str, *, cik: str = "", domain: str = "") -> str:
    """A stable key for one company.

    CIK FIRST, because it is the only identifier a company cannot change and
    two companies cannot share. Falling back to a normalised name is what
    lets a name-only run reuse a snapshot at all, and it is deliberately
    second: "Linear" once satisfied an alias for "Linear Minerals Corp."
    """
    if cik:
        return f"cik:{str(cik).lstrip('0') or '0'}"
    if domain:
        d = str(domain).lower().replace("https://", "").replace("http://", "")
        d = d.replace("www.", "").strip("/")
        if d:
            return f"domain:{d}"
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(name))
    return "name:" + "-".join(p for p in slug.split("-") if p)


class SnapshotStore:
    """One JSON file per company under the runtime root.

    Deliberately a file per company rather than one index: a fifty-company
    cohort writes fifty independent files and a torn write can cost one
    company's reuse, never the cohort's.
    """

    def __init__(self, runtime_root, *, durability: str = EPHEMERAL):
        self.root = pathlib.Path(runtime_root) / "snapshots"
        self.durability = durability

    def _path(self, key: str) -> pathlib.Path:
        safe = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Optional[PublicCompanySnapshot]:
        try:
            raw = self._path(key).read_text()
        except (OSError, ValueError):
            return None
        try:
            d = json.loads(raw)
        except ValueError:
            return None
        if d.get("schema") != SCHEMA:
            # A snapshot written by a different shape is not read. Migrating
            # it silently is how a field means two things at once.
            return None
        try:
            return PublicCompanySnapshot.from_dict(d)
        except (TypeError, ValueError):
            return None

    def put(self, snap: PublicCompanySnapshot) -> bool:
        """Write, or say it did not. Never raises: a snapshot that cannot be
        stored costs the NEXT run its head start and nothing else."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            d = snap.as_dict()
            # The writer stamps durability, not the caller: a snapshot must
            # not be able to claim more than its deployment can support.
            d["durability"] = self.durability
            tmp = self._path(snap.company_key).with_suffix(".tmp")
            tmp.write_text(json.dumps(d, sort_keys=True))
            tmp.replace(self._path(snap.company_key))
            return True
        except (OSError, ValueError, TypeError):
            return False


def plan_refresh(snap: Optional[PublicCompanySnapshot], *,
                 max_age_s: float = DEFAULT_MAX_AGE_S,
                 now: Optional[float] = None) -> dict:
    """What a run must actually do, given what is already known.

    THE QUESTION IS "WHAT CHANGED?", NOT "WHAT IS TRUE?". A run with a fresh
    snapshot revalidates the sources it already has and looks for new ones; it
    does not re-propose, re-rank and re-fetch a company from nothing.

    Returns a plan rather than performing it, so the decision is inspectable
    and testable without a network.
    """
    if snap is None:
        return {"mode": "COLD", "reason": "no snapshot for this company",
                "revalidate": (), "rediscover": True, "known_sources": 0}
    if not snap.is_fresh(max_age_s=max_age_s, now=now):
        return {"mode": "STALE",
                "reason": f"snapshot is {snap.age_s(now) / 3600:.1f}h old",
                "revalidate": tuple(s.url for s in snap.sources),
                "rediscover": True, "known_sources": len(snap.sources)}
    return {"mode": "WARM",
            "reason": f"snapshot is {snap.age_s(now) / 3600:.1f}h old",
            # Immutable documents are not revalidated at all. An accessioned
            # filing cannot change, so asking about it is a request that can
            # only ever answer "no".
            "revalidate": tuple(s.url for s in snap.sources
                                if not s.accession),
            "immutable": tuple(s.url for s in snap.sources if s.accession),
            "rediscover": False, "known_sources": len(snap.sources)}
