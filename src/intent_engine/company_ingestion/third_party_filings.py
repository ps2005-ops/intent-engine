"""Filings written by SOMEONE ELSE that name the subject company.

THE MEASURED GAP THIS CLOSES.

Across ten real companies the product retrieved ZERO independent vantage
points. Every source was the company describing itself: its site, its
executives, its own filings. The analyst was asked to reach a strategic view
with nothing to check the company's account against, and it correctly declined
or reached for figures it half-remembered.

The families that would fix that were probed and mostly are not reachable:
review sites answer 403, major newswire feeds answer 401/404, and no attributed
analyst source was accessible. Bypassing any of those is out of the question,
so they are reported unavailable rather than faked.

What IS reachable is EDGAR full-text search. A competitor's own 10-K naming the
subject is:

    author       a different registrant  -> INDEPENDENT of the subject
    venue        EDGAR                   -> primary regulatory record
    date         the filing date         -> exact, not "retrieved today"
    citation     a permanent accession    -> durable
    relevance    real, when the mention is substantive

The last word is what this module spends most of its care on. A company named
once in an exhibit index or a customer list is not evidence about that company,
and counting it would manufacture the very independence the last cycle proved
we did not have.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from intent_engine.company_ingestion import relevance as _COV
from intent_engine.company_ingestion.edgar import (
    MAX_FILING_BYTES, TRUNCATABLE_FORMS,
)

FTS_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"

#: forms whose text is substantive prose about a business, in rough order of
#: how much a third party says about a competitor inside them.
SUBSTANTIVE_FORMS = ("10-K", "20-F", "10-Q", "S-1", "424B4", "DEF 14A")

#: bounded: this is one evidence family, not a crawler
MAX_CANDIDATES = 4
MAX_HITS_SCANNED = 100

#: OVERSAMPLING AND THE FETCH BUDGET.
#:
#: Selection used to happen against search metadata alone, and the channel
#: supplies no text at search time -- measured live, `_snippet` and `highlight`
#: are both absent from every hit. So the relevance rule was being asked to
#: judge an empty string, which it correctly refused to do, which meant four
#: candidate slots were handed out on form and date alone. EVENTIKO INC. spent
#: one of them and was refused downstream.
#:
#: The order is therefore inverted: consider many, fetch a bounded few, judge
#: them on what they actually say, then keep the best. These two numbers are
#: the whole cost control -- at most MAX_FETCHES documents leave the machine
#: per company, regardless of how large the result set is.
MAX_CANDIDATES_CONSIDERED = 30
MAX_FETCHES = 12

#: A 10-K is front-loaded: Item 1 (Business) and Item 1A (Risk Factors) are
#: where a registrant discusses anyone else, and they open the document. A cap
#: here bounds memory and time without costing the passages we are looking for.
MAX_FETCH_BYTES = 3_000_000

#: How far back a filing may be and still bear on a CURRENT strategic claim.
#: Measured: an unfiltered search returned Adobe's newest third-party mention
#: from 2006 and ASML's from 2013. A competitor's view of a company twenty
#: years ago is a historical fact, not evidence about the company today, and
#: presenting it as corroboration would be worse than having none.
MAX_FILING_AGE_DAYS = 365 * 4

# A mention that is only a list entry, an index row or a trademark notice.
_INCIDENTAL = re.compile(
    r"(exhibit\s+index|list of subsidiaries|trademarks? of their respective|"
    r"table of contents|signature page)", re.I)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _sec_user_agent() -> str:
    """The shared UA plus a contact, exactly as edgar._sec_transport builds it.

    This module had invented its own User-Agent string with a placeholder
    contact. SEC fair-access guidance asks for a real one, and the rest of the
    codebase already threads SEC_CONTACT_EMAIL through for precisely that --
    so a second, weaker convention here was a way to start getting 403s that
    the other SEC caller would not.
    """
    import os
    from intent_engine.company_ingestion.records import USER_AGENT
    contact = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    return USER_AGENT + (f" contact:{contact}" if contact else "")


def _get_json(url, *, transport=None, timeout=20.0):
    if transport is not None:                     # injected in tests
        return transport(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": _sec_user_agent(),
                      "Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read())


def _normalise_cik(value) -> str:
    return str(value or "").strip().lstrip("0")


#: Legal-form words that differ between how a registrant signs a filing and
#: how the manifest spells the company. Stripped from both sides before
#: comparison; never used to match on their own.
_LEGAL_FORMS = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "lp", "llp", "plc", "sa", "nv", "ag", "se", "gmbh",
    "holdings", "holding", "group", "the",
})


def _core_name(value: str) -> str:
    """A company name reduced to its distinguishing words.

    EXACT, NOT FUZZY, AND DELIBERATELY SO. A containment test here would be
    the same bug this codebase has already shipped once: "Linear" matched
    "Linear Minerals Corp.", a different company, and the fix that widened
    matching was worse than the defect. Over-matching does not merely lose a
    candidate, it DELETES a true independent observation — so the comparison
    is equality between normalised cores, and anything less certain is
    allowed through as independent and adjudicated downstream.
    """
    cleaned = re.sub(r"\((?:CIK|[A-Z.]{1,6})[^)]*\)", " ", value or "")
    words = re.findall(r"[a-z0-9]+", cleaned.lower())
    kept = [w for w in words if w not in _LEGAL_FORMS]
    return " ".join(kept or words)


#: Words that describe a CORPORATE FUNCTION rather than a different business.
#: A registrant whose name is the subject's name plus only these is the
#: subject's own captive vehicle, however separately it files.
_AFFILIATE_FUNCTIONS = frozenset({
    "financial", "finance", "financing", "capital", "credit", "leasing",
    "lease", "funding", "receivables", "services", "service", "insurance",
    "investments", "investment", "trust", "treasury", "bank", "banking",
    "international", "global", "worldwide", "usa", "us", "america",
    "american", "north", "canada", "canadian", "europe", "european", "japan",
    "asia", "pacific", "operations", "operating", "enterprises", "industries",
    "products", "technologies", "systems", "solutions", "ventures", "partners",
    "sub", "subsidiary", "delaware", "escrow", "issuer", "notes",
})


def _is_affiliate(filer: str, company_name: str) -> bool:
    """A separately-filing arm of the SAME economic entity.

    MEASURED LIVE, AND THE WORST KIND OF MISS. Caterpillar's top-ranked
    "independent" source was CATERPILLAR FINANCIAL SERVICES CORP -- its own
    captive finance subsidiary. It files under its own CIK and signs with its
    own name, so both existing locks passed it, and the product presented the
    company's own arm as an outside voice corroborating the company.

    Deliberately narrow, and a POSITIVE finding only: the filer's core name
    must BEGIN with the subject's entire core name, and every remaining word
    must be a corporate-function word. That is what keeps this from becoming
    the containment test this module already refuses -- "Linear Minerals Corp."
    survives, because `minerals` names a different business, and losing a true
    independent observation is worse than carrying a weak one.
    """
    left, right = _core_name(filer).split(), _core_name(company_name).split()
    if not left or not right or len(left) <= len(right):
        return False
    if left[:len(right)] != right:
        return False
    return all(word in _AFFILIATE_FUNCTIONS for word in left[len(right):])


def _same_organisation(filer: str, company_name: str) -> bool:
    """Whether a filer name denotes the subject company itself."""
    left, right = _core_name(filer), _core_name(company_name)
    return (bool(left) and left == right) or _is_affiliate(filer, company_name)


def _filing_url(accession_with_doc: str, cik: str) -> str:
    """EDGAR archive URL for a full-text-search hit id."""
    accession, _, document = (accession_with_doc or "").partition(":")
    nodash = accession.replace("-", "")
    cik_plain = _normalise_cik(cik) or "0"
    doc = document or f"{accession}.txt"
    return (f"https://www.sec.gov/Archives/edgar/data/{cik_plain}/"
            f"{nodash}/{doc}")


def classify_mention(*, snippet: str, form: str,
                     company_name: str = "") -> dict:
    """Is this a substantive statement about the subject, or a list entry?

    THE SAME RELEVANCE RULE THE MEASUREMENT STAGE USES, APPLIED EARLIER.
    `_INCIDENTAL` only catches STRUCTURE -- tables of contents, exhibit
    indexes, signature pages. EVENTIKO INC.'s 10-K passed it and spent one of
    four candidate slots, because its snippet is ordinary prose:

        "...engaged via reputable companies such as Namecheap, Godaddy and
         Cloudflare."

    That filing was retrieved, stored, and then correctly refused downstream
    as IRRELEVANT -- so the slot bought nothing. Asking the question here
    instead means the slot goes to a filing that will survive the wall.

    This does NOT weaken either wall: it is the identical adjudication, and a
    snippet it cannot judge stays usable, because discarding a candidate on a
    truncated snippet would lose real evidence for a reason about our
    excerpt rather than about the filing.
    """
    from intent_engine.company_ingestion import relevance as _REL

    text = snippet or ""
    incidental = bool(_INCIDENTAL.search(text))
    substantive_form = any(form.upper().startswith(f) for f in SUBSTANTIVE_FORMS)
    verdict = _REL.adjudicate({"text_content": text},
                              subject_name=company_name)
    off_topic = str(verdict["state"]) == _REL.IRRELEVANT and bool(
        verdict["incidental_mentions"])
    return {"substantive_form": substantive_form,
            "incidental_context": incidental,
            "relevance": verdict["state"],
            "off_topic_mention": off_topic,
            "usable": substantive_form and not incidental and not off_topic}


def _too_old(file_date: str, *, today=None) -> bool:
    """True when this filing predates the recency window."""
    import datetime as _dt
    try:
        filed = _dt.date.fromisoformat(str(file_date)[:10])
    except ValueError:
        return True                       # undated is not usable as evidence
    now = today or _dt.date.today()
    return (now - filed).days > MAX_FILING_AGE_DAYS


def _get_document(url, *, fetcher=None, timeout=25.0,
                  max_bytes: int = MAX_FETCH_BYTES) -> str:
    """The filing's own bytes, capped. Raises; the caller records the reason."""
    if fetcher is not None:                       # injected in tests
        return fetcher(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": _sec_user_agent(),
                      "Accept": "text/html,application/xhtml+xml,*/*"})
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout) as response:
        return response.read(max_bytes).decode("utf-8", "replace")


