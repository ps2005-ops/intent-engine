"""V1.1 CompanyIngestionService — discovery → approval → retrieval →
claims → Founder Intelligence composition. Append-only, idempotent,
restart-safe. No source is fetched before its explicit approval.
"""
from __future__ import annotations

import hashlib
import logging
import pathlib
import json
import time
from urllib.parse import urlparse

from intent_engine.agentos.identity import stable_id as _kernel_stable_id
from intent_engine.company_ingestion.claims import (
    build_claims, executive_overview,
)
from intent_engine.company_ingestion.discovery import discover_candidates
from intent_engine.company_ingestion.edgar import (
    MAX_EDGAR_CANDIDATES, MAX_EDGAR_CANDIDATES_WEB_BLOCKED,
    propose_edgar_candidates,
)

#: THE RETRIEVAL PLAN'S RESULT CODES. What was actually available, named
#: once, so nothing downstream has to re-derive "was this company thinly
#: documented, or did our fetching fail?" from a failure count.
OFFICIAL_WEB_RETRIEVED = "OFFICIAL_WEB_RETRIEVED"
OFFICIAL_WEB_BLOCKED = "OFFICIAL_WEB_BLOCKED"
OFFICIAL_WEB_ABSENT = "OFFICIAL_WEB_ABSENT"
SEC_RETRIEVED = "SEC_RETRIEVED"
SEC_NONE = "SEC_NONE"
INDEPENDENT_RETRIEVED = "INDEPENDENT_RETRIEVED"
INDEPENDENT_NONE = "INDEPENDENT_NONE"
from intent_engine.company_ingestion.entities import (
    entity_identity_facts, official_fallback_candidates, resolve_entity,
)
from intent_engine.company_ingestion.external_discovery import (
    propose_external_candidates,
)
from intent_engine.company_ingestion.fetch import FetchResult, safe_fetch
from intent_engine.company_ingestion.acquisition_memory import (
    ALLOW as _ACQ_ALLOW, AcquisitionMemory,
)
from intent_engine.company_ingestion.filing_cache import FilingCache
from intent_engine.company_ingestion.snapshot import (
    PublicCompanySnapshot, SnapshotStore, SourceRecord,
    company_key as _company_key, plan_refresh)
