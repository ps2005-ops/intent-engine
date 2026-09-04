"""One truthful account of what each evidence family did, for every surface.

THE CONTRADICTION THIS ENDS. Measured on the deployed product: Caterpillar's
executive brief said, in one section,

    WHAT COULD ACTUALLY BE READ
    SEC 10-K (...)

and in the next,

    Filings and investor material — none

Both were computed correctly and from different denominators. The evidence
list counts DOCUMENTS RETRIEVED. `source_class_coverage` counts OBSERVATIONS
DERIVED, so a filing we read but could not extract a strategic observation
from vanished from the inventory while remaining in the bibliography. One page
of one analysis contradicted itself, and every surface built on top of that
state inherited the contradiction.

A COUNT CANNOT CARRY A REASON
-----------------------------
The deeper problem is that the family state was an integer. Zero had to stand
for all of:

    we never looked for this
    we looked and the door was shut
    we read a document and it said nothing usable
    this family cannot apply to this company

Those call for four different responses from a reader, and a bare `0` --
rendered as "— none" -- flattened them into a single shrug. Independence and
discovery coverage have both already been through this exact repair; this is
the same fix one level up, on the inventory itself.

WHAT THIS MODULE IS NOT
-----------------------
It does not retrieve, rank, judge relevance or decide independence. It reads
what a run already recorded -- documents, observations, failures -- and states
what happened to each family. It is the single object the brief, the X-Ray,
the deck and the Q&A all read, so they cannot disagree about the same run.
"""
from __future__ import annotations

from typing import Dict, Sequence

CONTRACT = "source_class_coverage.v2"

# --- the typed states ----------------------------------------------------------
#: Documents were read AND at least one observation came out of them.
PRESENT = "PRESENT"
#: Documents were read and nothing usable came out. The family was reached and
#: had nothing to say -- a fact about the material, not about our access.
RETRIEVED_NO_SIGNAL = "RETRIEVED_NO_SIGNAL"
#: We tried and were refused: 403, a redirect off the approved host, a page
#: that only renders to a full browser. A fact about our access.
BLOCKED = "BLOCKED"
#: We looked and there was nothing to fetch.
ATTEMPTED_NONE = "ATTEMPTED_NONE"
#: No candidate of this family was ever proposed, so nothing was attempted.
NOT_ATTEMPTED = "NOT_ATTEMPTED"

COVERAGE_STATES = (PRESENT, RETRIEVED_NO_SIGNAL, BLOCKED, ATTEMPTED_NONE,
                   NOT_ATTEMPTED)

#: The only state that may be read as "this family supports the analysis".
SUPPORTS_ANALYSIS = frozenset({PRESENT})

#: States where the absence is about US, not about the company. A surface may
#: never turn one of these into "the company has published nothing".
ABSENCE_IS_OURS = frozenset({BLOCKED, NOT_ATTEMPTED})

#: Failure types that mean the door was shut rather than the page was slow.
_ACCESS_DENIED = ("http_status", "blocked", "unsafe_redirect",
                  "javascript_only")

#: Families whose absence a blocked FIRST-PARTY fetch can explain. A
#: competitor's filing is not missing because the subject's website said no.
FIRST_PARTY = frozenset({"company_owned", "executive_statement"})

FAMILIES = ("company_owned", "executive_statement", "investor_material",
            "customer_voice", "competitor", "independent_reporting")


def _count_by_class(rows: Sequence[dict], key: str = "source_class") -> dict:
    counts = {}
    for row in rows or ():
        name = str((row or {}).get(key) or "").strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def assess(*, documents: Sequence[dict] = (), observations: Sequence[dict] = (),
           failures: Dict[str, int] = None,
           proposed: Sequence[dict] = ()) -> Dict[str, dict]:
    """What each family actually did on this run.

    `documents` are what we retrieved, `observations` what the reasoning layer
    derived from them, `proposed` what discovery put forward, and `failures`
    the run's failure counts by type. The difference between documents and
    observations is the whole point: it is the gap the old integer hid.
    """
    failures = failures if isinstance(failures, dict) else {}
    denied = sum(int(failures.get(k) or 0) for k in _ACCESS_DENIED)

    docs = _count_by_class(documents)
    obs = _count_by_class(observations)
    offered = _count_by_class(proposed)

    out = {}
    for family in FAMILIES:
        n_docs, n_obs = docs.get(family, 0), obs.get(family, 0)
        if n_obs:
            state, reason = PRESENT, ""
        elif n_docs:
            # THE CASE THAT PRODUCED THE CONTRADICTION. We hold the document
            # and it is in the bibliography; it simply yielded no observation.
            # Saying "none" here is what made one page disagree with itself.
            state = RETRIEVED_NO_SIGNAL
            reason = (f"{n_docs} document(s) of this kind were read, but "
                      f"nothing in them could be turned into a usable "
                      f"observation.")
        elif denied and family in FIRST_PARTY:
            state = BLOCKED
            reason = ("The company's own addresses refused automated access, "
                      "so this material may exist and be unreadable to us.")
        elif offered.get(family):
            state = ATTEMPTED_NONE
            reason = "Candidates were proposed and none could be retrieved."
        else:
            state = NOT_ATTEMPTED
            reason = "No source of this kind was found to try."
        out[family] = {"state": state, "documents": n_docs,
                       "observations": n_obs, "reason": reason,
                       "supports_analysis": state in SUPPORTS_ANALYSIS,
                       "absence_is_ours": state in ABSENCE_IS_OURS}
    return {"contract": CONTRACT, "families": out}


def legacy_counts(assessment: Dict[str, object]) -> dict:
    """The old integer map, for consumers not yet migrated.

    Counts OBSERVATIONS, exactly as before, so nothing that reads this changes
    behaviour. New consumers should read the typed state instead: this shape
    is what could not express why a family was empty.
    """
    families = (assessment or {}).get("families") or {}
    return {name: int(row.get("observations") or 0)
            for name, row in families.items() if row.get("observations")}


def contradicts(assessment: Dict[str, object]) -> list:
    """Families the bibliography would show but the inventory would not.

    The guard against this defect returning: any family holding documents
    while reporting no state that acknowledges them.
    """
    families = (assessment or {}).get("families") or {}
    return [name for name, row in families.items()
            if int(row.get("documents") or 0) > 0
            and row.get("state") in (NOT_ATTEMPTED, ATTEMPTED_NONE)]
