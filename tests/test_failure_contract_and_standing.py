"""Three defects the deployed preview showed a reader, and the rules now held.

Each was measured on `intent-engine-preview-v3`, not reasoned about:

  * `GET /runs/{id}` on an unapproved run answered "Bad request / approve at
    least one source" -- a framework status and an exception message;
  * `/story` and `/dashboard` carried a `<style>` block INSIDE `<main>`, so
    stylesheet text was part of `main.innerText`;
  * Constellation Software, a TSX-only issuer with no SEC filing in the run,
    was told "the company's filings carry this".
"""
from __future__ import annotations

import re

import pytest

from intent_engine.strategic_intelligence import evidence_classes as EC
from intent_engine.webapp import failures as F
from intent_engine.webapp.app import WebApp, _STYLE_BLOCK


@pytest.fixture
def app():
    return WebApp.__new__(WebApp)


def _body(response):
    return response[2]


def _main_text(html):
    match = re.search(r"<main\b[^>]*>(.*?)</main>", html, re.S | re.I)
    inner = match.group(1) if match else html
    return " ".join(re.sub(r"<[^>]+>", " ", inner).split())


# --- the failure contract -----------------------------------------------------

INTERNAL_MESSAGES = [
    "approve at least one source",
    "no approval recorded — nothing may be fetched",
    "cannot fetch unknown candidates: ['cand-1']",
    "no such run for this account",
    "run byte budget exhausted",
    "KeyError: 'thesis'",
    "IngestionError: unknown source_type 'x'",
]


@pytest.mark.parametrize("message", INTERNAL_MESSAGES)
def test_a_reader_never_sees_a_bare_status_and_an_exception(app, message):
    html = _body(app._error_page(400, message))
    text = _main_text(html)
    assert not text.startswith("Bad request")
    # The four things a reader is owed, on every failure page.
    for required in ("What did work", "What did not", "Why",
                     "What to do next"):
        assert required in text, f"{required!r} missing for {message!r}"


@pytest.mark.parametrize("message", [
    "approve at least one source",
    "no approval recorded — nothing may be fetched",
    "no such run for this account",
    "run byte budget exhausted",
])
def test_a_recognised_cause_never_leaks_its_internal_text(app, message):
    """When the cause was understood, our words replace the exception's."""
    assert message not in _body(app._error_page(400, message))


def test_an_unrecognised_cause_keeps_the_one_sentence_it_has(app):
    """The 500 handler puts the log reference here, and debug the traceback.

    Dropping an unrecognised message would trade a raw page for a silent one.
    """
    message = ("An internal error occurred and has been recorded "
               "(reference abc123def456). Quote this reference if you "
               "report it.")
    assert "abc123def456" in _body(app._error_page(500, message))


def test_the_awaiting_approval_state_is_not_the_readers_fault(app):
    text = _main_text(_body(app._error_page(400, "approve at least one "
                                                 "source")))
    assert "waiting for you" in text.lower()
    assert "Review the sources" in text


def test_every_category_explains_all_four_things():
    for category in F.CATEGORIES:
        explained = F.explain(category)
        assert explained["what_worked"], category
        assert explained["what_failed"], category
        assert explained["why"], category
        assert explained["next_step"], category
        assert isinstance(explained["retryable"], bool), category


def test_an_unmapped_category_falls_back_rather_than_raising():
    assert F.explain("NOT_A_CATEGORY")["category"] == F.INTERNAL_FAILURE


@pytest.mark.parametrize("message,expected", [
    ("approve at least one source", F.AWAITING_SOURCE_APPROVAL),
    ("no such share link (missing, revoked, or expired)",
     F.SHARE_LINK_UNAVAILABLE),
    ("no such run for this account", F.NOT_FOUND),
    ("no approved source could be retrieved", F.RETRIEVAL_INSUFFICIENT),
    ("the request timed out", F.ANALYSIS_TIMEOUT),
    ("something nobody mapped", F.INTERNAL_FAILURE),
])
def test_classification(message, expected):
    assert F.classify(message) == expected


# --- <style> is not content ---------------------------------------------------

def test_page_stylesheets_are_hoisted_out_of_the_body(app):
    body = ('<!doctype html><html><head><title>t</title></head><body><nav>n'
            '</nav><main><style>.dash{display:grid}</style><h1>Datadog</h1>'
            '<style>.act{color:#111}</style><p>The answer.</p></main>'
            '</body></html>')
    out = app._stylize(body)
    head, rest = out.split("</head>")
    assert _STYLE_BLOCK.findall(rest) == []
    assert ".dash{display:grid}" in head and ".act{color:#111}" in head
    assert "display:grid" not in _main_text(rest)
    assert "Datadog" in rest and "The answer." in rest


def test_hoisting_preserves_the_cascade(app):
    """A page's own rules must still come last, or they stop winning."""
    body = ('<!doctype html><html><head></head><body><main>'
            '<style>.page{color:red}</style></main></body></html>')
    head = app._stylize(body).split("</head>")[0]
    assert head.index("focus-visible") < head.index(".page{color:red}")


def test_a_page_without_a_head_is_left_alone(app):
    fragment = "<main><style>.a{color:red}</style></main>"
    assert app._stylize(fragment) == fragment


# --- limitation follows the source mixture ------------------------------------

def test_an_investor_relations_page_is_not_a_filing():
    """`discovery.py` gives `investor_material` to any /investor URL."""
    coverage = {"investor_material": 2, "company_owned": 4}
    limitation = EC.standing_limitation(coverage, has_filing=False)
    assert "filings" not in limitation
    assert "published by the company itself" in limitation


def test_a_real_filing_still_earns_the_accountable_limitation():
    coverage = {"investor_material": 1, "company_owned": 3}
    assert "filings" in EC.standing_limitation(coverage, has_filing=True)


def test_company_published_material_says_so():
    limitation = EC.standing_limitation({"company_owned": 3}, has_filing=False)
    assert "published by the company itself" in limitation
    assert "filings" not in limitation


def test_no_evidence_at_all_asks_for_what_is_missing():
    assert "rests only on the company's own website" in EC.standing_limitation(
        {}, has_filing=False)


def test_an_investor_page_alone_is_still_company_published():
    """Not a filing, but not nothing either -- it fell through to "none"."""
    limitation = EC.standing_limitation({"investor_material": 1},
                                        has_filing=False)
    assert "published by the company itself" in limitation


def test_independent_reporting_needs_no_standing_caveat():
    assert EC.standing_limitation({"independent_reporting": 1},
                                  has_filing=False) == ""


@pytest.mark.parametrize("url,expected", [
    ("https://www.sec.gov/Archives/edgar/data/1/ddog-20251231.htm", True),
    ("https://www.sedarplus.ca/csa-party/records/document.html?id=1", True),
    ("https://csisoftware.com/investors", False),
    ("https://example.com/ir/earnings", False),
    ("", False),
])
def test_only_a_regulators_archive_carries_accountability(url, expected):
    assert EC.is_regulatory_filing(url) is expected


def test_standing_falls_back_to_class_when_the_caller_cannot_tell():
    """Callers that cannot see URLs keep the previous behaviour."""
    assert EC.evidence_standing({"investor_material": 1}) == "accountable"
    assert EC.evidence_standing({"investor_material": 1},
                                has_filing=False) == "asserted"
