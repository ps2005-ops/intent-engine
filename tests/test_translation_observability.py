"""An operator must be able to see a 100% translation drop — without bodies.

The regression this locks: `report.py` stripped `rows`, which was the only
record of `evidence_translated` / `evidence_unclassifiable`, so a cycle that
translated nothing out of five hundred candidate sentences looked identical in
the report to a cycle that had nothing to translate.
"""
import json

import pytest

from intent_engine.market import evidence_translation as ET
from intent_engine.market import strategic_export as SE
from intent_engine.market import translation_report as TR

TOTAL_DROP_ROWS = [
    {"company": "palantir", "evidence": 6, "candidate_sentences": 128,
     "evidence_translated": 0, "evidence_unclassifiable": 128,
     "furniture_rejected": 376, "subject_mismatch": 0},
    {"company": "nvidia", "evidence": 3, "candidate_sentences": 1,
     "evidence_translated": 0, "evidence_unclassifiable": 1,
     "furniture_rejected": 2, "subject_mismatch": 0},
]
HEALTHY_ROWS = [
    {"company": "caterpillar", "evidence": 2, "candidate_sentences": 39,
     "evidence_translated": 6, "evidence_unclassifiable": 33,
     "furniture_rejected": 921, "subject_mismatch": 0},
]


def test_a_total_translation_drop_is_visible_in_the_report():
    payload = TR.summarise(TOTAL_DROP_ROWS)
    assert payload["translated_evidence"] == 0
    assert payload["candidate_sentences"] == 129
    assert payload["translation_rate"] == 0.0
    assert "NONE carried a commercial event" in payload["verdict"]
    assert "defect" in payload["verdict"]


def test_no_documents_is_a_different_verdict_from_no_events():
    """Three faults, three sentences. Stated, not left to be inferred."""
    empty = TR.summarise([{"company": "x", "evidence": 0,
                           "candidate_sentences": 0,
                           "evidence_translated": 0}])
    assert "upstream in retrieval" in empty["verdict"]

    furniture_only = TR.summarise([{"company": "x", "evidence": 4,
                                    "candidate_sentences": 0,
                                    "evidence_translated": 0}])
    assert "page furniture" in furniture_only["verdict"]

    working = TR.summarise(HEALTHY_ROWS)
    assert "carried a commercial event" in working["verdict"]
    assert working["translation_rate"] > 0


def test_the_report_never_carries_document_text():
    rows = list(HEALTHY_ROWS)
    rows[0] = dict(rows[0])
    rows[0]["summary"] = "x" * 4000        # a document body riding along
    payload = TR.summarise(rows)
    TR.assert_bounded(payload)             # must not raise
    assert "x" * 100 not in json.dumps(payload)


def test_unbounded_telemetry_fails_closed():
    with pytest.raises(TR.UnboundedTelemetry):
        TR.assert_bounded({"per_company": [{"company": "y" * 300}]})
    with pytest.raises(TR.UnboundedTelemetry):
        TR.assert_bounded({"per_company": [{"company": "a"}] * 500})


def test_per_company_rows_are_counts_only():
    payload = TR.summarise(HEALTHY_ROWS)
    for row in payload["per_company"]:
        for key, value in row.items():
            if key == "company":
                continue
            assert isinstance(value, int), f"{key} is not a count"


def test_stats_from_a_real_translation_reach_the_report():
    rows = [{"evidence_text":
             "Second-quarter 2026 sales and revenues increased 24% to "
             "$20.5 billion. Explore the store for apps and games today. "
             "A featured collection of the latest blog posts.",
             "source": "https://example.test/r", "kind": "filing",
             "published_at": "2026-08-01"}]
    items, _, stats = ET.translate_with_stats(
        rows, subject_company="caterpillar", as_of="2026-08-05")
    assert len(items) == 1
    payload = TR.summarise([], stats)
    assert payload["translated_evidence"] == 1
    assert payload["furniture_rejected"] >= 1
    assert payload["classification_by_type"] == {"EARNINGS_RESULT": 1}
    assert payload["rejection_reasons"]


def test_operator_telemetry_is_not_founder_facing():
    """None of this is allowlisted on the strategic export."""
    for field in ("translation", "candidate_sentences", "furniture_rejected",
                  "translation_rate", "rejection_reasons", "per_company"):
        assert field not in SE.ALLOWED, field


def test_markdown_block_is_short_and_states_the_verdict():
    lines = TR.render(TR.summarise(TOTAL_DROP_ROWS))
    assert lines[0] == "## EVIDENCE TRANSLATION"
    assert any("NONE carried a commercial event" in ln for ln in lines)
    assert len(lines) < 30
