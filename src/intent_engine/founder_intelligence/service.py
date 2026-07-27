"""FounderIntelligenceService (T023.5) — the canonical orchestration path.

Runs the intelligence pass in the exact trust sequence and writes only
`data/founder_intelligence.jsonl`. It creates a run, validates input,
resolves identity, records approved sources, assembles the trust-sequenced
sections from SourceClaims, and captures a reproducible snapshot. It holds
no action surface — no publish, send, execute, or external action — and no
run may use another run's or another company's claims.
"""
from __future__ import annotations

import hashlib

from intent_engine.company_ingestion.quality import (
    QUALITY_RULES_VERSION,
)
from intent_engine.agentos.identity import stable_id as _kernel_stable_id

from intent_engine.founder_intelligence import (
    confidence as _confidence, perspective as _persp, questions as _questions,
    understanding as _understanding,
)
from intent_engine.founder_intelligence.conversation import answer as _answer
from intent_engine.founder_intelligence.hooks import select_hook
from intent_engine.founder_intelligence.identity import resolve_identity
from intent_engine.founder_intelligence.intake import (
    consent_record, validate_input,
)
from intent_engine.founder_intelligence.records import (
    ASSEMBLING, ANALYZING, COMPLETE, FounderIntelligenceError,
    FounderIntelligenceEvent, IDENTITY_MISMATCH, IDENTITY_RESOLVED, INGESTING,
    PARTIAL, REJECTED, VALIDATING, assert_trust_sequence, canonical_domain,
    json_normalize, now_iso,
)
from intent_engine.founder_intelligence.state import (
    WorkspaceRuns, fold_runs, validate_fi_event,
)
from intent_engine.founder_intelligence.store import (
    DEFAULT_FI_PATH, FounderIntelligenceStore,
)


# Pipeline component versions. These participate in run identity (see
# FounderIntelligenceService.analysis_version), so bumping one deliberately
# invalidates cached runs produced by the older behaviour rather than serving
# them as current.
ANALYSIS_VERSION = "1.1.0"
DISCOVERY_POLICY_VERSION = "1.1.0"
EVIDENCE_TAXONOMY_VERSION = "1.0.0"
SYNTHESIS_VERSION = "1.1.0"


def analysis_fingerprint(company_input) -> str:
    """Short, stable digest of everything that defines one analysis.

    Covers the approved source set AND the pipeline version, so two analyses
    of the same company on the same day are the SAME run only when they used
    the same evidence and the same code. Anything else is genuinely a
    different analysis and gets its own identity instead of colliding with an
    existing record.
    """
    approved = tuple(sorted(getattr(company_input, "approved_inputs", ()) or ()))
    seed = "|".join((
        FounderIntelligenceService.analysis_version(),
        "approved=" + ",".join(str(a) for a in approved),
    ))
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


def _dont_believe_entries(cbs) -> list:
    """What THIS run cannot yet support, derived from the evidence actually
    present. Generic entries (of the "pricing may matter" or "customers may be
    confused" kind) are never emitted — each entry names the missing evidence
    and what would resolve it."""
    def _has(section, prefix):
        return any(c.claim_id.startswith(prefix)
                   for c in cbs.get(section, []) or [])

    entries = []
    if not _has("market_view", "mv.customer_language"):
        entries.append({
            "id": "independent_view",
            "headline": "We do not yet have an independent view of how this "
                        "company is perceived.",
            "why_insufficient": "every approved source in this run is "
                                "published by the company itself, so nothing "
                                "here can contradict its own positioning",
            "what_would_change": "one independent source — market reporting, "
                                 "an analyst note, a review site, or a "
                                 "customer interview"})
    if not _has("understanding", "u.pricing") or any(
            c.claim_id == "u.pricing" and c.availability == "UNAVAILABLE"
            for c in cbs.get("understanding", []) or []):
        entries.append({
            "id": "commercial_model",
            "headline": "We cannot yet describe how this company charges.",
            "why_insufficient": "no public pricing or packaging page was "
                                "retrievable in this run",
            "what_would_change": "a public pricing page, a published rate "
                                 "card, or contract/procurement disclosure"})
    if not _has("understanding", "u.customers"):
        entries.append({
            "id": "customer_outcomes",
            "headline": "We cannot yet say what outcomes customers actually "
                        "get.",
            "why_insufficient": "no customer story, case study, or use-case "
                                "evidence was retrievable",
            "what_would_change": "an official customer story or case study, "
                                 "or an approved independent account"})
    return entries