def assess_filing_mention(*, html: str, company_name: str,
                          author_name: str = "") -> dict:
    """What this filing actually says about the subject, from its own text.

    THE STAGE THAT DID NOT EXIST. `classify_mention` is the same adjudication,
    but it was only ever handed a search snippet -- and this channel has none,
    so it ran on "" every time in production and returned UNMEASURABLE, which
    is permissive by design. Reading the document is the only way the question
    can be answered at all on EDGAR.

    The excerpt returned is the SPAN THAT MATCHED, never a generic head of the
    document: an excerpt that does not contain the mention cannot justify the
    verdict printed beside it.
    """
    from intent_engine.company_ingestion import filing_text as _FT
    from intent_engine.company_ingestion import relevance as _REL

    extracted = _FT.extract_filing_text(html or "")
    text = extracted.get("text") or ""
    # WHO WROTE THIS decides whose behaviour a sentence describes. Without the
    # filer's name, "ChargePoint's environments are behind Cloudflare's CDN"
    # reads as an independent account of Cloudflare instead of ChargePoint
    # disclosing its own supplier -- measured live, that shape was half of
    # this company's supposed independent support.
    verdict = _REL.adjudicate({"text_content": text}, subject_name=company_name,
                              author_name=author_name)
    # THE EXCERPT IS THE SPAN THE VERDICT WAS BUILT FROM.
    #
    # It used to be the first non-boilerplate mention, which is a DIFFERENT
    # sentence from the ones that were counted. Measured live, that printed a
    # fund's holdings row -- "Bank of America Corporation (14) 3,830,768 5.90"
    # -- directly beside the words DIRECTLY_RELEVANT. An excerpt that did not
    # drive the verdict cannot justify it, and showing one is how a surface
    # starts lying with true parts.
    counted = [str(c) for c in (verdict.get("counted_spans") or [])]
    terms = _REL._terms(company_name, "")
    mentions = _REL._mentions(text, terms) if terms else []
    excerpt = " ".join(counted[0].split())[:600] if counted else ""
    return {
        "relevance": verdict["state"],
        "reason": verdict["reason"],
        "substantive_mentions": verdict["substantive_mentions"],
        "incidental_mentions": verdict["incidental_mentions"],
        "supports_corroboration": verdict["supports_corroboration"],
        "mention_count": len(mentions),
        "excerpt": excerpt,
        # EVERY span the verdict was built from, not just the first.
        #
        # The excerpt is one span, cut to 600 characters, and the clause that
        # GOVERNS a mention is often outside it: RingCentral's filing lists
        # "(Google G-Suite and Meet), Meta Platforms, Inc., Microsoft Teams,
        # Slack" — a competitor list whose verb, "we compete with", sits
        # before the cut. Relationship classification read that as UNKNOWN
        # and correctly refused it, losing the one genuine rival in the set.
        # Classification gets the whole counted set; display still gets the
        # single span that drove the verdict.
        "counted_spans": [" ".join(str(span).split())[:800]
                          for span in counted[:8]],
        "extracted_chars": len(text),
        "parse_error": extracted.get("parse_error", ""),
    }


