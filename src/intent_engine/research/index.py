"""The Evidence Index — research memory (T019).

This is the substrate. It owns normalized claims, source ids, evidence
ids, relation (contradiction) links, freshness/retirement state, and
graph node ids. Every other layer — packages, conclusions, proposals,
and every later agent (PM, Executive Decision, AgentOS, Personal AI) —
REFERENCES the index rather than restating its contents.

Two properties make it a memory rather than a cache:

  * it is built ONLY from append-only rows, so it is reproducible; and
  * it is NEVER written by a model. Extraction may propose candidates;
    only deterministic code writes an index entry.

The embedding/vector fields are deliberately absent in V1: adding them is
a declared-dependency decision (A3), and the index is shaped so they can
be added later as an additive column without touching consumers.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from intent_engine.research.records import (
    EVIDENCE_CLASSES, RELATIONS, ResearchError,
)
from intent_engine.research.sources import freshness_of, independence_group

INDEX_VERSION = "evidence_index.v1"


def normalize_claim(text: str) -> str:
    """Deterministic claim normalization — the key that lets two sources
    be recognized as addressing the SAME claim."""
    lowered = " ".join((text or "").lower().split())
    lowered = re.sub(r"[^\w\s%.-]", "", lowered)
    return lowered.strip()


def claim_key(text: str) -> str:
    return "claim-" + hashlib.sha256(
        normalize_claim(text).encode()).hexdigest()[:32]


@dataclass(frozen=True)
class EvidenceIndex:
    """A reproducible read model. Construct with `build_index(rows, ...)`."""
    request_id: str
    index_version: str = INDEX_VERSION
    sources: dict = field(default_factory=dict)      # source_id -> record
    evidence: dict = field(default_factory=dict)     # evidence_id -> record
    claims: dict = field(default_factory=dict)       # claim_key -> record
    relations: tuple = ()                            # typed edges
    contradictions: tuple = ()                       # (claim_key, ev_a, ev_b)
    retired_sources: frozenset = frozenset()
    retired_evidence: frozenset = frozenset()

    # --- lineage -------------------------------------------------------------
    def lineage(self, evidence_id: str) -> dict:
        """Improvement 5: evidence -> source -> retrieval -> session ->
        plan -> request, answerable for any evidence item."""
        item = self.evidence.get(evidence_id)
        if item is None:
            raise KeyError(f"no such evidence: {evidence_id}")
        source = self.sources.get(item["source_id"])
        if source is None:
            raise ResearchError(
                f"evidence {evidence_id} references unregistered source "
                f"{item['source_id']} — the index rejects orphans")
        return {
            "evidence_id": evidence_id,
            "claim_key": item.get("claim_key"),
            "evidence_class": item.get("evidence_class"),
            "extraction_method": item.get("extraction_method"),
            "source_id": source["source_id"],
            "source_class": source.get("source_class"),
            "source_quality": source.get("source_quality"),
            "canonical_locator": source.get("canonical_locator"),
            "content_hash": source.get("content_hash"),
            "retrieved_at": source.get("retrieved_at"),
            "session_id": item.get("session_id"),
            "plan_version": item.get("plan_version"),
            "request_id": self.request_id,
        }

    def evidence_for_claim(self, key: str) -> list:
        return sorted((e for e in self.evidence.values()
                       if e.get("claim_key") == key),
                      key=lambda e: e["evidence_id"])

    def usable_evidence(self) -> list:
        """Excludes retired sources and retired evidence. Stale evidence is
        INCLUDED (labelled), because stale is not unusable."""
        return sorted(
            (e for e in self.evidence.values()
             if e["evidence_id"] not in self.retired_evidence
             and e["source_id"] not in self.retired_sources),
            key=lambda e: e["evidence_id"])

    # --- invariants (improvement 8) ------------------------------------------
    def assert_invariants(self) -> dict:
        """Structural guarantees, checked rather than assumed."""
        problems = []
        for ev_id, item in self.evidence.items():
            if not item.get("source_id"):
                problems.append(f"evidence {ev_id} has no source")
            elif item["source_id"] not in self.sources:
                problems.append(f"evidence {ev_id} references unregistered "
                                f"source {item['source_id']}")
            if item.get("evidence_class") not in EVIDENCE_CLASSES:
                problems.append(f"evidence {ev_id} has an unknown class")
        for key, claim in self.claims.items():
            if not self.evidence_for_claim(key):
                problems.append(f"claim {key} has no evidence (orphan node)")
        for rel in self.relations:
            if rel["relation"] not in RELATIONS:
                problems.append(f"unknown relation {rel['relation']!r}")
            if rel.get("evidence_id") and rel["evidence_id"] not in self.evidence:
                problems.append(f"relation references unknown evidence "
                                f"{rel['evidence_id']}")
        for contradiction in self.contradictions:
            if len(contradiction.get("evidence_ids", ())) != 2:
                problems.append("a contradiction must name exactly two "
                                "evidence ids")
        if problems:
            raise ResearchError(f"evidence index invariants violated: "
                                f"{problems}")
        return {"index_version": self.index_version,
                "sources": len(self.sources), "evidence": len(self.evidence),
                "claims": len(self.claims), "relations": len(self.relations),
                "contradictions": len(self.contradictions),
                "invariants": "ok"}


def build_index(rows, request_id: str, *, as_of: str) -> EvidenceIndex:
    """Deterministically rebuild the index from append-only rows. Calling
    this twice on the same rows yields identical output — that is what
    makes every downstream artifact reproducible."""
    sources, evidence, claims = {}, {}, {}
    relations, contradictions = [], []
    retired_sources, retired_evidence = set(), set()

    for row in rows:
        p = row.payload or {}
        if row.event_type == "research.source_registered":
            sources[row.subject_id] = {**p, "source_id": row.subject_id,
                                       "session_id": row.session_id,
                                       "plan_version": row.plan_version}
        elif row.event_type == "research.source_retired":
            retired_sources.add(row.subject_id)
            if row.subject_id in sources:
                sources[row.subject_id]["retired_reason"] = p.get("reason")
        elif row.event_type == "research.source_unverified":
            if row.subject_id in sources:
                sources[row.subject_id]["verified"] = False
                sources[row.subject_id]["verification_note"] = p.get("reason")
        elif row.event_type == "research.source_verified":
            if row.subject_id in sources:
                sources[row.subject_id]["verified"] = True
        elif row.event_type == "research.evidence_indexed":
            evidence[row.subject_id] = {**p, "evidence_id": row.subject_id,
                                        "session_id": row.session_id,
                                        "plan_version": row.plan_version}
        elif row.event_type == "research.evidence_retired":
            retired_evidence.add(row.subject_id)
        elif row.event_type == "research.claim_indexed":
            claims[row.subject_id] = {**p, "claim_key": row.subject_id}
        elif row.event_type == "research.relation_indexed":
            relations.append({**p, "relation_id": row.subject_id})
            if p.get("relation") == "contradicts" and p.get("counterpart"):
                contradictions.append({
                    "claim_key": p.get("claim_key"),
                    "evidence_ids": sorted([p.get("evidence_id"),
                                            p.get("counterpart")]),
                    "conflict_reason": p.get("conflict_reason", "unknown")})

    # attach freshness + independence deterministically
    for source in sources.values():
        source["freshness"] = freshness_of(source, as_of=as_of)
        source["independence_group"] = independence_group(source)

    return EvidenceIndex(
        request_id=request_id, sources=sources, evidence=evidence,
        claims=claims, relations=tuple(relations),
        contradictions=tuple(contradictions),
        retired_sources=frozenset(retired_sources),
        retired_evidence=frozenset(retired_evidence))
