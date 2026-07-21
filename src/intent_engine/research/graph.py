"""Evidence graph, contradiction detection, stances, and ranking (T019).

The graph is the product. A founder should scan four buckets, not read
prose. Two rules distinguish this from a summarizer:

  * corroboration counts INDEPENDENT sources — three outlets quoting one
    wire report is one, not three;
  * MIXED never collapses to the majority, and a MIXED stance must carry
    a reason (different populations / dates / methodology / definitions),
    because a bare "MIXED" is not an answer.
"""
from __future__ import annotations

from intent_engine.research.records import (
    CONFLICT_REASONS, NON_SUPPORTING_CLASSES, QUALITY_HIGH, QUALITY_LOW,
    QUALITY_MEDIUM, QUALITY_UNKNOWN, STANCE_CONTRADICTED, STANCE_INSUFFICIENT,
    STANCE_MIXED, STANCE_NOT_INVESTIGATED, STANCE_SUPPORTED, STANCE_UNKNOWN,
    ResearchError,
)
from intent_engine.research.sources import count_independent

STANCE_VERSION = "stance.v1"
RANK_VERSION = "evidence_rank.v1"

_QUALITY_ORDER = {QUALITY_HIGH: 3, QUALITY_MEDIUM: 2, QUALITY_LOW: 1,
                  QUALITY_UNKNOWN: 0}


def rank_evidence(index, evidence_items: list) -> list:
    """Deterministic, versioned ranking by RECORDED properties only.

    Never by model preference. Quality outranks recency (anti-recency
    bias); recency breaks ties inside a quality band.
    """
    ranked = []
    for item in evidence_items:
        source = index.sources.get(item["source_id"], {})
        corroboration = _corroboration(index, item.get("claim_key"))
        inputs = {
            "source_quality": source.get("source_quality", QUALITY_UNKNOWN),
            "directness": ("primary" if not source.get("derived_from_source")
                           else "reporting_on_primary"),
            "independent_corroboration": corroboration["independent_count"],
            "freshness": source.get("freshness", {}).get("freshness"),
            "has_methodology": bool(source.get("methodology")),
            "published_date": source.get("published_date"),
        }
        score = (
            _QUALITY_ORDER.get(inputs["source_quality"], 0) * 1000
            + (200 if inputs["directness"] == "primary" else 0)
            + min(inputs["independent_corroboration"], 5) * 20
            + (10 if inputs["has_methodology"] else 0)
            + (5 if inputs["freshness"] == "FRESH" else 0))
        ranked.append({**item, "rank_version": RANK_VERSION,
                       "rank_score": score, "rank_inputs": inputs})
    return sorted(ranked, key=lambda e: (-e["rank_score"], e["evidence_id"]))


def _corroboration(index, claim_key) -> dict:
    """Independent-source count for one claim's SUPPORTING evidence."""
    supporting = [e for e in index.evidence_for_claim(claim_key)
                  if e.get("stance") == "supports"
                  and e["evidence_id"] not in index.retired_evidence
                  and e["source_id"] not in index.retired_sources]
    return count_independent([index.sources.get(e["source_id"], {})
                              for e in supporting])