#: Decision value, not search rank (§6/§7). The target is the most
#: decision-relevant bounded set, so a filing that DISCUSSES the company beats
#: a newer one that merely names it, and the count is never the objective.
_RELEVANCE_SCORE = {
    "DIRECTLY_RELEVANT": 100,
    "CONTEXTUALLY_RELEVANT": 60,
    "WEAKLY_RELEVANT": 25,
    "UNMEASURABLE": 10,
}
_FORM_SCORE = (("10-K", 20), ("20-F", 20), ("S-1", 15), ("424B4", 12),
               ("10-Q", 10), ("DEF 14A", 8))


def _form_score(form: str) -> int:
    upper = (form or "").upper()
    for prefix, points in _FORM_SCORE:
        if upper.startswith(prefix):
            return points
    return 0


def _freshness_score(file_date: str, *, today=None) -> int:
    import datetime as _dt
    try:
        filed = _dt.date.fromisoformat(str(file_date)[:10])
    except ValueError:
        return 0
    age = ((today or _dt.date.today()) - filed).days
    return max(0, int(round(20 * (1 - age / MAX_FILING_AGE_DAYS))))


def _selection_score(*, relevance: str, form: str, file_date: str,
                     substantive: int, today=None) -> int:
    return (_RELEVANCE_SCORE.get(str(relevance), 0)
            + _form_score(form)
            + _freshness_score(file_date, today=today)
            + min(substantive, 5) * 4)


