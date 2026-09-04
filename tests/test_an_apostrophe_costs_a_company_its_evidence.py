"""One character between a company and every filing it has ever made.

MEASURED LIVE on dd1511f0, through the deployed product. A customer typed
"Lowe's Companies" with a website and submitted WITHOUT choosing a
suggestion -- the ordinary thing to do when you already know who you mean.

    documents            1
    roles_missing        ['direction', 'market']
    abstention           EXTERNAL_ACCESS_REFUSED
    strategic_report     None

Lowe's has a 10-K in EDGAR. It was never fetched, because `_tokens` split on
the apostrophe: {lowe, s, companies} against the SEC's own
"LOWES COMPANIES INC" -> {lowes, companies}. Full-token containment failed,
`resolve_cik` answered None, and with no CIK `propose_edgar_candidates`
returns no candidates at all. lowes.com then refused the fetch, so the run
reached composition with one document, `may_synthesize` was False, and the
business-model gate this session repaired never ran.

THE SURFACE ALREADY KNEW. Typing `lowe's` into the autocomplete returns
"Lowes Companies Inc" -- measured, 238ms. The repair had reached the
suggestion endpoint and not the server-side fallback, so it survived exactly
where nobody looks: the path a customer takes when they type past the
dropdown.
"""
from __future__ import annotations

import tempfile
import pathlib

from intent_engine.company_ingestion.edgar import _tokens, resolve_cik
from intent_engine.company_ingestion.service import CompanyIngestionService

#: How the SEC actually spells it in `company_tickers.json`. No apostrophe.
SEC_TITLE = "LOWES COMPANIES INC"
TICKERS = (b'{"0": {"cik_str": 60667, "ticker": "LOW", '
           b'"title": "LOWES COMPANIES INC"}, '
           b'"1": {"cik_str": 63908, "ticker": "MCD", '
           b'"title": "MCDONALDS CORP"}, '
           b'"2": {"cik_str": 1652044, "ticker": "GOOGL", '
           b'"title": "Alphabet Inc."}}')


def _tickers(url, timeout, max_bytes=None):
    if "company_tickers" in url:
        return (200, {"Content-Type": "application/json"}, TICKERS, False)
    return (404, {}, b"", False)


# --- the tokeniser --------------------------------------------------------

def test_every_apostrophe_form_a_keyboard_produces_is_normalised():
    """A straight quote, a curly one from a paste, and none at all must all
    give the same tokens -- otherwise which key the customer pressed decides
    whether their company has filings."""
    plain = _tokens("Lowes Companies")
    for typed in ("Lowe's Companies", "Lowe’s Companies",
                  "Loweʼs Companies", "Lowe`s Companies"):
        assert _tokens(typed) == plain, typed


def test_the_registrants_own_title_now_contains_the_typed_name():
    assert _tokens("Lowe's Companies") <= _tokens(SEC_TITLE)
    assert _tokens("Lowe's") <= _tokens(SEC_TITLE)


def test_deleting_is_symmetric_so_a_title_with_one_is_unaffected():
    """Both sides lose the character, so a registrant whose own title carries
    an apostrophe matches exactly as it did."""
    assert _tokens("Macy's Inc") == _tokens("MACYS INC") == {"macys"}


def test_a_name_without_an_apostrophe_tokenises_exactly_as_before():
    """REGRESSION CONTROL. The repair must be invisible to every name that
    never had the character -- which is almost all of them."""
    assert _tokens("Synopsys Inc") == {"synopsys"}
    assert _tokens("T-Mobile US, Inc.") == {"t", "mobile", "us"}
    assert _tokens("Advanced Micro Devices") == {"advanced", "micro",
                                                 "devices"}
    assert _tokens("") == set()


def test_normalising_does_not_make_an_unrelated_company_match():
    """NEGATIVE CONTROL. Removing a character widens every comparison, and a
    widened identity match is how one company's filings become another's."""
    assert not _tokens("Macy's") <= _tokens(SEC_TITLE)
    assert not _tokens("Lowe's") <= _tokens("ALPHABET INC")
    assert not _tokens("McDonald's") <= _tokens(SEC_TITLE)


# --- through the resolver a run actually calls ----------------------------

def test_the_typed_possessive_resolves_to_the_filer():
    got = resolve_cik("Lowe's Companies", transport=_tickers, resolver=False)
    assert got and str(got["cik"]) == "60667"
    mcd = resolve_cik("McDonald's", transport=_tickers, resolver=False)
    assert mcd and str(mcd["cik"]) == "63908"


def test_a_company_in_no_table_still_resolves_to_nothing():
    assert resolve_cik("Zzyzx Widgets Cooperative", transport=_tickers,
                       resolver=False) is None


# --- and the whole chain, from the string a customer types ---------------

def test_the_customers_own_spelling_reaches_the_business_model_gate():
    """END TO END on the exact live input. Every link has to hold: normalise
    the apostrophe, recover the subject, fetch the registrant, classify, and
    refuse the pattern that does not belong to a retailer."""
    def sec(url, timeout, max_bytes=None):
        if "company_tickers" in url:
            return (200, {}, TICKERS, False)
        if "submissions" in url:
            return (200, {}, b'{"cik": 60667, "sic": "5211", '
                             b'"sicDescription": "Retail-Lumber"}', False)
        return (404, {}, b"", False)

    # Enough sentences to actually produce an observation. A document that
    # yields none makes `_strategic_report` return None, which would fail
    # this test for a reason that has nothing to do with the apostrophe.
    text = ("We operate home improvement stores. We are committing capital "
            "to capacity ahead of the demand for it, and our supply "
            "commitments are long-dated.")
    doc = {"final_url":
           "https://www.sec.gov/Archives/edgar/data/60667/low.htm",
           "source_class": "investor_material", "source_id": "low",
           "title": "SEC 10-K", "text": text, "text_content": text,
           "content_hash": "low", "retrieved_at": "2026-02-24"}
    with tempfile.TemporaryDirectory() as tmp:
        ci = CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl",
                                     resolver=False, transport=sec)
        run = ci.create_run(company_name="Lowe's Companies",
                            website="https://lowes.com", user_id="u",
                            as_of="2026-08-20T00:00:00+00:00")
        payload = ci._strategic_report("Lowe's Companies", [doc], [],
                                       run_id=run["run_id"], deep=False)
    audit = payload["pattern_audit"]
    assert audit["meta_cik"] == ""
    assert audit["subject_cik"] == "60667", (
        "the apostrophe still costs this company its own identity")
    assert audit["registrant_sic"] == "5211"
    assert audit["business_model"] == "SCALE_RETAIL"
    assert "capacity_ahead_of_demand" in audit["excluded_pattern_ids"]
