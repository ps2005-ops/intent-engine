"""V1.1 CompanyIngestionService — discovery → approval → retrieval →
claims → Founder Intelligence composition. Append-only, idempotent,
restart-safe. No source is fetched before its explicit approval.
"""
from __future__ import annotations

import hashlib

from intent_engine.agentos.identity import stable_id as _kernel_stable_id
from intent_engine.company_ingestion.claims import (
    build_claims, executive_overview,
)
from intent_engine.company_ingestion.discovery import discover_candidates
from intent_engine.company_ingestion.edgar import propose_edgar_candidates
from intent_engine.company_ingestion.external_discovery import (
    propose_external_candidates,
)
from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.company_ingestion.parsing import parse_html
from intent_engine.company_ingestion.pasted import pasted_source
from intent_engine.company_ingestion.records import (
    IngestionError, IngestionEvent, MAX_APPROVED_SOURCES,
    MAX_TOTAL_BYTES_PER_RUN, failure_record, retrieved_record,
)
from intent_engine.company_ingestion.store import DEFAULT_CI_PATH, IngestionStore
from intent_engine.company_ingestion.validation import (
    canonical_domain, validate_candidate_url,
)
from intent_engine.founder_intelligence.records import assert_no_secret

CONSENT_VERSION = "v1.1-source-approval"


