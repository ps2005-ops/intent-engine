"""A heading is a promise, and this page used to make one it could not keep.

REPORTED FROM THE LIVE DEMO on b88df2bb. Highspot's history page was headed

    Highspot — the strategy simulator

and opened "Pick a year. The chart holds the path the company actually took".
Underneath, it explained that Highspot is not an SEC filer, has no dated
regulator series, that the chart could not be drawn, and asked the reader to
supply three years of reported revenue and operating results.

Every sentence was true. The page was still a failure, because the title and
the lede were CONSTANTS at the top of the renderer -- written before anything
was known about the company -- so they promised a simulator to every company
on earth and then withdrew it in the body.

§I asks for one coherent hierarchy instead:

    LEVEL A  a dated financial series exists      -> the chart
    LEVEL B  no series, but a dated record exists -> a bounded rewind
    LEVEL C  not enough dated evidence            -> name the gap

and, crucially, that the page NAME ITSELF after what it can deliver.

The second defect these tests cover is why Highspot had no dated record at
all. `filings_from_documents` -- the declared fallback for companies with no
regulator series -- required "sec.gov" in the URL, so for exactly the
companies that need a fallback it returned nothing. Meanwhile the parser had
been extracting each page's publication date all along and the service threw
it away, keeping only a CURRENT/STALE flag derived from it.
"""
import datetime as dt

import pytest

from intent_engine.executive import history_rewind as HR


def _doc(date=None, url="https://acme.example/p", title="A page",
         url_only=False):
    out = {"final_url": url, "title": title, "source_type": "corporate"}
    if date and not url_only:
        out["published_date"] = date
    return out


# --- the dates that may be used, and the one that may not -------------------

def test_a_publisher_asserted_date_is_used():
    got = HR.dated_records([_doc("2024-03-05T09:00:00Z")])
    assert [r.iso for r in got] == ["2024-03-05"]
    assert got[0].date_source == "metadata"


def test_a_dated_url_path_is_used_when_metadata_carries_none():
    """Point B publishes under /Insights/Articles/YYYY/MM/ and nothing else.

    Reading metadata alone put a real consulting firm on the evidence-gap
    page while its own URLs carried the dates.
    """
    got = HR.dated_records(
        [_doc(url="https://www.pointb.com/Insights/Articles/2023/08/Learn")])
    assert [r.iso for r in got] == ["2023-08-01"]
    assert got[0].date_source == "url_path"


def test_metadata_beats_the_url_path():
    got = HR.dated_records(
        [_doc("2020-01-02", url="https://x.example/2023/08/a")])
    assert got[0].iso == "2020-01-02"
    assert got[0].date_source == "metadata"


@pytest.mark.parametrize("url", [
    "https://x.example/2023/13/a",        # month 13 is not a month
    "https://x.example/p/1234/56",        # an SKU, not a date
    "https://x.example/about",            # nothing dateable
])
def test_a_number_in_a_path_is_not_a_date(url):
    assert HR.dated_records([_doc(url=url)]) == ()


def test_an_undated_document_contributes_nothing():
    assert HR.dated_records([_doc()]) == ()


def test_a_future_date_is_refused():
    """A scheduled post or a template placeholder, never an event."""
    ahead = (dt.date.today() + dt.timedelta(days=400)).isoformat()
    assert HR.dated_records([_doc(ahead)]) == ()


def test_the_retrieval_time_is_never_a_date():
    """THE ONE DATE ALWAYS AVAILABLE AND NEVER MEANINGFUL.

    Every retrieved record carries `retrieved_at`. Using it would give every
    company a full, entirely fake timeline whose points were all today.
    """
    doc = _doc()
    doc["retrieved_at"] = "2026-09-11T00:00:00Z"
    assert HR.dated_records([doc]) == ()


# --- which rewind the evidence supports -------------------------------------

def test_no_dates_is_the_evidence_gap():
    assert HR.rewind_level(None, ()) == HR.LEVEL_GAP


def test_one_date_is_still_the_evidence_gap():
    """One date is a fact about a document, not a path: there is no earlier
    position to stand in and nothing to have been surprised by."""
    one = HR.dated_records([_doc("2024-01-01")])
    assert len(one) == 1
    assert HR.rewind_level(None, one) == HR.LEVEL_GAP


def test_two_dates_support_a_bounded_rewind():
    two = HR.dated_records([_doc("2024-01-01", url="https://a.example/1"),
                            _doc("2024-06-01", url="https://a.example/2")])
    assert HR.rewind_level(None, two) == HR.LEVEL_BOUNDED


def test_a_filed_series_outranks_everything():
    class _Timeline:
        available = True
    two = HR.dated_records([_doc("2024-01-01", url="https://a.example/1"),
                            _doc("2024-06-01", url="https://a.example/2")])
    assert HR.rewind_level(_Timeline(), two) == HR.LEVEL_SERIES


def test_every_level_names_the_page_differently():
    titles = {HR.LEVEL_TITLES[k] for k in
              (HR.LEVEL_SERIES, HR.LEVEL_BOUNDED, HR.LEVEL_GAP)}
    assert len(titles) == 3
    # and only the one that draws a chart may call itself a simulator
    assert "simulator" in HR.LEVEL_TITLES[HR.LEVEL_SERIES]
    assert "simulator" not in HR.LEVEL_TITLES[HR.LEVEL_BOUNDED]
    assert "simulator" not in HR.LEVEL_TITLES[HR.LEVEL_GAP]


# --- the vintage wall, restated on the second surface -----------------------

def test_the_bounded_rewind_holds_the_wall():
    docs = [_doc(f"202{y}-01-01", url=f"https://a.example/{y}")
            for y in range(0, 5)]
    rewind = HR.bounded_rewind(company="Acme",
                               records=HR.dated_records(docs))
    assert rewind.available
    counts = [(s.count_before, s.count_after) for s in rewind.stops]
    # before + after is the whole record at every stop, and before only grows
    assert all(b + a == 5 for b, a in counts)
    assert [b for b, _ in counts] == sorted(b for b, _ in counts)
    # the earliest stop cannot see the rest
    assert rewind.stops[0].count_before == 1
    assert rewind.stops[0].count_after == 4


def test_the_bounded_rewind_never_claims_a_chart():
    docs = [_doc("2024-01-01", url="https://a.example/1"),
            _doc("2024-06-01", url="https://a.example/2")]
    rewind = HR.bounded_rewind(company="Acme", records=HR.dated_records(docs))
    blob = " ".join([rewind.coverage_note, rewind.open_question]
                    + [s.record_then for s in rewind.stops]).lower()
    assert "chart" not in blob or "not" in blob
    assert rewind.what_would_upgrade, "a gap must say what would close it"


def test_one_record_yields_no_stops_and_explains_why():
    rewind = HR.bounded_rewind(
        company="Acme", records=HR.dated_records([_doc("2024-01-01")]))
    assert not rewind.available
    assert "single date" in rewind.coverage_note


def test_no_records_says_so_without_blaming_the_company():
    rewind = HR.bounded_rewind(company="Acme", records=())
    assert not rewind.available
    note = rewind.coverage_note.lower()
    assert "publisher had asserted" in note