from intent_engine.company_ingestion.transient import RetryLedger
from intent_engine.company_ingestion.filing_text import (
    is_filing_document, parse_filing_html,
)
from intent_engine.company_ingestion.parsing import parse_html, readable_title
from intent_engine.company_ingestion.pasted import pasted_source
from intent_engine.company_ingestion import source_coverage as _SC
from intent_engine.company_ingestion.readiness import (
    assess_readiness, explain as explain_readiness,
)
from intent_engine.company_ingestion.records import (
    CONNECT_TIMEOUT_S, IngestionError, IngestionEvent, MAX_APPROVED_SOURCES,
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


from concurrent.futures import TimeoutError as FuturesTimeout

_LOG = logging.getLogger(__name__)


def _bounded_result(future, deadline, stage: str, detail: str = "",
                    cap_s: float = 0.0):
    """A future's value, or None when the budget will not cover the wait.

    `may_start()` DECIDES WHETHER TO DISPATCH; THIS BOUNDS THE WAIT. The two
    are different questions and only the first was being asked here. A sitemap
    crawl or an EDGAR full-text search dispatched at t=5s with the budget
    intact could still be running at t=90s, and `future.result()` with no
    timeout waits for it however long that is -- so a run could pass every
    stage-level gate and still blow through the hard deadline inside one join.

    MEASURED: Microsoft, 517180e6, discovery 27.7s and retrieval 40.5s -- 63%
    of a 107.8s CORE, against a 60s interactive budget that nothing in this
    path could enforce.

    Returns None on timeout and records a gap, so the caller degrades to the
    candidates it already has instead of losing the run. A source that did not
    arrive in time is a bounded gap, which the reader is told about; it is not
    a failure.
    """
    if future is None:
        return None
    if deadline is None:
        return future.result()
    left = deadline.remaining
    # AN OPTIONAL BRANCH MAY NOT SPEND THE WHOLE BUDGET WAITING.
    #
    # MEASURED on NVIDIA at 6aefd58e: discovery 35.0s at 2% CPU, of which
    # ~18s was this join. The wait WAS bounded -- by everything that was
    # left, which on a 60s budget is generous enough never to bite. A source
    # class the product can do without does not get to decide how long the
    # reader waits, so an explicit cap applies on top of the budget.
    if cap_s > 0:
        left = min(left, cap_s)
    if left <= 0:
        deadline.record_gap(stage, detail or "no budget left to wait for it")
        future.cancel()
        return None
    try:
        return future.result(timeout=left)
    except FuturesTimeout:
        deadline.record_gap(
            stage, detail or f"did not return within {left:.1f}s of budget")
        future.cancel()
        return None


def _business_model_of(company_name, *, domain="", registrant=None,
                       evidence_text="") -> str:
    """This company's business-model class, or "" when it cannot be read.

    Empty is a real answer and the tension library fails closed on it: a
    tension we cannot rule out is not a tension we may assert.
    """
    try:
        from intent_engine.executive.company_profile import profile_for
        profile = profile_for(name=company_name, domain=domain,
                              registrant=registrant,
                              evidence_text=evidence_text)
        return profile.business_model_class if profile.known else ""
    except Exception:                                       # noqa: BLE001
        return ""


def _subject_evidence_text(documents, cik: str = "") -> str:
    """The SUBJECT'S OWN filing text, and nothing else.

    A competitor's 10-K describing ITS advertising revenue must never
    classify this company — that is how a rival's business model becomes
    the subject's. Two exclusions, both positive tests rather than trust:
    a document filed under a DIFFERENT registrant's EDGAR path is not this
    filer's, and a document the run itself classed `competitor` is not
    either.
    """
    from intent_engine.strategic_intelligence.observations import (
        subject_documents,
    )
    texts = []
    for doc in subject_documents(documents, subject_cik=cik):
        text = (doc.get("text_content") if isinstance(doc, dict)
                else getattr(doc, "text_content", "")) or ""
        texts.append(str(text))
    return "\n".join(texts)[:400_000]


def _patterns_for_company(company_name: str, domain: str = "",
                          registrant=None, evidence_text: str = ""):
    """The pattern library this company's business model can support.

    THE GATE IS ONLY AS GOOD AS WHAT IT IS TOLD. This asked `profile_for`
    for a classification while withholding the two inputs that produce one
    for any company outside the curated manifest — the regulator's industry
    code, and the filer's own revenue and segment sentences. Meta and Amazon
    are not in the manifest, so both resolved to UNKNOWN, UNKNOWN takes the
    whole library, and Meta was handed `capacity_ahead_of_demand` and told a
    chief executive about take-or-pay terms and ageing production lines. The
    applicability repair in `patterns_for` was correct and could not fire,
    because nothing ever reached it but UNKNOWN.

    `registrant` is the SEC's classification of this filer; `evidence_text`
    is the SUBJECT'S OWN filing text, which is what separates two businesses
    that share one industry code (SIC 7370 holds both Salesforce and Meta).
    Both are optional, and passing neither reproduces the old behaviour —
    which is why the seam test asserts the CALL SITE supplies them.

    Defensive by construction: a classification that cannot be resolved
    returns the whole library, so a profile lookup failing degrades to
    today's behaviour rather than to an empty analysis.
    """
    from intent_engine.strategic_intelligence.patterns import (PATTERN_LIBRARY,
                                                               patterns_for)
    try:
        from intent_engine.executive.company_profile import profile_for
        model = profile_for(name=company_name, domain=domain,
                            registrant=registrant,
                            evidence_text=evidence_text
                            ).business_model_class
    except Exception:                                       # noqa: BLE001
        return list(PATTERN_LIBRARY)
    return patterns_for(model)


#: §34. What the DEEP half of an analysis is doing, kept separate from the
#: run state because they answer different questions: the run state says
#: whether the pipeline is finished, this says whether the strategic reading
#: has arrived. A run can be COMPLETE with deep still PENDING, and a reader
#: who is shown one when they needed the other cannot tell what to wait for.
DEEP_PENDING = "PENDING"
DEEP_RUNNING = "RUNNING"
DEEP_COMPLETE = "COMPLETE"
DEEP_FAILED = "FAILED"
DEEP_UNAVAILABLE = "UNAVAILABLE"
DEEP_STATUSES = (DEEP_PENDING, DEEP_RUNNING, DEEP_COMPLETE, DEEP_FAILED,
                 DEEP_UNAVAILABLE)

#: §13. The decision fields a deep reading may change. Enums and identifiers
#: only -- a wording change literally cannot move any of them, so a "material
#: deep change" cannot be manufactured by rephrasing.
DEEP_MATERIAL_FIELDS = ("result_state", "reasoning_provenance")


class CompanyIngestionService:
    def __init__(self, path=DEFAULT_CI_PATH, *, transport=None,
                 resolver=None, analyst_client=None, analyst_cache=None,
                 filing_cache=None, retry_ledger=None,
                 acquisition_memory=None):
        self.store = IngestionStore(path)
        self.transport = transport      # injectable; None = real HTTP
        self.resolver = resolver        # injectable; False disables DNS check
        # SEC filings are immutable, publicly addressed documents, so the
        # 60-company programme re-reads the same bytes many times. The cache
        # holds RETRIEVED CONTENT only; every company-specific reading of
        # that content is recomputed per focal company. See filing_cache.
        self.filing_cache = (filing_cache if filing_cache is not None
                             else FilingCache())
        # WHERE A COMPANY'S PUBLIC STATE IS REMEMBERED BETWEEN RUNS.
        #
        # `FilingCache` already reuses IMMUTABLE documents -- an accessioned
        # 10-K cannot change, so re-requesting it is pure cost. What was
        # re-derived on every run is everything ELSE: which sources exist at
        # all. Measured on the preview, Microsoft spent 27.7s in discovery
        # re-proposing a source list it had already built, before a single
        # byte of evidence was fetched.
        #
        # Sibling of the store rather than inside it, so a snapshot that
        # cannot be read costs a run its head start and never its evidence.
        self.snapshots = SnapshotStore(pathlib.Path(path).parent)
        # WHAT WE ALREADY LEARNED ABOUT ASKING. `FilingCache` remembers
        # content and `SnapshotStore` remembers where to look; neither
        # remembers that `https://jnj.com/developers` answered 404 last time,
        # so every run re-bought that answer with one of its fourteen slots.
        # DISABLED under an injected transport: a test double defines its own
        # outcomes, and a memory written by one test would decide another.
        #
        # CO-LOCATED WITH THE STORE, exactly as `SnapshotStore` above is, and
        # for the same two reasons: in production the ingestion store lives on
        # the persistent disk (RUNTIME_ROOT), so the memory survives a deploy
        # and a cohort does not re-learn every dead URL; under test it lands in
        # the tmp path the store already uses, so the suite never writes into
        # the repository. A repo-relative default would have done both wrongly.
        self.acquisition_memory = (
            acquisition_memory if acquisition_memory is not None
            else AcquisitionMemory(
                pathlib.Path(path).parent / "cache" / "acquisition",
                enabled=(transport is None)))
        # RETRY ACCOUNTING IS PER RUN, AND THE DISTINCTION IS LOAD-BEARING.
        # The webapp builds exactly ONE of these services for the whole
        # process, so a ledger held on the service is shared by every
        # customer: the first analysis would spend the per-host and run
        # budgets and every later analysis in that process would get a
        # retry policy that never retries. An injected ledger is honoured
        # as-is, because a test that passes one wants to read it.
        self._injected_ledger = retry_ledger
        self._retry_ledgers: dict = {}
        # run_id -> what each retrieval avenue yielded.
        self._retrieval_plans: dict = {}
        self._registrant_cache: dict = {}
        self._classification_cache: dict = {}
        # The reasoning backend. None means "not configured", which produces
        # an honest EVIDENCE_LIMITED result -- never a template dressed up as
        # a finding. Injected in tests with a recorded client so CI makes no
        # model calls.
        self._analyst_client = analyst_client
        self._analyst_cache = analyst_cache

    def retry_ledger_for(self, run_id: str):
        """This run's retry accounting. One ledger per run, never per
        process — see the constructor for why that distinction matters."""
        if self._injected_ledger is not None:
            return self._injected_ledger
        ledger = self._retry_ledgers.get(run_id)
        if ledger is None:
            ledger = self._retry_ledgers[run_id] = RetryLedger()
        return ledger

    def retrieval_telemetry(self, run_id: str) -> dict:
        """What retrieval had to do to get this run's evidence.

        DIAGNOSTICS, NOT CUSTOMER COPY. A chief executive must never have to
        understand the phrase "429", a submissions-index size or a cache
        key. But when a run comes back thin, "sec.gov asked us to wait twice
        and we waited 3 seconds" is the difference between a defect in us
        and a fact about the company, and that answer previously existed
        only inside a local variable.
        """
        try:
            retry = self.retry_ledger_for(run_id).snapshot()
        except Exception:                                   # noqa: BLE001
            retry = {}
        try:
            cache = self.filing_cache.snapshot()
        except Exception:                                   # noqa: BLE001
            cache = {}
        try:
            memory = self.acquisition_memory.snapshot()
        except Exception:                                   # noqa: BLE001
            memory = {}
        return {"retry": retry, "filing_cache": cache,
                "acquisition_memory": memory,
                "sources": self.source_health(run_id),
                "evidence_roles": self.evidence_role_coverage(run_id),
                "abstention": self.abstention_reason(run_id)}

    #: The readiness ROLES, and which evidence families can fill each. This is
    #: `readiness`'s own grouping, imported rather than restated: a second
    #: copy would drift, and this file already learned that lesson three times
    #: over (`_EVIDENCE_FAMILIES`, `evidence_gaps` and `family_of` were three
    #: answers to "which family is this?").
    _ROLE_FAMILIES = {
        "identity_or_product": ("identity", "product"),
        "direction": ("strategy", "investor"),
        "market": ("customers", "independent", "commercial"),
    }

    def evidence_role_coverage(self, run_id: str) -> dict:
        """Which evidence ROLES this run filled, and which are still empty.

        Counting documents answers the wrong question: ten copies of one
        company narrative is weaker evidence than one filing, one independent
        filing and one economic source. The roles are what the readiness gate
        actually requires, so they are what a run should be measured against.
        """
        from intent_engine.company_ingestion.coverage import family_of
        try:
            documents = list(self.store.retrieved(run_id))
        except Exception:                                   # noqa: BLE001
            return {}
        families: dict = {}
        for document in documents:
            family = family_of(document)
            families[family] = families.get(family, 0) + 1
        covered = set(families)
        filled = [role for role, members in self._ROLE_FAMILIES.items()
                  if covered & set(members)]
        missing = [role for role in self._ROLE_FAMILIES if role not in filled]
        return {"required": sorted(self._ROLE_FAMILIES),
                "filled": sorted(filled), "missing": sorted(missing),
                "families": dict(sorted(families.items())),
                "documents": len(documents)}

    def source_health(self, run_id: str) -> dict:
        """Per-run acquisition outcomes, by cause and by host.

        The counts a qualification run needs to tell a degraded network from
        a degraded product, and the ones a live incident needs to tell which
        publisher stopped answering.
        """
        try:
            candidates = {c["candidate_id"]: c
                          for c in self.store.candidates(run_id)}
            failures = list(self.store.failures(run_id))
            retrieved = list(self.store.retrieved(run_id))
        except Exception:                                   # noqa: BLE001
            return {}
        counts = {"rate_limited": 0, "refused": 0, "not_found": 0,
                  "timed_out": 0, "budget": 0, "unreadable": 0, "other": 0}
        hosts: dict = {}
        for failure in failures:
            kind = failure.get("failure_type") or ""
            message = str(failure.get("safe_message") or "")
            url = (candidates.get(failure.get("candidate_id")) or {}).get("url")
            host = (urlparse(url or "").hostname or "")
            if host:
                hosts[host] = hosts.get(host, 0) + 1
            if kind == "deadline_exceeded":
                counts["budget"] += 1
            elif "429" in message:
                counts["rate_limited"] += 1
            elif any(c in message for c in ("401", "402", "403", "451")):
                counts["refused"] += 1
            elif "404" in message or "410" in message:
                counts["not_found"] += 1
            elif kind in ("timeout", "connection", "host_unreachable"):
                counts["timed_out"] += 1
            elif kind in ("javascript_only", "parse_error", "bad_mime",
                          "content_rejected", "too_large"):
                counts["unreadable"] += 1
            else:
                counts["other"] += 1
        requested = len(retrieved) + len(failures)
        return {"discovered": len(candidates), "requested": requested,
                "retrieved": len(retrieved), "failed": len(failures),
                "yield": (round(len(retrieved) / requested, 3)
                          if requested else 0.0),
                "by_cause": counts,
                "by_host": dict(sorted(hosts.items(),
                                       key=lambda kv: -kv[1])[:8])}

    def ownership_record(self, run_id: str) -> dict:
        """What this run decided about whose documents it was reading.

        Readable for ANY past run, including one nobody thought to
        instrument — which is the whole point. Empty dict means the run
        predates the event or never composed, and a caller must read that as
        UNKNOWN rather than as "no CIK".
        """
        try:
            for row in self.store.for_run(run_id):
                if row.event_type == "ci.ownership_resolved":
                    return dict(row.payload)
        except Exception:                                   # noqa: BLE001
            return {}
        return {}

    def retrieval_telemetry_overview(self) -> dict:
        """Retry and cache behaviour across every run this process served.

        Aggregated because the per-run ledgers are the unit of accounting
        but an operator asks a process-level question first: is SEC
        throttling us right now, and is the filing cache doing anything.
        """
        hosts: dict = {}
        retries = exhausted = 0
        seconds = 0.0
        for ledger in self._retry_ledgers.values():
            snap = ledger.snapshot()
            retries += snap.get("total_retries", 0)
            seconds += snap.get("total_retry_seconds", 0.0)
            exhausted += len(snap.get("exhausted_hosts") or ())
            for host, spent in (snap.get("retry_seconds_by_host") or {}).items():
                hosts[host] = round(hosts.get(host, 0.0) + spent, 3)
        try:
            cache = self.filing_cache.snapshot()
        except Exception:                                   # noqa: BLE001
            cache = {}
        return {
            "runs_with_a_ledger": len(self._retry_ledgers),
            "total_retries": retries,
            "total_retry_seconds": round(seconds, 3),
            "hosts_whose_budget_ran_out": exhausted,
            "retry_seconds_by_host": hosts,
            "filing_cache": cache,
        }

    def classification_inputs(self, run_id: str, name: str = "",
                              documents=None, allow_network: bool = True
                              ) -> dict:
        """What this run knows about WHAT KIND OF BUSINESS its subject is.

        THE ONE OWNER. This existed already, on the webapp, and the ingestion
        path had its own answer — which is how one run held two different
        classifications of the same company. The executive layer got the fix
        and the layer that gates the PATTERN LIBRARY did not, so Meta was
        classified for the analysis and unclassified for the hypotheses, and
        an advertising platform was offered a semiconductor capacity thesis.

        Two facts, both already in hand:

          * the regulator's industry code for THIS filer, resolved from the
            run's own CIK rather than by re-resolving the typed name;
          * the subject's own filing text, which is what separates the two
            different businesses SIC 7370 contains.

        A manifest company is classified by hand already, so neither is
        fetched for one. Cached per run; at most one SEC call.
        """
        if run_id in self._classification_cache:
            return self._classification_cache[run_id]
        out = {"registrant": {}, "evidence_text": ""}
        meta = self.run_meta(run_id) or {}
        try:
            from intent_engine.executive.company_profile import profile_for
            if profile_for(name=name or str(meta.get("company_name") or ""),
                           domain=str(meta.get("domain") or "")).known:
                self._classification_cache[run_id] = out
                return out
        except Exception:                                   # noqa: BLE001
            pass
        if allow_network:
            out["registrant"] = self._registrant_for(run_id, meta)
        if documents is None:
            try:
                documents = list(self.store.retrieved(run_id))
            except Exception:                               # noqa: BLE001
                documents = []
        # The SUBJECT'S OWN filing text, and the subject is identified the
        # same way as above -- reading `meta["cik"]` here selected the text of
        # no filer at all on every domain-entry run.
        try:
            _subject = str(self.subject_cik(meta) or "")
        except Exception:                                   # noqa: BLE001
            _subject = str(meta.get("cik") or "")
        out["evidence_text"] = _subject_evidence_text(documents, _subject)
        self._classification_cache[run_id] = out
        return out

    def _registrant_for(self, run_id: str, meta: dict) -> dict:
        """The SEC's classification of this filer, memoised per run.

        Fetched rather than assumed because it is the only thing that
        classifies a company outside the curated 100-company manifest, and
        an unclassified company takes every hypothesis in the library. Fully
        defensive: any failure yields {}, which is exactly today's behaviour.
        """
        if run_id in self._registrant_cache:
            return self._registrant_cache[run_id]
        out: dict = {}
        # `subject_cik`, NOT `meta["cik"]` -- THE SAME MISTAKE, A THIRD TIME.
        #
        # `meta["cik"]` is only populated when the customer TYPED a filer with
        # no website. Every run started from a domain -- the ordinary case,
        # and all ten of the unseen-company matrix -- carries "" here, so this
        # branch never ran, no registrant was ever fetched, and
        # `profile_for(registrant={})` answered UNKNOWN.
        #
        # UNKNOWN takes the WHOLE pattern library, which is what produced
        # thesis collapse: measured live on 56921bce, Synopsys (EDA
        # software), Emerson Electric (industrial) and Lowe's (retail) each
        # received the byte-identical headline decision "Whether a supply
        # commitment should be treated as fixed or renegotiable" -- the
        # `capacity_ahead_of_demand` scaffold, whose own
        # `excluded_model_classes` names SUBSCRIPTION_SOFTWARE and
        # SCALE_RETAIL and could never fire because nothing but UNKNOWN
        # reached the gate.
        #
        # `sufficiency.py` carries a comment describing this exact defect
        # being repaired in ITS guard: "a run started from a website carries
        # no CIK -- which is the ORDINARY case". The repair did not reach
        # here. Measured after the change: Synopsys resolves
        # SUBSCRIPTION_SOFTWARE, Emerson DESIGN_AND_MANUFACTURE, Lowe's
        # SCALE_RETAIL, BlackRock BALANCE_SHEET_OR_NETWORK -- three of which
        # exclude the capacity scaffold outright.
        try:
            cik = str(self.subject_cik(meta) or "").strip()
        except Exception:                                   # noqa: BLE001
            cik = str((meta or {}).get("cik") or "").strip()
        if cik:
            try:
                from intent_engine.company_ingestion.edgar import (
                    registrant_classification,
                )
                digits = int(cik.lstrip("0") or "0")
                out = registrant_classification(
                    {"cik": digits, "cik10": f"{digits:010d}"},
                    transport=self.transport, resolver=self.resolver) or {}
            except Exception:                               # noqa: BLE001
                out = {}
        self._registrant_cache[run_id] = out
        return out

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
                   user_id: str, as_of: str, cik: str = "",
                   actor_type: str = "human") -> dict:
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

        `actor_type` defaults to "human" because every caller until now was a
        founder clicking a button, and that flow is unchanged. The autonomous
        daily research cycle passes "system": it is not a person, and a run
        recorded as human-initiated would put a false actor in an append-only
        audit trail that exists precisely to answer "who asked for this?".
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
                     actor_type=actor_type, actor_id=user_id,
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
    @staticmethod
    def _snapshot_is_for(snap, meta) -> bool:
        """Is this snapshot about the company this run is about?

        CHECKED POSITIVELY, not assumed from the key. A key collision or a
        reused domain would otherwise put one company's source list under
        another's evidence -- the failure mode that makes a cache worse than
        no cache. CIK decides when both sides have one; otherwise the domain
        must match, and a snapshot with neither is refused.
        """
        cik = str(meta.get("cik") or "").lstrip("0")
        if cik and str(snap.cik or "").lstrip("0"):
            return cik == str(snap.cik).lstrip("0")
        dom = str(meta.get("domain") or "").lower()
        return bool(dom) and dom in {str(d).lower() for d in snap.domains}

    def _candidates_from_snapshot(self, run_id, snap, domain) -> list:
        """Re-propose the sources this company is already known to publish.

        The candidates are written through the SAME append-only path a cold
        discovery uses, so everything downstream -- selection, approval,
        retrieval, provenance -- cannot tell the difference and does not need
        to. What changes is only that nothing was searched for.
        """
        candidates = []
        for rank, src in enumerate(snap.sources):
            if not src.url:
                continue
            candidates.append({
                "url": src.url,
                "title": "",
                "why_relevant": "known source for this company (snapshot)",
                "discovery_method": "snapshot_reuse",
                "source_type": src.source_class or "company_owned",
                "source_class": src.source_class or "",
                "availability": "PROPOSED",
            })
        if not candidates:
            return []
        for i, candidate in enumerate(candidates):
            candidate_id = ("cand-" + hashlib.sha256(
                candidate["url"].encode()).hexdigest()[:12])
            payload = dict(candidate, candidate_id=candidate_id,
                           company_id=domain, rank=i)
            self._append("ci.candidate_discovered", run_id=run_id,
                         domain=domain, payload=payload,
                         idempotency_key=f"ci-cand:{run_id}:{candidate_id}")
        return self.store.candidates(run_id)

    def _write_snapshot(self, run_id, meta, candidates) -> bool:
        """Record what this cold run learned about where the sources are.

        STORES THE INDEX, NOT THE EVIDENCE. What goes in is the URL, its class
        and -- where the run established one -- its filing identity. What the
        document MEANT is recomputed every run from current evidence and the
        current economic state, which is why nothing here is a conclusion.
        """
        try:
            key = _company_key(meta.get("company_name", ""),
                               cik=str(meta.get("cik") or ""),
                               domain=meta.get("domain", ""))
            now = time.time()
            sources = tuple(
                SourceRecord(
                    url=c.get("url", ""),
                    source_class=str(c.get("source_class")
                                     or c.get("source_type") or ""),
                    accession=str((c.get("filing") or {}).get("accession")
                                  if isinstance(c.get("filing"), dict) else ""),
                    form=str((c.get("filing") or {}).get("form")
                             if isinstance(c.get("filing"), dict) else ""),
                    fetched_at=now)
                for c in candidates if c.get("url"))
            existing = self.snapshots.get(key)
            snap = PublicCompanySnapshot(
                company_key=key,
                canonical_name=str(meta.get("company_name") or ""),
                ticker=str(meta.get("ticker") or ""),
                cik=str(meta.get("cik") or ""),
                domains=tuple(d for d in [str(meta.get("domain") or "")] if d),
                sources=sources,
                provenance={"run_id": run_id, "discovery": "cold"},
                created_at=(existing.created_at if existing else now),
                refreshed_at=now)
            return self.snapshots.put(snap)
        except Exception:                                 # noqa: BLE001
            return False

    def discover(self, run_id: str, *, deadline=None, trace=None) -> list:
        """One bounded homepage fetch → candidate list. Idempotent: stored
        candidates are returned on rerun without refetching.

        `deadline` bounds the OPTIONAL discovery branches. Retrieval was
        bounded first and discovery was not, which left half the acquisition
        path outside the budget: this function makes SEC full-text-search and
        sitemap requests of its own, and a slow regulator could spend the
        whole interactive window before a single approved source was fetched.
        The company's own homepage and its EDGAR filings are not optional and
        are never skipped -- without them there is no analysis to bound.
        """
        stored = self.store.candidates(run_id)
        if stored:
            return stored
        meta = self.run_meta(run_id)
        if meta is None:
            raise IngestionError(f"no such run {run_id!r}")
        domain = meta["domain"]
        self._transition(run_id, domain, "DISCOVERING_SOURCES")

        # WHAT CHANGED, RATHER THAN WHAT IS TRUE.
        #
        # Everything below re-derives a company's source list from nothing:
        # fetch the homepage, walk the sitemap, search EDGAR full text, search
        # for third-party filings, apply the curated fallback. Measured on the
        # preview, that is 27.7s for Microsoft and 25-32s for Apple, spent
        # before one byte of evidence is retrieved -- and on a company already
        # read, none of it is new information.
        #
        # A fresh snapshot answers the question this stage exists to ask, so
        # the stage is skipped. It is skipped ENTIRELY or not at all: a
        # half-warm discovery that still fetched the homepage "to be safe"
        # would keep the cost and lose the clarity about what was reused.
        #
        # `plan_refresh` decides; this only carries the decision out. COLD and
        # STALE both fall through to the full path below -- STALE has a source
        # list but it is old enough that the LIST itself may be wrong, and a
        # stale list cannot be repaired by revalidating the entries on it.
        snap_plan = {"mode": "COLD", "reason": "snapshots not consulted"}
        try:
            key = _company_key(meta.get("company_name", ""),
                               cik=str(meta.get("cik") or ""), domain=domain)
            snap = self.snapshots.get(key)
            if snap is not None and not self._snapshot_is_for(snap, meta):
                # A snapshot for a DIFFERENT company is not a stale snapshot,
                # it is a wrong one, and consuming it would put another
                # company's sources under this run's evidence.
                snap = None
                snap_plan = {"mode": "INVALID",
                             "reason": "snapshot identity does not match"}
            if snap is not None:
                snap_plan = plan_refresh(snap)
            if snap_plan["mode"] == "WARM":
                # IDENTITY IS A PRECONDITION, NOT DISCOVERY, and skipping it
                # is what made the first warm run fast by losing the analysis.
                #
                # `readiness.may_synthesize` is `identity_ok and material in
                # (...)`, and `_identity_for` runs near the END of the cold
                # path -- so returning early skipped it, `identity_ok` was
                # false, synthesis was refused, and the run produced no
                # strategic report at all. Measured: Microsoft warm came back
                # in 34.4s against 66.1s with `result_state: None` and no
                # observations. A latency win that deletes the product.
                #
                # What this stage is allowed to skip is finding out WHERE the
                # sources are. Establishing WHO the company is is a different
                # question, it is cheap, and a report about nobody in
                # particular has nothing to be right or wrong about.
                self._identity_for(run_id, meta)
                reused = self._candidates_from_snapshot(run_id, snap, domain)
                if reused:
                    self._append(
                        "ci.snapshot_reused", run_id=run_id, domain=domain,
                        payload={"mode": "WARM",
                                 "snapshot_age_s": round(snap.age_s(), 1),
                                 "sources_reused": len(reused),
                                 "immutable": len(snap_plan.get("immutable")
                                                  or ()),
                                 "revalidate": len(snap_plan.get("revalidate")
                                                   or ()),
                                 "durability": snap.durability},
                        idempotency_key=f"ci-snapreuse:{run_id}")
                    return reused
                snap_plan = {"mode": "COLD",
                             "reason": "snapshot held no usable source"}
        except Exception as exc:                          # noqa: BLE001
            # A snapshot that cannot be read costs the head start, never the
            # run. Falling through here is a full cold discovery, which is
            # exactly today's behaviour.
            #
            # LOGGED, BECAUSE A SILENT FALLBACK LOOKS LIKE SUCCESS. This
            # branch already swallowed a real coding defect once: the new
            # event type was not in `INGESTION_EVENTS`, `_append` raised, and
            # every "warm" run quietly performed a full cold discovery while
            # reporting nothing wrong. A test that asserted the MODE would
            # have passed; what caught it was asserting that the expensive
            # calls did not happen.
            _LOG.warning("snapshot reuse failed for %s, falling back to cold "
                         "discovery: %s: %s", run_id, type(exc).__name__,
                         str(exc)[:200])
            snap_plan = {"mode": "COLD", "reason": f"{type(exc).__name__}"}

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
        # THE INDEPENDENT BRANCHES START TOGETHER.
        #
        # MEASURED on a cold Apple run: discovery cost 8.55s, and 5.3s of it
        # was `_third_party_filing_candidates` — EDGAR full-text search, which
        # needs the company's NAME and nothing this function has yet to
        # compute. It was waiting behind a homepage fetch and a sitemap walk
        # it has no dependency on whatsoever.
        #
        # Two things genuinely depend on the homepage: `discover_candidates`
        # (it reads the links) and the EDGAR *limit* (a run whose own site
        # refused us is allowed more filings). Those stay sequential below.
        # The list is then assembled in the ORIGINAL order, so the rank a
        # candidate is stored with — and therefore which sources the
        # recommendation picks — is byte-for-byte what it was.
        from concurrent.futures import ThreadPoolExecutor
        _pool = ThreadPoolExecutor(max_workers=2,
                                   thread_name_prefix="discover")
        try:
            # §18. Both are HIGH_VALUE_OPTIONAL: they widen the evidence and
            # neither is required for a defensible reading. A budget already
            # spent skips them and SAYS so, rather than making the customer
            # wait for enrichment they will not be shown.
            from intent_engine.company_ingestion.deadline import (
                HIGH_VALUE_OPTIONAL,
            )
            optional_ok = (deadline is None
                           or deadline.may_start(HIGH_VALUE_OPTIONAL))
            if not optional_ok and deadline is not None:
                deadline.record_gap(
                    "discovery", "third-party filings and sitemap not "
                                 "searched — interactive budget spent")
            third_party = (_pool.submit(self._third_party_filing_candidates,
                                        meta, run_id=run_id)
                           if optional_ok else None)
            sitemap = (_pool.submit(self._sitemap_candidates, meta["website"])
                       if meta.get("website") and optional_ok else None)
            if meta.get("website"):
                result = safe_fetch(meta["website"], transport=self.transport,
                                    resolver=self.resolver)
                links = []
                if result["ok"]:
                    links = parse_html(result["body"])["links"]
                candidates = discover_candidates(company_url=meta["website"],
                                                 homepage_links=links)
                # Sitemap/robots discovery: the publisher's OWN list of real,
                # canonical URLs. Guessed known-paths mostly 403/404; sitemap
                # URLs exist by construction, and this works even when the
                # homepage is JavaScript-rendered and exposes no links.
                # robots.txt Disallow is honoured. Dispatched before the
                # homepage fetch above; only the join happens here.
                if sitemap is not None:
                    _sm = _bounded_result(
                        sitemap, deadline, "discovery",
                        "sitemap crawl did not return within its share of "
                        "the interactive budget",
                        cap_s=self._OPTIONAL_DISCOVERY_CAP_S)
                    candidates = candidates + (_sm or [])
                # Bounded external-source proposals (customer voice etc.)
                # broaden the evidence beyond company-owned pages. Off-domain,
                # UNVERIFIED, and (like every candidate) fetched only after
                # explicit approval.
                candidates = candidates + propose_external_candidates(
                    company_name=meta.get("company_name", ""), domain=domain)
            # WHAT THE COMPANY'S OWN WEB PRESENCE ACTUALLY GAVE US, decided here
            # rather than inferred later. Three states, and they are not the same
            # finding: a site we never had, a site that refused us, and a site we
            # read. Only the third is evidence about the company.
            if not meta.get("website"):
                web_plan = OFFICIAL_WEB_ABSENT
            elif not result["ok"] or not candidates:
                web_plan = OFFICIAL_WEB_BLOCKED
            else:
                web_plan = OFFICIAL_WEB_RETRIEVED
            # Authoritative structured fallback: for public companies, official SEC
            # EDGAR filings are permitted, server-rendered (non-JavaScript) HTML —
            # so a run is not at the mercy of a JavaScript-only marketing site.
            # Fully defensive: yields nothing (never raises) if the company is not
            # a filer or SEC is unreachable, so discovery is never broken by it.
            #
            # THE BUDGET MOVES TO WHERE IT IS SERVED. A run whose own site gave us
            # nothing does not make more requests overall — it makes them at
            # EDGAR, which answers, instead of at a host that does not.
            # TIMED SEPARATELY. Discovery is 23.2s of a 107s cohort median
            # and is reported as one number, so which of its five stages costs
            # what is currently unknown -- and the largest is the one to
            # repair. This call reaches SEC.
            # NOT DISPATCHED IN PARALLEL, AND HERE IS WHY IT LOOKS LIKE IT
            # SHOULD BE.
            #
            # MEASURED on NVIDIA at 6aefd58e: this call did not START until
            # t+11.2s, queued behind a homepage fetch whose links it never
            # reads -- it needs the name and CIK, both already in `meta`. Six
            # seconds of a sixty-five-second run, apparently free to reclaim.
            #
            # The attempt was made and reverted. Its LIMIT depends on the
            # homepage -- 5 filings if our own site refused us, 3 if it
            # answered -- so dispatching early means requesting the larger set
            # and truncating. That is output-identical in the CANDIDATE LIST
            # and is NOT identical in REQUEST COUNT: every run with a working
            # homepage would make two extra requests to SEC, the one host this
            # file is most careful about.
            #
            # `test_the_blocked_budget_is_strictly_larger_and_is_the_one_used`
            # pins the property that broke: a run whose own site gave us
            # nothing does not make MORE requests overall, it makes them
            # somewhere that answers. Six seconds is not worth spending that.
            #
            # A version that reclaimed the time without the extra requests
            # would need the proposal to accept an OFFSET, so a blocked run
            # could top up from 3 to 5 rather than re-ask for 5.
            _edg_w, _edg_c = time.monotonic(), time.thread_time()
            candidates = candidates + propose_edgar_candidates(
                company_name=meta.get("company_name", ""),
                cik=str(meta.get("cik") or ""),
                limit=(MAX_EDGAR_CANDIDATES_WEB_BLOCKED
                       if web_plan in (OFFICIAL_WEB_ABSENT, OFFICIAL_WEB_BLOCKED)
                       else MAX_EDGAR_CANDIDATES),
                transport=self.transport, resolver=self.resolver)
            if trace is not None:
                trace.mark("edgar_propose", _edg_w, _edg_c)
            # THE ONLY INDEPENDENT VANTAGE POINT WE CAN ACTUALLY REACH.
            #
            # Ten companies produced ZERO independent sources: every one was the
            # company describing itself. The families that would fix that were
            # probed and are not accessible without bypassing controls we will not
            # bypass -- review sites answer 403, newswire feeds 401/404. What IS
            # public is EDGAR full-text search, where a COMPETITOR'S OWN 10-K names
            # this company. Different author, regulatory venue, exact date,
            # permanent citation.
            if third_party is not None:
                _tp = _bounded_result(
                    third_party, deadline, "discovery",
                    "third-party filing search did not return within its "
                    "share of the interactive budget",
                    cap_s=self._OPTIONAL_DISCOVERY_CAP_S)
                candidates = candidates + (_tp or [])
        finally:
            # NOT `wait=True`. Bounding the joins above and then
            # blocking here on the same futures would give the
            # unbounded wait straight back -- the timeout would be
            # recorded as a gap and the request would still sit
            # here until the worker finished. A cancelled future
            # whose thread is still winding down costs nothing the
            # reader can see.
            _pool.shutdown(wait=False)
        # Curated official sources for a KNOWN entity. This is what stops a
        # multinational whose primary domain refuses automated access from
        # collapsing into whatever single filing happened to be reachable:
        # investor relations, earnings, annual/integrated reports, newsroom and
        # segment pages live at stable URLs that are not derivable from a
        # homepage we could not read. Bounded, approval-gated, and classified by
        # authority + entity relationship, so a subsidiary page can never be
        # read as the parent speaking.
        _idw, _idc = time.monotonic(), time.thread_time()
        identity = self._identity_for(run_id, meta)
        if trace is not None:
            trace.mark("identity_resolve", _idw, _idc)
        _offw, _offc = time.monotonic(), time.thread_time()
        if identity.get("entity_resolved"):
            candidates = candidates + official_fallback_candidates(
                identity["_profile"], exclude_urls=[c["url"]
                                                    for c in candidates])
        if trace is not None:
            trace.mark("official_fallback", _offw, _offc)
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
        # THE RETRIEVAL PLAN'S OWN RESULT, recorded once, so every consumer
        # reads the same answer to "what was actually available?" rather than
        # re-deriving it from failure counts.
        self._retrieval_plans[run_id] = {
            "official_web": web_plan,
            "sec": (SEC_RETRIEVED if any(
                c.get("source_class") == "investor_material"
                for c in candidates) else SEC_NONE),
            "independent": (INDEPENDENT_RETRIEVED if any(
                c.get("source_class") in ("independent_reporting",
                                          "customer_voice", "competitor")
                for c in candidates) else INDEPENDENT_NONE),
        }
        self._transition(run_id, domain, "AWAITING_SOURCE_APPROVAL")
        # REMEMBER WHERE THE SOURCES WERE, so the next run does not search for
        # them again. Written after the full path has run, from the candidates
        # it actually produced -- a snapshot built from an aborted or empty
        # discovery would teach the next run that this company has no sources.
        stored_candidates = self.store.candidates(run_id)
        if stored_candidates:
            self._write_snapshot(run_id, meta, stored_candidates)
        return stored_candidates

    def retrieval_plan(self, run_id: str) -> dict:
        """What each retrieval avenue yielded for this run.

        Empty when discovery has not run. An empty dict is NOT a measured
        "nothing was available" — it means nobody has looked yet.
        """
        return dict(self._retrieval_plans.get(run_id) or {})

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
                rejected_ids: list, actor_type: str = "human") -> dict:
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
                     domain=meta["domain"], actor_type=actor_type,
                     actor_id=user_id, subject_type="approval",
                     subject_id=payload["approval_id"], payload=payload,
                     idempotency_key=f"appr:{run_id}")
        return payload

    # --- retrieval -------------------------------------------------------------------
    def fetch_approved(self, run_id: str, *, candidate_ids=None,
                       deadline=None, sufficiency_probe=None) -> dict:
        """Fetch ONLY approved candidates; idempotent per source+content;
        partial success is honest.

        ``candidate_ids`` restricts/extends the fetch to an explicit set — used
        by the quality retry loop to retrieve ADDITIONAL evidence for families
        the first pass missed. Every id must still be a discovered candidate of
        this run, and the original approval remains immutable.

        ``sufficiency_probe`` is called with the documents retrieved so far,
        after each wave, and returns `sufficiency.evaluate`'s verdict. When it
        reports `sufficient`, acquisition stops BLOCKING and the untouched
        targets come back under ``deferred`` — to be acquired after the reader
        has an answer, not instead of. Omitted (every batch caller, every
        existing test), acquisition runs to the end of the list exactly as it
        always did.
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
        # THE NETWORK, OVERLAPPED. Every decision below is still made one
        # candidate at a time, in this order. See `_prefetch`.
        # ACQUISITION IN WAVES, SO SUFFICIENCY CAN ACTUALLY STOP IT.
        #
        # `_prefetch` dispatched EVERY approved target before the decision
        # loop ran, so by the time the first document was judged, the network
        # cost of all fourteen had already been paid. A stopping condition
        # evaluated after that loop can only decide what to THINK about work
        # already done -- it cannot make the reader wait less, which is the
        # whole point of having one.
        #
        # So dispatch is chunked into waves of `_FETCH_CONCURRENCY`, which is
        # exactly the width the pool had anyway. The decision loop still walks
        # `targets` IN ORDER and decides one candidate at a time, so the
        # ledger, the byte budget and the failure sequence are what they were;
        # the only thing that moved is when the next wave is dialled.
        #
        # WITHOUT A PROBE, THERE IS ONE WAVE and this is byte-for-byte the
        # previous behaviour -- which is what every batch caller and every
        # existing test gets.
        ok, failed, deferred = [], [], []
        stopped_by = None
        if sufficiency_probe is None:
            waves = [list(targets)]
        else:
            width = max(1, int(self._FETCH_CONCURRENCY))
            waves = [list(targets[i:i + width])
                     for i in range(0, len(targets), width)] or [[]]
        for wave in waves:
            if stopped_by is not None:
                # NOT A FAILURE AND NOT A DROP. These are handed back so the
                # caller can acquire them AFTER the reader has an answer; a
                # deferred source that never arrives is recorded as a gap.
                deferred.extend(wave)
                continue
            prefetched = self._prefetch(wave, candidates, run_id=run_id,
                                        already=already,
                                        host_failures=host_failures,
                                        deadline=deadline)
            for candidate_id in wave:
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
                # A previously retrieved SEC filing is served from disk. The
                # cached entry is the RESPONSE, not a reading of it: parsing,
                # relevance, relationship and competitor classification all run
                # below on every path, so analysing one filing for two companies
                # still produces two different readings.
                _cache_outcome, cached = self.filing_cache.get(candidate["url"])
                # WHAT WE ALREADY LEARNED ABOUT THIS ADDRESS.
                #
                # A 404 is not a fact about today. Measured on a clean
                # Johnson & Johnson run, NINE of fourteen approved slots went
                # to guessed paths -- /api, /docs, /developers, /plans -- on a
                # pharmaceutical company, every one a 404, and the next run
                # bought the same nine answers again. The slot is the scarce
                # resource, so remembering the answer IS the repair.
                #
                # The cached branch wins: a filing already on disk costs no
                # request at all, so a stale verdict may never suppress it.
                # The skip is RECORDED as a failure with the date and status
                # that justified it, so the reader is told about the gap
                # rather than quietly shown less.
                memory = self.acquisition_memory.verdict(candidate["url"])
                if cached is None and memory["verdict"] != _ACQ_ALLOW:
                    failed.append(self._fail(
                        run_id, domain, candidate_id,
                        memory.get("failure_type") or "http_status",
                        memory["reason"], False))
                    continue
                if cached is not None:
                    result = FetchResult(
                        ok=True, status_code=cached["status_code"],
                        mime_type=cached["mime_type"],
                        body=(cached["body"] if wants_pdf
                              else cached["body"].decode("utf-8", "replace")),
                        final_url=candidate["url"], redirects=[],
                        failure_type=None, safe_message="", retryable=False,
                        truncated=cached["truncated"])
                elif candidate_id in prefetched:
                    # Already acquired concurrently above. The DECISION about it
                    # is still made here, in this order, so the ledger, the byte
                    # budget and the failure sequence are what they always were.
                    result = prefetched.pop(candidate_id)
                elif deadline is not None and not deadline.may_start():
                    # THE BUDGET HAS TO BIND HERE TOO. `_prefetch` declines to
                    # DISPATCH past the deadline, but a candidate it skipped
                    # arrives here and this branch used to dial it anyway -- so an
                    # expired budget still spent the full serial time, which is
                    # the entire failure it exists to prevent. Caught by
                    # `test_deadline_bounds_acquisition_and_records_the_gap`,
                    # which measured 2.44s against a budget of 0.05s.
                    deadline.record_gap(
                        "evidence", f"{candidate.get('url', '')[:120]} not "
                                    f"requested — interactive budget spent")
                    failed.append(self._fail(
                        run_id, domain, candidate_id, "deadline_exceeded",
                        "not requested: the interactive time budget for this "
                        "analysis was spent before this source was reached",
                        True))
                    continue
                else:
                    started = time.monotonic()
                    result = self._acquire(
                        candidate, run_id=run_id, wants_pdf=wants_pdf,
                        timeout=(None if deadline is None
                                 else deadline.budget_for(CONNECT_TIMEOUT_S)))
                    if deadline is not None:
                        deadline.spend(time.monotonic() - started)
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
                # THE SAME REFUSAL, RAISED FROM THE OTHER END.
                #
                # The guard above catches `SecretRejected` from
                # `_build_record`, and the comment there is explicit that a
                # false positive "must cost this one source, never the run".
                # But the credential rule is enforced a SECOND time, by
                # `records.validate()` inside `store.append`, and it raises
                # `IngestionError` -- which that guard does not catch. So the
                # protected path was only half protected.
                #
                # MEASURED 2026-09-03: an NVIDIA run died outright with
                # "raw credentials / auth headers must never be persisted",
                # raised from `_append`, after a third-party filing reached
                # the store. The detector is deliberately blunt -- any 13-16
                # digit run reads as a card number, and SEC filings
                # concatenate commission file numbers into exactly that shape
                # -- so this is the false positive the first guard was written
                # for, arriving through the door it does not cover.
                #
                # One source is dropped and recorded honestly; the run
                # continues with the rest of its evidence.
                try:
                    self._append("ci.source_retrieved", run_id=run_id,
                                 domain=domain, subject_type="source",
                                 subject_id=source_id, payload=record,
                                 idempotency_key=f"src:{run_id}:{source_id}:"
                                                 f"{record['content_hash'][:12]}")
                except IngestionError as exc:
                    total_bytes -= record["byte_count"]
                    failed.append(self._fail(
                        run_id, domain, candidate_id, "content_rejected",
                        str(exc), False))
                    continue
                ok.append(record)

            if sufficiency_probe is not None:
                verdict = sufficiency_probe(ok)
                if verdict and verdict.get("sufficient"):
                    stopped_by = dict(verdict)
        return {"ok": ok, "failed": failed, "deferred": deferred,
                "sufficiency": stopped_by,
                "status": "COMPLETE" if not failed
                else ("PARTIAL" if ok else "FAILED")}

    #: §48/§49. Bounded, and bounded twice. The global cap is what a free
    #: instance can hold sockets and memory for; the per-host cap is what
    #: keeps a concurrent pass from looking like a burst to one publisher.
    #: SEC in particular answers 429 to bursts, and a 429 costs the run more
    #: than the serialism it replaced.
    #: How long an OPTIONAL discovery branch may hold the run.
    #:
    #: MEASURED on NVIDIA at 6aefd58e: discovery 35.0s at 2% CPU. The homepage
    #: fetch ran to 11.2s, the EDGAR proposal to 17.2s, and the remaining ~18s
    #: was the join on the third-party filing search -- EDGAR full-text, which
    #: is the only independent vantage most runs get and is also the slowest
    #: thing in the stage.
    #:
    #: It was already bounded by `deadline.remaining`, which on a 60s budget
    #: is 40s and therefore never bit. `CLASS_SHARE` exists to say what a
    #: class may spend CUMULATIVELY; this says what one branch may spend
    #: WAITING, which is a different question and the one that was unanswered.
    #:
    #: 8s is chosen from the measurement rather than rounded to taste: the
    #: same search cost 5.3s on a cold Apple run, so this keeps the branch
    #: that usually succeeds and drops the tail that does not.
    _OPTIONAL_DISCOVERY_CAP_S = 8.0

    _FETCH_CONCURRENCY = 6
    #: NOT RAISED, AND THE ATTEMPT IS RECORDED HERE SO IT IS NOT REPEATED.
    #:
    #: Retrieval costs 24.6s for ~10 documents, most of them from one host, so
    #: a cap of 2 serialises them into about five rounds where there could be
    #: three. That is a real, measured cost and raising this looked correct.
    #:
    #: It was reverted because the justification did not survive checking.
    #: `docs/INTERACTIVE_PERFORMANCE.md` records the premise as measured --
    #: "SEC answers 429 to bursts, and a 429 costs more than the serialism it
    #: replaced" -- and the counter-claim (that the 429s were company-
    #: correlated rather than cadence-correlated) could not be cited from this
    #: repository at all. A documented measurement outranks a recollection.
    #:
    #: `test_concurrency_is_bounded_per_host` asserts a LITERAL 3 rather than
    #: `_FETCH_PER_HOST + 1`, precisely so raising this constant cannot raise
    #: its own bound. That guard caught this change, which is what it is for.
    #:
    #: To revisit properly: instrument 429s per host against concurrency on
    #: the live service, record the result in the docs, and change the guard
    #: and the constant together with that evidence attached.
    _FETCH_PER_HOST = 2

    def _acquire(self, candidate, *, run_id, wants_pdf, timeout=None):
        """One URL, over the network or out of the filing cache.

        Extracted so the sequential decision loop and the concurrent prefetch
        share ONE acquisition path. Two copies of this would be two retry
        policies, two cache-write rules and two byte budgets that drift.
        """
        from intent_engine.company_ingestion.pdf import PDF_MIME_PREFIXES
        kwargs = dict(
            transport=self.transport, resolver=self.resolver,
            extra_mime_prefixes=(PDF_MIME_PREFIXES if wants_pdf else ()),
            binary=wants_pdf,
            retry_ledger=self.retry_ledger_for(run_id),
            # Filings only, flagged by the EDGAR adapter. `max_bytes` raises
            # the budget for a statutory document, because most large-cap
            # filings exceed the general 2MB cap and were being discarded
            # whole — measured live on Caterpillar, whose 10-Q came back "too
            # large" and left the run bounded. `accept_truncated` is the
            # fallback for anything past even that budget; nothing downstream
            # may call such a read complete.
            accept_truncated=bool(candidate.get("accept_truncated")),
            max_bytes=int(candidate.get("max_bytes") or MAX_RESPONSE_BYTES))
        if timeout is not None:
            kwargs["timeout"] = timeout
        # POLITENESS BEFORE THE REQUEST, not after being told off for it.
        # Zero for almost every host; it exists so a cohort's SEC reads
        # arrive spaced instead of as a burst, which is what a rate limiter
        # actually reacts to.
        wait = self.acquisition_memory.delay_before(candidate["url"])
        if wait > 0:
            time.sleep(min(wait, 2.0))
        result = safe_fetch(candidate["url"], **kwargs)
        # REMEMBERED ACROSS RUNS, so the next analysis of this company spends
        # the slot on something that can succeed. Only outcomes that are a
        # property of the TARGET are kept -- see `classify_outcome`.
        self.acquisition_memory.record(
            candidate["url"], ok=bool(result["ok"]),
            status=result.get("status_code"),
            failure_type=result.get("failure_type") or "")
        if result["ok"]:
            self.filing_cache.put(
                candidate["url"],
                body=(result["body"] if isinstance(result["body"], bytes)
                      else str(result["body"]).encode("utf-8")),
                mime_type=result.get("mime_type", ""),
                status_code=result.get("status_code", 200),
                truncated=bool(result.get("truncated")))
        return result

    def _prefetch(self, targets, candidates, *, run_id, already,
                  host_failures, deadline=None) -> dict:
        """Acquire the approved URLs CONCURRENTLY. Returns candidate_id -> result.

        WHY THIS IS SEPARATE FROM THE DECISION LOOP
        -------------------------------------------
        The loop below is not a loop over independent work: it accumulates a
        byte budget, trips a dead-host breaker mid-pass, and appends to an
        append-only ledger in a defined order. Parallelising it in place would
        change all three, and the failure would be invisible — the same
        documents, admitted in a different order, with a breaker that trips
        against whichever host happened to answer first.

        So only the NETWORK moves. Fourteen approved URLs on a cold Apple run
        were fetched one after another; they are independent of each other,
        and nothing downstream depends on the order they arrive in — only on
        the order they are DECIDED in, which is unchanged.

        The breaker is still honoured here, at dispatch: a host that has
        already refused twice is not dialled again, exactly as before. What it
        cannot do concurrently is trip on a failure that has not happened yet,
        so a candidate the breaker would have skipped may be fetched. That
        costs a request; it cannot change a decision, because the loop below
        re-applies the breaker against the failures it has actually seen.
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from intent_engine.company_ingestion.pdf import is_pdf

        pending = []
        for candidate_id in targets:
            candidate = candidates[candidate_id]
            source_id = f"src-{candidate_id[5:]}"
            if source_id in already:
                continue                      # already retrieved in this run
            host = urlparse(candidate.get("url") or "").hostname
            if host and host_failures.get(host, 0) >= self._DEAD_HOST_AFTER:
                continue                      # the breaker has this host
            if self.filing_cache.get(candidate["url"])[1] is not None:
                continue                      # served from disk, not dialled
            if self.acquisition_memory.verdict(
                    candidate["url"])["verdict"] != _ACQ_ALLOW:
                continue                      # known dead; the loop records it
            pending.append((candidate_id, candidate, host or ""))
        if len(pending) < 2:
            return {}                         # nothing to overlap

        lock = threading.Lock()
        live_failures: dict = dict(host_failures)
        host_slots: dict = {}
        out: dict = {}

        def acquire(entry):
            candidate_id, candidate, host = entry
            with lock:
                if live_failures.get(host, 0) >= self._DEAD_HOST_AFTER:
                    return                    # died while we were queued
            if deadline is not None and not deadline.may_start():
                with lock:
                    deadline.record_gap(
                        "evidence", f"{candidate.get('url', '')[:120]} not "
                                    f"requested — interactive budget spent")
                return
            slot = host_slots.setdefault(host, threading.Semaphore(
                self._FETCH_PER_HOST))
            with slot:
                budget = (None if deadline is None
                          else deadline.budget_for(CONNECT_TIMEOUT_S))
                if budget == 0.0:
                    return
                started = time.monotonic()
                try:
                    result = self._acquire(
                        candidate, run_id=run_id,
                        wants_pdf=is_pdf(url=candidate["url"]),
                        timeout=budget)
                except Exception:                          # noqa: BLE001
                    return                    # the loop re-fetches it itself
                finally:
                    if deadline is not None:
                        deadline.spend(time.monotonic() - started)
            with lock:
                out[candidate_id] = result
                if not result["ok"] and host and \
                        result["failure_type"] in self._HOST_LEVEL_FAILURES:
                    live_failures[host] = live_failures.get(host, 0) + 1

        workers = min(self._FETCH_CONCURRENCY, len(pending))
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="fetch") as pool:
            list(pool.map(acquire, pending))
        return out

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
                extra_observations=(), previous_model=None, attempt: int = 1,
                deep: bool = True, trace=None, deadline=None):
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
        if trace is not None:
            with trace.span("fi_run") as _sp:
                result = fi_service.run(
                    company_name=meta["company_name"],
                    website=meta["website"], claims_by_section=claims,
                    as_of=meta["as_of"],
                    approved_inputs=tuple(d["source_id"] for d in documents))
                _sp["item_count"] = len(documents)
        else:
            result = fi_service.run(
                company_name=meta["company_name"], website=meta["website"],
                claims_by_section=claims, as_of=meta["as_of"],
                approved_inputs=tuple(d["source_id"] for d in documents))
        result["ingestion_run_id"] = run_id
        result["overview"] = executive_overview(
            claims, company_name=meta["company_name"],
            source_count=len(documents), failure_count=len(failures))
        if trace is not None:
            with trace.span("evidence_library"):
                result["evidence_library"] = self.evidence_library(run_id)
        else:
            result["evidence_library"] = self.evidence_library(run_id)
        # V1.2 strategic intelligence layer: derive structured observations
        # from the approved documents and run the deterministic strategic
        # reasoning engine over them. Additive — the legacy sections are
        # untouched. Company-owned-only evidence is honestly marked partial by
        # the strategic quality gate.
        result["readiness"] = readiness
        result["readiness_explanation"] = explain_readiness(readiness)
        # WHAT THE GATE WAS ACTUALLY LOOKING AT, recorded beside its verdict.
        #
        # Meta's bounded page states "7 page(s) read; 1 carried usable
        # evidence" and then lists the seven, including Meta's own 10-K and
        # 10-Q. The list is read live from the store; the number comes from
        # this assessment. Three mechanisms that would explain the gap were
        # tested against the seven real documents and all three are false:
        # `usable_documents` returns 7 of 7, `is_english` returns True for 7
        # of 7, and raw-HTML truncation swept from 16MB down to 200KB leaves
        # 7 of 7 (the real cap is 16MB, so nothing truncates at all).
        #
        # So a fourth guess is not worth making. This records the inputs, and
        # the next run says which number is wrong instead of being argued
        # about from the outside.
        # WHICH FILTER DROPPED THEM. MEASURED on b0050e3, NVIDIA:
        #
        #     compose=12  usable=4  families=customers|investor
        #
        # The gate saw every document the store held -- no seam, unlike Meta
        # -- and discarded eight of the twelve inside itself. `usable` alone
        # cannot say whether that was retrieval status, an empty body, the
        # 400-character dedup fingerprint or the language test, and those are
        # four different repairs. Counting them costs one pass over documents
        # already in memory.
        from intent_engine.company_ingestion.readiness import (
            readiness_inputs as _inputs,
        )
        result["readiness_inputs"] = _inputs(documents, readiness,
                                             attempt=attempt)
        if readiness["may_synthesize"]:
            if trace is not None:
                with trace.span("strategic_report"):
                    result["strategic_report"] = self._strategic_report(
                        meta["company_name"], documents, extra_observations,
                        previous_model=previous_model, run_id=run_id,
                        deep=deep, trace=trace, deadline=deadline)
            else:
                result["strategic_report"] = self._strategic_report(
                    meta["company_name"], documents, extra_observations,
                    previous_model=previous_model, run_id=run_id, deep=deep,
                    deadline=deadline)
            # A CORE PASS DID NOT ATTEMPT REASONING, SO IT IS NOT A
            # REASONING ATTEMPT.
            #
            # `ci.reasoning_assessed` is the operator's record of whether the
            # ANALYST accepted, and `reasoning_overview` divides acceptances
            # by attempts. Recording the core pass would enter
            # "attempted=True, accepted=False" for a pass that never called
            # the analyst -- halving the measured acceptance rate with runs
            # that never asked. The deep pass records it, once, when it has
            # actually happened.
            # `_strategic_report` returns None when no observation could be
            # derived at all, and that is still a reasoning outcome worth
            # recording -- `attempted` is computed from it.
            _core_only = (result["strategic_report"] or {}).get(
                "deep_status") == DEEP_PENDING
            if not _core_only:
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
                             max_passes=None, deadline=None, trace=None,
                             **compose_kwargs) -> dict:
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
                refusing_hosts=self.refusing_hosts(run_id),
                memory=self.acquisition_memory)
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
            # THE LAST UNBOUNDED ACQUISITION PATH. Retrieval and discovery
            # were both put inside the budget and this was not: the quality
            # gate can order up to MAX_RETRY_PASSES ADDITIONAL fetch passes
            # from inside composition, each one a fresh set of network calls
            # with nothing above it counting the seconds. A run could pass
            # every stage-level bound and still spend minutes here.
            if deadline is not None and not deadline.may_start():
                deadline.record_gap(
                    "evidence", f"targeted retry for {reason} not attempted "
                                f"— interactive budget spent")
                break
            attempted.update(extra)
            before = dict(gaps)
            if trace is not None:
                with trace.span("quality_retry_fetch", deadline=deadline,
                                retry_pass=attempt) as _sp:
                    self.fetch_approved(run_id, candidate_ids=extra,
                                        deadline=deadline)
                    _sp["item_count"] = len(extra)
            else:
                self.fetch_approved(run_id, candidate_ids=extra,
                                    deadline=deadline)
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
        if trace is not None:
            with trace.span("compose_proper", deadline=deadline):
                result = self.compose(run_id, fi_service=fi_service,
                                      attempt=spent, trace=trace,
                                      deadline=deadline, **compose_kwargs)
        else:
            result = self.compose(run_id, fi_service=fi_service, attempt=spent,
                                  deadline=deadline, **compose_kwargs)
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
            # THE KEY HAS TO NAME ITS CONTENT, NOT COUNT ITS INPUTS.
            #
            # This was `reasoning:{run_id}:{len(documents)}`, which was true
            # while a run reasoned exactly once. Progressive analysis reasons
            # TWICE over the same documents -- once for the core, once when
            # the strategic reading is merged -- so the document count is
            # identical and the payload is not. MEASURED: three tests died on
            # `idempotency_key 'reasoning:...:14' was already used for
            # different content`.
            #
            # Both passes are worth recording: "the core reasoned from the
            # pattern library" and "the analyst then accepted" are two facts
            # about one run, and collapsing them would lose the acceptance
            # rate the operator view exists to report. So the provenance --
            # which is exactly what differs -- goes in the key.
            idempotency_key=(f"reasoning:{run_id}:{len(documents)}:"
                             f"{report.get('reasoning_provenance') or 'none'}"))

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

    def enrich_deep(self, run_id: str, result: dict, *, previous_model=None,
                    deadline=None) -> dict:
        """Run the strategic reading and merge it into THIS result (§12).

        ONE analysis, upgraded -- never a second report. The core object the
        reader already opened is mutated in place, so there is no window in
        which two documents about one company disagree, and no way for a
        reader to be looking at an orphaned earlier version.

        A failure here costs the DEEP half and nothing else: the core stays
        exactly as it was, and `deep_status` says what happened. That is the
        §25 contract -- model failure may not destroy a result the customer
        is already reading.
        """
        report = (result or {}).get("strategic_report")
        if not isinstance(report, dict):
            return result                     # nothing composed; nothing to add
        if report.get("deep_status") not in (DEEP_PENDING, None):
            return result                     # already enriched, or refused
        meta = self.run_meta(run_id) or {}
        company_name = meta.get("company_name", "")
        documents = list(self.store.retrieved(run_id))
        before = {k: report.get(k) for k in DEEP_MATERIAL_FIELDS}
        import time as _time
        started = _time.monotonic()
        try:
            deep = self._strategic_report(
                company_name, documents, (), previous_model=previous_model,
                run_id=run_id, deep=True)
        except Exception as exc:              # noqa: BLE001 - core survives
            report["deep_status"] = DEEP_FAILED
            report["deep_failure"] = type(exc).__name__
            report["deep_seconds"] = round(_time.monotonic() - started, 2)
            return result
        # A DEEP FAILURE IS NOT AN ANALYSIS FAILURE, and it may not overwrite
        # the core's state with its own.
        #
        # MEASURED LIVE on 517180e6, Microsoft: a complete readable report,
        # `deep_status: COMPLETE`, and `result_state: FAILED` on the same run.
        # The cause is this branch. `analyse` returns
        # `(None, ResultState.FAILED, [])` when the provider call gives up --
        # it FAILS WITHOUT RAISING -- so the `except` above never fires, the
        # loop below merged that FAILED over the core's own state, and the
        # line after it announced the deep pass as COMPLETE. Two false
        # statements from one missing check.
        #
        # The core the reader is already holding is unchanged by a model call
        # that did not return: its evidence, coverage and provenance are the
        # same objects. So the core keeps its state, and the deep half is
        # recorded as what it was.
        deep_failed = deep.get("result_state") == "FAILED"
        merged = ("strategic_analysis", "result_state",
                  "result_state_detail", "reasoning_provenance",
                  "critic_findings", "strategic_memory", "daily_view",
                  "evidence_count", "withheld_explanation")
        for key in merged:
            if key in deep:
                # `result_state`/`result_state_detail` describe the WHOLE run.
                # Everything else here is owned by the reasoning layer and is
                # absent or empty on a failed pass, so it carries no lie.
                if deep_failed and key in ("result_state",
                                           "result_state_detail"):
                    continue
                report[key] = deep[key]
        if deep_failed:
            report["deep_status"] = DEEP_FAILED
            report["deep_failure"] = "ANALYST_RETURNED_FAILED"
        else:
            report["deep_status"] = DEEP_COMPLETE
        report["deep_seconds"] = round(_time.monotonic() - started, 2)
        # §13. What the deeper reading CHANGED about what the executive was
        # first shown, recorded rather than silently rewritten.
        after = {k: report.get(k) for k in DEEP_MATERIAL_FIELDS}
        report["deep_changes"] = [
            {"field": k, "core": before[k], "deep": after[k]}
            for k in DEEP_MATERIAL_FIELDS if before[k] != after[k]]
        return result

    def _strategic_report(self, company_name, documents, extra_observations,
                          previous_model=None, run_id="", deep: bool = True,
                          trace=None, deadline=None):
        from intent_engine.strategic_intelligence.observations import (
            derive_analyst_evidence, derive_observations,
        )
        from intent_engine.strategic_intelligence.reasoning import (
            build_strategic_report,
        )
        # ONLY THE SUBJECT'S OWN DOCUMENTS DESCRIBE THE SUBJECT. The run
        # retrieves other registrants' filings on purpose — they are the only
        # independent vantage we can reach — and a signal found in one of
        # them is a fact about THAT filer. JPMorgan rendered Wells Fargo's
        # capacity sentence as its own distribution model until the producer
        # was told whose documents these are.
        # THE SUBJECT'S CIK IS WHAT DECIDES OWNERSHIP. Without it every
        # EDGAR document looks equally like this filer's own, and Wells
        # Fargo's 10-K stated JPMorgan's business model on the live page.
        subject_cik = str((self.run_meta(run_id) or {}).get("cik") or "")
        if trace is not None:
            # BYTES, NOT JUST DOCUMENTS. This stage scans each document's full
            # text -- signal detection, filing detection, section-aware
            # excerpt selection -- so its cost tracks CHARACTERS, not the
            # document count. Deployed it used 4.2x the CPU of the local run
            # on 11 documents against 10, and without the size there is no way
            # to tell a real defect from one extra 10-K. A comparison that
            # cannot rule out its own confound is not a measurement.
            _chars = sum(len(d.get("text_content") or "") for d in documents)
            with trace.span("derive_observations",
                            documents=len(documents),
                            text_chars=_chars) as _sp:
                observations = derive_observations(
                    documents, company=company_name, subject_cik=subject_cik,
                    deadline=deadline)
                _sp["item_count"] = len(observations or ())
                _sp["deadline_stopped"] = bool(
                    deadline is not None
                    and getattr(deadline, "expired", False))
        else:
            observations = derive_observations(
                documents, company=company_name, subject_cik=subject_cik,
                deadline=deadline)
        # RECORD THE DECISION, NOT JUST ITS RESULT.
        #
        # Four deploys went into a defect whose entire difficulty was that
        # this one field could not be inspected after the run ended. "Was the
        # CIK empty?" was unanswerable because nothing wrote it down at the
        # moment it mattered, and the run that would have answered it was
        # gone before the question was framed. This is deliberately an EVENT
        # rather than a live route: an event outlives the run, the process
        # and the deploy, and can be read for a run nobody thought to
        # instrument.
        # TIMED WITH TWO TIMESTAMPS, NOT A `with`. This block is ~40 lines
        # and wrapping it would re-indent every one of them to add a
        # measurement -- the edit shape that already cost this investigation
        # a mis-indented call and a phantom helper.
        _own_w, _own_c = time.monotonic(), time.thread_time()
        if run_id:
            owned = sum(1 for o in observations
                        if getattr(o, "subject_owned", True))
            # KEYED ON THE CONTENT ITSELF, which closes the class rather than
            # the instance.
            #
            # The count was the first repair, and it fixed the case measured
            # (AMD, a22929c, composing over 12 documents then 13). It cannot
            # fix a second composition over the SAME NUMBER of documents
            # whose observations differ -- and the re-gate now fires on more
            # runs than it used to, so equal-count recompositions became
            # ordinary. A diagnostic event has no business failing an
            # analysis, and this key can no longer collide: identical
            # content still dedupes to one row, and anything different gets
            # its own.
            _fingerprint = hashlib.sha256(json.dumps(
                {"cik": subject_cik, "documents": len(documents),
                 "observations": len(observations), "owned": owned},
                sort_keys=True).encode()).hexdigest()[:12]
            self._append(
                "ci.ownership_resolved", run_id=run_id,
                domain=str((self.run_meta(run_id) or {}).get("domain") or ""),
                payload={"subject_cik": subject_cik,
                         "subject_cik_present": bool(subject_cik),
                         "documents": len(documents),
                         "observations": len(observations),
                         "observations_subject_owned": owned,
                         "observations_from_another_filer":
                             len(observations) - owned},
                # KEYED ON WHAT IT RECORDS, like every other per-composition
                # event here (`claims:`, `reasoning:`, `ci-retry:`).
                #
                # This one was keyed on the run alone while its payload
                # carries `documents` and `observations` -- numbers that
                # change the moment a run composes twice. A retry pass, or a
                # re-gate after late evidence, then hit the append-only
                # store's collision guard:
                #
                #     ValueError: idempotency_key 'ci-ownership:<run>' was
                #     already used for different content
                #
                # and the whole composition failed. Latent until the EDGAR
                # budget widened and second passes became ordinary; AMD died
                # this way on a22929c at t=58.
                idempotency_key=f"ci-ownership:{run_id}:{_fingerprint}")
        if trace is not None:
            trace.mark("ownership_append", _own_w, _own_c,
                       wrote_event=bool(run_id))
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
        # CLASSIFY BEFORE COMPOSING. One owner for "what kind of business is
        # this", shared with the executive layer — a second copy is exactly
        # how the two disagreed inside one run.
        if trace is not None:
            with trace.span("classification"):
                classification = self.classification_inputs(
                    run_id, company_name, documents=documents)
        else:
            classification = self.classification_inputs(
                run_id, company_name, documents=documents)
        _build_span = (trace.span("build_report") if trace is not None
                       else __import__("contextlib").nullcontext({}))
        with _build_span:
            report = build_strategic_report(
                company_name=company_name, observations=observations,
                previous_model=previous_model,
                # THE PATTERN LIBRARY, GATED BY WHAT KIND OF BUSINESS THIS IS.
                #
                # Without this the library offers every reading to every company
                # and the signals decide. Signals record what a company's pages
                # TALK ABOUT, which is why Cloudflare -- whose 10-K discusses
                # network capacity and names large customers -- was handed the
                # capacity-ahead-of-demand reading and told a CEO about
                # "take-or-pay terms" and "replacing ageing lines".
                #
                # An unclassified company still gets the whole library: see
                # `patterns_for`. Withholding readings from a company we could not
                # classify trades a wrong answer for no answer, and no answer is
                # the failure this product was reopened to fix.
                # CLASSIFY BEFORE GATING. Passing only the name resolved every
                # company outside the manifest to UNKNOWN, and UNKNOWN takes the
                # whole library — which is how an advertising platform was told
                # about take-or-pay terms. The domain, the regulator's industry
                # code, and the filer's OWN revenue/segment sentences are what
                # separate two businesses sharing one SIC code.
                patterns=_patterns_for_company(
                    company_name,
                    domain=str((self.run_meta(run_id) or {}).get("domain") or ""),
                    registrant=classification["registrant"],
                    evidence_text=classification["evidence_text"]),
                # WHAT THE SEARCH DID, carried to the surface a reader sees. The
                # brief rendered "Another registrant's filing - none" as a bare
                # zero because this never crossed; only the provenance drawer had
                # it, and the drawer is not what a chief executive opens first.
                discovery_coverage=self.discovery_report(run_id),
                retrieval_failures=self.failure_summary(run_id),
                economic_history=self.archive_depth(run_id),
                # THE ONE ACCOUNT OF WHAT EACH FAMILY DID. Built from documents
                # AND observations, because the gap between them is exactly what
                # the old observation-only count could not express.
                source_coverage=_SC.assess(
                    documents=documents,
                    observations=[{"source_class": getattr(o, "source_class", "")}
                                  for o in (observations or ())],
                    failures=self.failure_summary(run_id)),
                # THE SAME CLASSIFICATION THAT GATES THE PATTERN LIBRARY, GATING
                # THE TENSION LIBRARY. A tension fires on signal names, and signal
                # names are generic enough that a chip designer's partner and
                # platform language matched a marketplace's -- NVIDIA led with
                # "Consolidating checkout/identity/data rails may encroach on
                # layers partners currently monetize". One classification, two
                # gates, no second copy.
                business_model=_business_model_of(
                    company_name,
                    domain=str((self.run_meta(run_id) or {}).get("domain") or ""),
                    registrant=classification["registrant"],
                    evidence_text=classification["evidence_text"]))
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
        payload["reasoning_provenance"] = "pattern_library"
        payload["result_state"] = ResultState.EVIDENCE_LIMITED
        payload["strategic_analysis"] = None
        # CORE STOPS HERE, AND IT IS NOT A DEGRADED ANALYSIS.
        #
        # Everything above is derived from THIS company's retrieved evidence:
        # what changed, when, from which source, what it depends on, what is
        # missing. What is NOT above is the strategic reading, and the model
        # call that produces it is the whole remaining latency — measured on
        # the deployed service at 192-204s inside one stage, against a 60s
        # interactive budget.
        #
        # So the reader gets the evidence-grounded half immediately and the
        # reasoning is merged into this same object when it arrives. The
        # scaffolds in `hypotheses`/`patterns`/`blind_spots` are NOT promoted
        # to findings to fill the gap: they are library structure, they are
        # generic by construction, and presenting them as this company's
        # conclusions would buy latency with the one thing that may not be
        # spent on it.
        if not deep:
            payload["deep_status"] = DEEP_PENDING
            payload["result_state"] = ResultState.DEEP_PENDING
            payload["result_state_detail"] = \
                ResultState.EXPLANATION[ResultState.DEEP_PENDING]
            return payload
        # COMPUTED HERE BECAUSE ONLY THE DEEP PATH READS IT.
        #
        # This ran ABOVE the `if not deep` return, so every interactive CORE
        # request paid for a second full scan of every retrieved document and
        # then discarded the result -- 587.5ms locally, and the larger half of
        # a 17.6s block on the preview. Nothing between the old call site and
        # the return touched `evidence`, so moving it changes no output; the
        # CORE payload is byte-identical either way.
        #
        # `derive_analyst_evidence` is pure -- no I/O, no writes, one return --
        # so that is established by reading rather than by trusting a test.
        if trace is not None:
            with trace.span("analyst_evidence") as _ae:
                evidence = derive_analyst_evidence(documents, company_name)
                _ae["item_count"] = len(evidence or ())
        else:
            evidence = derive_analyst_evidence(documents, company_name)
        evidence += list(extra_observations or ())
        payload["deep_status"] = DEEP_RUNNING
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

    def archive_depth(self, run_id: str) -> dict:
        """How far back OUR OWN observations go, for the history assessment.

        Measured from `retrieved_at` -- when we actually read the document --
        never from a date printed inside it. A filing covering 2019 that we
        first read last week was not available at a 2019 decision point, and
        using the document's own date would admit exactly the hindsight that
        makes a replay worthless.
        """
        from intent_engine.strategic_intelligence import economic_history as EH
        try:
            rows = [{"observed_at": r.get("retrieved_at")}
                    for r in self.store.retrieved(run_id)]
        except Exception:  # noqa: BLE001 - a read model may not fail a run
            return {}
        return EH.assess(observations=rows)

    def record_trace(self, run_id: str, phase: str, waterfall: dict) -> None:
        """Persist one phase's spans. Best-effort: never fail an analysis."""
        try:
            self._append("ci.trace_recorded", run_id=run_id,
                         domain=(self.run_meta(run_id) or {}).get("domain", ""),
                         payload={"phase": phase, **waterfall},
                         idempotency_key=f"ci-trace:{run_id}:{phase}")
        except Exception:                         # noqa: BLE001
            pass

    def trace(self, run_id: str) -> list:
        """Every recorded phase for one run, oldest first."""
        return [row.payload for row in self.store.for_run(run_id)
                if row.event_type == "ci.trace_recorded"]

    def mark_lifecycle(self, run_id: str, marker: str) -> None:
        """Record that a run crossed one lifecycle boundary, at this instant.

        Idempotent per (run, marker): the FIRST crossing is the true one, and
        a retry or a second worker must not move a timestamp the measurement
        already depends on.
        """
        from intent_engine.company_ingestion.records import LIFECYCLE_MARKERS
        if marker not in LIFECYCLE_MARKERS:
            raise IngestionError(f"unknown lifecycle marker: {marker!r}")
        self._append("ci.lifecycle_marked", run_id=run_id,
                     domain=(self.run_meta(run_id) or {}).get("domain", ""),
                     payload={"marker": marker},
                     idempotency_key=f"ci-lifecycle:{run_id}:{marker}")

    def lifecycle(self, run_id: str) -> dict:
        """The canonical timings for one run, as ISO instants.

        Read from the persisted event stream rather than from a process
        dictionary, so a restart, a second worker or a later question can all
        still get the same answer.
        """
        out: dict = {}
        for row in self.store.for_run(run_id):
            if row.event_type == "ci.lifecycle_marked":
                out.setdefault(row.payload.get("marker", ""), row.occurred_at)
            elif row.event_type == "ci.run_created":
                out.setdefault("created", row.occurred_at)
        out.pop("", None)
        return out

    def failure_summary(self, run_id: str) -> dict:
        """Counts by failure type for this run. Never URLs.

        WHY A SURFACE NEEDS THIS. Caterpillar's brief showed six empty
        evidence families and no reason for any of them. The reason existed:
        caterpillar.com answers 403 to automated requests, and the run
        recorded that. Without it the page reads as though the company has
        published nothing, which is a claim about the company rather than
        about our access to it.
        """
        counts = {}
        try:
            for row in self.store.failures(run_id):
                key = str((row or {}).get("failure_type") or "unknown")
                counts[key] = counts.get(key, 0) + 1
        except Exception:  # noqa: BLE001 - a read model may not fail a run
            return {}
        return counts

    def abstention_reason(self, run_id: str, *, reasoning_error: str = "",
                          capacity_refused: bool = False) -> dict:
        """WHY this run did not produce a full report, as one classified label.

        For telemetry and qualification, never for the reader: the customer
        gets prose that names the hosts and says what is missing. A cohort
        that reports every bounded abstention as "insufficient evidence"
        cannot tell a rate limit from a genuinely thin company, and the
        50-company requalification had 23 such rows under one label.

        Never raises: a read model may not fail a run.
        """
        from intent_engine.company_ingestion import abstention as _AB
        try:
            documents = list(self.store.retrieved(run_id))
            failures = list(self.store.failures(run_id))
            verdict = assess_readiness(
                documents=documents,
                identity=self.entity_identity(run_id),
                failures=failures)
            return _AB.classify(
                readiness_state=verdict.get("state", ""),
                failures=failures, documents=documents,
                unmet_checks=verdict.get("unmet_checks") or (),
                reasoning_error=reasoning_error,
                capacity_refused=capacity_refused)
        except Exception:                       # noqa: BLE001
            return {"reason": _AB.INTERNAL_FAILURE,
                    "detail": "the abstention reason could not be computed",
                    "counts": {}, "hosts": {}, "documents": 0}

    def record_analysis_updated(self, run_id: str, *, fields, new_documents,
                                reason: str) -> None:
        """Record that evidence arriving after `core_ready` moved the answer.

        The reader is told a named set of fields changed and how much new
        evidence caused it. Not a new report and not a correction: the first
        answer was defensible on the evidence it had, and this is what the
        rest of the evidence did to it.
        """
        meta = self.run_meta(run_id) or {}
        self._append("ci.analysis_updated", run_id=run_id,
                     domain=meta.get("domain", ""),
                     subject_type="run", subject_id=run_id,
                     payload={"fields_changed": sorted(fields),
                              "new_documents": int(new_documents),
                              "reason": reason},
                     # CONTENT-DERIVED, NOT RUN-SCOPED. A key over the run
                     # and the field NAMES alone collides the moment the same
                     # fields move twice with different counts -- which is
                     # precisely the `ci-ownership:<run>` defect this file
                     # already carries a comment about. The payload that can
                     # differ goes in the key.
                     idempotency_key="ci-updated:" + run_id + ":"
                                     + hashlib.sha256(json.dumps(
                                         {"f": sorted(fields),
                                          "n": int(new_documents)},
                                         sort_keys=True).encode()
                                     ).hexdigest()[:12])

    def analysis_updates(self, run_id: str) -> list:
        """Every `ci.analysis_updated` row for this run, oldest first."""
        return [dict(row.payload) for row in self.store.for_run(run_id)
                if row.event_type == "ci.analysis_updated"]

    def discovery_report(self, run_id: str) -> dict:
        """What the independent-channel search DID for this run.

        Empty when discovery never ran, which every consumer must read as
        DISCOVERY_NOT_RUN. An empty dict is not a measured zero.
        """
        return dict(getattr(self, "_discovery_reports", {}).get(run_id) or {})

    def _third_party_filing_candidates(self, meta, run_id: str = "") -> list:
        """Filings by OTHER registrants naming this company. Never raises."""
        from intent_engine.company_ingestion.third_party_filings import (
            discover_third_party_filings,
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
            report = discover_third_party_filings(
                company_name=company_name, subject_cik=subject_cik)
        except Exception:  # noqa: BLE001 - discovery must never break
            return []
        # RETAINED, NOT JUST RETURNED. The candidates flow onward as sources;
        # the SEARCH ITSELF -- what it tried, read and rejected -- has no other
        # route to the dossier, and without it the drawer cannot tell a
        # finding about the company from a limit of our retrieval.
        if not hasattr(self, "_discovery_reports"):
            self._discovery_reports = {}
        if run_id:
            self._discovery_reports[run_id] = report
        return report.get("candidates") or []

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
