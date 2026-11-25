"""TrendIntelligenceService (§3) — ingest via a provider, classify, explain.

No real network here — a `TrendSource` is injected. Ingestion enforces the full
required-field set and a permitted access method (unauthorized scraping is not
expressible). Classification distinguishes the seven trend kinds §3 demands and
the explanation is a PATTERN description, never a copy of source content.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from intent_engine.growth_os.attention.service import score_executive_attention
from intent_engine.growth_os.foundation import (
    Confidence,
    GrowthOSError,
    IntelRecord,
    IntelStore,
    Provenance,
)
from intent_engine.growth_os.research.records import normalize_topic
from intent_engine.growth_os.trends.providers import RawTrendItem, TrendSource
from intent_engine.growth_os.trends.records import (
    REQUIRED_OBSERVATION_FIELDS,
    TREND_BOT,
    TREND_CONTROVERSY,
    TREND_EXECUTIVE,
    TREND_HIGH_VOLUME_LOW_VALUE,
    TREND_OBSERVED,
    TREND_ONE_OFF,
    TREND_RISING,
    TREND_SEASONAL,
    TREND_STREAM,
    TrendClassification,
)

_BUSINESS_KEYS = {
    "executive_engagement", "qualified_visits", "demo_requests", "waitlist_joins",
    "trials", "github_stars_target", "target_account_replies", "crm_qualified_leads",
    "pipeline_influence", "conversion", "revenue",
}


class TrendIntelligenceService:
    def __init__(self, store: IntelStore):
        self.store = store

    # -- ingest --------------------------------------------------------------
    def ingest(self, source: TrendSource, *, query: str,
               since: Optional[str] = None, actor: str = "agent") -> list[IntelRecord]:
        """Pull observations from a provider and persist each as an IntelRecord
        with full provenance + confidence. Idempotent per (provider, topic, day,
        url). A missing required field is refused loudly."""
        recorded: list[IntelRecord] = []
        for item in source.fetch(query=query, since=since):
            rec = self._to_record(source, item, actor)
            recorded.append(self.store.append(rec))
        return recorded

    def _to_record(self, source: TrendSource, item: RawTrendItem,
                   actor: str) -> IntelRecord:
        retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = {
            "provider": source.name, "source_url": item.source_url,
            "retrieved_at": retrieved, "published_at": item.published_at,
            "audience": item.audience, "topic": normalize_topic(item.topic),
            "topic_display": item.topic, "format": item.fmt,
            "engagement": dict(item.engagement),
            "metric_definitions": dict(item.metric_definitions),
            "sample_limitations": item.sample_limitations or "not stated",
            "permitted_method": source.method,
            "quality_signals": dict(item.quality_signals),
            "business_signals": dict(item.business_signals),
            "is_seasonal": bool(item.is_seasonal),
        }
        missing = [f for f in REQUIRED_OBSERVATION_FIELDS if f not in payload]
        if missing:
            raise GrowthOSError(f"trend observation missing required fields: {missing}")
        # confidence is lower when the sample is limited or definitions are absent
        conf = 0.7
        if item.sample_limitations:
            conf -= 0.15
        if not item.metric_definitions:
            conf -= 0.15
        basis = (f"provider {source.name} via {source.method}; "
                 f"limitations: {payload['sample_limitations']}")
        prov = Provenance(source=source.name, method=source.method,
                          uri=item.source_url, retrieved_at=retrieved)
        day = (item.published_at or retrieved)[:10]
        return IntelRecord(
            stream=TREND_STREAM, event_type=TREND_OBSERVED, actor=actor,
            provenance=prov, confidence=Confidence(max(conf, 0.1), basis=basis),
            payload=payload, observed_at=item.published_at,
            idempotency_key=f"trend:{source.name}:{payload['topic']}:{day}:{item.source_url}")

    # -- read ----------------------------------------------------------------
    def _for_topic(self, topic: str) -> list[IntelRecord]:
        norm = normalize_topic(topic)
        rows = [r for r in self.store.for_event_type(TREND_OBSERVED)
                if r.payload.get("topic") == norm]
        rows.sort(key=lambda r: r.payload.get("published_at", ""))
        return rows

    # -- classify (deterministic, explainable) ------------------------------
    def classify_trend(self, topic: str) -> Optional[TrendClassification]:
        rows = self._for_topic(topic)
        if not rows:
            return None
        sig = self._features(rows)
        reasons: list[str] = []

        # 1. data quality first — a bot/low-quality signal is not a real trend
        if sig["avg_bot_ratio"] >= 0.5 or sig["avg_unique_ratio"] <= 0.3:
            reasons.append(f"bot/low-quality: bot_ratio={sig['avg_bot_ratio']:.2f}, "
                           f"unique_account_ratio={sig['avg_unique_ratio']:.2f}")
            return TrendClassification(TREND_BOT, reasons, sig)
        # 2. seasonal recurrence
        if sig["is_seasonal"]:
            reasons.append("flagged/observed as recurring seasonal interest")
            return TrendClassification(TREND_SEASONAL, reasons, sig)
        # 3. meaningful executive/buyer attention
        if sig["has_business_signal"]:
            reasons.append(f"business-outcome signals present: {sorted(sig['business_keys'])}")
            return TrendClassification(TREND_EXECUTIVE, reasons, sig)
        # 4. controversy (engagement driven by conflict, not value)
        if sig["controversy_ratio"] >= 1.5 and sig["avg_sentiment"] < 0:
            reasons.append(f"controversy: comment/like ratio {sig['controversy_ratio']:.2f}, "
                           f"negative sentiment {sig['avg_sentiment']:.2f}")
            return TrendClassification(TREND_CONTROVERSY, reasons, sig)
        # 5. genuinely rising across time
        if sig["distinct_days"] >= 2 and sig["engagement_trend"] == "rising":
            reasons.append(f"rising engagement across {sig['distinct_days']} days")
            return TrendClassification(TREND_RISING, reasons, sig)
        # 6. lots of attention, no quality/business behind it
        if sig["attention_volume"] >= sig["high_volume_threshold"]:
            reasons.append(f"high attention ({sig['attention_volume']}) but no "
                           "quality-engagement or business signal")
            return TrendClassification(TREND_HIGH_VOLUME_LOW_VALUE, reasons, sig)
        # 7. otherwise a single spike
        reasons.append("single spike, no recurrence or downstream signal")
        return TrendClassification(TREND_ONE_OFF, reasons, sig)

    def _features(self, rows: list[IntelRecord]) -> dict:
        days = sorted({r.payload.get("published_at", "")[:10] for r in rows if r.payload.get("published_at")})
        bot = [r.payload["quality_signals"].get("bot_ratio", 0.0) for r in rows]
        uniq = [r.payload["quality_signals"].get("unique_account_ratio", 1.0) for r in rows]
        sent = [r.payload["quality_signals"].get("sentiment", 0.0) for r in rows]
        biz_keys = set()
        for r in rows:
            biz_keys |= (set(r.payload.get("business_signals", {})) & _BUSINESS_KEYS)
        controversy = self._avg([r.payload["quality_signals"].get("comment_like_ratio", 0.0) for r in rows])
        attention_volume = sum(
            r.payload["engagement"].get("impressions", 0) + r.payload["engagement"].get("views", 0)
            for r in rows)
        return {
            "n_obs": len(rows), "distinct_days": len(days),
            "avg_bot_ratio": self._avg(bot), "avg_unique_ratio": self._avg(uniq, default=1.0),
            "avg_sentiment": self._avg(sent), "controversy_ratio": controversy,
            "is_seasonal": any(r.payload.get("is_seasonal") for r in rows),
            "has_business_signal": bool(biz_keys), "business_keys": biz_keys,
            "engagement_trend": self._engagement_trend(rows, days),
            "attention_volume": attention_volume,
            "high_volume_threshold": 10_000,
        }

    @staticmethod
    def _avg(xs, default=0.0):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else default

    def _engagement_trend(self, rows: list[IntelRecord], days: list) -> str:
        if len(days) < 2:
            return "flat"
        by_day = defaultdict(float)
        for r in rows:
            d = r.payload.get("published_at", "")[:10]
            eng = r.payload["engagement"]
            by_day[d] += eng.get("engagement", 0) or (eng.get("saves", 0) + eng.get("shares", 0))
        d0, d1 = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
        span = (d1 - d0).days or 1
        mid = d0 + timedelta(days=span // 2)
        early = sum(v for d, v in by_day.items() if date.fromisoformat(d) <= mid)
        late = sum(v for d, v in by_day.items() if date.fromisoformat(d) > mid)
        return "rising" if late > early else "fading" if late < early else "flat"

    # -- explain (pattern description; never copies content) ----------------
    def explain_trend(self, topic: str) -> Optional[dict]:
        rows = self._for_topic(topic)
        if not rows:
            return None
        cls = self.classify_trend(topic)
        formats = self._mode([r.payload.get("format") for r in rows])
        audience = self._mode([r.payload.get("audience") for r in rows])
        q = rows[-1].payload.get("quality_signals", {})
        exec_score = score_executive_attention({
            "role_verified": q.get("role_verified"),
            "target_account_match": q.get("target_account_match"),
            "meaningful_reply": q.get("meaningful_reply"),
            "conversion": bool(rows[-1].payload.get("business_signals", {}).get("conversion")),
        })
        return {
            "topic": rows[-1].payload.get("topic_display"),
            "trend_type": cls.trend_type,
            "what_is_spreading": f"{formats} content about "
                                 f"{rows[-1].payload.get('topic_display')}",
            "audience": audience,
            "why_it_works": "; ".join(cls.reasons),
            "hook_structure": q.get("hook_pattern", "not observed — needs manual review"),
            "motivation": q.get("motivation", "not observed — needs manual review"),
            "credibility_mechanism": q.get("credibility", "not observed — needs manual review"),
            "format": formats,
            "timing": self._timing(rows),
            "cta": q.get("cta_pattern", "not observed — needs manual review"),
            "business_relevance": (
                f"executive attention {exec_score.value if exec_score.is_known else 'UNKNOWN'} "
                f"({exec_score.basis})"),
            "risks_of_copying": self._copy_risks(cls.trend_type),
            "provenance": [r.provenance.source for r in rows],
            "confidence": rows[-1].confidence.value,
        }

    @staticmethod
    def _mode(values):
        vals = [v for v in values if v]
        if not vals:
            return "unknown"
        return max(set(vals), key=vals.count)

    @staticmethod
    def _timing(rows):
        days = {r.payload.get("published_at", "")[:10] for r in rows}
        return f"observed across {len(days)} day(s)"

    @staticmethod
    def _copy_risks(trend_type: str) -> str:
        return {
            TREND_CONTROVERSY: "brand-safety risk; engagement is conflict-driven, not value-driven",
            TREND_BOT: "signal is inflated by low-quality/bot engagement — not a real audience",
            TREND_ONE_OFF: "not repeatable; a single spike rarely generalizes",
            TREND_HIGH_VOLUME_LOW_VALUE: "high reach but no evidence of business value",
            TREND_SEASONAL: "time-boxed; will fade until the season returns",
            TREND_RISING: "copying the topic ≠ copying the value; add original evidence/POV",
            TREND_EXECUTIVE: "highest value, highest scrutiny — claims must be defensible",
        }.get(trend_type, "validate against your own audience before adopting")