class FounderIntelligenceService:
    def __init__(self, path=DEFAULT_FI_PATH, *, llm_client=None,
                 model_version="fake-model.v0"):
        self.store = FounderIntelligenceStore(path)
        self.llm_client = llm_client
        self.model_version = model_version

    # --- write path ----------------------------------------------------------
    def _stable_id(self, key: str) -> str:
        return _kernel_stable_id(self.store, key)

    @staticmethod
    def analysis_version() -> str:
        """The pipeline version a run was produced by.

        Bump any component here and previously cached runs stop being reused,
        because the run identity changes. That is the point: a run produced by
        an older discovery policy or quality ruleset must not be served as if
        the current pipeline had produced it.
        """
        return "|".join([
            f"analysis={ANALYSIS_VERSION}",
            f"discovery={DISCOVERY_POLICY_VERSION}",
            f"evidence={EVIDENCE_TAXONOMY_VERSION}",
            f"quality={QUALITY_RULES_VERSION}",
            f"synthesis={SYNTHESIS_VERSION}",
        ])

    def _record(self, event_type, *, run_id, company_domain, actor_type="system",
                actor_id="founder_intelligence", source="system", payload=None,
                subject_type=None, subject_id=None, idempotency_key=None,
                provenance=None) -> FounderIntelligenceEvent:
        candidate = FounderIntelligenceEvent(
            event_type=event_type, actor_type=actor_type, actor_id=actor_id,
            source=source, run_id=run_id, company_domain=company_domain,
            subject_type=subject_type, subject_id=subject_id,
            payload=json_normalize(dict(payload or {})),
            provenance=json_normalize(dict(provenance or {})),
            idempotency_key=idempotency_key)
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.content_fingerprint() != candidate.content_fingerprint():
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already used "
                        "for different content")
                return existing
        ok, reason = validate_fi_event(self.get_runs(), candidate)
        if not ok:
            raise FounderIntelligenceError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    def _transition(self, run_id, company_domain, to):
        self._record("fi.run_transitioned", run_id=run_id,
                     company_domain=company_domain,
                     payload={"to": to},
                     idempotency_key=f"transition:{run_id}:{to}")

    # --- the canonical run ---------------------------------------------------
    def run(self, *, company_name, website, requester_role=None,
            business_question=None, claims_by_section, as_of,
            resolved_domain=None, approved_inputs=(),
            competitor_supported=False) -> dict:
        """Execute the intelligence pass in the trust sequence. `claims_by_
        section` is the run-scoped SourceClaim set (from the demo fixture or
        approved-source adapters) — the service composes, it computes no
        intelligence."""
        company_input = validate_input(
            company_name=company_name, website=website,
            requester_role=requester_role, business_question=business_question,
            approved_inputs=approved_inputs)
        domain = canonical_domain(website)
        # INCIDENT FIX: the identity seed must cover everything that defines
        # the analysis, not just the company and the date.
        #
        # It was `run:{domain}:{as_of}`. The recorded payload, however,
        # embeds `approved_inputs` — the actual source set — which legitimately
        # differs between two analyses of the same company on the same day,
        # because discovery is affected by which pages respond. So the second
        # analysis reused the key with different content and `_record` raised
        #   ValueError: idempotency_key 'run:palantir.com:<date>' was already
        #   used for different content
        # surfacing to the tester as HTTP 500. Palantir and Shopify failed this
        # way; Sony only survived because both its runs produced identical
        # near-empty content, so the fingerprints happened to match.
        #
        # Folding the analysis fingerprint in means: identical inputs AND
        # identical pipeline version still collapse to one run (the
        # idempotent-retry contract below is preserved), while a genuinely
        # different analysis gets its own identity instead of colliding. It
        # also stops a stale low-quality run from trapping the user after the
        # pipeline improves — a new version simply cannot reuse the old id.
        seed = f"run:{domain}:{as_of}:{analysis_fingerprint(company_input)}"
        run_id = self._stable_id(seed)

        # CREATED -> VALIDATING
        self._record("fi.run_created", run_id=run_id, company_domain=domain,
                     subject_type="run", subject_id=run_id,
                     payload={"input": company_input.as_dict(),
                              "consent": consent_record(company_input)},
                     # This key MUST stay equal to the seed `_stable_id` looks
                     # up, or a retry mints a fresh run_id and duplicates the
                     # run — violating the documented idempotent-retry
                     # contract. Discovered by the web layer's cross-user
                     # isolation test.
                     idempotency_key=seed)
        self._transition(run_id, domain, VALIDATING)

        # identity
        identity = resolve_identity(
            company_name=company_name, website=website, as_of=as_of,
            resolved_domain=resolved_domain)
        if identity.identity_confidence == IDENTITY_MISMATCH:
            self._record("fi.run_rejected", run_id=run_id, company_domain=domain,
                         payload={"reason": "identity mismatch — the website "
                                            "resolves to a different "
                                            "organization; confirm before "
                                            "analysis"},
                         idempotency_key=f"reject:{run_id}")
            return {"run_id": run_id, "status": REJECTED,
                    "reason": "identity mismatch — stopped, not merged"}
        self._transition(run_id, domain, IDENTITY_RESOLVED)
        self._record("fi.identity_resolved", run_id=run_id, company_domain=domain,
                     payload={"identity": identity.as_dict()},
                     idempotency_key=f"identity:{run_id}")

        # ingest approved inputs (recorded; nothing fetched)
        self._transition(run_id, domain, INGESTING)
        # analyze -> assemble
        self._transition(run_id, domain, ANALYZING)
        self._transition(run_id, domain, ASSEMBLING)

        sections = self._assemble_sections(claims_by_section,
                                           competitor_supported)
        assert_trust_sequence(sections)
        for section in sections:
            self._record("fi.section_assembled", run_id=run_id,
                         company_domain=domain, subject_type="section",
                         subject_id=section.kind,
                         payload={"section_kind": section.kind,
                                  "availability": section.availability},
                         idempotency_key=f"section:{run_id}:{section.kind}")

        limitations = [l for s in sections for l in s.limitations]
        complete = any(s.kind == "company_understanding"
                       and s.availability == "SUPPORTED" for s in sections)
        self._record("fi.run_completed", run_id=run_id, company_domain=domain,
                     payload={"complete": complete, "limitations": limitations},
                     idempotency_key=f"complete:{run_id}")
        return {
            "run_id": run_id, "company_domain": domain,
            "status": COMPLETE if complete else PARTIAL,
            "identity": identity.as_dict(),
            "sections": [s.as_dict() for s in sections],
            "limitations": limitations,
            "note": "synthetic/approved-source analysis; every claim cites a "
                    "source artifact and its freshness",
        }

    def _assemble_sections(self, cbs: dict, competitor_supported) -> list:
        """Compose the trust-sequenced sections. Order is fixed here."""
        understanding = cbs.get("understanding", [])
        analytics = cbs.get("analytics", [])
        market = cbs.get("market_view", [])
        persona = cbs.get("persona", [])
        blind = cbs.get("blind_spot", [])
        assumption = cbs.get("assumption", [])
        attention = cbs.get("attention", [])
        opportunity = cbs.get("opportunity", [])

        company_lang = next((c for c in market if "company" in c.claim_id), None)
        customer_lang = next((c for c in market if "customer" in c.claim_id),
                             None)
        # Take the assumptions as supplied rather than matching brittle
        # claim-id suffixes: the first is the visible assumption, a second (if
        # present) is the complicating evidence.
        visible_assumption = assumption[0] if assumption else None
        complicating = assumption[1] if len(assumption) > 1 else None

        hook = select_hook(blind_spot_claims=blind, market_view_claims=market,
                           persona_claims=persona)

        all_claims = [c for group in cbs.values()
                      if isinstance(group, list) for c in group]
        # Company-specific skepticism: state what THIS run cannot support,
        # derived from the evidence families actually present. Never a generic
        # "pricing may matter" entry.
        dont_believe = _dont_believe_entries(cbs)

        return [
            _understanding.assemble_understanding(understanding),
            _understanding.assemble_analytics(analytics),
            _persp.assemble_stood_out(hook),
            _persp.assemble_market_view(company_lang, customer_lang),
            _persp.assemble_blind_spots(blind),
            _persp.assemble_assumptions(visible_assumption, complicating),
            _persp.assemble_attention(attention),
            _confidence.assemble_confidence(all_claims),
            _persp.assemble_dont_believe_yet(dont_believe),
            _questions.assemble_leadership_questions(
                understanding + market + persona),
            _persp.assemble_competitors(
                supported=bool(cbs.get("competitor")) or competitor_supported,
                claims=cbs.get("competitor", ())),
            _persp.assemble_opportunities(opportunity),
        ]

    def converse(self, run_id: str, question: str, *, run_claims) -> dict:
        """A public follow-up over THIS run's claims only."""
        return _answer(question, run_claims=run_claims,
                       llm_client=self.llm_client,
                       model_version=self.model_version)

    def record_feedback(self, run_id, company_domain, *, useful: str,
                        note: str = "", actor_id="founder") -> str:
        """Feedback is founder input, not accepted truth; it never mutates
        intelligence."""
        from intent_engine.founder_intelligence.records import assert_no_secret
        assert_no_secret(note, where="feedback")
        fid = self._stable_id(f"feedback:{run_id}:{useful}")
        self._record("fi.feedback_recorded", run_id=run_id,
                     company_domain=company_domain, actor_type="human",
                     actor_id=actor_id, subject_type="feedback", subject_id=fid,
                     payload={"feedback_id": fid, "useful": useful,
                              "note": note,
                              "authority": "founder feedback — evidence for "
                                           "future product evaluation, not a "
                                           "change to domain intelligence"},
                     idempotency_key=f"feedback:{run_id}:{useful}")
        return fid

    def record_telemetry(self, run_id, company_domain, event: str) -> None:
        self._record("fi.telemetry_event", run_id=run_id,
                     company_domain=company_domain, subject_type="telemetry",
                     payload={"event": event},
                     idempotency_key=f"telemetry:{run_id}:{event}")

    # --- reads ---------------------------------------------------------------
    def get_runs(self) -> WorkspaceRuns:
        return fold_runs(self.store.read_all(), validate=True)

    def run_status(self, run_id: str) -> str:
        run = self.get_runs().runs.get(run_id)
        return run.status if run else "UNKNOWN"
