"""T019 bars: the anti-hallucination wall. A model may never emit a
source, URL, citation, author, or date."""
from unittest.mock import MagicMock

import pytest

from intent_engine.research import ExtractionRejected, validate_candidate
from intent_engine.research.extraction import (
    EXTRACTION_TOOL_SCHEMA, FORBIDDEN_CANDIDATE_FIELDS, extract_candidates,
)

SOURCE_TEXT = ("Reply rate rose from 4% to 9% after the subject line was "
               "shortened. The authors note the sample was one quarter of "
               "outbound email. We recommend shortening subject lines.")
SOURCE = {"source_id": "S1"}


def _client(candidates):
    client = MagicMock()
    client.call_tool.return_value = {"candidates": candidates}
    return client


def test_schema_has_no_field_for_provenance():
    """Structural, not instructional: the model cannot emit a URL because
    there is nowhere to put one."""
    props = EXTRACTION_TOOL_SCHEMA["properties"]["candidates"]["items"]["properties"]
    for banned in ("url", "source", "citation", "author", "date", "doi"):
        assert banned not in props
    assert set(props) == {"claim_text", "evidence_class", "quote_span"}


def test_locatable_claim_is_accepted():
    accepted = validate_candidate(
        {"claim_text": "Reply rate rose from 4% to 9%",
         "evidence_class": "observation",
         "quote_span": "Reply rate rose from 4% to 9%"},
        SOURCE_TEXT, SOURCE)
    assert accepted["source_id"] == "S1"
    assert accepted["extraction_method"] == "model_assisted"


def test_model_emitted_provenance_fields_are_rejected():
    for field in sorted(FORBIDDEN_CANDIDATE_FIELDS):
        with pytest.raises(ExtractionRejected, match="forbidden provenance"):
            validate_candidate(
                {"claim_text": "Reply rate rose from 4% to 9%",
                 "evidence_class": "observation", field: "invented"},
                SOURCE_TEXT, SOURCE)


def test_url_or_doi_inside_claim_text_is_rejected():
    for invented in ("see https://fake.example/study",
                     "per doi.org/10.1234/nope", "www.madeup.org says"):
        with pytest.raises(ExtractionRejected, match="URL or DOI"):
            validate_candidate({"claim_text": f"Reply rate rose. {invented}",
                                "evidence_class": "observation"},
                               SOURCE_TEXT + invented, SOURCE)


def test_unlocatable_claim_is_rejected():
    with pytest.raises(ExtractionRejected, match="not locatable"):
        validate_candidate({"claim_text": "Reply rate tripled in every market",
                            "evidence_class": "observation"},
                           SOURCE_TEXT, SOURCE)


def test_overclaiming_language_is_rejected():
    with pytest.raises(ExtractionRejected, match="overclaims"):
        validate_candidate(
            {"claim_text": "This proves shorter subject lines always work",
             "evidence_class": "mechanism"}, SOURCE_TEXT, SOURCE)


def test_unknown_class_and_empty_claim_rejected():
    with pytest.raises(ExtractionRejected, match="unknown evidence_class"):
        validate_candidate({"claim_text": "Reply rate rose from 4% to 9%",
                            "evidence_class": "vibes"}, SOURCE_TEXT, SOURCE)
    with pytest.raises(ExtractionRejected, match="empty claim"):
        validate_candidate({"claim_text": "  ", "evidence_class": "observation"},
                           SOURCE_TEXT, SOURCE)


def test_hallucination_attempt_yields_zero_accepted_and_a_safe_echo():
    """Scenario B: invented URL + fabricated author + unregistered citation."""
    client = _client([
        {"claim_text": "Reply rate rose from 4% to 9%",
         "evidence_class": "observation",
         "url": "https://fabricated.example/paper",
         "author": "Dr. Nobody", "citation": "Nobody et al. 2025"},
        {"claim_text": "A totally invented finding about every market",
         "evidence_class": "observation"},
    ])
    result = extract_candidates(client, SOURCE, SOURCE_TEXT,
                                model_version="fake.v0")
    assert result["accepted"] == []
    assert len(result["rejected"]) == 2
    echoed = str(result["rejected"])
    for leak in ("fabricated.example", "Dr. Nobody", "Nobody et al"):
        assert leak not in echoed          # not even inside a rejection row


def test_provenance_versions_are_recorded():
    client = _client([{"claim_text": "Reply rate rose from 4% to 9%",
                       "evidence_class": "observation"}])
    result = extract_candidates(client, SOURCE, SOURCE_TEXT,
                                model_version="fake.v0")
    assert result["provenance"]["model_version"] == "fake.v0"
    assert result["provenance"]["prompt_version"] == "research_extraction.v1"


def test_bounded_candidate_count():
    many = [{"claim_text": "Reply rate rose from 4% to 9%",
             "evidence_class": "observation"} for _ in range(50)]
    result = extract_candidates(_client(many), SOURCE, SOURCE_TEXT,
                                model_version="fake.v0")
    assert result["usage"]["accepted"] <= 12


def test_malformed_model_output_raises_rather_than_reading_as_no_evidence():
    client = MagicMock()
    client.call_tool.return_value = {"candidates": "not a list"}
    with pytest.raises(ExtractionRejected, match="malformed"):
        extract_candidates(client, SOURCE, SOURCE_TEXT, model_version="v0")


def test_empty_candidate_list_is_a_valid_answer():
    result = extract_candidates(_client([]), SOURCE, SOURCE_TEXT,
                                model_version="fake.v0")
    assert result["accepted"] == [] and result["rejected"] == []
    assert result["usage"]["candidates_returned"] == 0
