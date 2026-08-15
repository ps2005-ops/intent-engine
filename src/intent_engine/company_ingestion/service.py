"""V1.1 CompanyIngestionService — discovery → approval → retrieval →
claims → Founder Intelligence composition. Append-only, idempotent,
restart-safe. No source is fetched before its explicit approval.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

from intent_engine.agentos.identity import stable_id as _kernel_stable_id
from intent_engine.company_ingestion.claims import (
    build_claims, executive_overview,
)
from intent_engine.company_ingestion.discovery import discover_candidates
from intent_engine.company_ingestion.edgar import propose_edgar_candidates
from intent_engine.company_ingestion.entities import (
    entity_identity_facts, official_fallback_candidates, resolve_entity,
)
from intent_engine.company_ingestion.external_discovery import (
    propose_external_candidates,
)
from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.company_ingestion.filing_text import (
    is_filing_document, parse_filing_html,
)
from intent_engine.company_ingestion.parsing import parse_html, readable_title
from intent_engine.company_ingestion.pasted import pasted_source
from intent_engine.company_ingestion.readiness import (
    assess_readiness, explain as explain_readiness,
)
from intent_engine.company_ingestion.records import (
    IngestionError, IngestionEvent, MAX_APPROVED_SOURCES,
    MAX_RESPONSE_BYTES, MAX_TOTAL_BYTES_PER_RUN, failure_record,
    retrieved_record,
)
from intent_engine.company_ingestion.store import DEFAULT_CI_PATH, IngestionStore
from intent_engine.company_ingestion.validation import (
    canonical_domain, validate_candidate_url,
)
from intent_engine.founder_intelligence.records import (
    SecretRejected, assert_no_secret,
)

CONSENT_VERSION = "v1.1-source-approval"


class CompanyIngestionService:
    def __init__(self, path=DEFAULT_CI_PATH, *, transport=None,
                 resolver=None, analyst_client=None, analyst_cache=None):
        self.store = IngestionStore(path)
        self.transport = transport      # injectable; None = real HTTP
        self.resolver = resolver        # injectable; False disables DNS check
        # The reasoning backend. None means "not configured", which produces
        # an honest EVIDENCE_LIMITED result -- never a template dressed up as
        # a finding. Injected in tests with a recorded client so CI makes no
        # model calls.
        self._analyst_client = analyst_client
        self._analyst_cache = analyst_cache

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
                   user_id: str, as_of: str, cik: str = "") -> dict:
        """Open a run. A website is optional when a CIK identifies the filer.

        WHY A RUN MAY HAVE NO WEBSITE. Typed entry resolves any SEC
        registrant, but the regulator records no web domain -- so Toyota and
        Vale were identified and then could not be analysed. Guessing
        `toyota.com` would send retrieval at whatever sits there; the
        authoritative material is the company's own filings, which are
        reachable from the CIK alone.

        THE DOMAIN STAYS EMPTY, deliberately. Substituting `sec.gov` would
        make the REGULATOR the company's website: filings would group as
        company-published material from the sec.gov origin, and the
        independence count would read one origin for every filer on earth.
        The domain is what the company publishes on, and this company
        publishes nowhere we know of.
        """
        website = validate_candidate_url(website) if website else ""
        assert_no_secret(company_name, where="company name")
        domain = canonical_domain(website) if website else ""
        cik = str(cik or "").strip()
        if not domain and not cik:
            raise IngestionError(
                "a run needs either a website or the CIK of a filer; with "
                "neither there is no subject to retrieve")
        # The run's identity anchor. Keyed on the CIK when there is no
        # domain -- keying on the empty string would give every domainless
        # company the same run id on a given day and silently merge two
        # companies' evidence into one run.
        subject_key = domain or f"sec-cik:{cik}"
        stable_key = f"ci-run:{subject_key}:{user_id}:{as_of}"
        run_id = _kernel_stable_id(self.store, stable_key)
        self._append("ci.run_created", run_id=run_id, domain=domain,
                     actor_type="human", actor_id=user_id,
                     subject_type="run", subject_id=run_id,
                     payload={"company_name": company_name,
                              "website": website, "user_id": user_id,
                              "as_of": as_of, "cik": cik,
                              "subject_key": subject_key},
                     idempotency_key=stable_key)
        return {"run_id": run_id, "domain": domain, "website": website,
                "cik": cik, "subject_key": subject_key}

    def run_meta(self, run_id: str):
        for row in self.store.for_run(run_id):
            if row.event_type == "ci.run_created":
                return dict(row.payload, domain=row.company_domain)
        return None

    # --- entity identity ---------------------------------------------------
    def _identity_for(self, run_id: str, meta: dict) -> dict:
        """Resolve and persist WHO this run is about, independently of what it
        manages to retrieve.

        The Sony failure was not only a retrieval failure. The run had no
        asserted identity at all, so the entity became a side effect of the
        documents: one 6-K arrived, and the report was about whatever that
        filing was about. Establishing identity first means a thin evidence set
        produces a thin report about the RIGHT company, not a confident report
        about the wrong one.

        Recorded once per run (append-only, idempotent). Returns a dict with
        `entity_resolved`, the stored facts, and — for in-process callers only —
        the profile under `_profile`, which is never persisted.
        """
        resolution = resolve_entity(company_name=meta.get("company_name", ""),
                                    website=meta.get("website", ""))
        payload = {"run_id": run_id,
                   "status": resolution.status,
                   "reason": resolution.reason,
                   "entity_resolved": resolution.resolved,
                   "choices": resolution.as_dict()["choices"]}
        if resolution.resolved:
            payload.update(entity_identity_facts(resolution.profile))
            payload["entity_id"] = resolution.profile.entity_id
        elif meta.get("company_name") and (meta["domain"] or meta.get("cik")):
            # The registry is small by design, so "not in the registry" is the
            # normal case, not a failure. A name plus a domain that validated
            # still names a subject well enough to analyse — what is NOT
            # acceptable is having neither, which is the only case the
            # readiness gate treats as an unresolved identity.
            #
            # A CIK counts, and counts for MORE than a domain: a domain is
            # bought and resold, while a CIK is assigned by the regulator to
            # one filer and identifies exactly the entity whose filings are
            # about to be read. Without this branch a domainless filer was
            # identified at the door and then declared unidentified here.
            payload["fallback_subject"] = meta["company_name"]
            payload["fallback_domain"] = meta["domain"]
            if meta.get("cik"):
                payload["fallback_cik"] = str(meta["cik"])
        self._append("ci.entity_identified", run_id=run_id,
                     domain=meta["domain"], subject_type="identity",
                     subject_id=payload.get("entity_id", "unresolved"),
                     payload=payload,
                     idempotency_key=f"identity:{run_id}")
        out = dict(payload)
        out["_profile"] = resolution.profile
        return out

    def entity_identity(self, run_id: str) -> dict:
        """The persisted identity record for a run, or {} if none."""
        for row in self.store.for_run(run_id):
            if row.event_type == "ci.entity_identified":
                return dict(row.payload)
        return {}

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
        candidates = []
        # A run with no website made no homepage request, so there is no
        # homepage outcome. `ok` rather than a failure: recording a homepage
        # RETRIEVAL FAILURE for a company we never claimed had a homepage
        # would put a fabricated failure in the run's own record and count
        # against its source health.
        result = {"ok": True, "failure_type": "", "safe_message": ""}
        # EVERY DISCOVERY PATH BELOW STARTS FROM A DOMAIN. A run opened on a
        # CIK alone has none, and each of these would either fetch the empty
        # string or propose candidates on a guessed host. They are skipped
        # rather than fed a placeholder: the EDGAR path further down needs no
        # domain, and for a filer it is the authoritative source anyway.
        if meta.get("website"):
            result = safe_fetch(meta["website"], transport=self.transport,
                                resolver=self.resolver)
            links = []
            if result["ok"]:
                links = parse_html(result["body"])["links"]
            candidates = discover_candidates(company_url=meta["website"],
                                             homepage_links=links)
            # Sitemap/robots discovery: the publisher's OWN list of real,
            # canonical URLs. Guessed known-paths mostly 403/404; sitemap URLs
            # exist by construction, and this works even when the homepage is
            # JavaScript-rendered and exposes no links. robots.txt Disallow is
            # honoured.
            candidates = candidates + self._sitemap_candidates(meta["website"])
            # Bounded external-source proposals (customer voice etc.) broaden
            # the evidence beyond company-owned pages. Off-domain, UNVERIFIED,
            # and (like every candidate) fetched only after explicit approval.
            candidates = candidates + propose_external_candidates(
                company_name=meta.get("company_name", ""), domain=domain)
        # Authoritative structured fallback: for public companies, official SEC
        # EDGAR filings are permitted, server-rendered (non-JavaScript) HTML —
        # so a run is not at the mercy of a JavaScript-only marketing site.
        # Fully defensive: yields nothing (never raises) if the company is not
        # a filer or SEC is unreachable, so discovery is never broken by it.
        candidates = candidates + propose_edgar_candidates(
            company_name=meta.get("company_name", ""),
            cik=str(meta.get("cik") or ""),
            transport=self.transport, resolver=self.resolver)
        # THE ONLY INDEPENDENT VANTAGE POINT WE CAN ACTUALLY REACH.
        #
        # Ten companies produced ZERO independent sources: every one was the
        # company describing itself. The families that would fix that were
        # probed and are not accessible without bypassing controls we will not
        # bypass -- review sites answer 403, newswire feeds 401/404. What IS
        # public is EDGAR full-text search, where a COMPETITOR'S OWN 10-K names
        # this company. Different author, regulatory venue, exact date,
        # permanent citation.
        candidates = candidates + self._third_party_filing_candidates(meta)
        # Curated official sources for a KNOWN entity. This is what stops a
        # multinational whose primary domain refuses automated access from
        # collapsing into whatever single filing happened to be reachable:
        # investor relations, earnings, annual/integrated reports, newsroom and
        # segment pages live at stable URLs that are not derivable from a
        # homepage we could not read. Bounded, approval-gated, and classified by
        # authority + entity relationship, so a subsidiary page can never be
        # read as the parent speaking.
        identity = self._identity_for(run_id, meta)
        if identity.get("entity_resolved"):
            candidates = candidates + official_fallback_candidates(
                identity["_profile"], exclude_urls=[c["url"]
                                                    for c in candidates])
        # Deduplicate by URL. The same page is legitimately found by more than
        # one discovery path (a guessed known path AND the sitemap), and each
        # produces a different payload for the same candidate_id — which would
        # collide on the candidate's idempotency key and abort discovery.
        #
        # When the same URL arrives by several routes, keep the payload from
        # the route that says the most about it:
        #
        #   0. a curated official source — a human asserted what this page is
        #      and whose voice it speaks in;
        #   1. a sitemap entry — publisher-verified to exist, and carries the
        #      publisher's own classification;
        #   2. a guessed known path — only a hypothesis.
        #
        # Keeping the guess instead silently demotes a curated source to a
        # guess: Palantir's commercial-offerings page is both a registry entry
        # AND a path we would have guessed, and because the guess was generated
        # first it won — so the page ranked as a guess and was never selected.
        def _route_rank(candidate):
            if candidate.get("discovery_method") == "official_fallback":
                return 0
            return 1 if "sitemap" in candidate.get("why_relevant", "") else 2

        best_by_url: dict = {}
        for candidate in candidates:
            url = candidate["url"]
            incumbent = best_by_url.get(url)
            if incumbent is None or _route_rank(candidate) < \
                    _route_rank(incumbent):
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

    # --- observed reachability ---------------------------------------------
    # Failure types that mean "this host will not serve us", as opposed to
    # "this particular page is missing". A 404 says nothing about the host.
    _HOST_REFUSAL_FAILURES = ("http_status", "connection", "timeout",
                              "blocked", "host_unreachable")

    #: Failures that are about the HOST rather than the path. A 404 says this
    #: page is missing; a read timeout says nobody is answering, and the next
    #: nine URLs on that host will each pay the full timeout to learn the
    #: same thing.
    _HOST_LEVEL_FAILURES = ("connection", "timeout")

    #: How many host-level failures before this run stops dialling a host.
    #: Two, not one: a single read timeout can be transient, and paying it
    #: twice is cheap insurance against suppressing a host that would have
    #: answered. Measured on the breaker cohort, where AMD and McKinsey each
    #: took ten timeouts at CONNECT_TIMEOUT_S=8 -- about eighty seconds per
    #: pass, three passes deep, and they were the only two runs over 150s.
    _DEAD_HOST_AFTER = 2

    def _host_failure_counts(self, run_id: str, candidates: dict) -> dict:
        """How many HOST-LEVEL failures each host has produced in this run.

        Counts only `connection` and `timeout` — a 404 or a 403 is about the
        path or the request, and one missing page must never take a whole
        host out of the run.
        """
        counts: dict = {}
        for failure in self.store.failures(run_id):
            if failure.get("failure_type") not in self._HOST_LEVEL_FAILURES:
                continue
            candidate = candidates.get(failure.get("candidate_id")) or {}
            host = urlparse(candidate.get("url") or "").hostname
            if host:
                counts[host] = counts.get(host, 0) + 1
        return counts

    def refusing_hosts(self, run_id: str) -> set:
        """Hosts this run has ALREADY watched refuse us.

        Discovery fetches the homepage before anything is approved, so by the
        time sources are selected we often already know the company's own
        domain answers 403 to every request. Nothing consumed that knowledge:
        selection ranked `sony.com` investor-relations pages above SEC filings
        that were sitting there, retrievable, and the run admitted zero
        documents while five candidates would have worked.

        Deliberately conservative — only hosts we personally watched fail, and
        only on failures that are about the host rather than the path.
        """
        meta = self.run_meta(run_id) or {}
        by_id = {c["candidate_id"]: c for c in self.store.candidates(run_id)}
        refused, seen_ok = set(), set()
        for record in self.store.retrieved(run_id):
            host = urlparse(record.get("final_url") or "").hostname
            if host:
                seen_ok.add(host)
        for failure in self.store.failures(run_id):
            if failure.get("failure_type") not in self._HOST_REFUSAL_FAILURES:
                continue
            message = failure.get("safe_message") or ""
            if failure.get("failure_type") == "http_status" and \
                    "404" in message:
                continue                 # a missing page, not a closed door
            candidate_id = failure.get("candidate_id")
            if candidate_id == "homepage":
                host = urlparse(meta.get("website") or "").hostname
            else:
                host = urlparse(
                    (by_id.get(candidate_id) or {}).get("url") or "").hostname
            if host:
                refused.add(host)
        return {h for h in refused if h not in seen_ok}

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
        # THE DEAD-HOST BREAKER. Seeded from the DURABLE failure store, not a
        # local set, so it also covers the bounded rediscovery passes
        # `compose_with_quality` runs afterwards -- which is where the same
        # dead host was being dialled a second and third time.
        host_failures = self._host_failure_counts(run_id, candidates)
        ok, failed = [], []
        for candidate_id in targets:
            candidate = candidates[candidate_id]
            source_id = f"src-{candidate_id[5:]}"
            host = urlparse(candidate.get("url") or "").hostname
            if host and host_failures.get(host, 0) >= self._DEAD_HOST_AFTER \
                    and source_id not in already:
                # Not a finding about the company: a host that has already
                # refused to answer twice in this run is recorded as
                # unreachable rather than dialled again for eight seconds.
                failed.append(self._fail(
                    run_id, domain, candidate_id, "host_unreachable",
                    f"{host} failed {host_failures[host]} times earlier in "
                    f"this run; not dialled again", True))
                continue
            if source_id in already:
                ok.append(already[source_id])
                continue
            if total_bytes >= MAX_TOTAL_BYTES_PER_RUN:
                failed.append(self._fail(run_id, domain, candidate_id,
                                         "too_large",
                                         "run byte budget exhausted", False))
                continue
            # Investor decks, shareholder letters and annual reports are often
            # PDFs; fetch those as raw bytes through the same guarded path.
            from intent_engine.company_ingestion.pdf import (
                PDF_MIME_PREFIXES, PDF_OK, extract_pdf, is_pdf,
            )
            wants_pdf = is_pdf(url=candidate["url"])
            result = safe_fetch(
                candidate["url"], transport=self.transport,
                resolver=self.resolver,
                extra_mime_prefixes=PDF_MIME_PREFIXES if wants_pdf else (),
                binary=wants_pdf,
                # Filings only, flagged by the EDGAR adapter. `max_bytes`
                # raises the budget for a statutory document, because most
                # large-cap filings exceed the general 2MB cap and were being
                # discarded whole — measured live on Caterpillar, whose 10-Q
                # came back "too large" and left the run bounded.
                # `accept_truncated` is the fallback for anything past even
                # that budget; nothing downstream may call such a read
                # complete.
                accept_truncated=bool(candidate.get("accept_truncated")),
                max_bytes=int(candidate.get("max_bytes")
                              or MAX_RESPONSE_BYTES))
            if not result["ok"]:
                failed.append(self._fail(
                    run_id, domain, candidate_id, result["failure_type"],
                    result["safe_message"], result.get("retryable", False)))
                # Count it immediately so the breaker trips WITHIN this pass.
                # Seeding from the store alone would only help the next pass,
                # and the ten timeouts that motivated this were all in one.
                if host and result["failure_type"] in self._HOST_LEVEL_FAILURES:
                    host_failures[host] = host_failures.get(host, 0) + 1
                continue
            self._transition(run_id, domain, "PARSING_SOURCES")
            body = result["body"]
            if wants_pdf or is_pdf(mime=result.get("mime_type", ""),
                                   body=body if isinstance(body, bytes) else b""):
                raw = body if isinstance(body, bytes) else body.encode()
                document = extract_pdf(raw, url=candidate["url"])
                if document["status"] != PDF_OK:
                    # An encrypted, malformed, or image-only PDF is recorded
                    # as an honest failure — never admitted as empty evidence.
                    failed.append(self._fail(
                        run_id, domain, candidate_id, "parse_error",
                        document["reason"], False))
                    continue
                parsed = {"title": readable_title(document["title"],
                                                  candidate.get("title")),
                          "meta_description": "",
                          "text": document["text"],
                          "content_hash": document["content_hash"],
                          "modified_date": "", "links": [],
                          "extraction_mode": "pdf",
                          "blocks_found": 0}
            elif is_filing_document(url=candidate["url"],
                                    form=candidate.get("form", "")):
                # A regulatory filing is not a web page and is not parsed like
                # one. `parse_html` buffers text only inside `<p>`/`<li>`/`<td>`
                # and a modern inline-XBRL filing contains NONE of the first
                # two — Datadog's 10-K has zero `<p>` and 4,857 `<span>`, so
                # 93% of the document was silently discarded and Item 7 never
                # reached a detector. Ordinary pages keep the ordinary parser.
                parsed = parse_filing_html(
                    body, url=candidate["url"],
                    form=candidate.get("form", ""),
                    truncated=bool(result.get("truncated")),
                    status_code=result.get("status_code", 200),
                    mime_type=result.get("mime_type", "text/html"))
            else:
                parsed = parse_html(body)
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
            # A source whose text trips the credential detector is DROPPED, not
            # stored — but dropping it must cost this one source, never the
            # run. The detector is deliberately blunt (any 13–16 digit run
            # reads as a card number), and SEC EDGAR result pages concatenate
            # commission file numbers into exactly that shape. Letting the
            # exception escape turned one false positive on one public filing
            # into a total analysis failure with a generic error page.
            try:
                record = self._build_record(
                    source_id=source_id, run_id=run_id, domain=domain,
                    candidate=candidate, result=result, parsed=parsed,
                    body=body, freshness=freshness)
            except SecretRejected as exc:
                failed.append(self._fail(
                    run_id, domain, candidate_id, "content_rejected",
                    str(exc), False))
                continue
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

    def _build_record(self, *, source_id, run_id, domain, candidate, result,
                      parsed, body, freshness):
        return retrieved_record(
                source_id=source_id, run_id=run_id, company_id=domain,
                original_url=candidate["url"], final_url=result["final_url"],
                source_type=candidate["source_type"],
                source_class=candidate.get("source_class", "company_owned"),
                status_code=result.get("status_code", 200),
                mime_type=result.get("mime_type", "text/html"),
                content_hash=parsed["content_hash"],
                byte_count=(len(body) if isinstance(body, bytes)
                            else len(body.encode())),
                title=readable_title(parsed["title"],
                                     candidate.get("title")),
                # A FILING arrives already retained section by section, under
                # the same total bound. Slicing it again from the front would
                # reintroduce exactly the failure that retention exists to
                # remove — Item 1 alone runs to 98,000 characters in a Datadog
                # 10-K, so a front cut at 120,000 stores Business and stops
                # before MD&A. Everything else keeps the flat cap it had.
                text_content=(parsed["text"] if parsed.get("filing")
                              else parsed["text"][:120_000]),
                meta_description=parsed["meta_description"][:500],
                freshness=freshness,
                extraction_mode=parsed.get("extraction_mode", "body"),
                blocks_found=parsed.get("blocks_found") or 0,
                filing=parsed.get("filing"))

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
                extra_observations=(), previous_model=None, attempt: int = 1):
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
        # THE GATE. Decided before synthesis, on the evidence alone, because
        # synthesis is willing: given one filing it still produces a thesis,
        # hypotheses and leadership questions laid out exactly like a report
        # built on twenty sources, and the reader cannot tell the difference.
        # A warning would not help — a warning still renders the report, and
        # the rendered report is what does the damage.
        readiness = assess_readiness(
            documents=documents, identity=self.entity_identity(run_id),
            failures=failures, extra_observations=extra_observations,
            attempt=attempt)
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
        result["readiness"] = readiness
        result["readiness_explanation"] = explain_readiness(readiness)
        if readiness["may_synthesize"]:
            result["strategic_report"] = self._strategic_report(
                meta["company_name"], documents, extra_observations,
                previous_model=previous_model)
            self._record_reasoning(run_id, domain, documents,
                                   result["strategic_report"])
        else:
            # No strategic dashboard is built at all. Not a hidden one, not an
            # empty one — the section simply does not exist, so there is
            # nothing for a renderer to accidentally present as a finding.
            result["strategic_report"] = None
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
        # Persist quality diagnostics for every composition, so an operator can
        # always see why a run was published, retried, or limited.
        self._record_quality(run_id, result,
                             key=f"quality:{run_id}:{len(documents)}")
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
    def business_graph(self, run_id: str, result=None):
        """This run, in the platform's shared vocabulary.

        THE CALLER THE GRAPH DID NOT HAVE. The business graph shipped with a
        projection function and nothing that invoked it, which is integration
        in appearance only: `grep business_graph src/` returned nothing
        outside the graph package itself. Ingestion is the right owner because
        it already holds both inputs -- the retrieval log and the report the
        run produced -- so no new state and no adapter is introduced.

        Rebuilt on demand rather than stored. The graph is a projection of the
        append-only log, so persisting it would create a second copy that can
        disagree with the events it came from, and the events would still be
        the truth.
        """
        from intent_engine.business_graph.projections import from_ingestion_run
        if result is None:
            result = {}
        report = result.get("strategic_report")
        return from_ingestion_run(
            run_id=run_id,
            retrieved=[d for d in self.store.retrieved(run_id)
                       if d.get("retrieval_status") == "OK"],
            report=report)

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
                already_approved=already, failed_urls=failed_urls,
                refusing_hosts=self.refusing_hosts(run_id))
            if not extra:
                break                    # nothing new could be tried
            reason = ("missing evidence families: "
                      + ", ".join(gaps["missing_families"][:4]))
            # The key is derived from the TARGETS, not just the pass number: a
            # recompose after a restart legitimately plans a different set
            # (earlier targets are already retrieved), and reusing the key
            # would collide on differing content.
            target_key = hashlib.sha256(
                ",".join(sorted(extra)).encode()).hexdigest()[:12]
            self._append("ci.run_transitioned", run_id=run_id,
                         domain=self.run_meta(run_id)["domain"],
                         payload={"to": "DISCOVERING_SOURCES",
                                  "retry_pass": attempt, "reason": reason,
                                  "targets": list(extra)},
                         idempotency_key=f"ci-retry:{run_id}:{target_key}")
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

        # The evidence-gathering loop above IS the readiness gate's retry. Tell
        # the gate how many passes were actually spent, or it would report
        # "worth another look" to a user whose budget is already gone — and
        # offer them a retry button that could only repeat itself.
        spent = 1 + sum(1 for h in history if isinstance(h.get("pass"), int))
        result = self.compose(run_id, fi_service=fi_service, attempt=spent,
                              **compose_kwargs)
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
        self._record_quality(run_id, result)
        if result["quality"]["outcome"] == REPORT_QUALITY_PASS:
            result.setdefault("quality_note", "")
        return result

    def _record_quality(self, run_id, result, *, key=None) -> None:
        """Persist report-quality diagnostics so an operator can see WHY a run
        was published, retried, or limited. Deterministic and secret-free."""
        quality = result.get("quality") or {}
        history = result.get("quality_history") or []
        metrics = dict(quality.get("metrics") or {})
        initial = next((h for h in history if isinstance(h.get("pass"), int)),
                       None)
        payload = {
            "run_id": run_id,
            "outcome": quality.get("outcome"),
            "failed_rules": list(quality.get("failed_rules") or [])[:12],
            "retry_passes": result.get("quality_passes", 0),
            "retry_reasons": [h.get("reason") for h in history
                              if isinstance(h.get("pass"), int)],
            "families_initial": (initial or {}).get("families_before", []),
            "families_final": metrics.get("families", []),
            "successful_sources": metrics.get("successful_sources"),
            "populated_share": metrics.get("populated_share"),
            "placeholder_share": metrics.get("placeholder_share"),
            "has_product_evidence": metrics.get("has_product_evidence"),
            "has_customer_evidence": metrics.get("has_customer_evidence"),
            "has_strategy_evidence": metrics.get("has_strategy_evidence"),
            "legal_as_insight": metrics.get("legal_as_insight", []),
            "rules_version": quality.get("rules_version"),
            "ingestion_status": result.get("ingestion_status"),
        }
        meta = self.run_meta(run_id) or {}
        self._append("ci.quality_assessed", run_id=run_id,
                     domain=meta.get("domain", ""), subject_type="quality",
                     subject_id=run_id, payload=payload,
                     # Content-derived: a recompose (e.g. after a restart)
                     # legitimately produces a different diagnostic, and a
                     # pass-number key would collide on differing content.
                     idempotency_key=key or (
                         "quality-final:" + run_id + ":" + hashlib.sha256(
                             json.dumps(payload, sort_keys=True,
                                        default=str).encode()
                         ).hexdigest()[:12]))

    def quality_diagnostics(self, run_id: str):
        """The stored quality diagnostics for a run (operator surface)."""
        rows = [r.payload for r in self.store.for_run(run_id)
                if r.event_type == "ci.quality_assessed"]
        return rows[-1] if rows else None

    def _record_reasoning(self, run_id, domain, documents, report) -> None:
        """One event per synthesis attempt: did the rich path actually land?

        OPERATOR-ONLY. None of this reaches a founder screen. It exists
        because "the reasoning backend is configured" and "a grounded analysis
        was accepted" turned out to be very different things, and nothing in
        the system recorded the difference.
        """
        report = report or {}
        findings = report.get("critic_findings") or []
        causes: dict = {}
        for finding in findings:
            causes[finding.get("check", "unknown")] = \
                causes.get(finding.get("check", "unknown"), 0) + 1
        from intent_engine.strategic_intelligence.observations import (
            derive_analyst_evidence,
        )
        from intent_engine.strategic_intelligence.source_semantics import (
            independent_count,
        )
        evidence = derive_analyst_evidence(
            documents, (self.run_meta(run_id) or {}).get("company_name", ""))
        # `investor_material` is a COMPANY-authored filing; EDGAR is its venue,
        # not its author. Counting it as independent is what produced the
        # false "EDGAR supplied 10 independent sources" reading.
        independent = independent_count(
            getattr(o, "source_class", "") for o in evidence)
        filings = sum(1 for d in documents
                      if "sec.gov" in (d.get("final_url") or ""))
        self._append(
            "ci.reasoning_assessed", run_id=run_id, domain=domain,
            subject_type="reasoning", subject_id=run_id,
            payload={"run_id": run_id,
                     "attempted": bool(report),
                     "result_state": report.get("result_state"),
                     "provenance": report.get("reasoning_provenance"),
                     "accepted": report.get("reasoning_provenance")
                     == "grounded_analyst",
                     "rejection_causes": causes,
                     "documents": len(documents),
                     "analyst_evidence": len(evidence),
                     "independent_sources": independent,
                     "filings": filings},
            idempotency_key=f"reasoning:{run_id}:{len(documents)}")

    def reasoning_overview(self) -> dict:
        """Rich-analysis acceptance, for operators. Never founder-facing."""
        rows = [r.payload for r in self.store.read_all()
                if r.event_type == "ci.reasoning_assessed"]
        if not rows:
            return {"attempts": 0, "accepted": 0, "acceptance_rate": 0.0,
                    "top_rejection_causes": [], "averages": {}}
        attempts = len(rows)
        accepted = sum(1 for r in rows if r.get("accepted"))
        causes: dict = {}
        for r in rows:
            for cause, n in (r.get("rejection_causes") or {}).items():
                causes[cause] = causes.get(cause, 0) + n
        def mean(key):
            values = [r.get(key) or 0 for r in rows]
            return round(sum(values) / len(values), 2) if values else 0.0
        return {
            "attempts": attempts,
            "accepted": accepted,
            "rejected": attempts - accepted,
            "acceptance_rate": round(100.0 * accepted / attempts, 1),
            "top_rejection_causes": sorted(causes.items(),
                                           key=lambda kv: -kv[1]),
            "averages": {"documents": mean("documents"),
                         "analyst_evidence": mean("analyst_evidence"),
                         "independent_sources": mean("independent_sources"),
                         "filings": mean("filings")},
            "by_result_state": {
                state: sum(1 for r in rows if r.get("result_state") == state)
                for state in {r.get("result_state") for r in rows}},
        }

    def quality_overview(self) -> dict:
        """Cross-run report-quality health for authenticated operators:
        which runs failed, which were limited, and which evidence families are
        most often missing."""
        rows = [r for r in self.store.read_all()
                if r.event_type == "ci.quality_assessed"]
        by_outcome: dict = {}
        missing_family_counts: dict = {}
        runs = []
        for row in rows:
            payload = row.payload
            outcome = payload.get("outcome") or "UNKNOWN"
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
            for family in ("product", "customers", "strategy", "investor",
                           "identity"):
                if family not in (payload.get("families_final") or []):
                    missing_family_counts[family] = \
                        missing_family_counts.get(family, 0) + 1
            runs.append({"run_id": payload.get("run_id"),
                         "domain": row.company_domain,
                         "outcome": outcome,
                         "retry_passes": payload.get("retry_passes", 0),
                         "sources": payload.get("successful_sources"),
                         "populated_share": payload.get("populated_share")})
        return {"total_runs": len(rows), "by_outcome": by_outcome,
                "most_often_missing": sorted(missing_family_counts.items(),
                                             key=lambda kv: -kv[1]),
                "runs": runs[-50:]}

    def _strategic_report(self, company_name, documents, extra_observations,
                          previous_model=None):
        from intent_engine.strategic_intelligence.observations import (
            derive_analyst_evidence, derive_observations,
        )
        from intent_engine.strategic_intelligence.reasoning import (
            build_strategic_report,
        )
        observations = derive_observations(documents, company=company_name)
        observations += list(extra_observations or ())
        if not observations:
            # MEASURED: 2 of 5 real companies (Toyota, Costco) died here with
            # usable evidence in hand. `derive_observations` requires a
            # controlled-vocabulary SIGNAL match because a signal is the unit
            # the PATTERN LIBRARY matches against -- a requirement the analyst
            # does not share and which observations.py itself calls harmful to
            # conflate. Returning None here meant no signal keyword => no
            # analyst call at all, on evidence the analyst could have read.
            #
            # So fall back to the analyst's own derivation. The pattern library
            # simply matches nothing and contributes no hypotheses, which is
            # the honest outcome; the analyst still gets to read the evidence.
            observations = derive_analyst_evidence(documents, company_name)
            if not observations:
                return None
        report = build_strategic_report(company_name=company_name,
                                        observations=observations,
                                        previous_model=previous_model)
        payload = report.as_dict()

        # --- the reasoning layer ------------------------------------------
        # The pattern library above produced `payload["hypotheses"]`. Those
        # are scaffolds: useful as structure, not trustworthy as insight,
        # which is the whole reason this layer exists. So the result is
        # labelled with WHERE its reasoning came from, and the analyst's
        # verified output supersedes the scaffolds when it is available.
        #
        # When the analyst is not available the scaffolds are NOT quietly
        # presented as strategic conclusions. The state says so.
        from intent_engine.strategic_intelligence.analyst import (
            AnalystUnavailable, ResultState, analyse,
        )
        evidence = derive_analyst_evidence(documents, company_name)
        evidence += list(extra_observations or ())

        payload["reasoning_provenance"] = "pattern_library"
        payload["result_state"] = ResultState.EVIDENCE_LIMITED
        payload["strategic_analysis"] = None
        try:
            analysis, state, findings = analyse(
                company_name, evidence,
                client=self._analyst_client, cache=self._analyst_cache,
                entity_hint=self._entity_hint(company_name, documents))
        except AnalystUnavailable:
            payload["result_state"] = ResultState.EVIDENCE_LIMITED
            payload["result_state_detail"] = (
                "No reasoning backend is configured, so no strategic "
                "conclusion is asserted. The evidence below was retrieved and "
                "verified; the patterns shown are structural scaffolds, not "
                "findings about this company.")
            return payload

        payload["result_state"] = state
        payload["critic_findings"] = [
            {"check": f.check, "severity": f.severity, "message": f.message}
            for f in findings]
        if analysis is not None:
            payload["strategic_analysis"] = analysis.to_dict()
            if state == ResultState.COMPLETE:
                payload["reasoning_provenance"] = "grounded_analyst"
                # What changed since last time, and the one screen built from
                # it. A founder opening this every morning wants the delta,
                # not the same analysis again.
                from intent_engine.strategic_intelligence.analyst.memory import (
                    compare,
                )
                from intent_engine.strategic_intelligence.analyst.priority import (
                    daily_view,
                )
                prior = (previous_model or {}).get("strategic_analysis") \
                    if isinstance(previous_model, dict) else None
                memory = compare(
                    payload["strategic_analysis"], prior,
                    evidence_count=len(evidence),
                    previous_evidence_count=(previous_model or {}).get(
                        "evidence_count") if isinstance(previous_model, dict)
                    else None)
                payload["strategic_memory"] = memory
                payload["daily_view"] = daily_view(
                    payload["strategic_analysis"], memory=memory)
                payload["evidence_count"] = len(evidence)
        payload["result_state_detail"] = ResultState.EXPLANATION.get(state, "")
        # WHY IT WAS WITHHELD, in the reader's terms. The generic
        # STRATEGICALLY_INSUFFICIENT text says the pages were "descriptive
        # rather than strategic", which was measurably not the reason on these
        # runs -- they were refused for reaching after figures the sources did
        # not contain. A founder told the wrong reason acts on the wrong thing.
        # ONLY the states the EVIDENCE caused. This was `!= COMPLETE`, which
        # meant an analyst that never ran was explained as an evidence
        # shortfall -- found live when an exhausted API balance produced
        # FAILED and the reader was told every source was the company's own.
        # That founder collects more sources and nothing improves.
        if state in ResultState.EVIDENCE_EXPLAINED:
            from intent_engine.strategic_intelligence.numeric_ledger import (
                build_ledger,
            )
            from intent_engine.strategic_intelligence.source_semantics import (
                independent_count,
            )
            from intent_engine.strategic_intelligence import (
                withheld_explanation as WX,
            )
            explanation = WX.explain(
                findings=payload.get("critic_findings") or [],
                families=sorted({getattr(o, "source_class", "")
                                 for o in evidence
                                 if getattr(o, "source_class", "")}),
                independent_sources=independent_count(
                    getattr(o, "source_class", "") for o in evidence),
                document_count=len(documents),
                numeric_facts=len(build_ledger(evidence)))
            payload["withheld_explanation"] = explanation
            payload["result_state_detail"] = WX.render_text(explanation)
        return payload

    def subject_cik(self, meta) -> str:
        """The CIK of the company this run is about, or "".

        ONE SPELLING, TWO STAGES. Filing DISCOVERY uses this to refuse the
        subject's own filings as third-party candidates; independence
        MEASUREMENT uses it to refuse them as independent corroboration.
        They are the same question, and when only discovery could answer it
        the measurement stage silently counted a company's own 10-K as an
        outside vantage point -- which shipped, and was visible on the live
        preview as "two independent origins" for Cloudflare, one of them
        Cloudflare.

        A run started from a website carries no CIK, which is the ordinary
        case and the reason the fallback exists. Re-resolving by name is
        fuzzy and could return a DIFFERENT registrant, whose filings would
        then be excluded as "the subject's own" while the real subject's
        were kept as third-party -- the attribution error inverted. That is
        why the run's own CIK is preferred and the lookup never overrides it.
        """
        recorded = str((meta or {}).get("cik") or "").strip()
        if recorded:
            return recorded
        try:
            from intent_engine.company_ingestion.edgar import resolve_cik
            resolved = resolve_cik((meta or {}).get("company_name", ""),
                                   transport=self.transport,
                                   resolver=self.resolver)
            return str((resolved or {}).get("cik") or "")
        except Exception:  # noqa: BLE001 - subject identification is best-effort
            return ""

    def _third_party_filing_candidates(self, meta) -> list:
        """Filings by OTHER registrants naming this company. Never raises."""
        from intent_engine.company_ingestion.third_party_filings import (
            propose_third_party_filings,
        )
        # An injected transport means a test double or a replay, and the
        # full-text index is not part of it. Reaching the live endpoint from a
        # test suite is both wrong and slow -- it tripled the suite's runtime
        # the first time this shipped without the guard.
        if self.transport is not None:
            return []
        company_name = meta.get("company_name", "")
        subject_cik = self.subject_cik(meta)
        try:
            return propose_third_party_filings(
                company_name=company_name, subject_cik=subject_cik)
        except Exception:  # noqa: BLE001 - discovery must never break
            return []

    @staticmethod
    def _entity_hint(company_name, documents):
        """Tell the analyst when the evidence spans more than one entity."""
        hosts = {(d.get("final_url") or "").split("/")[2].lower()
                 for d in documents if (d.get("final_url") or "").count("/") > 2}
        if len(hosts) > 1:
            return ("Retrieved evidence spans more than one host "
                    f"({', '.join(sorted(hosts)[:5])}). Establish which legal "
                    "entity each fact belongs to before attributing it to "
                    f"{company_name}.")
        return None

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