def _structural_candidates(payload, *, company_name, subject_cik, today,
                           rejected) -> list:
    """Hits that are worth spending a fetch on, cheapest tests first.

    Nothing here judges CONTENT -- the channel supplies none. These are the
    filters that can be answered from the index alone, and every rejection is
    recorded so a zero can later be told apart from a search that never ran.
    """
    subject = _normalise_cik(subject_cik)
    seen_filers, out = set(), []
    for hit in (payload.get("hits", {}).get("hits", []) or [])[:MAX_HITS_SCANNED]:
        source = hit.get("_source", {}) or {}
        ciks = [_normalise_cik(c) for c in (source.get("ciks") or [])]
        # THE WHOLE POINT: the subject's own filings are company-authored, and
        # counting them here would recreate the false independence this
        # module exists to end.
        if subject and subject in ciks:
            rejected.append({"reason": "SUBJECT_OWN_FILING",
                             "filer": (source.get("display_names") or [""])[0]})
            continue
        if not ciks:
            rejected.append({"reason": "NO_FILER_CIK", "filer": ""})
            continue
        filer_cik = ciks[0]
        names = source.get("display_names") or []
        filer = (names[0] if names else "").strip()
        if not filer:
            rejected.append({"reason": "NO_FILER_NAME", "filer": ""})
            continue
        # SECOND LOCK ON THE SAME DOOR, BY NAME.
        #
        # `subject_cik` is resolved best-effort by the caller and its failure
        # is swallowed, so a resolver outage silently empties the CIK filter
        # above — and every candidate this module emits is stamped
        # INDEPENDENT_OF_SUBJECT. The failure would therefore not look like a
        # failure: it would look like the company corroborating itself, which
        # is the one output this module exists to prevent.
        #
        # Verified against the live index with the CIK filter off: Cloudflare's
        # own 10-K is returned as the first hit for "Cloudflare, Inc.".
        if _same_organisation(filer, company_name):
            rejected.append({"reason": "SUBJECT_OWN_FILING_BY_NAME",
                             "filer": filer})
            continue
        if filer_cik in seen_filers:              # one voice per organisation
            rejected.append({"reason": "DUPLICATE_ORIGIN", "filer": filer})
            continue
        form = str(source.get("file_type") or "")
        if not any(form.upper().startswith(f) for f in SUBSTANTIVE_FORMS):
            rejected.append({"reason": "NON_SUBSTANTIVE_FORM", "filer": filer})
            continue
        if _too_old(source.get("file_date", ""), today=today):
            rejected.append({"reason": "OUTSIDE_RECENCY_WINDOW",
                             "filer": filer})
            continue
        seen_filers.add(filer_cik)
        short = re.sub(r"\s*\(CIK[^)]*\)", "", filer).strip()
        out.append({"url": _filing_url(hit.get("_id", ""), filer_cik),
                    "filer": short, "filer_cik": filer_cik, "form": form,
                    "file_date": str(source.get("file_date", ""))})
        if len(out) >= MAX_CANDIDATES_CONSIDERED:
            break
    return out