def stance_for_claim(index, claim_key: str, *, requirements: dict,
                     investigated: bool = True) -> dict:
    """One of six stances, computed from the PLAN's requirements.

    NOT INVESTIGATED is distinct from UNKNOWN: the first means nobody
    looked, the second means somebody looked and found nothing.
    """
    if not investigated:
        return {"stance": STANCE_NOT_INVESTIGATED, "stance_version": STANCE_VERSION,
                "reasons": ["this question was not searched — absence of "
                            "evidence has not been established"],
                "supporting": [], "contradicting": [],
                "independent_support": 0}

    minimum = requirements.get("minimum_sources", 2)
    floor = requirements.get("minimum_quality", QUALITY_LOW)
    floor_rank = _QUALITY_ORDER.get(floor, 1)

    items = [e for e in index.evidence_for_claim(claim_key)
             if e["evidence_id"] not in index.retired_evidence
             and e["source_id"] not in index.retired_sources
             and e.get("evidence_class") not in NON_SUPPORTING_CLASSES]

    supporting = [e for e in items if e.get("stance") == "supports"]
    contradicting = [e for e in items if e.get("stance") == "contradicts"]
    qualifying = [e for e in items if e.get("stance") == "qualifies"]

    def _meets_floor(evidence_list):
        return [e for e in evidence_list
                if _QUALITY_ORDER.get(
                    index.sources.get(e["source_id"], {}).get(
                        "source_quality", QUALITY_UNKNOWN), 0) >= floor_rank]

    sup_ok, con_ok = _meets_floor(supporting), _meets_floor(contradicting)
    independent_support = count_independent(
        [index.sources.get(e["source_id"], {}) for e in sup_ok])
    independent_contra = count_independent(
        [index.sources.get(e["source_id"], {}) for e in con_ok])

    # Evidence below the declared quality floor does not DRIVE the stance,
    # but it is never invisible: dropping a source because it disagrees is
    # exactly the failure this subsystem exists to prevent.
    below_floor_contra = [e["evidence_id"] for e in contradicting
                          if e not in con_ok]
    below_floor_support = [e["evidence_id"] for e in supporting
                           if e not in sup_ok]

    base = {"stance_version": STANCE_VERSION,
            "supporting": [e["evidence_id"] for e in supporting],
            "contradicting": [e["evidence_id"] for e in contradicting],
            "qualifying": [e["evidence_id"] for e in qualifying],
            "below_floor_contradicting": below_floor_contra,
            "below_floor_supporting": below_floor_support,
            "independent_support": independent_support["independent_count"],
            "independent_contradiction": independent_contra["independent_count"],
            "collapsed_by_independence": independent_support["collapsed"],
            "minimum_sources": minimum, "minimum_quality": floor}
    if below_floor_contra:
        base["below_floor_note"] = (
            f"{len(below_floor_contra)} contradicting item(s) fall below the "
            f"{floor} quality floor and do not drive the stance — they are "
            "listed here rather than discarded")

    if not items:
        return {**base, "stance": STANCE_UNKNOWN,
                "reasons": ["sources were searched; none addresses this claim"]}

    if sup_ok and con_ok:
        reason = _conflict_reason(index, sup_ok, con_ok)
        return {**base, "stance": STANCE_MIXED, "conflict_reason": reason,
                "reasons": [
                    "both supporting and contradicting evidence meet the "
                    "quality floor; the majority does NOT decide this",
                    f"conflict attributed to: {reason}"]}

    if con_ok and independent_contra["independent_count"] >= minimum:
        return {**base, "stance": STANCE_CONTRADICTED,
                "reasons": [f"{independent_contra['independent_count']} "
                            "independent contradicting sources at or above "
                            "the quality floor, none supporting"]}

    if sup_ok and independent_support["independent_count"] >= minimum:
        return {**base, "stance": STANCE_SUPPORTED,
                "reasons": [f"{independent_support['independent_count']} "
                            "independent supporting sources at or above the "
                            "quality floor, none contradicting"]}

    return {**base, "stance": STANCE_INSUFFICIENT,
            "reasons": [
                f"fewer than {minimum} INDEPENDENT sources meet the "
                f"{floor} quality floor "
                f"(independent support: {independent_support['independent_count']}, "
                f"independent contradiction: {independent_contra['independent_count']})"]}


def _conflict_reason(index, supporting, contradicting) -> str:
    """Why MIXED exists — deterministic attribution from recorded fields.

    An ASYMMETRIC declaration counts as a difference: if one side scopes
    itself to small accounts and the other states no population at all,
    that is a population difference and saying so is more useful than
    'unknown'. Checked in order of explanatory power.
    """
    def _field(items, name):
        return {index.sources.get(e["source_id"], {}).get(name)
                for e in items} - {None}

    for name, reason in (("population", "different_populations"),
                         ("methodology", "different_methodology"),
                         ("definition", "different_definitions")):
        sup, con = _field(supporting, name), _field(contradicting, name)
        if (sup or con) and sup != con:
            return reason

    sup_dates, con_dates = (_field(supporting, "published_date"),
                            _field(contradicting, "published_date"))
    if sup_dates and con_dates and min(sup_dates)[:4] != min(con_dates)[:4]:
        return "different_dates"
    return "unknown"


def assert_conflict_reason(reason: str) -> None:
    if reason not in CONFLICT_REASONS:
        raise ResearchError(f"unknown conflict reason: {reason!r}")
