"""Customer-safe provenance: where a claim came from, and who said it.

WHAT THIS IS
------------
A SANITIZED PROJECTION of documents already retrieved and already classified
by `independence`. It is not a second provenance store, and it computes no
lineage of its own -- two definitions of "independent" in one system is a
defect this codebase has already shipped and repaired twice.

WHY IT IS A PROJECTION AND NOT A COPY
-------------------------------------
The dossier withholds internal reference ids by design, and that is correct:
`source_id`, run ids and graph node ids are storage identity, not evidence.
But withholding the ids is not a reason to withhold the EVIDENCE, and a
product that cannot show a buyer where a claim came from is asking to be
taken on faith. So this carries the publicly checkable facts -- title, URL,
author, host, subject, dates, a bounded passage -- and never the identifiers.

THE ATTRIBUTION WALL (§10)
--------------------------
    HOST     who served the bytes
    AUTHOR   who wrote them
    SUBJECT  who they are about

Cloudflare's 10-K is hosted by the SEC, authored by Cloudflare, and about
Cloudflare. Presenting that as "independent government confirmation" is the
exact false claim this system published live, and the three fields are kept
apart here so no surface can collapse them again by accident.

ABSENCE IS A STATE (§13)
------------------------
An empty list must never read as "no evidence existed". The five states below
separate "we have it", "it exists and you may not see it", "we never had it",
"we had it and the source is gone", and "the question does not apply".
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Sequence

from intent_engine.company_ingestion import independence as IND

CONTRACT = "claim_provenance.v1"

# --- visibility states (closed) ---------------------------------------------
PROVENANCE_AVAILABLE = "PROVENANCE_AVAILABLE"
PROVENANCE_WITHHELD_PRIVATE = "PROVENANCE_WITHHELD_PRIVATE"
PROVENANCE_UNAVAILABLE = "PROVENANCE_UNAVAILABLE"
PROVENANCE_SOURCE_GONE = "PROVENANCE_SOURCE_GONE"
PROVENANCE_NOT_APPLICABLE = "PROVENANCE_NOT_APPLICABLE"

VISIBILITY_STATES = (PROVENANCE_AVAILABLE, PROVENANCE_WITHHELD_PRIVATE,
                     PROVENANCE_UNAVAILABLE, PROVENANCE_SOURCE_GONE,
                     PROVENANCE_NOT_APPLICABLE)

#: Source classes that are the company talking about itself. `competitor` and
#: `customer_voice` are NOT here: those documents are company-published too,
#: but published by a DIFFERENT company, which is the whole point.
_SELF_CLASSES = frozenset({"company_owned", "executive_statement",
                           "investor_material"})

#: The longest passage a dossier will carry. Long enough to show the sentence
#: a claim rests on, short enough that the dossier is a citation rather than a
#: republication of somebody's copyrighted page.
MAX_PASSAGE = 320

#: §16 -- what a reader is told, per lineage. The enum stays underneath; this
#: is what appears on the page, because "REGULATOR_OR_PRIMARY_FILING" tells a
#: CEO nothing and "a filing the company wrote itself" tells them everything.
_PLAIN = {
    IND.COMPANY_SELF_REPORT: "The company's own account of itself",
    IND.REGULATOR_OR_PRIMARY_FILING: "A regulatory filing written by a "
                                     "third party",
    IND.INDEPENDENT_EXTERNAL_SOURCE: "Third-party reporting",
    IND.SAME_ORIGIN: "Another document from a source already counted",
    IND.SAME_DOCUMENT: "A duplicate of a document already counted",
    IND.DERIVED_REPUBLICATION: "A republication of a document already counted",
    IND.UNKNOWN_LINEAGE: "A source whose origin could not be established",
}

#: The sentence for the case the product got wrong in production.
_SELF_FILING_PLAIN = "A filing the company wrote about itself, hosted by the "
_SELF_FILING_HOSTS = {"sec.gov": "SEC", "sedarplus.ca": "SEDAR+",
                      "sedar.com": "SEDAR"}


def _provenance_id(row: dict, document: dict) -> str:
    """Stable, and derived from CONTENT rather than from storage identity.

    Deriving it from `source_id` would export an internal id under a new
    name, which is the leak this projection exists to avoid.
    """
    basis = (str(document.get("content_hash") or "")
             or str(row.get("url") or "") or str(row.get("index")))
    return "prv_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _passage(document: dict) -> str:
    """A bounded excerpt, preferring the description the publisher wrote."""
    for key in ("meta_description", "text_content"):
        text = " ".join(str(document.get(key) or "").split())
        if len(text) >= 40:
            return text[:MAX_PASSAGE].rstrip() + (
                "…" if len(text) > MAX_PASSAGE else "")
    return ""


def _plain_label(row: dict, *, self_authored: bool, host: str) -> str:
    if self_authored and row.get("is_filing"):
        regulator = next(
            (name for suffix, name in _SELF_FILING_HOSTS.items()
             if host == suffix or host.endswith("." + suffix)), "the regulator")
        return _SELF_FILING_PLAIN + regulator
    return _PLAIN.get(row.get("lineage", ""), "A source of unstated kind")


def project(documents: Sequence[dict], *, subject_filers=(),
            subject_domain: str = "", subject_name: str = "") -> Dict[str, Any]:
    """One sanitized provenance record per retrieved document.

    Takes the SAME subject identification `independence.assess` takes, and
    passes it straight through, so the two can never disagree about whether a
    document is the subject's own.
    """
    if not documents:
        return {"contract": CONTRACT, "state": PROVENANCE_UNAVAILABLE,
                "reason": "no documents were retrieved for this company, so "
                          "there is nothing to attribute",
                "records": []}

    rows = IND.classify(documents, subject_filers=subject_filers,
                        subject_domain=subject_domain)
    records: List[dict] = []
    for row, document in zip(rows, documents):
        url = str(row.get("url") or "")
        host = IND._host(url)
        self_authored = IND.subject_authored(
            document, subject_filers=subject_filers,
            subject_domain=subject_domain)
        # A document with no class recorded is not "company owned by default"
        # -- guessing here is how an unknown becomes corroboration upstream.
        source_class = str(row.get("source_class") or "")
        if not self_authored and source_class in _SELF_CLASSES and not url:
            self_authored = False

        filing = bool(document.get("filing")) or IND._is_primary_filing(
            document)
        enriched = dict(row, is_filing=filing)
        author = _author_of(document, host=host, url=url,
                            self_authored=self_authored,
                            subject_name=subject_name)
        records.append({
            "provenance_id": _provenance_id(row, document),
            "title": str(document.get("title") or "").strip(),
            "url": url,
            # THE THREE THAT MUST NOT COLLAPSE.
            "author": author,
            "host": host,
            "subject": subject_name or subject_domain,
            "self_authored": self_authored,
            "source_class": source_class,
            "evidence_type": "FILING" if filing else "WEB_DOCUMENT",
            "published_at": str(document.get("published_at") or ""),
            "retrieved_at": str(document.get("retrieved_at")
                                or document.get("known_at") or ""),
            "freshness": str(document.get("freshness") or ""),
            "lineage": row.get("lineage", ""),
            "independence_bearing": bool(row.get("independence_bearing")),
            "origin_group": row.get("origin_family", ""),
            "passage": _passage(document),
            "plain_statement": _plain_label(
                enriched, self_authored=self_authored, host=host),
            "visibility": (PROVENANCE_AVAILABLE if url
                           else PROVENANCE_WITHHELD_PRIVATE),
        })
    return {"contract": CONTRACT, "state": PROVENANCE_AVAILABLE,
            "reason": "", "records": records}


def _author_of(document: dict, *, host: str, url: str, self_authored: bool,
               subject_name: str) -> str:
    """Who WROTE it, never who served it.

    Reading the host here is the defect: it made every SEC-hosted document
    "SEC", which is how a company's own annual report came to look like
    government confirmation of that company.
    """
    stated = str(document.get("author") or document.get("publisher") or "")
    if stated.strip():
        return stated.strip()
    if self_authored and subject_name:
        return subject_name
    filer = IND.filing_author(url)
    if filer:
        return f"SEC filer {filer}"
    return host or ""


def for_claim(projection: dict, claim_refs: Sequence[str]) -> dict:
    """The subset of a projection supporting one claim (§14).

    An empty result is NOT_APPLICABLE rather than an empty bibliography: a
    claim that cites nothing has a different problem from a claim whose
    citations are withheld, and one empty list cannot say both.
    """
    if not isinstance(projection, dict) or not projection.get("records"):
        return {"contract": CONTRACT, "state": PROVENANCE_UNAVAILABLE,
                "reason": (projection or {}).get("reason", ""), "records": []}
    wanted = {str(r) for r in (claim_refs or ()) if str(r)}
    if not wanted:
        return {"contract": CONTRACT, "state": PROVENANCE_NOT_APPLICABLE,
                "reason": "this statement does not rest on a retrieved "
                          "document",
                "records": []}
    chosen = [r for r in projection["records"]
              if r["provenance_id"] in wanted]
    if not chosen:
        return {"contract": CONTRACT, "state": PROVENANCE_UNAVAILABLE,
                "reason": "the sources behind this statement are not in this "
                          "dossier",
                "records": []}
    return {"contract": CONTRACT, "state": PROVENANCE_AVAILABLE,
            "reason": "", "records": chosen}