def _emit(candidate, *, company_name, assessment) -> dict:
    form, short = candidate["form"], candidate["filer"]
    # A MENTION IS NOT A RELATIONSHIP.
    #
    # `source_class` was the constant "competitor" for every filing that
    # named the subject, which is a claim this adapter has no evidence for.
    # Measured for Meta: Oklo had a PREPAYMENT AGREEMENT with it (a
    # customer), Network-1 had a CASE AGAINST it (a litigant), Enbridge's
    # selected excerpt never mentioned it at all — and all three arrived
    # graded DIRECTLY_RELEVANT, because relevance counted passages instead
    # of reading them. Only RingCentral, which lists it among the products it
    # competes with, was actually a rival.
    #
    # The class is now READ from the excerpt. Everything that is not a
    # competitive relationship stays in the run as independent third-party
    # evidence — which is what it is, and often the more useful fact.
    from intent_engine.executive.relationship import (
        classify_relationship, source_class_for,
    )
    spans = assessment.get("counted_spans") or []
    relationship = classify_relationship(
        subject=company_name, counterparty=short,
        text="\n".join(str(s) for s in spans)
             or str(assessment.get("excerpt") or ""),
        date=candidate.get("file_date", ""), source=candidate["url"])
    return {
        "url": candidate["url"],
        "source_type": "external_approved",
        "discovery_method": "third_party_filing",
        "same_domain": False,
        # A different registrant writing about the subject. Not the
        # subject's own investor material -- that distinction is the
        # entire contribution of this adapter.
        "source_class": source_class_for(relationship.relationship_type),
        "relationship_type": relationship.relationship_type,
        "relationship_evidence": relationship.evidence,
        "relationship_confidence": relationship.confidence,
        "why_useful": f"{short} describes {company_name} in its own "
                      f"{form} filing",
        "why_relevant": "an independent registrant's account of this "
                        "company, filed under regulatory obligation",
        "availability": "UNVERIFIED",
        "title": f"{short} — {form} ({candidate['file_date'] or 'undated'})",
        "third_party_filer": short,
        "third_party_cik": candidate["filer_cik"],
        "filed_on": candidate["file_date"],
        "evidence_family": "competitor_or_peer_filing",
        "independence": "INDEPENDENT_OF_SUBJECT",
        "bias_note": "a peer or competitor has an interest in how it "
                     "describes this company",
        # Measured before selection, from the filing's own text.
        "mention_relevance": assessment["relevance"],
        "mention_reason": assessment["reason"],
        "mention_excerpt": assessment["excerpt"],
        "substantive_mentions": assessment["substantive_mentions"],
        # A STATUTORY FILING IS A STATUTORY FILING WHOEVER FILED IT.
        #
        # These candidates carried no byte budget at all, so `fetch_approved`
        # fell back to the 2MB cap meant for an untrusted arbitrary host —
        # and every one of these is a 10-K on sec.gov, the exact publisher
        # whose real document sizes motivated `MAX_FILING_BYTES` in the first
        # place. Measured live on a Meta run: all four third-party filings
        # came back "too large" while the subject's own filings, which do
        # carry the budget, were read without trouble.
        #
        # This is the whole third-party vantage point — the only source class
        # in the product that is independent of the subject — being discarded
        # by a default. Same publisher, same budget, same truncation rule.
        "form": form,
        "accept_truncated": form in TRUNCATABLE_FORMS,
        "max_bytes": MAX_FILING_BYTES,
    }


