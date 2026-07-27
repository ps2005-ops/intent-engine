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

    # Sitemap evidence family -> (source_type, source_class) in the existing
    # candidate contract, so sitemap-discovered URLs flow through the same
    # approval, retrieval, and classification path as every other candidate.
    _FAMILY_TO_TYPE = {
        "investor": ("external_approved", "investor_material"),
        "customers": ("customers", "company_owned"),
        "documentation": ("product", "company_owned"),
        "product": ("product", "company_owned"),
        "newsroom": ("blog", "executive_statement"),
        "leadership": ("about", "company_owned"),
        "pricing": ("pricing", "company_owned"),
        "careers": ("careers", "company_owned"),
    }

    def _sitemap_candidates(self, website: str) -> list:
        """Publisher-listed URLs grouped by evidence family. Fully defensive:
        any failure yields nothing, so discovery is never broken by it."""
        from intent_engine.company_ingestion.sitemap import (
            discover_from_sitemap,
        )

        def fetcher(url):
            # sitemaps are served as XML; this widened MIME set applies ONLY to
            # discovery reads, never to documents admitted as evidence.
            return safe_fetch(url, transport=self.transport,
                              resolver=self.resolver,
                              extra_mime_prefixes=("application/xml",
                                                   "text/xml"))

        try:
            found = discover_from_sitemap(website, fetcher=fetcher)
        except Exception:                                   # noqa: BLE001
            return []
        out = []
        for entry in found:
            source_type, source_class = self._FAMILY_TO_TYPE.get(
                entry["family"], ("product", "company_owned"))
            out.append({
                "url": entry["url"],
                "source_type": source_type,
                "discovery_method": "known_path",
                "same_domain": True,
                "source_class": source_class,
                "why_useful": f"{entry['family']} evidence listed in the "
                              "company's own sitemap",
                "why_relevant": ("published by the company in its sitemap — a "
                                 "real, canonical URL rather than a guess"),
            })
        return out

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
        # Sitemap/robots discovery: the publisher's OWN list of real, canonical
        # URLs. Guessed known-paths mostly 403/404; sitemap URLs exist by
        # construction, and this works even when the homepage is JavaScript-
        # rendered and exposes no links. robots.txt Disallow is honoured.
        candidates = candidates + self._sitemap_candidates(meta["website"])
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
        # Deduplicate by URL. The same page is legitimately found by more than
        # one discovery path (a guessed known path AND the sitemap), and each
        # produces a different payload for the same candidate_id — which would
        # collide on the candidate's idempotency key and abort discovery.
        #
        # A SITEMAP-listed URL wins over a guessed known path for the same URL:
        # the sitemap entry is publisher-verified and carries the publisher's
        # own classification, whereas the guess is only a hypothesis. Order is
        # otherwise preserved, so discovery stays deterministic.
        def _verified(candidate):
            return "sitemap" in candidate.get("why_relevant", "")

        best_by_url: dict = {}
        for candidate in candidates:
            url = candidate["url"]
            if url not in best_by_url:
                best_by_url[url] = candidate
            elif _verified(candidate) and not _verified(best_by_url[url]):
                best_by_url[url] = candidate
        candidates = list(best_by_url.values())
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
    def fetch_approved(self, run_id: str, *, candidate_ids=None) -> dict:
        """Fetch ONLY approved candidates; idempotent per source+content;
        partial success is honest.

        ``candidate_ids`` restricts/extends the fetch to an explicit set — used
        by the quality retry loop to retrieve ADDITIONAL evidence for families
        the first pass missed. Every id must still be a discovered candidate of
        this run, and the original approval remains immutable.
        """
        meta = self.run_meta(run_id)
        approval = self.store.approval(run_id)
        if approval is None:
            raise IngestionError("no approval recorded — nothing may be "
                                 "fetched")
        domain = meta["domain"]
        self._transition(run_id, domain, "FETCHING_APPROVED_SOURCES")
        candidates = {c["candidate_id"]: c
                      for c in self.store.candidates(run_id)}
        targets = (list(candidate_ids) if candidate_ids is not None
                   else list(approval["approved_candidate_ids"]))
        unknown = [i for i in targets if i not in candidates]
        if unknown:
            raise IngestionError(f"cannot fetch unknown candidates: {unknown}")
        already = {r["source_id"]: r for r in self.store.retrieved(run_id)}
        total_bytes = sum(r.get("byte_count", 0) for r in already.values())
        ok, failed = [], []
        for candidate_id in targets:
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
        # Semantic coverage: WHICH kinds of evidence the report rests on, and
        # what is missing. A source count alone cannot express that three SEC
        # filings say nothing about the product or its customers.
        from intent_engine.company_ingestion.coverage import (
            EVIDENCE_REPORT_READY, assess, missing_family_guidance,
        )
        coverage = assess(documents)
        coverage["next_evidence_steps"] = missing_family_guidance(
            coverage["missing_core"])
        result["coverage"] = coverage
        # Deterministic report-quality gate: retrieval succeeding is not the
        # same as the report being useful. Scored here so callers can decide to
        # rediscover before publishing (see analyze_with_quality).
        from intent_engine.company_ingestion.quality import (
            assess as assess_quality,
        )
        result["quality"] = assess_quality(result, documents,
                                           company_name=meta["company_name"])
        final = "COMPLETE" if not failures else "PARTIAL"
        # Honest downgrade: a run whose evidence does not span enough
        # independent families is never presented as COMPLETE, even when every
        # approved source happened to retrieve successfully.
        if final == "COMPLETE" and coverage["state"] != EVIDENCE_REPORT_READY:
            final = "PARTIAL"
        self._transition(run_id, domain, final)
        result["ingestion_status"] = final
        return result

    # --- quality-gated composition (retry + targeted rediscovery) ------------
    def compose_with_quality(self, run_id: str, *, fi_service,
                             max_passes=None, **compose_kwargs) -> dict:
        """Compose, score the report, and — when the quality gate says more
        evidence would plausibly help — retrieve targeted additional sources
        and compose again. Bounded, deterministic, and fully diagnosed.

        Never fabricates: a retry only approves candidates that were ALREADY
        discovered for this run, never re-requests a URL that failed, and stops
        as soon as quality passes or the budget is spent. If the report is
        still short of the bar, it is published as explicitly LIMITED — never
        as complete.
        """
        from intent_engine.company_ingestion.quality import (
            REPORT_QUALITY_FAIL, REPORT_QUALITY_PASS, REPORT_QUALITY_RETRYABLE,
            downgrade_to_limited, evidence_gaps,
        )
        from intent_engine.company_ingestion.retry import (
            MAX_RETRY_PASSES, plan_retry,
        )
        budget = MAX_RETRY_PASSES if max_passes is None else max_passes
        # Gather evidence to sufficiency BEFORE synthesising. Composing once
        # per evidence set would mint a second report run for the same
        # (company, as_of) — so the retry loop runs on the evidence, not on a
        # throwaway report, and the report is synthesised exactly once.
        history = []
        attempted: set = set()
        for attempt in range(1, budget + 1):
            gaps = evidence_gaps(self.store.retrieved(run_id))
            if gaps["sufficient"]:
                break
            approval = self.store.approval(run_id) or {}
            already = set(approval.get("approved_candidate_ids", ())) | attempted
            failed_ids = {f.get("candidate_id")
                          for f in self.store.failures(run_id)}
            failed_urls = {c["url"] for c in self.store.candidates(run_id)
                           if c["candidate_id"] in failed_ids}
            extra = plan_retry(
                missing_families=gaps["missing_families"],
                candidates=self.store.candidates(run_id),
                already_approved=already, failed_urls=failed_urls)
            if not extra:
                break                    # nothing new could be tried
            reason = ("missing evidence families: "
                      + ", ".join(gaps["missing_families"][:4]))
            self._append("ci.run_transitioned", run_id=run_id,
                         domain=self.run_meta(run_id)["domain"],
                         payload={"to": "DISCOVERING_SOURCES",
                                  "retry_pass": attempt, "reason": reason,
                                  "targets": list(extra)},
                         idempotency_key=f"ci-retry:{run_id}:{attempt}")
            attempted.update(extra)
            before = dict(gaps)
            self.fetch_approved(run_id, candidate_ids=extra)
            after = evidence_gaps(self.store.retrieved(run_id))
            history.append({"pass": attempt, "reason": reason,
                            "new_sources": list(extra),
                            "families_before": before["families"],
                            "families_after": after["families"],
                            "documents_before": before["document_count"],
                            "documents_after": after["document_count"]})

        result = self.compose(run_id, fi_service=fi_service, **compose_kwargs)
        if "quality" not in result:
            # No source could be retrieved at all: compose already returned an
            # honest FAILED run with no report to score. Rediscovery cannot
            # help — record why and leave the failure exactly as it is.
            result["quality_history"] = history + [
                {"pass": "final", "outcome": REPORT_QUALITY_FAIL,
                 "failed_rules": ["no approved source could be retrieved"]}]
            result["quality_passes"] = sum(1 for h in history
                                           if isinstance(h.get("pass"), int))
            return result
        history.append({"pass": "final",
                        "outcome": result["quality"]["outcome"],
                        "metrics": result["quality"]["metrics"],
                        "failed_rules": result["quality"]["failed_rules"]})
        if result["quality"]["outcome"] == REPORT_QUALITY_RETRYABLE:
            result["quality"] = downgrade_to_limited(result["quality"])
            history.append({"pass": "downgrade",
                            "outcome": result["quality"]["outcome"],
                            "note": "evidence rediscovery exhausted; "
                                    "published as a clearly limited report"})
        result["quality_history"] = history
        result["quality_passes"] = sum(1 for h in history
                                       if isinstance(h.get("pass"), int))
        if result["quality"]["outcome"] == REPORT_QUALITY_PASS:
            result.setdefault("quality_note", "")
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
        # Failed sources are shown by their READABLE identity (title/URL/host),
        # never by an opaque internal candidate id.
        from urllib.parse import urlparse
        by_id = {c["candidate_id"]: c for c in self.store.candidates(run_id)}
        for failure in self.store.failures(run_id):
            candidate = by_id.get(failure.get("candidate_id")) or {}
            url = candidate.get("url", "")
            host = (urlparse(url).hostname or "") if url else ""
            groups["unavailable_or_failed"].append(
                {"title": candidate.get("title") or host or "Company page",
                 "origin": url or host or "a requested page",
                 "source_family": candidate.get("source_class",
                                                "company_owned"),
                 "failure_type": failure["failure_type"],
                 "message": failure["safe_message"],
                 "retryable": failure["retryable"]})
        return groups
