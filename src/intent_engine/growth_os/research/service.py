"""GrowthResearchService (§1) — the only write path for growth research.

Records typed, evidenced observations; folds a topic's evolution over time; and
proposes (never promotes) learning candidates when intent is recurring, rising
and well-evidenced. Human-gated: a candidate is only ever `proposed` here — a
human accepts it into the ledger.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from intent_engine.growth_os.foundation import (
    Confidence,
    GrowthOSError,
    IntelRecord,
    IntelStore,
    LearningCandidate,
    Provenance,
)
from intent_engine.growth_os.research.records import (
    INTENT_CLASSES,
    RESEARCH_DOMAINS,
    RESEARCH_KINDS,
    RESEARCH_OBSERVED,
    RESEARCH_STREAM,
    normalize_topic,
)


@dataclass
class TopicEvolution:
    topic: str
    observations: int
    first_seen: str
    last_seen: str
    distinct_days: int
    latest_confidence: float
    trend: str                        # rising | steady | fading
    intents: dict                     # intent_class -> count
    evidence: list                    # record ids


class GrowthResearchService:
    def __init__(self, store: IntelStore):
        self.store = store

    # -- write --------------------------------------------------------------
    def observe(self, *, kind: str, domain: str, text: str, intent: str,
                provenance: Provenance, confidence: Confidence,
                actor: str = "agent", observed_at: Optional[str] = None,
                payload: Optional[dict] = None) -> IntelRecord:
        """Record one understood-intent observation. Idempotent per
        (kind, domain, normalized topic, observed day) so re-seeing the same
        thing the same day is a no-op, but seeing it another day APPENDS —
        that append IS the evolution signal."""
        if kind not in RESEARCH_KINDS:
            raise GrowthOSError(f"kind {kind!r} not in {sorted(RESEARCH_KINDS)}")
        if domain not in RESEARCH_DOMAINS:
            raise GrowthOSError(f"domain {domain!r} not in {sorted(RESEARCH_DOMAINS)}")
        if intent not in INTENT_CLASSES:
            raise GrowthOSError(f"intent {intent!r} not in {list(INTENT_CLASSES)}")
        norm = normalize_topic(text)
        if not norm:
            raise GrowthOSError("text is required")
        obs_at = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        day = obs_at[:10]
        idem = f"obs:{kind}:{domain}:{norm}:{day}"
        # One observation per (kind, domain, topic, day): re-seeing the same
        # topic the same day is a no-op even if the raw wording differs (the
        # first day's record stands as the evidence). Evolution is tracked
        # ACROSS days, which get distinct keys and distinct records.
        existing = self.store.find_by_idempotency_key(idem)
        if existing is not None:
            return existing
        body = {"kind": kind, "domain": domain, "text": text, "topic": norm,
                "intent": intent, **(payload or {})}
        rec = IntelRecord(
            stream=RESEARCH_STREAM, event_type=RESEARCH_OBSERVED, actor=actor,
            provenance=provenance, confidence=confidence, payload=body,
            observed_at=obs_at, idempotency_key=idem)
        return self.store.append(rec)

    # -- read / fold --------------------------------------------------------
    def _observations(self) -> list[IntelRecord]:
        return self.store.for_event_type(RESEARCH_OBSERVED)

    def topic_evolution(self, text: str) -> Optional[TopicEvolution]:
        norm = normalize_topic(text)
        rows = [r for r in self._observations() if r.payload.get("topic") == norm]
        if not rows:
            return None
        rows.sort(key=lambda r: r.observed_at)
        days = sorted({r.observed_at[:10] for r in rows})
        intents: dict = defaultdict(int)
        for r in rows:
            intents[r.payload.get("intent", "informational")] += 1
        return TopicEvolution(
            topic=norm, observations=len(rows),
            first_seen=rows[0].observed_at, last_seen=rows[-1].observed_at,
            distinct_days=len(days),
            latest_confidence=rows[-1].confidence.value,
            trend=self._trend(days),
            intents=dict(intents),
            evidence=[r.record_id for r in rows])

    @staticmethod
    def _trend(days: list) -> str:
        """Rising if activity is denser in the RECENT half of the observed time
        span, fading if denser earlier, steady otherwise. Split by time (not by
        count of days), so bursts of recent interest read as rising even when
        the earlier signal was spread thin. Deterministic + explainable."""
        if len(days) < 2:
            return "steady"
        d0 = date.fromisoformat(days[0])
        d1 = date.fromisoformat(days[-1])
        span = (d1 - d0).days
        if span == 0:
            return "steady"
        midpoint = d0 + timedelta(days=span // 2)
        early = sum(1 for d in days if date.fromisoformat(d) <= midpoint)
        late = sum(1 for d in days if date.fromisoformat(d) > midpoint)
        return "rising" if late > early else "fading" if late < early else "steady"

    def top_topics(self, *, domain: Optional[str] = None, limit: int = 20
                   ) -> list[TopicEvolution]:
        rows = self._observations()
        if domain:
            rows = [r for r in rows if r.payload.get("domain") == domain]
        topics = {r.payload.get("topic") for r in rows}
        evos = [e for e in (self.topic_evolution(t) for t in topics) if e]
        evos.sort(key=lambda e: (e.observations, e.distinct_days), reverse=True)
        return evos[:limit]

    # -- learning candidates (proposed only; a human accepts) ---------------
    def emerging_candidates(self, *, min_observations: int = 3,
                            min_distinct_days: int = 2,
                            min_confidence: float = 0.5) -> list[LearningCandidate]:
        """Propose a candidate for each recurring, rising, well-evidenced topic.
        Nothing is promoted — every candidate is 'proposed' for human review."""
        out: list[LearningCandidate] = []
        for evo in self.top_topics(limit=1000):
            if (evo.observations >= min_observations
                    and evo.distinct_days >= min_distinct_days
                    and evo.trend == "rising"
                    and evo.latest_confidence >= min_confidence):
                out.append(LearningCandidate(
                    statement=(f"Rising intent around '{evo.topic}' "
                               f"({evo.observations} obs over {evo.distinct_days} "
                               f"days) — create content targeting it."),
                    success_metric="qualified engagement on topic-targeted content",
                    evidence=evo.evidence,
                    confidence=Confidence(
                        min(evo.latest_confidence, 0.9),
                        basis=(f"recurring/rising: {evo.observations} observations "
                               f"across {evo.distinct_days} distinct days")),
                    proposed_by="growth_research"))
        return out
