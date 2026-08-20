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
  - it prefers filings whose primary HTML document parses into real text. A
    10-K usually exceeds the per-response byte cap; it is retrieved anyway,
    TRUNCATED AND MARKED AS SUCH, because Item 1. Business is at the front of
    an annual report and the truncation removes the end.

WHY ONE OF EACH KIND. Ranking purely by form preference gave every slot to
current reports (8-K), because a filer publishes many more of those than
periodic ones. Measured on the deployed preview 2026-08-04: every Palantir run
retrieved nine company-owned pages and one executive page, no filings at all —
and the analysis then reported "Revenue split between services and product is
not public" as a FINDING. It is in the quarterly report, which was never
proposed. `_spread_by_family` now serves each family once before serving any
family twice, and demotes filings older than three years so a 2015 prospectus
cannot hold a slot a current report needs.

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
from intent_engine.company_ingestion.transient import (
    DEFAULT_POLICY, call_with_retry,
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

# Prefer text-bearing filings whose primary document parses cleanly.
#
# The 10-K used to sit behind the 10-Q here because its primary document is
# frequently multi-megabyte and the retrieval discarded anything over the cap.
# It is now retrieved truncated (see TRUNCATABLE_FORMS), and it is the ONLY
# filing carrying a Competition section, so it leads.
_PREFERRED_FORMS = ("10-K", "10-Q", "20-F", "40-F", "8-K", "6-K", "S-1",
                    "424B4", "DEF 14A")
MAX_EDGAR_CANDIDATES = 3

# ONE FILING OF EACH KIND, NOT THREE OF THE SAME KIND.
#
# Ranking purely by form preference spent all three slots on 8-Ks, because a
# filer publishes far more current reports than periodic ones. Measured on the
# deployed preview: every Palantir run retrieved 9 company-owned pages and 1
# executive page, no filings at all in the report -- and the analysis then
# stated "Revenue split between services and product is not public" as a
# finding, which is false. It is in the periodic report; the periodic report
# was simply never proposed.
#
# A periodic report carries revenue disaggregation, customer concentration and
# risk factors. A current report carries the earnings release. They answer
# different questions, so the budget takes one of each before it takes a
# second of either.
#
# The annual and the quarterly report are SEPARATE families, by the same
# argument that separated periodic from current above: they answer different
# questions, so the budget takes one of each before a second of either.
#
# Sharing a "periodic" family meant the 10-Q always won it — it ranks higher
# in _PREFERRED_FORMS because it fits the byte cap — and with three candidate
# slots the round-robin filled them with 10-Q, 8-K and DEF 14A. The annual
# report was never proposed on any run.
#
# That is the whole reason competitive intelligence rendered as an absence on
# every validation company: the Competition section exists only in Item 1 of
# the annual report, and the annual report never arrived.
_FORM_FAMILY = {
    "10-K": "annual", "20-F": "annual", "40-F": "annual",
    "10-Q": "quarterly",
    "8-K": "current", "6-K": "current",
    "S-1": "registration", "424B4": "registration", "DEF 14A": "proxy",
}
#: The order families are first served in.
_FAMILY_ORDER = ("annual", "quarterly", "current", "registration", "proxy")

#: Forms whose primary document routinely exceeds the per-response byte cap
#: and which are still worth retrieving truncated, because the sections that
#: matter are at the front. See `external_intel.annual_filing`.
#:
#: THE 10-Q IS DELIBERATELY NOT HERE, and the reason is measured rather than
#: inherited. An annual report survives truncation because Item 1. Business
#: sits at the front. A quarterly report does not: measured 2026-08-05, the
#: MD&A heading sits at character 2,418,251 of 3,459,434 in Caterpillar's
#: latest 10-Q — 70% of the way in, and past any cut worth making. Truncating
#: a 10-Q keeps the tagged financial tables and discards the management
#: narrative, which is the part a reader is there for.
#:
#: So a large quarterly report is fixed by the BUDGET below, not by tolerating
#: a half-read of it. Adding the form here would have converted a visible
#: "too large" failure into an invisible half-document — the more dangerous of
#: the two, because nothing downstream would have known to say so.
TRUNCATABLE_FORMS = frozenset({"10-K", "20-F", "40-F"})

#: SEC filings get their own size budget, separate from the 2MB cap that
#: governs ordinary web retrieval.
#:
#: WHY THEY ARE NOT THE SAME NUMBER. The general cap bounds an UNTRUSTED
#: response from an arbitrary host — it is a safety limit, and it should stay
#: where it is. EDGAR is a known publisher serving structured statutory
#: documents over one validated domain, and real ones are simply larger than
#: 2MB. Measured 2026-08-05 on latest primary documents: JPMorgan 10-K
#: 12,927,325 bytes, Berkshire 10-K 10,396,820, Caterpillar 10-K 6,100,469
#: and 10-Q 3,459,434, Walmart 10-K 2,323,981, Palantir 10-K 2,192,014.
#:
#: At 2MB, seven of those twelve documents were discarded whole. That is what
#: "too large: the page exceeded the size budget" meant on Caterpillar's live
#: run, and it is why a company with a complete public record produced a
#: bounded analysis. 16MB clears the largest observed filing with headroom
#: without pretending there is no limit at all.
MAX_FILING_BYTES = 16_000_000

#: THE SUBMISSIONS INDEX IS NOT A WEB DOCUMENT AND MUST NOT SHARE ITS CAP.
#:
#: MEASURED. JPMorgan Chase (CIK 19617) files 25,746 recent documents, 22,368
#: of them 424B2 structured-note prospectuses, and its submissions JSON is
#: 4,573,499 bytes against a 2,000,000-byte MAX_RESPONSE_BYTES. The transport
#: truncated it at exactly 2 MB, `json.loads` raised on the half-object, the
#: broad `except` returned [], and the customer was told "no approved source
#: could be retrieved" for a company whose 10-K was sitting in the index.
#:
#: Every other Batch-A company's index is about 160 KB, so nothing else in
#: the cohort came near the cap and the defect looked like a JPMorgan quirk.
#: It is not: it is every filer that issues frequently — the large banks and
#: shelf issuers — and it scales with filing count, not with company size.
MAX_SUBMISSIONS_BYTES = 32_000_000


class SubmissionsTruncated(Exception):
    """The index was cut off by the byte budget, so it cannot be read.

    A DISTINCT EXCEPTION BECAUSE THE TWO OUTCOMES ARE DIFFERENT FACTS. "This
    filer has no usable filings" and "we could not read the filer's index"
    were both reported as an empty candidate list, and the second is a defect
    in us that was being displayed as a fact about the company.
    """


_DROP_TOKENS = {"inc", "incorporated", "corp", "corporation", "co", "company",
                "ltd", "limited", "plc", "llc", "lp", "holdings", "group",
                "technologies", "technology", "the", "and", "of"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                          # surface 3xx as HTTPError


def _sec_transport(url: str, timeout: float,
                   max_bytes: int = MAX_RESPONSE_BYTES):
    """Production transport for SEC endpoints. Mirrors the ordinary retrieval
    transport but sends a UA that identifies the requester per SEC fair-access
    guidance (adds a contact if SEC_CONTACT_EMAIL is set). Returns
    (status, headers_dict, body_bytes_capped, exceeded).

    `max_bytes` defaults to the ordinary cap so the metadata calls in this
    module are unaffected; only a filing DOCUMENT is fetched with
    MAX_FILING_BYTES."""
    contact = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    ua = USER_AGENT + (f" contact:{contact}" if contact else "")
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept": "application/json,text/html"})
    response = opener.open(request, timeout=timeout)
    body = response.read(max_bytes + 1)
    headers = {k.lower(): v for k, v in response.headers.items()}
    return (response.status, headers, body[:max_bytes],
            len(body) > max_bytes)


def _fetch_bytes(url, *, transport, resolver, timeout=8.0,
                 max_bytes=None, retry_policy=None, retry_ledger=None,
                 sleeper=None, rng=None) -> bytes:
    """Fetch a permitted SEC URL through the SSRF wall. The URL is validated
    and its host resolved to public addresses before any request; SEC serves
    JSON, so this is not subject to the HTML-only MIME gate. Injected
    transports (tests) are honoured so the suite never touches the network.

    SEC is the host that actually throttles this product, and this function —
    not `safe_fetch` — is how every EDGAR metadata read reaches it. Bounded,
    host-scoped retry is applied here for the same reason it is applied
    there: a 429 is "not now", and answering it by telling a customer their
    company has no filings is wrong."""
    url = validate_candidate_url(url)
    if resolver is not False:
        resolve_public_addresses(urlparse(url).hostname, resolver=resolver)
    tx = transport if transport is not None else _sec_transport

    def _attempt():
        if max_bytes is None:
            return tx(url, timeout)
        try:
            return tx(url, timeout, max_bytes)
        except TypeError:
            # An injected transport that predates the budget argument keeps
            # working against its own cap, which is what every test double
            # does today.
            return tx(url, timeout)

    status, headers, body, exceeded = call_with_retry(
        _attempt, url=url, policy=retry_policy or DEFAULT_POLICY,
        ledger=retry_ledger, sleeper=sleeper, rng=rng)
    if isinstance(body, str):
        body = body.encode()
    # TRUNCATION IS NOT AN ANSWER. Returning the cut-off bytes hands a broken
    # JSON document to a parser whose failure is indistinguishable from a
    # filer with nothing on file.
    if exceeded:
        raise SubmissionsTruncated(
            f"{url} exceeded the {max_bytes or MAX_RESPONSE_BYTES:,}-byte "
            f"budget for this call")
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


#: A filing older than this describes a company that may no longer exist in
#: the form described. Registration statements are the usual offenders -- a
#: filer has exactly one S-1 and it never ages out of the index, so spreading
#: by family alone handed slot three to Palantir's 2020 S-1 and Shopify's 2015
#: prospectus. Stale filings are demoted, never dropped: for a company that has
#: filed nothing since, its S-1 is still the best disclosure available.
_STALE_AFTER_DAYS = 1095


def _is_stale(date: str, today: str) -> bool:
    """True when `date` is more than three years before `today` (ISO dates)."""
    try:
        from datetime import date as _date
        filed = _date.fromisoformat(date[:10])
        now = _date.fromisoformat(today[:10])
    except Exception:                                       # noqa: BLE001
        return False
    return (now - filed).days > _STALE_AFTER_DAYS


def _spread_by_family(order, forms, dates=(), today="") -> list:
    """Round-robin an already-ranked index list across form families.

    Order WITHIN a family is preserved, so the best periodic report is still
    the best periodic report; only the interleaving changes. A form the family
    table does not name keeps its rank and is served last, and anything stale
    is served after everything current regardless of family.
    """
    if not today:
        from datetime import date as _date
        today = _date.today().isoformat()
    buckets, stale = {}, []
    for i in order:
        filed = dates[i] if i < len(dates) else ""
        if filed and _is_stale(filed, today):
            stale.append(i)
            continue
        buckets.setdefault(_FORM_FAMILY.get(forms[i], "other"), []).append(i)
    families = [f for f in _FAMILY_ORDER if f in buckets]
    families += [f for f in buckets if f not in _FAMILY_ORDER]
    out = []
    while any(buckets[f] for f in families):
        for family in families:
            if buckets[family]:
                out.append(buckets[family].pop(0))
    return out + stale


def registrant_classification(resolved, *, transport=None,
                              resolver=None) -> dict:
    """The SIC classification the SEC assigns this registrant.

    WHY THIS IS ALLOWED TO CLASSIFY A BUSINESS. The validation manifest
    classifies 100 companies by hand, and a company outside it used to fall
    to an implicit UNKNOWN -- which read to a customer as "we know nothing
    about Toyota". That was never true: Toyota is a registrant and the
    regulator has already classified it.

    A SIC code is the same KIND of fact as the manifest's
    business_model_class: authored, reviewed, assigned by a third party, and
    definitional rather than empirical. It says which industry the filer was
    placed in; it says nothing about what the company did last quarter. So
    it may seed a business-model profile and it may never seed a finding.

    It is strictly coarser than the manifest -- one code covers a whole
    major group -- which is why a profile derived from it is labelled
    PARTIAL and never AVAILABLE.

    Returns {"sic", "sic_description", "cik"} or {}. Never raises.
    """
    try:
        raw = _fetch_bytes(
            SUBMISSIONS_URL.format(cik10=resolved["cik10"]),
            transport=transport, resolver=resolver,
            max_bytes=MAX_SUBMISSIONS_BYTES)
        payload = json.loads(raw.decode("utf-8", "replace"))
    except Exception:                                       # noqa: BLE001
        return {}
    sic = str(payload.get("sic") or "").strip()
    if not sic:
        return {}
    return {"sic": sic,
            "sic_description": str(payload.get("sicDescription") or "").strip(),
            "cik": str(resolved.get("cik") or "")}


def submissions(cik, *, transport=None, resolver=None) -> dict:
    """The registrant's submissions record, or {}. Never raises.

    Exists so the history surface can read a company's DATED filing record
    without re-resolving it by name. `filing_candidates` already fetches this
    document to pick three URLs and then discards the dates, which is the
    only per-company dated series a first run has any access to.

    `cik` may be padded or bare; EDGAR wants ten digits.
    """
    digits = "".join(c for c in str(cik or "") if c.isdigit())
    if not digits:
        return {}
    try:
        raw = _fetch_bytes(SUBMISSIONS_URL.format(cik10=digits.zfill(10)),
                           transport=transport, resolver=resolver,
                           max_bytes=MAX_SUBMISSIONS_BYTES)
        payload = json.loads(raw.decode("utf-8", "replace"))
    except Exception:                                       # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def filing_candidates(resolved, *, transport=None, resolver=None,
                      limit=MAX_EDGAR_CANDIDATES) -> list:
    """Propose recent filing primary-document candidates for a resolved CIK.
    Returns candidate dicts (source_class investor_material). Never raises."""
    try:
        raw = _fetch_bytes(
            SUBMISSIONS_URL.format(cik10=resolved["cik10"]),
            transport=transport, resolver=resolver,
            max_bytes=MAX_SUBMISSIONS_BYTES)
        recent = json.loads(raw.decode("utf-8", "replace"))["filings"]["recent"]
        forms = recent["form"]
        accessions = recent["accessionNumber"]
        docs = recent["primaryDocument"]
        dates = recent.get("filingDate", [""] * len(forms))
    except Exception:                                       # noqa: BLE001
        return []
    cik = resolved["cik"]
    out, seen = [], set()
    # Rank by preferred form, then recency (submissions are newest-first)...
    order = sorted(range(len(forms)),
                   key=lambda i: (_PREFERRED_FORMS.index(forms[i])
                                  if forms[i] in _PREFERRED_FORMS else 99, i))
    # ...then interleave so each FAMILY is served once before any family is
    # served twice. See `_FORM_FAMILY`: the unspread order gave all three slots
    # to current reports and the periodic report was never proposed.
    order = _spread_by_family(order, forms, dates)
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
            # An annual report is worth retrieving even when it overruns the
            # per-response cap: Item 1. Business is at the front and the
            # truncation removes the end. The retrieval marks it truncated
            # and nothing downstream may call it complete.
            "form": form,
            "accept_truncated": form in TRUNCATABLE_FORMS and not is_exhibit,
            # A statutory filing is fetched against the EDGAR budget. An
            # exhibit is an ordinary attachment and stays on the general cap.
            "max_bytes": (MAX_RESPONSE_BYTES if is_exhibit
                          else MAX_FILING_BYTES),
        })
        if len(out) >= limit:
            break
    return out


def propose_edgar_candidates(*, company_name, ticker=None, transport=None,
                             resolver=None, cik="") -> list:
    """Resolve the company and return authoritative SEC filing candidates.
    Fully defensive: returns [] if the company can't be resolved or SEC is
    unreachable — discovery must never fail because of this adapter.

    `cik` short-circuits the name lookup. A run opened on a CIK already knows
    exactly which filer it is about, and re-deriving that from the typed name
    can only lose: name matching is fuzzy, and a second resolution that lands
    on a different registrant would attribute one company's filings to
    another.
    """
    try:
        if cik:
            digits = str(cik).strip().lstrip("0") or "0"
            resolved = {"cik": int(digits), "cik10": f"{int(digits):010d}",
                        "title": company_name, "ticker": ticker or ""}
        else:
            resolved = resolve_cik(company_name, ticker=ticker,
                                   transport=transport, resolver=resolver)
        if not resolved:
            return []
        return filing_candidates(resolved, transport=transport,
                                 resolver=resolver)
    except Exception:                                       # noqa: BLE001
        return []
