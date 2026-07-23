"""The deterministic demo company (T023.5).

A single, clearly-synthetic company so the product can be experienced even
when live ingestion is unavailable. It is NOT a real company with invented
facts — it is a fictional one, and every view states that it is synthetic.

It supplies the SourceClaims the assembly composes, engineered to exercise
the whole experience honestly: a supported profile, two personas with a
homepage/persona mismatch, a company-vs-market language difference, a
public-signal timeline, ONE conflicted claim, ONE stale source, ONE
unavailable metric, one possible blind spot, one assumption worth testing,
one leadership question, one opportunity hypothesis, and an unsupported
competitor request.
"""
from __future__ import annotations

from intent_engine.personal.records import (
    AVAIL_CONFLICTED, AVAIL_PARTIAL, AVAIL_SUPPORTED, AVAIL_UNAVAILABLE,
    FRESH_CURRENT, FRESH_STALE, SourceClaim, SourceRef,
)

DEMO_COMPANY_NAME = "Northwind Logistics Cloud (synthetic demo)"
DEMO_DOMAIN = "northwind-demo.example"
DEMO_AS_OF = "2026-07-21T00:00:00+00:00"
DEMO_NOTE = "SYNTHETIC DEMO COMPANY — all facts are fictional"


def _ref(artifact_type, artifact_id, *, observed_at=DEMO_AS_OF,
         freshness=FRESH_CURRENT):
    return SourceRef(subsystem="demo_fixture", artifact_type=artifact_type,
                     artifact_id=artifact_id,
                     replay_id=f"demo:{artifact_type}:{artifact_id}:{DEMO_AS_OF}",
                     as_of=DEMO_AS_OF, observed_at=observed_at,
                     freshness_status=freshness, snapshot_version="demo.v1")


def _claim(claim_id, text, availability, artifact_type, artifact_id, *,
           freshness=FRESH_CURRENT, transformation="direct", confidence=None):
    return SourceClaim(
        claim_id=claim_id, text=text, availability=availability,
        source_refs=(_ref(artifact_type, artifact_id, freshness=freshness),)
        if availability != AVAIL_UNAVAILABLE else (),
        transformation=transformation, freshness_status=freshness,
        confidence=confidence)


def demo_claims() -> dict:
    """The claims, grouped by the section they support. Deterministic."""
    return {
        # --- Proof of Understanding ---------------------------------------
        "understanding": [
            _claim("u.identity", "Company identity: Northwind Logistics Cloud "
                   "(synthetic demo)", AVAIL_SUPPORTED, "profile", "identity",
                   confidence="High"),
            _claim("u.model", "Business model: subscription software for "
                   "logistics operations teams", AVAIL_SUPPORTED, "profile",
                   "model", confidence="Moderate"),
            _claim("u.value", "Primary value proposition (company-stated): "
                   "AI workflow automation for freight coordination",
                   AVAIL_SUPPORTED, "profile", "value", confidence="Moderate"),
            _claim("u.segment", "Primary visible customer: mid-market "
                   "logistics operations teams", AVAIL_PARTIAL, "profile",
                   "segment", confidence="Moderate"),
            _claim("u.market", "Market/category: logistics operations "
                   "software", AVAIL_SUPPORTED, "profile", "market",
                   confidence="Moderate"),
            _claim("u.geo", "Geographic footprint: primarily North America "
                   "(from currently approved sources)", AVAIL_PARTIAL,
                   "profile", "geo", confidence="Low"),
        ],
        # --- Analytics (honest states) ------------------------------------
        "analytics": [
            _claim("a.signals", "Public signal summary: 14 dated public "
                   "signals over the last 6 months", AVAIL_SUPPORTED,
                   "signal_summary", "count"),
            _claim("a.hiring", "Hiring signals: 3 operations-facing roles "
                   "posted this quarter", AVAIL_SUPPORTED, "hiring", "count",
                   freshness=FRESH_STALE),
            _claim("a.revenue", "Public financial signals", AVAIL_UNAVAILABLE,
                   "financial", "none"),
            _claim("a.engagement", "Public engagement signals appear present "
                   "but the sources disagree on their trend", AVAIL_CONFLICTED,
                   "engagement", "trend"),
        ],
        # --- Market view (company language vs market language) -------------
        "market_view": [
            _claim("m.company_lang", "Company emphasizes: 'AI workflow "
                   "automation'", AVAIL_SUPPORTED, "company_language",
                   "emphasis"),
            _claim("m.customer_lang", "Customer language emphasizes: "
                   "'eliminating manual follow-up'", AVAIL_SUPPORTED,
                   "customer_language", "emphasis"),
        ],
        # --- Personas (with homepage/persona mismatch) --------------------
        "persona": [
            _claim("p.ops", "Public signals suggest a persona: logistics "
                   "operations teams", AVAIL_SUPPORTED, "persona", "ops"),
            _claim("p.self_serve", "Public signals suggest a second persona: "
                   "small self-serve dispatchers", AVAIL_PARTIAL, "persona",
                   "self_serve"),
            _claim("p.homepage", "The homepage appears primarily oriented "
                   "toward the operations-team persona", AVAIL_SUPPORTED,
                   "homepage_target", "primary"),
        ],
        # --- One possible blind spot (source-backed) ----------------------
        "blind_spot": [
            _claim("b.messaging", "Public messaging appears narrower than the "
                   "visible customer evidence", AVAIL_SUPPORTED, "blind_spot",
                   "messaging_narrower", confidence="Moderate"),
        ],
        # --- One assumption worth testing ---------------------------------
        "assumption": [
            _claim("as.feature", "Visible assumption: buyers choose primarily "
                   "on feature breadth", AVAIL_SUPPORTED, "assumption",
                   "feature_breadth"),
            _claim("as.speed", "Complicating evidence: customer language more "
                   "frequently emphasizes implementation speed", AVAIL_PARTIAL,
                   "assumption_evidence", "speed"),
        ],
        # --- One leadership question source -------------------------------
        "attention": [
            _claim("at.customer", "Customer understanding surfaced as an "
                   "attention area (owning subsystem: product)", AVAIL_SUPPORTED,
                   "attention", "customer_understanding"),
            _claim("at.trust", "Trust/education surfaced as an attention area",
                   AVAIL_PARTIAL, "attention", "trust"),
        ],
        # --- One opportunity hypothesis -----------------------------------
        "opportunity": [
            _claim("o.self_serve", "A self-serve onboarding path may reach the "
                   "second visible persona", AVAIL_PARTIAL, "opportunity",
                   "self_serve", confidence="Low"),
        ],
        # --- A stale source (surfaced as stale) ---------------------------
        "stale": [
            _claim("s.press", "An older press mention associates the company "
                   "with 'freight visibility'", AVAIL_SUPPORTED, "press",
                   "old_mention", freshness=FRESH_STALE),
        ],
        # competitor requests have no owning subsystem (Gap 2)
        "competitor_request": True,
        "note": DEMO_NOTE,
    }
