"""Bounded, leakage-safe company intelligence refresh (section 9).

`research_fn(company, as_of)` is injected — a deterministic fake in tests, a
bounded LLM+web adapter in production — so this module stays credential-
independent and offline-testable. Two hard rules it enforces regardless of the
adapter:

  * LEAKAGE CHECK — any evidence whose `published_at` is AFTER `as_of` is
    dropped (recorded as leaked, never ingested). A prediction made on a date
    can only ever see evidence available by that date.
  * IDEMPOTENT INGEST — evidence is de-duplicated on its content signature, so
    a re-run of the daily refresh does not pile up duplicate rows.

Each refresh updates the company's durable state (thesis, priorities, freshness)
so the dashboard can show how stale each company's research is.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

EVIDENCE_STREAM = "company_evidence"
STATE_STREAM = "company_state"

ResearchFn = Callable[[Any, str], Optional[Dict[str, Any]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Evidence(BaseModel):
    company_id: str
    kind: str                       # filing | earnings | product | pricing | ...
    summary: str
    source: str
    published_at: str               # ISO date/datetime the evidence is dated
    ingested_at: str = Field(default_factory=_now)
    confidence: float = 0.5
    interpretation: str = ""

    def signature(self) -> str:
        return sha256("|".join([self.company_id, self.source,
                                self.published_at, self.summary]
                               ).encode("utf-8")).hexdigest()[:16]


class CompanyState(BaseModel):
    company_id: str
    thesis: str = ""
    priorities: List[str] = Field(default_factory=list)
    last_refreshed: str = Field(default_factory=_now)
    as_of: str = ""
    evidence_count: int = 0


def refresh_company(company, research_fn: ResearchFn, store, as_of: str) -> Dict:
    """Refresh one company. Returns kept/leaked evidence + the updated state."""
    result = research_fn(company, as_of) or {}
    kept: List[Evidence] = []
    leaked: List[dict] = []
    for raw in result.get("evidence", []):
        published = str(raw.get("published_at", ""))[:10]
        if published and published > as_of[:10]:
            leaked.append(raw)                       # leakage: never ingest
            continue
        ev = Evidence(
            company_id=company.company_id, kind=raw.get("kind", "news"),
            summary=raw.get("summary", ""), source=raw.get("source", ""),
            published_at=raw.get("published_at", as_of),
            confidence=float(raw.get("confidence", 0.5)),
            interpretation=raw.get("interpretation", ""))
        store.append(EVIDENCE_STREAM, ev.signature(), ev.model_dump(mode="json"),
                     status="ingested", idem_key=f"ev:{ev.signature()}",
                     company_id=company.company_id, ts=ev.ingested_at)
        kept.append(ev)

    existing = store.get(STATE_STREAM, company.company_id)
    prior_count = existing.payload.get("evidence_count", 0) if existing else 0
    state = CompanyState(
        company_id=company.company_id,
        thesis=result.get("thesis", existing.payload.get("thesis", "")
                          if existing else ""),
        priorities=result.get("priorities",
                              list(company.strategic_priorities)),
        last_refreshed=_now(), as_of=as_of,
        evidence_count=prior_count + len(kept))
    store.append(STATE_STREAM, company.company_id, state.model_dump(mode="json"),
                 status="refreshed", company_id=company.company_id,
                 ts=state.last_refreshed,
                 idem_key=f"state:{company.company_id}:{as_of}:{state.evidence_count}")
    return {"company_id": company.company_id, "kept": kept, "leaked": leaked,
            "state": state}


def company_state(store, company_id: str) -> Optional[CompanyState]:
    rec = store.get(STATE_STREAM, company_id)
    return CompanyState(**rec.payload) if rec else None


def all_states(store) -> Dict[str, dict]:
    return {r.record_id: r.payload for r in store.latest(STATE_STREAM)}


def evidence_for(store, company_id: str) -> List[dict]:
    return [r.payload for r in store.latest(EVIDENCE_STREAM, company_id=company_id)]