class CompanyIngestionService:
    def __init__(self, path=DEFAULT_CI_PATH, *, transport=None,
                 resolver=None):
        self.store = IngestionStore(path)
        self.transport = transport      # injectable; None = real HTTP
        self.resolver = resolver        # injectable; False disables DNS check

    # --- plumbing --------------------------------------------------------------
    def _append(self, event_type, *, run_id, domain, actor_type="system",
                actor_id="company_ingestion", subject_type=None,
                subject_id=None, payload=None, idempotency_key=None):
        return self.store.append(IngestionEvent(
            event_type=event_type, actor_type=actor_type, actor_id=actor_id,
            run_id=run_id, company_domain=domain, subject_type=subject_type,
            subject_id=subject_id, payload=dict(payload or {}),
            idempotency_key=idempotency_key))

    def _transition(self, run_id, domain, to):
        self._append("ci.run_transitioned", run_id=run_id, domain=domain,
                     payload={"to": to},
                     idempotency_key=f"ci-transition:{run_id}:{to}")

    # --- run lifecycle -----------------------------------------------------------
    def create_run(self, *, company_name: str, website: str,
                   user_id: str, as_of: str) -> dict:
        website = validate_candidate_url(website)
        assert_no_secret(company_name, where="company name")
        domain = canonical_domain(website)
        stable_key = f"ci-run:{domain}:{user_id}:{as_of}"
        run_id = _kernel_stable_id(self.store, stable_key)
        self._append("ci.run_created", run_id=run_id, domain=domain,
                     actor_type="human", actor_id=user_id,
                     subject_type="run", subject_id=run_id,
                     payload={"company_name": company_name,
                              "website": website, "user_id": user_id,
                              "as_of": as_of},
                     idempotency_key=stable_key)
        return {"run_id": run_id, "domain": domain, "website": website}

    def run_meta(self, run_id: str):
        for row in self.store.for_run(run_id):
            if row.event_type == "ci.run_created":
                return dict(row.payload, domain=row.company_domain)
        return None

    # --- discovery ---------------------------------------------------------------
    def discover(self, run_id: str) -> list:
        """One bounded homepage fetch → candidate list. Idempotent: stored
        candidates are returned on rerun without refetching."""
        stored = self.store.candidates(run_id)
        if stored:
            return stored
        meta = self.run_meta(run_id)
        if meta is None:
            raise IngestionError(f"no such run {run_id!r}")
        domain = meta["domain"]
        self._transition(run_id, domain, "DISCOVERING_SOURCES")
        result = safe_fetch(meta["website"], transport=self.transport,
                            resolver=self.resolver)
        links = []
        if result["ok"]:
            links = parse_html(result["body"])["links"]
        candidates = discover_candidates(company_url=meta["website"],
                                         homepage_links=links)
        # Bounded external-source proposals (customer voice etc.) broaden the
        # evidence beyond company-owned pages. Off-domain, UNVERIFIED, and
        # (like every candidate) fetched only after explicit approval.
        candidates = candidates + propose_external_candidates(
            company_name=meta.get("company_name", ""), domain=domain)
        # Authoritative structured fallback: for public companies, official SEC
        # EDGAR filings are permitted, server-rendered (non-JavaScript) HTML —
        # so a run is not at the mercy of a JavaScript-only marketing site.
        # Fully defensive: yields nothing (never raises) if the company is not
        # a filer or SEC is unreachable, so discovery is never broken by it.
        candidates = candidates + propose_edgar_candidates(
            company_name=meta.get("company_name", ""),
            transport=self.transport, resolver=self.resolver)
        for i, candidate in enumerate(candidates):
            candidate_id = f"cand-{hashlib.sha256(candidate['url'].encode()).hexdigest()[:12]}"
            availability = candidate.get("availability")
            if availability is None:
                availability = ("PROPOSED" if result["ok"] or
                                candidate["discovery_method"] != "homepage_link"
                                else "UNVERIFIED")
            payload = dict(candidate, candidate_id=candidate_id,
                           company_id=domain, rank=i, availability=availability)
            self._append("ci.candidate_discovered", run_id=run_id,
                         domain=domain, subject_type="candidate",
                         subject_id=candidate_id, payload=payload,
                         idempotency_key=f"cand:{run_id}:{candidate_id}")
        if not result["ok"]:
            self._append("ci.retrieval_failed", run_id=run_id, domain=domain,
                         subject_type="failure", subject_id="homepage",
                         payload=failure_record(
                             failure_id=f"fail-home-{run_id[:8]}",
                             run_id=run_id, candidate_id="homepage",
                             failure_type=result["failure_type"],
                             safe_message=result["safe_message"],
                             retryable=result.get("retryable", False)),
                         idempotency_key=f"fail:{run_id}:homepage")
        self._transition(run_id, domain, "AWAITING_SOURCE_APPROVAL")
        return self.store.candidates(run_id)

    # --- approval ------------------------------------------------------------------
    def approve(self, run_id: str, *, user_id: str, approved_ids: list,
                rejected_ids: list) -> dict:
        existing = self.store.approval(run_id)
        if existing is not None:
            return existing              # immutable approval history
        meta = self.run_meta(run_id)
        if meta is None:
            raise IngestionError(f"no such run {run_id!r}")
        if meta["user_id"] != user_id:
            raise IngestionError("approval must come from the run's owner")
        known = {c["candidate_id"] for c in self.store.candidates(run_id)}
        unknown = [i for i in approved_ids if i not in known]
        if unknown:
            raise IngestionError(f"approval references unknown candidates: "
                                 f"{unknown}")
        if len(approved_ids) > MAX_APPROVED_SOURCES:
            raise IngestionError(
                f"at most {MAX_APPROVED_SOURCES} sources per analysis run")
        if not approved_ids:
            raise IngestionError("approve at least one source")
        payload = {"approval_id": f"appr-{run_id[:12]}", "run_id": run_id,
                   "user_id": user_id,
                   "approved_candidate_ids": list(approved_ids),
                   "rejected_candidate_ids": list(rejected_ids),
                   "consent_version": CONSENT_VERSION}
        self._append("ci.approval_recorded", run_id=run_id,
                     domain=meta["domain"], actor_type="human",
                     actor_id=user_id, subject_type="approval",
                     subject_id=payload["approval_id"], payload=payload,
                     idempotency_key=f"appr:{run_id}")
        return payload

    # --- retrieval -------------------------------------------------------------------
    def fetch_approved(self, run_id: str) -> dict:
        """Fetch ONLY approved candidates; idempotent per source+content;
        partial success is honest."""
        meta = self.run_meta(run_id)
        approval = self.store.approval(run_id)
        if approval is None:
            raise IngestionError("no approval recorded — nothing may be "
                                 "fetched")
        domain = meta["domain"]
        self._transition(run_id, domain, "FETCHING_APPROVED_SOURCES")
        candidates = {c["candidate_id"]: c
                      for c in self.store.candidates(run_id)}
        already = {r["source_id"]: r for r in self.store.retrieved(run_id)}
        total_bytes = sum(r.get("byte_count", 0) for r in already.values())
        ok, failed = [], []
        for candidate_id in approval["approved_candidate_ids"]:
            candidate = candidates[candidate_id]
            source_id = f"src-{candidate_id[5:]}"
            if source_id in already:
                ok.append(already[source_id])
                continue
            if total_bytes >= MAX_TOTAL_BYTES_PER_RUN:
                failed.append(self._fail(run_id, domain, candidate_id,
                                         "too_large",
                                         "run byte budget exhausted", False))
                continue
            result = safe_fetch(candidate["url"], transport=self.transport,
                                resolver=self.resolver)
            if not result["ok"]:
                failed.append(self._fail(
                    run_id, domain, candidate_id, result["failure_type"],
                    result["safe_message"], result.get("retryable", False)))
                continue
            self._transition(run_id, domain, "PARSING_SOURCES")
            parsed = parse_html(result["body"])
            if not parsed["text"].strip():
                # Fetched successfully but yielded no readable text — a
                # JavaScript-only shell or an empty document. Record it as a
                # per-source failure rather than admitting an empty "document"
                # that would silently pad an otherwise evidence-free report.
                failed.append(self._fail(
                    run_id, domain, candidate_id, "javascript_only",
                    "page returned no readable text (JavaScript-only or "
                    "empty document)", False))
                continue
            freshness = "CURRENT"
            if parsed.get("modified_date"):
                from datetime import datetime, timezone
                try:
                    modified = datetime.fromisoformat(
                        parsed["modified_date"].replace("Z", "+00:00"))
                    if modified.tzinfo is None:
                        modified = modified.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc)
                                - modified).days
                    if age_days > 400:
                        freshness = "STALE"
                except ValueError:
                    pass                 # a date we cannot parse stays CURRENT
            record = retrieved_record(
                source_id=source_id, run_id=run_id, company_id=domain,
                original_url=candidate["url"], final_url=result["final_url"],
                source_type=candidate["source_type"],
                source_class=candidate.get("source_class", "company_owned"),
                status_code=result.get("status_code", 200),
                mime_type=result.get("mime_type", "text/html"),
                content_hash=parsed["content_hash"],
                byte_count=len(result["body"].encode()),
                title=parsed["title"] or candidate.get("title"),
                text_content=parsed["text"][:120_000],
                meta_description=parsed["meta_description"][:500],
                freshness=freshness)
            total_bytes += record["byte_count"]
            self._append("ci.source_retrieved", run_id=run_id, domain=domain,
                         subject_type="source", subject_id=source_id,
                         payload=record,
                         idempotency_key=f"src:{run_id}:{source_id}:"
                                         f"{record['content_hash'][:12]}")
            ok.append(record)
        return {"ok": ok, "failed": failed,
                "status": "COMPLETE" if not failed
                else ("PARTIAL" if ok else "FAILED")}

    def _fail(self, run_id, domain, candidate_id, failure_type, message,
              retryable):
        existing = self.store.find_by_idempotency_key(
            f"fail:{run_id}:{candidate_id}")
        if existing is not None:
            return existing.payload      # idempotent retry, same failure
        payload = failure_record(
            failure_id=f"fail-{candidate_id[5:]}", run_id=run_id,
            candidate_id=candidate_id, failure_type=failure_type,
            safe_message=message, retryable=retryable)
        self._append("ci.retrieval_failed", run_id=run_id, domain=domain,
                     subject_type="failure", subject_id=payload["failure_id"],
                     payload=payload,
                     idempotency_key=f"fail:{run_id}:{candidate_id}")
        return payload

    # --- pasted evidence ----------------------------------------------------------
    def add_pasted(self, run_id: str, *, user_id: str, label: str,
                   origin: str, text: str, privacy: str,
                   authorized: bool, date_known: str = "",
                   source_class: str = "independent_reporting") -> dict:
        meta = self.run_meta(run_id)
        if meta is None or meta["user_id"] != user_id:
            raise IngestionError("pasted evidence must come from the run's "
                                 "owner")
        record = pasted_source(run_id=run_id, company_id=meta["domain"],
                               label=label, origin=origin, text=text,
                               privacy=privacy, authorized=authorized,
                               date_known=date_known, source_class=source_class)
        self._append("ci.pasted_evidence_added", run_id=run_id,
                     domain=meta["domain"], actor_type="human",
                     actor_id=user_id, subject_type="source",
                     subject_id=record["source_id"], payload=record,
                     idempotency_key=f"pasted:{run_id}:"
                                     f"{record['source_id']}")
        return record

    # --- composition ------------------------------------------------------------------
    def compose(self, run_id: str, *, fi_service, competitor_approved=False,
                extra_observations=(), previous_model=None):
        """Build real claims and run the existing Founder Intelligence
        composition. Deterministic; restart-safe (rebuilds from stored
        documents).

        ``extra_observations`` is a bounded, explicit source-addition hook:
        curated/approved StrategicObservations (e.g. the Shopify validation
        fixture, or classified external sources) added to the ones derived
        from retrieved documents before strategic reasoning runs."""
        meta = self.run_meta(run_id)
        domain = meta["domain"]
        documents = self.store.retrieved(run_id)
        failures = self.store.failures(run_id)
        if not documents:
            self._transition(run_id, domain, "FAILED")
            return {"status": "FAILED",
                    "reason": "no approved source could be retrieved; "
                              "failed retrieval is not evidence of "
                              "real-world absence"}
        self._transition(run_id, domain, "BUILDING_SOURCE_ARTIFACTS")
        claims = build_claims(documents=documents,
                              company_name=meta["company_name"],
                              domain=domain,
                              competitor_approved=competitor_approved)
        self._transition(run_id, domain, "ASSEMBLING_COMPANY_UNDERSTANDING")
        self._append("ci.claims_built", run_id=run_id, domain=domain,
                     subject_type="claims", subject_id=run_id,
                     payload={"sections": {k: len(v) for k, v in
                                           claims.items()
                                           if isinstance(v, list)}},
                     idempotency_key=f"claims:{run_id}:{len(documents)}")
        self._transition(run_id, domain, "ASSEMBLING_REPORT")
        result = fi_service.run(
            company_name=meta["company_name"], website=meta["website"],
            claims_by_section=claims, as_of=meta["as_of"],
            approved_inputs=tuple(d["source_id"] for d in documents))
        result["ingestion_run_id"] = run_id
        result["overview"] = executive_overview(
            claims, company_name=meta["company_name"],
            source_count=len(documents), failure_count=len(failures))
        result["evidence_library"] = self.evidence_library(run_id)
        # V1.2 strategic intelligence layer: derive structured observations
        # from the approved documents and run the deterministic strategic
        # reasoning engine over them. Additive — the legacy sections are
        # untouched. Company-owned-only evidence is honestly marked partial by
        # the strategic quality gate.
        result["strategic_report"] = self._strategic_report(
            meta["company_name"], documents, extra_observations,
            previous_model=previous_model)
        final = "COMPLETE" if not failures else "PARTIAL"
        self._transition(run_id, domain, final)
        result["ingestion_status"] = final
        return result

    def _strategic_report(self, company_name, documents, extra_observations,
                          previous_model=None):
        from intent_engine.strategic_intelligence.observations import (
            derive_observations,
        )
        from intent_engine.strategic_intelligence.reasoning import (
            build_strategic_report,
        )
        observations = derive_observations(documents)
        observations += list(extra_observations or ())
        if not observations:
            return None
        report = build_strategic_report(company_name=company_name,
                                        observations=observations,
                                        previous_model=previous_model)
        return report.as_dict()

    # --- evidence library ---------------------------------------------------------
    def evidence_library(self, run_id: str) -> dict:
        groups = {"company_website": [], "external_public": [],
                  "user_provided": [], "unavailable_or_failed": []}
        seen = set()
        for record in self.store.retrieved(run_id):
            if record["source_id"] in seen:
                continue
            seen.add(record["source_id"])
            entry = {"title": record.get("title"),
                     "origin": record["final_url"],
                     "source_type": record["source_type"],
                     "retrieved_at": record["retrieved_at"],
                     "hash": record["content_hash"][:12],
                     "freshness": record["freshness"],
                     "retrieval_status": record["retrieval_status"]}
            if record["source_type"] == "pasted":
                groups["user_provided"].append(entry)
            elif record["source_type"] == "external_approved":
                groups["external_public"].append(entry)
            else:
                groups["company_website"].append(entry)
        for failure in self.store.failures(run_id):
            groups["unavailable_or_failed"].append(
                {"origin": failure["candidate_id"],
                 "failure_type": failure["failure_type"],
                 "message": failure["safe_message"],
                 "retryable": failure["retryable"]})
        return groups
