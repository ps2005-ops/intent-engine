"""Federal contract awards — where both parties are typed fields, not prose.

WHY THIS FAMILY IS FIRST AMONG THE STRUCTURED ONES
--------------------------------------------------
Everything this engine has tried so far extracts a counterparty by parsing a
sentence, and every failure it has had in that area came from a regex that
matched the wrong clause: boilerplate mistaken for a competitor list, a
sentence's subject mistaken for its object, a category noun mistaken for a
company. An award record has no clause to mis-parse. `Recipient Name` and
`Awarding Agency` are separate typed fields written by the payer.

So the fabrication risk here is not "did we read the sentence correctly" but
"is this recipient actually the company we think it is", and that is a
resolver question with a testable answer.

THE KEYWORD TRAP
----------------
USASpending's search is a keyword search, and a keyword search for "Shopify"
returns awards to anybody whose description mentions Shopify. Every row is
therefore re-checked against the subject's aliases with whole-token matching
before it can become a relationship. A row that does not resolve is COUNTED,
not silently dropped — the ratio of retrieved to resolved is the number that
says whether this source is worth its request budget.

AN AWARD IS AN EVENT, NOT A DEPENDENCE
--------------------------------------
The award proves a transaction between two named parties over a stated
period. It does not prove the buyer is material to the seller, that the
relationship renews, or that either depends on the other. So:

    admitted:  COMPANY --SELLS_TO--> AGENCY,  bounded by the award's own
               period of performance
    refused:   DEPENDS_ON in either direction, however large the amount

Amount is carried as provenance so a later module can ask about materiality
against revenue. It is never itself the basis for a stronger predicate.

DIRECTION
---------
One relationship, not two. `SELLS_TO` from the company to the agency is the
canonical direction; a symmetric `BUYS_FROM` row would double every count in
the graph while adding nothing a reader could not derive.
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actor_relationships as AR
from . import counterparty_sources as CS

CONTRACT = "gov_award.v1"

ENDPOINT = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

#: Contracts and contract IDVs. Grants and loans are excluded: a grant
#: recipient is not selling anything, and calling it SELLS_TO would be the
#: same category error as calling a co-mention a partnership.
CONTRACT_AWARD_TYPES = ("A", "B", "C", "D")

#: How far back an award still says something about a current relationship.
#: Two years, matching the shortest belief cadence doubled — an award from
#: 2011 is history, not a live counterparty.
LOOKBACK_DAYS = 730

_FIELDS = ["Award ID", "Recipient Name", "Awarding Agency",
           "Awarding Sub Agency", "Award Amount", "Start Date", "End Date",
           "Description"]


def _post(url: str, payload: dict, *, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "IntentEngine research (ps2005@my.yorku.ca)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch(subject: str, aliases: Sequence[str], as_of: str = "", *,
          transport: Optional[Callable[[str, dict], dict]] = None,
          limit: int = 25) -> Tuple[CS.Document, ...]:
    """Retrieve recent contract awards whose recipient may be this company.

    `transport` is injected so the whole family is testable without a
    network, and so a rate limit isolates here rather than in the measurement
    harness that is meant to be reporting on it.
    """
    end = (as_of or _dt.date.today().isoformat())[:10]
    try:
        start = (_dt.date.fromisoformat(end)
                 - _dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    except ValueError:
        return ()
    keyword = _search_term(subject, aliases)
    if not keyword:
        return ()
    payload = {
        "filters": {
            "keywords": [keyword],
            "award_type_codes": list(CONTRACT_AWARD_TYPES),
            "time_period": [{"start_date": start, "end_date": end}],
        },
        "fields": list(_FIELDS), "page": 1, "limit": limit,
        "sort": "Award Amount", "order": "desc",
    }
    send = transport or (lambda url, body: _post(url, body))
    data = send(ENDPOINT, payload)

    out: List[CS.Document] = []
    for row in (data.get("results") or []):
        award_id = str(row.get("Award ID") or "")
        recipient = str(row.get("Recipient Name") or "")
        agency = str(row.get("Awarding Agency") or "")
        sub = str(row.get("Awarding Sub Agency") or "")
        out.append(CS.Document(
            document_id=f"usaspending:{award_id}",
            family=CS.GOVERNMENT_AWARD, subject=subject,
            title=f"{recipient} — {agency} award {award_id}",
            text=str(row.get("Description") or ""),
            url=f"https://www.usaspending.gov/award/{award_id}",
            published_at=str(row.get("Start Date") or "")[:10],
            fields={"recipient": recipient, "agency": agency,
                    "sub_agency": sub,
                    "amount": str(row.get("Award Amount") or ""),
                    "start_date": str(row.get("Start Date") or "")[:10],
                    "end_date": str(row.get("End Date") or "")[:10]}))
    return tuple(out)


def _search_term(subject: str, aliases: Sequence[str]) -> str:
    """The longest alias, because a short one returns the whole index."""
    candidates = [a for a in aliases if len(a) >= 4] or [subject]
    return max(candidates, key=len).strip()


def extract(document: CS.Document, subject: str, aliases: Sequence[str]
            ) -> Tuple[Tuple[AR.ActorRelationship, ...],
                       Dict[str, int], Dict[str, int]]:
    """Turn one award row into at most one relationship, or refuse it.

    The refusals are the useful half. `recipient_is_not_the_subject` counts
    the keyword search's false positives, and if that number dominates then
    the family's problem is the query rather than the source.
    """
    refused: Dict[str, int] = {}
    counts: Dict[str, int] = {}

    def refuse(reason: str):
        refused[reason] = refused.get(reason, 0) + 1
        return (), refused, counts

    recipient = document.fields.get("recipient", "")
    agency = document.fields.get("agency", "")
    sub_agency = document.fields.get("sub_agency", "")
    if not recipient or not agency:
        return refuse("award_missing_a_party")
    # Both ends are named in typed fields, so every retained row is a
    # candidate before any resolver runs. Counting here rather than after
    # resolution is what makes the retrieved-to-resolved ratio meaningful.
    counts["named_actor_mentions"] = 2
    counts["relationship_candidates"] = 1
    matched = CS.resolution(recipient, list(aliases) + [subject])
    if not matched:
        return refuse("recipient_is_not_the_subject")
    counts["identity_resolved"] = 1
    if matched == CS.SUBSIDIARY_OR_DIVISION:
        counts["identity_resolved_via_subsidiary"] = 1
    # The buying party is the sub-agency where one is named: "Defense
    # Logistics Agency" is who actually buys, and "Department of Defense" is
    # a department of government. Both are named actors; the specific one is
    # the counterparty a strategic reader cares about.
    buyer = sub_agency or agency
    if not AR.is_named_actor(buyer):
        return refuse("buyer_names_no_actor")

    span = (f"{recipient} received award {document.document_id.split(':')[-1]} "
            f"from {buyer}"
            + (f" ({agency})" if sub_agency and sub_agency != agency else "")
            + (f" for {document.text[:120]}" if document.text else ""))
    try:
        row = AR.relationship(
            subject_actor=recipient, predicate=AR.SELLS_TO,
            object_actor=buyer,
            evidence_ids=(document.document_id,),
            source_document=document.url,
            subject_span=recipient, object_span=buyer,
            relationship_span=span,
            object_kind=AR.GOVERNMENT,
            # The payer wrote this down in a typed field. Nobody inferred it.
            epistemic_status=AR.OBSERVED,
            valid_from=document.fields.get("start_date", ""),
            created_at=document.published_at)
    except AR.RelationshipRejected as exc:
        return refuse(f"contract:{type(exc).__name__}")

    # An award ends. The relationship is bounded by the contract's own period,
    # so a graph read in 2030 does not claim a 2025 contract is current.
    end = document.fields.get("end_date", "")
    if end:
        row = AR.ActorRelationship(**{**row.__dict__, "valid_to": end})
    return (row,), refused, counts


def durability_note(document: CS.Document) -> str:
    """What the award does NOT establish, said once, in the record itself."""
    return ("a contract award establishes a transaction between two named "
            "parties over a stated period; it does not establish dependence, "
            "materiality, renewal, or that either party will still be a "
            "counterparty after "
            + (document.fields.get("end_date") or "the period ends"))
