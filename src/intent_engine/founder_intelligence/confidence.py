"""Executive Confidence (T023.5) — preserves uncertainty, never a master score.

Presents the confidence/freshness/availability the agents already supplied,
grouped into what the product is most confident about, partially confident
about, where sources disagree, what it cannot yet determine, and the oldest
important evidence. It never reduces this multidimensional picture to a
single misleading number, and there is no company master score anywhere.
"""
from __future__ import annotations

from intent_engine.founder_intelligence.records import (
    AVAIL_CONFLICTED, AVAIL_PARTIAL, AVAIL_STALE, AVAIL_SUPPORTED,
    AVAIL_UNAVAILABLE, FRESH_HISTORICAL, FRESH_STALE, InsightCard,
    IntelligenceSection, SECTION_CONFIDENCE,
)

CONFIDENCE_VERSION = "fi_confidence.v1"


def assemble_confidence(all_claims) -> IntelligenceSection:
    most = [c for c in all_claims if c.availability == AVAIL_SUPPORTED
            and c.confidence in ("High",)]
    partial = [c for c in all_claims if c.availability == AVAIL_PARTIAL
               or c.confidence in ("Moderate", "Low")]
    disagree = [c for c in all_claims if c.availability == AVAIL_CONFLICTED]
    cannot = [c for c in all_claims if c.availability == AVAIL_UNAVAILABLE]
    stale = [c for c in all_claims
             if c.freshness_status in (FRESH_STALE, FRESH_HISTORICAL)]

    def _card(cid, headline, claims, availability):
        # Only cite claims that actually carry a source ref; a summary of
        # what is UNAVAILABLE cites nothing and is itself UNAVAILABLE, so it
        # never masquerades as supported.
        cited = tuple(c for c in claims[:5] if c.source_refs)
        avail = availability if cited else AVAIL_UNAVAILABLE
        return InsightCard(
            insight_id=f"{SECTION_CONFIDENCE}.{cid}", kind=SECTION_CONFIDENCE,
            headline=headline, availability=avail, claims=cited)

    cards = [
        _card("most", f"Most confident about: {len(most)} supported area(s)",
              most, AVAIL_SUPPORTED),
        _card("partial", f"Partial confidence about: {len(partial)} area(s)",
              partial, AVAIL_PARTIAL),
        _card("disagree", f"Sources disagree about: {len(disagree)} area(s)",
              disagree, AVAIL_CONFLICTED),
        # "cannot determine" is about ABSENCE — no citation, UNAVAILABLE
        InsightCard(insight_id=f"{SECTION_CONFIDENCE}.cannot",
                    kind=SECTION_CONFIDENCE,
                    headline=f"Cannot yet determine: {len(cannot)} area(s)",
                    availability=AVAIL_UNAVAILABLE, claims=()),
    ]
    oldest_note = ""
    if stale:
        oldest = min(stale, key=lambda c: c.source_refs[0].observed_at or "z"
                     if c.source_refs else "z")
        if oldest.source_refs:
            oldest_note = ("oldest important evidence: "
                           f"{oldest.source_refs[0].observed_at}")
    section = IntelligenceSection(
        kind=SECTION_CONFIDENCE, title="Executive confidence",
        cards=tuple(cards), availability=AVAIL_SUPPORTED,
        limitations=((oldest_note,) if oldest_note else ()),
        note="uncertainty, staleness, disagreement, and unavailable metrics "
             "are preserved; there is no single company score")
    section.validate()
    return section
