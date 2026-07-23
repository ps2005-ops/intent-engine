"""Research read adapter (T023).

Enumerates research requests (via the public `store.request_ids()`) and
reads their packages and conclusions — no new research API is required
(see dependency-gap doc, gap 2). Every conclusion is cited to its request
and package with a replay handle and a freshness derived from the package
`as_of`.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_CONFLICTED, AVAIL_SUPPORTED, FRESH_UNKNOWN, SourceClaim, SourceRef,
    freshness_of,
)

# Uncertainty labels a research conclusion can carry; CONFLICTING preserves
# disagreement rather than smoothing it.
_CONFLICTED_LABELS = {"CONFLICTING", "UNKNOWN"}


class ResearchAdapter(Adapter):
    subsystem = "research"

    def highlights(self, limit: int = 5) -> list:
        """Recent research conclusions as cited claims. Disagreement is
        preserved: a CONFLICTING conclusion becomes a CONFLICTED claim, not
        a confident one."""
        if not self.available:
            return [unavailable_claim("research.highlights",
                                      "the research subsystem is not connected")]
        claims = []
        for request_id in self.service.store.request_ids():
            for package_id in self.service.list_packages(request_id):
                package = self.service.get_package(request_id, package_id)
                observed = package.get("as_of")
                fresh = freshness_of(observed, self.as_of)
                for question, detail in package["coverage"]["per_question"].items():
                    stances = [s["stance"] for s in detail["stances"]]
                    conflicted = any(s in _CONFLICTED_LABELS for s in stances) \
                        or detail["bucket"] == "contradicted"
                    availability = AVAIL_CONFLICTED if conflicted else AVAIL_SUPPORTED
                    text = (f"research on '{question}' is "
                            + ("conflicted — the sources disagree and it is "
                               "not settled" if conflicted
                               else f"{detail['bucket']}"))
                    replay = f"research:{request_id}:{package_id}:{self.as_of}"
                    claims.append(SourceClaim(
                        claim_id=f"research.{package_id}.{len(claims)}",
                        text=text, availability=availability,
                        source_refs=(SourceRef(
                            subsystem="research", artifact_type="conclusion",
                            artifact_id=f"{package_id}:{question}",
                            replay_id=replay, as_of=self.as_of,
                            observed_at=observed, freshness_status=fresh,
                            snapshot_version=package.get("package_version")),),
                        transformation="direct", freshness_status=fresh))
                    if len(claims) >= limit:
                        return claims
        if not claims:
            return [unavailable_claim("research.highlights",
                                      "no research package is recorded yet")]
        return claims

    def read_research_debt(self) -> list:
        """Open research debt across packages, for investigation candidates.
        The debt is exactly what the research package reported."""
        if not self.available:
            return []
        out = []
        for request_id in self.service.store.request_ids():
            for package_id in self.service.list_packages(request_id):
                package = self.service.get_package(request_id, package_id)
                for item in package.get("research_debt", []):
                    out.append({
                        "kind": item.get("kind"),
                        "detail": item.get("detail", ""),
                        "question": item.get("question", ""),
                        "source_ref": SourceRef(
                            subsystem="research", artifact_type="research_debt",
                            artifact_id=f"{package_id}:{item.get('kind')}",
                            replay_id=f"research:{request_id}:{package_id}:{self.as_of}",
                            as_of=self.as_of).as_dict()})
        return out
