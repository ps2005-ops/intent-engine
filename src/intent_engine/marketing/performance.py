"""Marketing performance ingestion + conservative attribution (3E/3F).

Append-only store of performance observations for a published (or dry-run
simulated) content variant, plus the marketing -> shared Learning Ledger
bridge (3A/3G). Credential-independent: metrics are passed in with their
provenance and retrieval time (a real channel connector is a documented
later step). Nothing is fabricated — an absent metric stays absent.

Attribution is deliberately conservative (3F): every ingested record is
tagged with an attribution class, and the bridge never claims causality
from correlation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

# Attribution classes, weakest to strongest evidence.
OBSERVED = "observed_conversion"      # directly tracked (tagged link fired)
CORRELATED = "correlated_outcome"     # co-occurred, not causally linked
INFERRED = "inferred_attribution"     # modeled/assumed
UNKNOWN = "unknown"

ATTRIBUTION_CLASSES = {OBSERVED, CORRELATED, INFERRED, UNKNOWN}

DEFAULT_PERF_PATH = Path("data/marketing_performance.jsonl")

# Conservative sample gate before performance becomes a learning candidate.
MIN_PERF_SAMPLE = 2


@dataclass(frozen=True)
class PerformanceRecord:
    campaign_id: str
    variant_id: str
    channel: str
    metrics: Dict[str, float]           # only what was actually observed
    attribution_class: str
    provenance: Dict[str, str]          # source, campaign/channel/variant ids
    retrieved_at: str
    external_post_id: Optional[str] = None
    at: str = field(default_factory=lambda:
                    datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def validate(self) -> None:
        if self.attribution_class not in ATTRIBUTION_CLASSES:
            raise ValueError(
                f"unknown attribution_class {self.attribution_class!r}")
        if not self.retrieved_at:
            raise ValueError("retrieved_at (data provenance) is required")


class PerformanceStore:
    def __init__(self, path: Union[str, Path] = DEFAULT_PERF_PATH):
        self.path = Path(path)

    def ingest(self, record: PerformanceRecord, *, bus=None) -> PerformanceRecord:
        record.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "campaign_id": record.campaign_id, "variant_id": record.variant_id,
                "channel": record.channel, "metrics": record.metrics,
                "attribution_class": record.attribution_class,
                "provenance": record.provenance, "retrieved_at": record.retrieved_at,
                "external_post_id": record.external_post_id, "at": record.at},
                sort_keys=True) + "\n")
        if bus is not None:
            bus.publish("marketing.performance_ingested", subject_type="campaign",
                        subject_id=record.campaign_id,
                        producer="marketing_performance", actor_type="system",
                        actor_id="marketing_performance", source="system",
                        payload={"variant_id": record.variant_id,
                                 "channel": record.channel,
                                 "attribution_class": record.attribution_class,
                                 "metric_keys": sorted(record.metrics.keys())},
                        idempotency_key=f"perf:{record.campaign_id}:"
                                        f"{record.variant_id}:{record.retrieved_at}")
        return record

    def read_all(self) -> List[dict]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out

    def for_campaign(self, campaign_id: str) -> List[dict]:
        return [r for r in self.read_all() if r["campaign_id"] == campaign_id]


def candidates_from_performance(campaign_id: str, learning_ledger, *,
                                store: Optional[PerformanceStore] = None) -> List[str]:
    """Marketing performance -> shared Learning Ledger candidates (3A/3G).
    Conservative: only OBSERVED-class records count toward the sample, no
    candidate from a tiny sample, and the statement never claims causality.
    Idempotent per (campaign, variant)."""
    store = store or PerformanceStore()
    rows = store.for_campaign(campaign_id)
    by_variant: Dict[str, List[dict]] = {}
    for r in rows:
        if r["attribution_class"] == OBSERVED:
            by_variant.setdefault(r["variant_id"], []).append(r)

    open_variants = {
        c.provenance.get("variant_id")
        for c in learning_ledger.list(source="marketing")
        if c.status in ("proposed", "evaluated")}

    from intent_engine.learning.records import SuccessCriterion
    proposed = []
    for variant_id, obs in by_variant.items():
        if len(obs) < MIN_PERF_SAMPLE or variant_id in open_variants:
            continue
        c = learning_ledger.propose(
            source="marketing", target=f"variant:{variant_id}",
            statement=(f"Content variant {variant_id} shows a consistent "
                       f"observed signal over {len(obs)} data points "
                       "(association, not proven causal)"),
            hypothesis="this variant/audience/timing outperforms the baseline",
            baseline_ref="marketing.campaign_baseline",
            success_criteria=[SuccessCriterion(
                metric="observed_conversion_rate", comparator=">=",
                threshold=0.0, direction="higher_better")],
            param_diff={"variant_id": variant_id, "channel": obs[0]["channel"]},
            provenance={"variant_id": variant_id, "campaign_id": campaign_id,
                        "samples": len(obs), "attribution": OBSERVED},
            idempotency_key=f"marketing:{campaign_id}:{variant_id}")
        proposed.append(c.id)
    return proposed