def discover_third_party_filings(*, company_name: str, subject_cik: str = "",
                                 transport=None, fetcher=None,
                                 limit: int = MAX_CANDIDATES,
                                 forms: str = "10-K", today=None,
                                 max_fetches: int = MAX_FETCHES) -> dict:
    """Fetch-then-select over the one independent channel that answers us.

    Returns the CANDIDATES AND THE SEARCH ITSELF. A zero here is not a bare
    number: it carries how many hits the channel had, how many survived the
    cheap filters, how many documents we actually read, why each rejection
    happened, and whether we ran out of budget or ran out of candidates. That
    distinction is what separates "this company has no independent coverage"
    from "we did not look hard enough", and only the second is true today.
    """
    import datetime as _dt
    report = {
        "contract": "third_party_discovery.v1",
        "channel": "edgar_full_text_search",
        "query": company_name,
        "candidates": [],
        "coverage": _COV.DISCOVERY_NOT_RUN,
        "channels_attempted": [],
        "channels_successful": [],
        "hits_total": 0,
        "candidates_considered": 0,
        "candidates_fetched": 0,
        "rejected": [],
        "rejection_reasons": {},
        "independent_relevant_origins": 0,
        "budget_exhausted": False,
        "searched_on": (today or _dt.date.today()).isoformat(),
    }
    if not (company_name or "").strip():
        return report

    report["channels_attempted"] = ["edgar_full_text_search"]
    query = urllib.parse.quote(f'"{company_name}"')
    start = ((today or _dt.date.today())
             - _dt.timedelta(days=MAX_FILING_AGE_DAYS)).isoformat()
    url = (f"{FTS_ENDPOINT}?q={query}&forms={urllib.parse.quote(forms)}"
           f"&dateRange=custom&startdt={start}"
           f"&enddt={(today or _dt.date.today()).isoformat()}")
    try:
        payload = _get_json(url, transport=transport)
    except Exception as exc:                      # noqa: BLE001 - never raise
        # A channel we could not reach is BLOCKED, which never licenses
        # "none exists" -- the one inference this whole module guards.
        report["coverage"] = _COV.DISCOVERY_BLOCKED
        report["rejection_reasons"] = {f"CHANNEL_ERROR:{type(exc).__name__}": 1}
        return report

    report["channels_successful"] = ["edgar_full_text_search"]
    report["hits_total"] = int(
        ((payload.get("hits", {}) or {}).get("total", {}) or {}).get("value", 0)
        or len((payload.get("hits", {}) or {}).get("hits", []) or []))

    rejected = report["rejected"]
    candidates = _structural_candidates(
        payload, company_name=company_name, subject_cik=subject_cik,
        today=today, rejected=rejected)
    report["candidates_considered"] = len(candidates)

    # AN INJECTED SEARCH WITH NO INJECTED FETCH IS A TEST DOUBLE.
    #
    # Reaching the live EDGAR archive from a replay would be both wrong and
    # slow, and it is exactly the mistake the service already guards against
    # one layer up. Recorded rather than silently skipped: a run that read no
    # documents did not search, whatever its search returned.
    if transport is not None and fetcher is None:
        report["rejection_reasons"] = {"FETCH_NOT_AVAILABLE": len(candidates)}
        report["coverage"] = _COV.DISCOVERY_NOT_RUN
        return report

    scored, fetches, exhausted_budget = [], 0, False
    for candidate in candidates:
        # THE BUDGET IS THE BOUND, NOT THE RESULT COUNT. Stopping the moment
        # `limit` filings are usable would make the FIRST acceptable set the
        # answer; stopping on the budget lets a better filing displace a
        # weaker one, which is the point of oversampling at all.
        if fetches >= max_fetches:
            exhausted_budget = True
            break
        try:
            html = _get_document(candidate["url"], fetcher=fetcher)
        except Exception as exc:                  # noqa: BLE001
            rejected.append({"reason": f"FETCH_FAILED:{type(exc).__name__}",
                             "filer": candidate["filer"]})
            fetches += 1
            continue
        fetches += 1
        assessment = assess_filing_mention(html=html,
                                           company_name=company_name,
                                           author_name=candidate["filer"])
        if not assessment["supports_corroboration"]:
            rejected.append({"reason": f"IRRELEVANT:{assessment['reason']}",
                             "filer": candidate["filer"]})
            continue
        scored.append((
            _selection_score(relevance=assessment["relevance"],
                             form=candidate["form"],
                             file_date=candidate["file_date"],
                             substantive=assessment["substantive_mentions"],
                             today=today),
            candidate, assessment))

    report["candidates_fetched"] = fetches
    report["budget_exhausted"] = exhausted_budget
    scored.sort(key=lambda row: row[0], reverse=True)
    report["candidates"] = [
        _emit(candidate, company_name=company_name, assessment=assessment)
        for _, candidate, assessment in scored[:limit]]
    report["independent_relevant_origins"] = len(report["candidates"])

    counts = {}
    for row in rejected:
        key = str(row.get("reason", "")).split(":")[0]
        counts[key] = counts.get(key, 0) + 1
    report["rejection_reasons"] = counts
    report["coverage"] = _coverage_state(
        considered=len(candidates), fetched=fetches,
        budget_exhausted=exhausted_budget, selected=len(report["candidates"]),
        limit=limit)
    return report


