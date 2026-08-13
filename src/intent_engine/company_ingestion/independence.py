"""Evidence independence: are these rows one observation or many?

A document count is not corroboration. Ten copies of one press release is one
claim observed once, and every layer above retrieval — coverage, the critic,
the dossier, and any future confidence number — reads a row count as if it
were a count of independent observations. This module is the producer that
makes that distinction available, and it is deliberately conservative: it
answers "how many genuinely separate vantage points do we have on this?" and
refuses to guess when it cannot tell.

WHAT THIS IS NOT
----------------
It is NOT a second source-classification system. `records.SOURCE_CLASSES` and
`records.INDEPENDENT_CLASSES` already say which VANTAGE POINT a document
speaks from, and the strategic layer consumes them in a dozen places. That
axis is reused here unchanged.

What did not exist is the ORIGIN axis: two documents can both be
`independent_reporting` and still be the same wire story republished twice.
Vantage point alone cannot see that, because it is a property of one document
and syndication is a relation BETWEEN documents. Independence needs both:
an outside vantage point AND an origin nothing else in the set already
supplied.

WHY UNKNOWN IS NOT INDEPENDENT
------------------------------
The cheapest way to inflate this number is to treat "we could not establish
lineage" as "distinct". That converts ignorance into corroboration, which is
the exact failure this module exists to prevent, so UNKNOWN_LINEAGE is
counted, reported, and never counted as independent.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Dict, List, Sequence
from urllib.parse import urlparse

from intent_engine.company_ingestion.records import INDEPENDENT_CLASSES

CONTRACT = "evidence_independence.v1"

# --- lineage vocabulary (closed) --------------------------------------------
#: Why a document is, or is not, a separate observation. Closed on purpose: an
#: open vocabulary here would let a caller invent a label that no consumer
#: knows how to discount.
SAME_DOCUMENT = "SAME_DOCUMENT"
SAME_ORIGIN = "SAME_ORIGIN"
DERIVED_REPUBLICATION = "DERIVED_REPUBLICATION"
COMPANY_SELF_REPORT = "COMPANY_SELF_REPORT"
REGULATOR_OR_PRIMARY_FILING = "REGULATOR_OR_PRIMARY_FILING"
INDEPENDENT_EXTERNAL_SOURCE = "INDEPENDENT_EXTERNAL_SOURCE"
UNKNOWN_LINEAGE = "UNKNOWN_LINEAGE"

LINEAGES = (SAME_DOCUMENT, SAME_ORIGIN, DERIVED_REPUBLICATION,
            COMPANY_SELF_REPORT, REGULATOR_OR_PRIMARY_FILING,
            INDEPENDENT_EXTERNAL_SOURCE, UNKNOWN_LINEAGE)

#: The only two lineages that can ADD an independent observation. A company
#: self-report is evidence — often the best evidence — but it is the subject
#: speaking about itself, so it can never corroborate itself.
INDEPENDENCE_BEARING = frozenset({REGULATOR_OR_PRIMARY_FILING,
                                  INDEPENDENT_EXTERNAL_SOURCE})

# --- corroboration vocabulary (closed) --------------------------------------
SINGLE_SOURCE = "SINGLE_SOURCE"
SAME_ORIGIN_MULTIPLE_DOCUMENTS = "SAME_ORIGIN_MULTIPLE_DOCUMENTS"
PARTIALLY_INDEPENDENT = "PARTIALLY_INDEPENDENT"
INDEPENDENTLY_CORROBORATED = "INDEPENDENTLY_CORROBORATED"
LINEAGE_UNAVAILABLE = "LINEAGE_UNAVAILABLE"

CORROBORATION_STATES = (SINGLE_SOURCE, SAME_ORIGIN_MULTIPLE_DOCUMENTS,
                        PARTIALLY_INDEPENDENT, INDEPENDENTLY_CORROBORATED,
                        LINEAGE_UNAVAILABLE)

#: Ordered weakest to strongest. Property C ("a syndication must never
#: strengthen corroboration") is a statement about this order, so the order is
#: part of the contract and is asserted against, not just documented.
CORROBORATION_ORDER = {LINEAGE_UNAVAILABLE: 0, SINGLE_SOURCE: 1,
                       SAME_ORIGIN_MULTIPLE_DOCUMENTS: 2,
                       PARTIALLY_INDEPENDENT: 3,
                       INDEPENDENTLY_CORROBORATED: 4}

#: Two independent origins is the threshold for corroboration. One outside
#: vantage point is a single observation however well sourced it is.
MIN_INDEPENDENT_FOR_CORROBORATION = 2

_INDEPENDENT_VANTAGE = frozenset(INDEPENDENT_CLASSES)

#: Hosts whose documents are primary filings regardless of who linked them.
_PRIMARY_FILING_HOSTS = ("sec.gov", "sedarplus.ca", "sedar.com")

_WORD = re.compile(r"[a-z0-9]+")
#: Overlap at which two documents from DIFFERENT origins are the same text.
#: Deliberately high: a false republication finding DELETES a real independent
#: observation, which is worse than missing a syndication.
_REPUBLICATION_JACCARD = 0.60
_SHINGLE = 5


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower().lstrip(".")
    except ValueError:
        return ""


#: An EDGAR archive path names the FILER in it:
#: /Archives/edgar/data/<cik>/<accession>/<document>
_EDGAR_FILER = re.compile(r"/archives/edgar/data/(\d+)/", re.I)


def filing_author(url: str) -> str:
    """The registrant who WROTE a filing, when the URL names them.

    Returns "" when the URL is not a filing archive path, so a caller can
    fall back to the host without having to know EDGAR's layout.
    """
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower().lstrip(".")
    if not (host == "sec.gov" or host.endswith(".sec.gov")):
        return ""
    found = _EDGAR_FILER.search(parsed.path or "")
    return found.group(1).lstrip("0") if found else ""


def origin_family(url: str) -> str:
    """The publishing origin: WHO PRODUCED THIS TEXT, not who hosts it.

    Coarse on purpose and NEVER used for a security decision — this decides
    whether two documents corroborate each other, not whether a URL may be
    fetched. `blog.acme.com` and `www.acme.com` are the same publisher for
    corroboration purposes, which is exactly the collapse we want here and
    exactly the collapse that would be a vulnerability in a redirect check.

    A REGULATOR IS A VENUE, NOT AN AUTHOR
    --------------------------------------
    Reading the host alone made every document filed with the SEC one origin.
    Measured on the frozen ten: United Airlines' own 10-K describing Boeing —
    a different company, writing under regulatory obligation, with its own
    interests — was labelled SAME_ORIGIN as Boeing's 10-K and dropped from the
    independent count, because both are served from sec.gov. Three distinct
    authors collapsed into one observation.

    That is the wrong axis. Syndication is "the same words from the same
    author reprinted elsewhere"; two registrants filing separately are two
    observations however they are served. So an EDGAR archive URL takes its
    origin from the FILER named in the path, and everything else — where no
    author is derivable from the URL — keeps host-based grouping unchanged.
    """
    author = filing_author(url)
    if author:
        return f"sec.gov/filer/{author}"
    host = _host(url)
    if not host:
        return ""
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    return ".".join(labels[-2:])


def _shingles(text: str) -> frozenset:
    words = _WORD.findall((text or "").lower())[:400]
    if len(words) < _SHINGLE:
        return frozenset()
    return frozenset(
        hashlib.blake2b(" ".join(words[i:i + _SHINGLE]).encode(),
                        digest_size=8).digest()
        for i in range(len(words) - _SHINGLE + 1))


def _jaccard(left: frozenset, right: frozenset) -> float:
    if not left or not right:
        return 0.0
    union = len(left | right)
    return (len(left & right) / union) if union else 0.0


def _is_primary_filing(document: dict) -> bool:
    """A regulator-hosted document, or one the filing pipeline stamped.

    Read from BOTH the `filing` marker and the host, because a filing reached
    through a third-party mirror still carries the marker while an EDGAR URL
    fetched directly may not.
    """
    if document.get("filing"):
        return True
    host = _host(document.get("final_url") or document.get("original_url"))
    return any(host == h or host.endswith("." + h)
               for h in _PRIMARY_FILING_HOSTS)


def _vantage(document: dict) -> str:
    """The lineage this document would carry if nothing preceded it."""
    source_class = str(document.get("source_class") or "").strip()
    if _is_primary_filing(document):
        # A FILING BY SOMEONE ELSE IS AN OUTSIDE VANTAGE POINT.
        #
        # Both facts about a competitor's 10-K are true — an independent
        # registrant wrote it, and the regulator published it — but only one
        # of them answers the question this vocabulary asks, which is whose
        # account of the company this is. Checking the venue first made the
        # subject's own 10-K and a customer's 10-K the same lineage, so a
        # dossier could not tell a founder which one it had.
        #
        # The independent count does NOT move here: both lineages are already
        # INDEPENDENCE_BEARING. What moves is what the founder is told (§47).
        # The gate is the vantage class, so the subject's own filing — always
        # company-published — can never reach this branch.
        if source_class in _INDEPENDENT_VANTAGE:
            return INDEPENDENT_EXTERNAL_SOURCE
        return REGULATOR_OR_PRIMARY_FILING
    if not source_class:
        # No vantage recorded is not "company owned by default". A missing
        # input is reported as missing; guessing here is how an unknown
        # becomes corroboration two layers up.
        return UNKNOWN_LINEAGE
    if source_class in _INDEPENDENT_VANTAGE:
        return INDEPENDENT_EXTERNAL_SOURCE
    return COMPANY_SELF_REPORT


def classify(documents: Sequence[dict]) -> List[dict]:
    """Label every row with its lineage, in retrieval order.

    The FIRST row to establish an origin anchors it; later rows from that
    origin are SAME_ORIGIN. That makes the result depend on order, which is
    deliberate and is the production order — but it means a caller must not
    shuffle rows between two runs and compare the labels.
    """
    seen_hashes: Dict[str, int] = {}
    anchored_origins: Dict[str, int] = {}
    shingles: List[frozenset] = []
    out: List[dict] = []

    for index, document in enumerate(documents):
        url = document.get("final_url") or document.get("original_url") or ""
        family = origin_family(url)
        content_hash = str(document.get("content_hash") or "").strip()
        text = str(document.get("text_content") or "")
        mine = _shingles(text)
        shingles.append(mine)

        lineage, anchor = None, None

        if content_hash and content_hash in seen_hashes:
            lineage, anchor = SAME_DOCUMENT, seen_hashes[content_hash]
        elif family and family in anchored_origins:
            lineage, anchor = SAME_ORIGIN, anchored_origins[family]
        else:
            # Different origin, same words: a republication. Compared against
            # every earlier row rather than only the anchors, because the
            # thing being detected is a shared TEXT, not a shared origin.
            for earlier in range(index):
                if not shingles[earlier] or not mine:
                    continue
                other_url = (documents[earlier].get("final_url")
                             or documents[earlier].get("original_url") or "")
                if origin_family(other_url) == family:
                    continue
                if _jaccard(mine, shingles[earlier]) >= _REPUBLICATION_JACCARD:
                    lineage, anchor = DERIVED_REPUBLICATION, earlier
                    break

        if lineage is None:
            lineage = _vantage(document)
            if family:
                anchored_origins[family] = index
        if content_hash and content_hash not in seen_hashes:
            seen_hashes[content_hash] = index

        out.append({
            "index": index,
            "source_id": document.get("source_id", ""),
            "url": url,
            "origin_family": family,
            "source_class": document.get("source_class") or "",
            "lineage": lineage,
            "anchor_index": anchor,
            "independence_bearing": lineage in INDEPENDENCE_BEARING,
        })
    return out


#: Lineages that ESTABLISH something not already in the set. The complement —
#: SAME_DOCUMENT, SAME_ORIGIN, DERIVED_REPUBLICATION — are all ways of saying
#: "this row is another copy of an observation already counted".
_NEW_OBSERVATION = frozenset({COMPANY_SELF_REPORT,
                              REGULATOR_OR_PRIMARY_FILING,
                              INDEPENDENT_EXTERNAL_SOURCE, UNKNOWN_LINEAGE})


def _corroboration(independent: int, distinct: int, rows: int,
                   unknown: int) -> tuple:
    """The state, and the sentence that establishes it.

    Note what is NOT here: no numeric confidence is produced from these
    counts. Two independent sources is a fact about the evidence; how much to
    believe the claim is a judgement that belongs to a layer that can see the
    claim, and manufacturing a number here would launder a row count into an
    authority it has not earned.
    """
    if rows == 0:
        return LINEAGE_UNAVAILABLE, "no evidence rows to assess"
    if unknown == rows:
        return (LINEAGE_UNAVAILABLE,
                f"all {rows} row(s) carry no lineage signal, so independence "
                f"could not be established either way")
    if independent >= MIN_INDEPENDENT_FOR_CORROBORATION:
        return (INDEPENDENTLY_CORROBORATED,
                f"{independent} independent origins among {distinct} "
                f"distinct observation(s)")
    if independent == 1:
        return (PARTIALLY_INDEPENDENT,
                "exactly one outside vantage point; a second independent "
                "origin is what would corroborate it")
    if distinct > 1:
        return (SAME_ORIGIN_MULTIPLE_DOCUMENTS,
                f"{rows} document(s) reduce to {distinct} observation(s), "
                f"none of them an outside vantage point")
    return (SINGLE_SOURCE,
            f"{rows} document(s) trace back to one observation, which is "
            f"not an outside vantage point")


def assess(documents: Sequence[dict], *,
           contradicting_ids: Sequence[str] = ()) -> dict:
    """Independence for one company's evidence set.

    `contradicting_ids` is passed THROUGH, never resolved here: whether two
    observations conflict is a question about their claims, which this module
    cannot see. It is surfaced so that a contradiction stays visible next to
    the corroboration state instead of being averaged into it — an
    independently corroborated claim that is also contradicted is not the
    same as an uncontested one, and a single state cannot say both.
    """
    rows = classify(documents)
    lineage_counts = Counter(row["lineage"] for row in rows)
    families = sorted({row["origin_family"] for row in rows
                       if row["origin_family"]})
    independent_rows = [row for row in rows if row["independence_bearing"]]
    # One per ORIGIN: two independence-bearing rows from the same publisher
    # are one vantage point seen twice. `classify` already labels the second
    # SAME_ORIGIN, so this is belt-and-braces against a future caller that
    # reorders rows.
    independent_origins = sorted({row["origin_family"]
                                  for row in independent_rows
                                  if row["origin_family"]})
    # Rows with no URL cannot be grouped by origin, so they collapse into ONE
    # bucket rather than counting individually. Ten pasted documents of
    # unknown provenance are not ten vantage points, and counting them that
    # way is precisely the inflation this module exists to refuse.
    independent_count = len(independent_origins) + (
        1 if any(not row["origin_family"] for row in independent_rows) else 0)

    family_sizes = Counter(row["origin_family"] for row in rows
                           if row["origin_family"])
    concentration = (round(max(family_sizes.values()) / len(rows), 4)
                     if family_sizes and rows else None)

    distinct_observations = sum(1 for row in rows
                                if row["lineage"] in _NEW_OBSERVATION)
    state, reason = _corroboration(
        independent_count, distinct_observations, len(rows),
        lineage_counts.get(UNKNOWN_LINEAGE, 0))

    return {
        "contract": CONTRACT,
        # The producer RAN. A caller that omits this module entirely must
        # report UNAVAILABLE instead — "0 independent" and "never measured"
        # are different facts and this field is what separates them.
        "state": "MEASURED",
        "evidence_count": len(rows),
        "independent_evidence_count": independent_count,
        "source_family_count": len(families),
        "primary_source_count": lineage_counts.get(
            REGULATOR_OR_PRIMARY_FILING, 0),
        "company_self_report_count": lineage_counts.get(
            COMPANY_SELF_REPORT, 0),
        "independent_external_count": lineage_counts.get(
            INDEPENDENT_EXTERNAL_SOURCE, 0),
        "unknown_lineage_count": lineage_counts.get(UNKNOWN_LINEAGE, 0),
        "duplicate_document_count": lineage_counts.get(SAME_DOCUMENT, 0),
        "same_origin_count": lineage_counts.get(SAME_ORIGIN, 0),
        "republication_count": lineage_counts.get(DERIVED_REPUBLICATION, 0),
        # None, never 0.0: a ratio over an empty set is UNMEASURABLE, and a
        # zero here would read as "perfectly unconcentrated".
        "concentration_ratio": concentration,
        "distinct_observation_count": distinct_observations,
        "corroboration_state": state,
        "corroboration_reason": reason,
        "independent_origins": independent_origins,
        "source_families": families,
        "contradicting_evidence_ids": list(contradicting_ids),
        "lineage_counts": dict(sorted(lineage_counts.items())),
        "rows": rows,
    }
