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

FTS_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"

#: forms whose text is substantive prose about a business, in rough order of
#: how much a third party says about a competitor inside them.
SUBSTANTIVE_FORMS = ("10-K", "20-F", "10-Q", "S-1", "424B4", "DEF 14A")

#: bounded: this is one evidence family, not a crawler
MAX_CANDIDATES = 4
MAX_HITS_SCANNED = 100

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


def _filing_url(accession_with_doc: str, cik: str) -> str:
    """EDGAR archive URL for a full-text-search hit id."""
    accession, _, document = (accession_with_doc or "").partition(":")
    nodash = accession.replace("-", "")
    cik_plain = _normalise_cik(cik) or "0"
    doc = document or f"{accession}.txt"
    return (f"https://www.sec.gov/Archives/edgar/data/{cik_plain}/"
            f"{nodash}/{doc}")


def classify_mention(*, snippet: str, form: str) -> dict:
    """Is this a substantive statement about the subject, or a list entry?"""
    text = snippet or ""
    incidental = bool(_INCIDENTAL.search(text))
    substantive_form = any(form.upper().startswith(f) for f in SUBSTANTIVE_FORMS)
    return {"substantive_form": substantive_form,
            "incidental_context": incidental,
            "usable": substantive_form and not incidental}


def _too_old(file_date: str, *, today=None) -> bool:
    """True when this filing predates the recency window."""
    import datetime as _dt
    try:
        filed = _dt.date.fromisoformat(str(file_date)[:10])
    except ValueError:
        return True                       # undated is not usable as evidence
    now = today or _dt.date.today()
    return (now - filed).days > MAX_FILING_AGE_DAYS


def propose_third_party_filings(*, company_name: str, subject_cik: str = "",
                                transport=None, limit: int = MAX_CANDIDATES,
                                forms: str = "10-K", today=None) -> list:
    """Candidate filings BY OTHER REGISTRANTS that name this company.

    Defensive by contract: returns [] on any failure. Discovery must never be
    broken by an upstream index being slow, changed or unreachable.
    """
    if not (company_name or "").strip():
        return []
    query = urllib.parse.quote(f'"{company_name}"')
    import datetime as _dt
    start = ((today or _dt.date.today())
             - _dt.timedelta(days=MAX_FILING_AGE_DAYS)).isoformat()
    url = (f"{FTS_ENDPOINT}?q={query}&forms={urllib.parse.quote(forms)}"
           f"&dateRange=custom&startdt={start}"
           f"&enddt={(today or _dt.date.today()).isoformat()}")
    try:
        payload = _get_json(url, transport=transport)
    except Exception:                             # noqa: BLE001 - never raise
        return []

    subject = _normalise_cik(subject_cik)
    seen_filers, out = set(), []
    for hit in (payload.get("hits", {}).get("hits", []) or [])[:MAX_HITS_SCANNED]:
        if len(out) >= limit:
            break
        source = hit.get("_source", {}) or {}
        ciks = [_normalise_cik(c) for c in (source.get("ciks") or [])]
        # THE WHOLE POINT: the subject's own filings are company-authored, and
        # counting them here would recreate the false independence this
        # module exists to end.
        if subject and subject in ciks:
            continue
        if not ciks:
            continue
        filer_cik = ciks[0]
        if filer_cik in seen_filers:              # one voice per organisation
            continue
        names = source.get("display_names") or []
        filer = (names[0] if names else "").strip()
        if not filer:
            continue
        form = str(source.get("file_type") or "")
        if _too_old(source.get("file_date", ""), today=today):
            continue
        verdict = classify_mention(
            snippet=" ".join(str(x) for x in (source.get("_snippet") or "")),
            form=form)
        if not verdict["usable"]:
            continue
        seen_filers.add(filer_cik)
        short = re.sub(r"\s*\(CIK[^)]*\)", "", filer).strip()
        out.append({
            "url": _filing_url(hit.get("_id", ""), filer_cik),
            "source_type": "external_approved",
            "discovery_method": "third_party_filing",
            "same_domain": False,
            # A different registrant writing about the subject. Not the
            # subject's own investor material -- that distinction is the
            # entire contribution of this adapter.
            "source_class": "competitor",
            "why_useful": f"{short} describes {company_name} in its own "
                          f"{form} filing",
            "why_relevant": "an independent registrant's account of this "
                            "company, filed under regulatory obligation",
            "availability": "UNVERIFIED",
            "title": f"{short} — {form} ({source.get('file_date', 'undated')})",
            "third_party_filer": short,
            "third_party_cik": filer_cik,
            "filed_on": source.get("file_date", ""),
            "evidence_family": "competitor_or_peer_filing",
            "independence": "INDEPENDENT_OF_SUBJECT",
            "bias_note": "a peer or competitor has an interest in how it "
                         "describes this company",
        })
    return out