def _coverage_state(*, considered: int, fetched: int, budget_exhausted: bool,
                    selected: int, limit: int) -> str:
    """How thoroughly this channel was actually searched. MEASURED, NEVER SET.

    A constant here would be the defect this codebase keeps shipping: a field
    that reads like a measurement and is a literal. Every branch below is a
    fact about what the run did.
    """
    if budget_exhausted:
        # Candidates remained that we chose not to read. We cannot speak for
        # what they say, so "found none" stays unavailable.
        return _COV.DISCOVERY_PARTIAL
    if selected >= limit:
        return _COV.DISCOVERY_ADEQUATE
    if considered == 0 or fetched >= considered:
        # Every candidate the channel offered was read to the end.
        return _COV.DISCOVERY_EXHAUSTED
    return _COV.DISCOVERY_PARTIAL


def propose_third_party_filings(*, company_name: str, subject_cik: str = "",
                                transport=None, limit: int = MAX_CANDIDATES,
                                forms: str = "10-K", today=None,
                                fetcher=None) -> list:
    """Candidate filings BY OTHER REGISTRANTS that name this company.

    Defensive by contract: returns [] on any failure. Discovery must never be
    broken by an upstream index being slow, changed or unreachable.
    """
    try:
        return discover_third_party_filings(
            company_name=company_name, subject_cik=subject_cik,
            transport=transport, fetcher=fetcher, limit=limit, forms=forms,
            today=today)["candidates"]
    except Exception:                             # noqa: BLE001 - never raise
        return []
