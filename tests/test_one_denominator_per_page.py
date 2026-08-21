"""A page may not state two different counts of the same evidence.

MEASURED LIVE on 5d43053, Meta Platforms and Amazon, one run each:

    "7 page(s) read; 1 carried usable evidence."

directly above a list of seven, three of which are the subject's own SEC
filings. The list is read from the store at render time; the number was
computed inside `compose`. Both are labelled as facts about the same run and
they cannot both be true of the list shown.

THREE MECHANISMS WERE TESTED AGAINST THE SEVEN REAL DOCUMENTS AND ALL THREE
ARE FALSE -- `usable_documents` keeps 7 of 7, `is_english` is True for 7 of
7, and raw-HTML truncation swept from 16MB down to 200KB keeps 7 of 7 (the
real cap is 16MB, so nothing truncates). So this does not pretend to fix the
count. It fixes what the page is allowed to CLAIM about a list it can see,
and `readiness_inputs` records what the gate was looking at so the next wave
measures the gap instead of arguing about it.
"""
import io

import pytest

from company_fixture_pages import BASE as FIXTURE_SITE, transport as fixture_transport

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "f.jsonl",
                            ci_store_path=tmp_path / "c.jsonl"),
                  transport=fixture_transport, resolver=False)


def _session():
    return {"user_id": "u1", "csrf": "c", "anonymous": True}


def _page(app, run_id, *, source_count, documents):
    result = {"readiness": {"state": "READY_FOR_LIMITED_REPORT"},
              "readiness_explanation": {
                  "headline": "Some kinds of evidence are missing",
                  "found": ["investor or earnings material"],
                  "missing": ["official company description"],
                  "blockers": [], "source_count": source_count,
                  "can_retry": False}}
    app.ci.store.retrieved = lambda rid: documents
    _s, _h, body = app._insufficient_evidence_page(_session(), run_id, result)
    return body


def _docs(n):
    return [{"retrieval_status": "OK",
             "final_url": f"https://www.sec.gov/Archives/edgar/data/{i}/f.htm",
             "original_url": f"https://www.sec.gov/Archives/edgar/data/{i}/f.htm",
             "title": f"SEC 10-K ({i})",
             "text_content": f"Document {i}. " + ("real filing prose. " * 40)}
            for i in range(n)]


def test_the_page_does_not_claim_one_usable_over_a_list_of_seven(app):
    """THE LIVE DEFECT. The smaller, older number may not be presented as a
    statement about the seven documents printed underneath it."""
    body = _page(app, "run-a", source_count=1, documents=_docs(7))
    assert "7 page(s) read" in body
    assert "1 carried usable evidence" not in body, (
        "the page still attributes the compose-time count to this list")


def test_the_page_says_the_gate_saw_fewer(app):
    """It is not silence either. A reader who can see seven documents and a
    limited verdict is owed the reason the two do not match."""
    body = _page(app, "run-b", source_count=1, documents=_docs(7))
    assert "gate was applied to 1" in body


def test_a_genuine_smaller_usable_count_is_still_reported(app):
    """THE NEGATIVE CONTROL. When the gate saw MORE documents than survived
    -- pages read that carried nothing -- that is a true and useful sentence
    and it must survive this change."""
    body = _page(app, "run-c", source_count=9, documents=_docs(4))
    assert "4 page(s) read" in body
    assert "9 carried usable evidence" in body


def test_agreeing_counts_print_one_number(app):
    body = _page(app, "run-d", source_count=5, documents=_docs(5))
    assert "5 page(s) read." in body
    assert "carried usable evidence" not in body
    assert "gate was applied" not in body
