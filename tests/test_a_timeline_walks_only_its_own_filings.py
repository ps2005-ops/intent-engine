"""Another registrant's 10-K is not this company's dated record.

WHAT THIS PINS
--------------
MEASURED live on 6fe2b847. West Monroe Partners, LLC — a private consultancy
with no CIK at all — was given a two-point history timeline under the words

    "The dated record that was retrieved is below: it establishes when this
     company said what"

built from two 10-Ks filed by CIK 1736035 and CIK 1803498. project44,
Dataminr and Boomi each carried one filing belonging to somebody else.

WHERE IT CAME FROM. `_history_timeline` asks `_filer_cik` first and, for a real
filer, builds from that registrant's own submissions — correct, and a
previous repair put it there. The FALLBACK then accepted any retrieved
document whose URL contained "sec.gov". The independent-source search exists
precisely to retrieve filings by OTHER registrants that NAME the subject, so
the fallback was being handed exactly the documents it must not use.

The evidence drawer had it right the whole time: it labels those sources
"SEC filer 1803498", because provenance separates WHO WROTE IT from who it is
about. The timeline did not ask.

A company that files nothing has no regulatory record. An empty subject CIK
therefore contributes NO filings rather than whatever happened to be
retrieved — the same authority `declared_cik` already holds for retrieval.
"""
from __future__ import annotations

from intent_engine.executive.history_rewind import (
    build, filings_from_documents,
)

SUBJECT = "https://www.sec.gov/Archives/edgar/data/1943896/000194389626000013/rbrk-20260131.htm"
OTHER = "https://www.sec.gov/Archives/edgar/data/1803498/000180349824000012/x-10k.htm"
OTHER2 = "https://www.sec.gov/Archives/edgar/data/1736035/000173603523000004/y-10k.htm"
OWN_PAGE = "https://www.westmonroe.com/insights"


def _doc(url, form="10-K", title="SEC 10-K (2024-03-15)"):
    return {"final_url": url, "title": title, "filing": {"form": form}}


DOCS = [_doc(OTHER), _doc(OTHER2, title="SEC 10-K (2023-02-27)"),
        _doc(SUBJECT, title="SEC 10-K (2026-01-31)"),
        {"final_url": OWN_PAGE, "title": "Insights"}]


def test_a_non_filer_gets_no_regulatory_timeline():
    """THE DEFECT. West Monroe has no CIK, so every SEC document in its
    evidence belongs to somebody else by construction."""
    assert filings_from_documents(DOCS) == ()
    assert filings_from_documents(DOCS, subject_cik="") == ()


def test_only_the_subjects_own_filings_are_walked():
    got = filings_from_documents(DOCS, subject_cik="0001943896")
    assert [f.url for f in got] == [SUBJECT]


def test_another_registrants_filing_is_never_included():
    for cik in ("0001943896", "1943896"):
        urls = {f.url for f in filings_from_documents(DOCS, subject_cik=cik)}
        assert OTHER not in urls and OTHER2 not in urls, cik


def test_the_leading_zeros_of_a_cik_do_not_decide_identity():
    padded = filings_from_documents(DOCS, subject_cik="0001943896")
    bare = filings_from_documents(DOCS, subject_cik="1943896")
    assert [f.url for f in padded] == [f.url for f in bare] == [SUBJECT]


def test_a_non_sec_document_is_still_not_a_filing():
    got = filings_from_documents([{"final_url": OWN_PAGE, "title": "x",
                                   "filing": {"form": "10-K"}}],
                                 subject_cik="1943896")
    assert got == ()


def test_the_timeline_a_non_filer_gets_explains_itself():
    """Not an empty frame: the page has to say why there is nothing."""
    timeline = build(company="West Monroe Partners, LLC",
                     filings=filings_from_documents(DOCS))
    assert timeline.vintages == ()
    assert "no dated record to rewind" in timeline.coverage_note
    assert "limit of what was retrieved" in timeline.coverage_note


def test_a_real_filer_still_gets_its_timeline():
    """The repair must not empty the page for a company that does file."""
    timeline = build(company="Rubrik, Inc.",
                     filings=filings_from_documents(DOCS,
                                                    subject_cik="1943896"))
    assert len(timeline.filings) == 1
    assert timeline.filings[0]["url"] == SUBJECT


def test_the_call_site_passes_the_subject_cik():
    """A repair the caller does not use is not a repair."""
    import inspect

    from intent_engine.webapp.app import WebApp

    src = inspect.getsource(WebApp._history_timeline)
    assert "filings_from_documents(documents, subject_cik=cik)" in src, \
        "the fallback is called without the subject's identity"
