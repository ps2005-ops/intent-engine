"""V1.2 SEC EDGAR authoritative-source adapter.

Public companies frequently ship JavaScript-only marketing sites whose pages
yield no server-rendered text — so a run that depends only on the company's own
HTML can retrieve zero usable evidence and dead-end (the Palantir failure). SEC
EDGAR is a permitted, official, structured, non-JavaScript source of
authoritative disclosure. This module resolves a company to its SEC CIK and
proposes a small set of recent filing documents as approval-gated candidates.

It is deliberately conservative and safe:
  - it fetches only public SEC endpoints, through the SAME SSRF wall used for
    every other retrieval (URL validation + public-address resolution);
  - it never bypasses access controls, CAPTCHAs, paywalls, logins, or robots
    policy, and reads only material a normal permitted user could read;
  - it is fully defensive: ANY failure (network down, parse error, no match)
    yields an empty candidate list, so discovery is never broken by SEC;
  - it prefers small filings (8-K/6-K) whose primary HTML document stays under
    the per-response byte cap and parses into real text — 10-K/10-Q primary
    documents are often multi-megabyte and are only a lower preference.

Nothing is fetched *for analysis* here: the returned candidates are proposed
and, like every candidate, retrieved only after explicit user approval.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from urllib.parse import urlparse

from intent_engine.company_ingestion.records import (
    MAX_RESPONSE_BYTES, USER_AGENT,
)
from intent_engine.company_ingestion.validation import (
    resolve_public_addresses, validate_candidate_url,
)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVE_DOC_URL = ("https://www.sec.gov/Archives/edgar/data/{cik}/"
                   "{accession_nodash}/{doc}")
FILING_INDEX_URL = ("https://www.sec.gov/Archives/edgar/data/{cik}/"
                    "{accession_nodash}/index.json")

# Prefer small, text-bearing filings whose primary document parses cleanly and
# stays well under the per-response byte cap. 10-K/10-Q primary documents are
# frequently multi-megabyte, so they are a lower preference on purpose.
_PREFERRED_FORMS = ("8-K", "6-K", "10-Q", "10-K", "20-F", "S-1", "424B4",
                    "DEF 14A", "40-F")
MAX_EDGAR_CANDIDATES = 3
_DROP_TOKENS = {"inc", "incorporated", "corp", "corporation", "co", "company",
                "ltd", "limited", "plc", "llc", "lp", "holdings", "group",
                "technologies", "technology", "the", "and", "of"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                          # surface 3xx as HTTPError


def _sec_transport(url: str, timeout: float):
    """Production transport for SEC endpoints. Mirrors the ordinary retrieval
    transport but sends a UA that identifies the requester per SEC fair-access
    guidance (adds a contact if SEC_CONTACT_EMAIL is set). Returns
    (status, headers_dict, body_bytes_capped, exceeded)."""
    contact = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    ua = USER_AGENT + (f" contact:{contact}" if contact else "")
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept": "application/json,text/html"})
    response = opener.open(request, timeout=timeout)
    body = response.read(MAX_RESPONSE_BYTES + 1)
    headers = {k.lower(): v for k, v in response.headers.items()}
    return (response.status, headers, body[:MAX_RESPONSE_BYTES],
            len(body) > MAX_RESPONSE_BYTES)


def _fetch_bytes(url, *, transport, resolver, timeout=8.0) -> bytes:
    """Fetch a permitted SEC URL through the SSRF wall. The URL is validated
    and its host resolved to public addresses before any request; SEC serves
    JSON, so this is not subject to the HTML-only MIME gate. Injected
    transports (tests) are honoured so the suite never touches the network."""
    url = validate_candidate_url(url)
    if resolver is not False:
        resolve_public_addresses(urlparse(url).hostname, resolver=resolver)
    tx = transport if transport is not None else _sec_transport
    status, headers, body, _exceeded = tx(url, timeout)
    if isinstance(body, str):
        body = body.encode()
    return body


def business_document(cik, accession_nodash, primary_doc, *, transport=None,
                      resolver=None):
    """Resolve the filing's BUSINESS-content document.

    An 8-K's primary document is the procedural cover page ("pursuant to the
    Securities Exchange Act ... Delaware ... Commission File Number") — legally
    required, but useless as executive intelligence. The substance lives in
    EXHIBIT 99.1 (the earnings release / press release). Prefer that when the
    filing index lists it, and fall back to the primary document.

    Returns (document_name, is_exhibit). Never raises.
    """
    try:
        raw = _fetch_bytes(
            FILING_INDEX_URL.format(cik=cik, accession_nodash=accession_nodash),
            transport=transport, resolver=resolver)
        items = json.loads(raw.decode("utf-8", "replace"))["directory"]["item"]
    except Exception:                                       # noqa: BLE001
        return primary_doc, False
    best = None
    for entry in items:
        name = str(entry.get("name", ""))
        low = name.lower()
        if not low.endswith((".htm", ".html")):
            continue
        # ex99*.htm / *ex-99*.htm / exhibit99*.htm — the earnings release
        if "ex99" in low.replace("-", "").replace("_", "") or \
                "exhibit99" in low.replace("-", "").replace("_", ""):
            # prefer 99.1 specifically when several exhibits exist
            if best is None or "991" in low.replace("-", "").replace(".", ""):
                best = name
    return (best, True) if best else (primary_doc, False)


def _tokens(name: str) -> set:
    words = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    return {w for w in words if w and w not in _DROP_TOKENS}


def resolve_cik(company_name, *, ticker=None, transport=None, resolver=None):
    """Best-effort resolve a company to its zero-padded 10-digit CIK using the
    official SEC ticker map. Matches by ticker first, then by name tokens.
    Returns {cik, cik10, title, ticker} or None. Never raises."""
    try:
        raw = _fetch_bytes(TICKERS_URL, transport=transport, resolver=resolver)
        table = json.loads(raw.decode("utf-8", "replace"))
    except Exception:                                       # noqa: BLE001
        return None
    rows = table.values() if isinstance(table, dict) else table
    want_ticker = (ticker or "").strip().upper()
    want_tokens = _tokens(company_name)
    best = None                                             # (cik, title, tkr)
    for row in rows:
        try:
            row_ticker = str(row.get("ticker", "")).upper()
            title = str(row.get("title", ""))
            cik = int(row.get("cik_str"))
        except (AttributeError, TypeError, ValueError):
            continue
        if want_ticker and row_ticker == want_ticker:
            best = (cik, title, row_ticker)
            break
        if want_tokens and want_tokens <= _tokens(title):
            # Full token containment (e.g. {palantir} <= {palantir}); keep the
            # shortest title to prefer the exact entity over subsidiaries.
            if best is None or len(title) < len(best[1]):
                best = (cik, title, row_ticker)
    if best is None:
        return None
    cik, title, row_ticker = best
    return {"cik": cik, "cik10": f"{cik:010d}", "title": title,
            "ticker": row_ticker}


def filing_candidates(resolved, *, transport=None, resolver=None,
                      limit=MAX_EDGAR_CANDIDATES) -> list:
    """Propose recent filing primary-document candidates for a resolved CIK.
    Returns candidate dicts (source_class investor_material). Never raises."""
    try:
        raw = _fetch_bytes(
            SUBMISSIONS_URL.format(cik10=resolved["cik10"]),
            transport=transport, resolver=resolver)
        recent = json.loads(raw.decode("utf-8", "replace"))["filings"]["recent"]
        forms = recent["form"]
        accessions = recent["accessionNumber"]
        docs = recent["primaryDocument"]
        dates = recent.get("filingDate", [""] * len(forms))
    except Exception:                                       # noqa: BLE001
        return []
    cik = resolved["cik"]
    out, seen = [], set()
    # Rank by preferred form, then recency (submissions are newest-first).
    order = sorted(range(len(forms)),
                   key=lambda i: (_PREFERRED_FORMS.index(forms[i])
                                  if forms[i] in _PREFERRED_FORMS else 99, i))
    for i in order:
        form, doc, acc = forms[i], docs[i], accessions[i]
        if not doc or not acc or not doc.lower().endswith((".htm", ".html")):
            continue
        nodash = acc.replace("-", "")
        # Prefer the filing's business content (Exhibit 99.1 earnings release)
        # over the procedural cover page, so the report gets results and
        # strategy commentary rather than filing boilerplate.
        chosen, is_exhibit = business_document(
            cik, nodash, doc, transport=transport, resolver=resolver)
        url = ARCHIVE_DOC_URL.format(cik=cik, accession_nodash=nodash,
                                     doc=chosen)
        if url in seen:
            continue
        seen.add(url)
        date = dates[i] if i < len(dates) else ""
        out.append({
            "url": url,
            "source_type": "external_approved",
            "discovery_method": "external_proposed",
            "same_domain": False,
            "source_class": "investor_material",
            "why_useful": ("official earnings release / exhibit — results and "
                           "strategy commentary" if is_exhibit else
                           "official SEC filing — authoritative disclosure"),
            "why_relevant": (f"official {form} filing from SEC EDGAR — "
                             "audited, authoritative, and served as plain HTML "
                             "(not a JavaScript-only marketing page)"),
            "availability": "PROPOSED",
            "title": (f"SEC {form} exhibit{f' ({date})' if date else ''}"
                      if is_exhibit
                      else f"SEC {form}{f' ({date})' if date else ''}"),
        })
        if len(out) >= limit:
            break
    return out


def propose_edgar_candidates(*, company_name, ticker=None, transport=None,
                             resolver=None) -> list:
    """Resolve the company and return authoritative SEC filing candidates.
    Fully defensive: returns [] if the company can't be resolved or SEC is
    unreachable — discovery must never fail because of this adapter."""
    try:
        resolved = resolve_cik(company_name, ticker=ticker,
                               transport=transport, resolver=resolver)
        if not resolved:
            return []
        return filing_candidates(resolved, transport=transport,
                                 resolver=resolver)
    except Exception:                                       # noqa: BLE001
        return []
