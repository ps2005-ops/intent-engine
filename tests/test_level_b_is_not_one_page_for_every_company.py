"""A bounded rewind must be about THIS company's record (§11, §12, §19).

THE DEFECT THIS CLOSES. Before this change, every LEVEL B stop rendered two
fixed sentences with two counts substituted:

    "By <Month Year>, N dated page(s) published by <company> had been
     retrieved, most recently <titles>"
    "A reader on this date could establish what <company> said it did and who
     it said it served, from material the company had published by then"

The second sentence is true of every company that has ever published a web
page, and it is asserted whether the company's record contains a pricing page
or three press releases. That is a template with a name substituted into it,
which is exactly what §19 refuses -- and it would have been rendered
identically for however many of the forty landed on LEVEL B.

The economic half was not template, it was absent: measured 2026-09-11, this
module contained ONE occurrence of the string "econom", inside a docstring.

WHAT IS NOT TRADED AWAY. The vintage wall. `econ_at` is handed a stop date and
must answer with state published ON OR BEFORE it; a reader that returns a
later state is REFUSED rather than rendered, because the one promise this page
makes is that nothing at a date can see what came after it. Zero linked stops
is a legitimate outcome and says so: a deployment that has published no
economic state cannot borrow today's.
"""
from __future__ import annotations

import datetime as _dt
import inspect
import re

import pytest

from intent_engine.executive import history_rewind as HR


def _records(rows):
    return tuple(
        HR.DatedRecord(date=_dt.date.fromisoformat(d), title=t,
                       url=f"https://example.com/{i}", kind=k)
        for i, (d, t, k) in enumerate(rows))


#: Two genuinely different records: different dates, titles and KINDS.
SECURITY = _records([
    ("2021-03-02", "Rubrik Security Cloud", "segment"),
    ("2022-06-15", "Zero Trust Data Security", "corporate"),
    ("2023-09-01", "Customers", "customers"),
    ("2024-04-25", "Rubrik announces first quarter results", "newsroom"),
])
FREIGHT = _records([
    ("2019-01-10", "Freight visibility for shippers", "segment"),
    ("2020-05-05", "Pricing", "pricing"),
    ("2021-08-08", "project44 raises Series E", "newsroom"),
])


class _Ctx:
    """What `econ_context.load(as_of=...)` hands back when a state exists."""

    def __init__(self, as_of="2022-01-01", available=True):
        self.available = available
        self.as_of = as_of
        self.area = "United States"
        self.conditions = {"labour_market": "TIGHT", "credit": "TIGHTENING"}
        self.shocks = ("policy rate shock",)
        self.reason = ""


def _econ_from(first_published: str):
    """A reader honouring the wall: nothing published before its own date."""
    def reader(iso_date):
        return _Ctx(as_of=first_published) \
            if iso_date >= first_published else None
    return reader


def _skeleton(rewind, company):
    """The page with the company's name and every number removed.

    Two companies whose rewinds are identical under this transform are being
    served one template.
    """
    text = " ".join(s.record_then + " " + s.knowable + " " + s.lesson
                    for s in rewind.stops)
    return re.sub(r"\d+", " N ", text.replace(company, "CO"))


# --- the template collapse --------------------------------------------------

def test_two_companies_do_not_get_the_same_rewind():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY)
    b = HR.bounded_rewind(company="project44", records=FREIGHT)
    assert a.available and b.available
    assert _skeleton(a, "Rubrik") != _skeleton(b, "project44"), (
        "both companies received the same page with the name and the counts "
        "swapped -- a template, not a rewind")


def test_what_was_knowable_depends_on_what_the_company_published():
    """A record of one segment page does not license a claim that a reader
    could establish how the company charged."""
    seg_only = HR.bounded_rewind(
        company="Acme", records=_records([
            ("2020-01-01", "Platform", "segment"),
            ("2021-01-01", "Platform v2", "segment")]))
    priced = HR.bounded_rewind(
        company="Acme", records=_records([
            ("2020-01-01", "Platform", "segment"),
            ("2021-01-01", "Pricing", "pricing")]))
    assert "charged" not in seg_only.stops[-1].knowable.lower(), (
        "a company that published no pricing page was described as having "
        "made its charging knowable")
    assert "charged" in priced.stops[-1].knowable.lower(), (
        "a company that DID publish a pricing page was not credited with it")


def test_the_record_names_the_company_s_own_pages():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY)
    joined = " ".join(s.record_then for s in a.stops)
    assert "Rubrik Security Cloud" in joined, (
        "the rewind summarised the record as a count and never quoted one of "
        f"the company's own page titles: {joined[:200]}")


def test_a_stop_says_what_it_teaches():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY)
    assert all(s.lesson.strip() for s in a.stops), (
        "a stop carried no reading of what it shows about the company")


# --- the economic linkage ---------------------------------------------------

def test_a_stop_is_placed_beside_the_economy_of_its_own_period():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY,
                          econ_at=_econ_from("2022-01-01"))
    linked = [s for s in a.stops if s.economic_state == HR.ECON_LINKED]
    assert linked, "no stop was placed beside any economic state"
    assert a.economic_links == len(linked)
    assert all("2022-01-01" in s.economic_then for s in linked)
    assert all("labour market TIGHT" in s.economic_then for s in linked), (
        "the economic panel names no actual condition")


def test_no_stop_borrows_an_economic_state_from_after_its_own_date():
    """THE WALL. A reader that hands back a LATER state is refused."""
    def leaky(iso_date):
        return _Ctx(as_of="2025-12-31")        # always later than every stop
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY, econ_at=leaky)
    assert a.economic_links == 0, (
        "a state dated after the stop was rendered as that stop's "
        "contemporaneous economy -- hindsight, on the one page whose whole "
        "promise is that it holds a wall")
    assert all(s.economic_state == HR.ECON_NO_STATE_FOR_DATE
               for s in a.stops)


def test_an_early_stop_has_no_economy_and_says_so():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY,
                          econ_at=_econ_from("2022-01-01"))
    early = [s for s in a.stops if s.date < "2022-01-01"]
    assert early, "the fixture has no stop before the state was published"
    for stop in early:
        assert stop.economic_state == HR.ECON_NO_STATE_FOR_DATE
        assert not stop.economic_then, (
            "a stop earlier than any published state still carried one")


def test_zero_linked_stops_is_stated_not_hidden():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY)
    assert a.economic_links == 0
    assert "no economic state had been published" in a.economic_note.lower()
    assert "not a judgement that the period was uneventful" \
        in a.economic_note.lower(), (
        "a deployment with no economic state let the silence read as a "
        "finding about the period")


def test_a_raising_reader_costs_the_panel_and_not_the_page():
    def boom(iso_date):
        raise RuntimeError("store unreadable")
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY, econ_at=boom)
    assert a.available, "an unreadable economic store broke the whole rewind"
    assert all(s.economic_state == HR.ECON_NO_STATE_FOR_DATE
               for s in a.stops)


def test_not_attempted_is_distinct_from_nothing_published():
    """Three outcomes, and conflating the first two is the defect the
    discovery drawer was repaired for -- restated here so the same mistake
    cannot be made twice in one product."""
    never = HR.bounded_rewind(company="Rubrik", records=SECURITY)
    assert all(s.economic_state == HR.ECON_NOT_ATTEMPTED
               for s in never.stops)
    nothing = HR.bounded_rewind(company="Rubrik", records=SECURITY,
                                econ_at=lambda d: None)
    assert all(s.economic_state == HR.ECON_NO_STATE_FOR_DATE
               for s in nothing.stops)
    assert HR.ECON_NOT_ATTEMPTED != HR.ECON_NO_STATE_FOR_DATE


# --- the page ---------------------------------------------------------------

def _html(rewind, company="Rubrik"):
    from intent_engine.founder_brief import steps
    return steps._bounded_rewind(rewind, company)


def test_the_page_renders_the_economic_panel():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY,
                          econ_at=_econ_from("2022-01-01"))
    html = _html(a)
    assert "Economic conditions then" in html
    assert "What this teaches about the strategy" in html
    assert "What the company said then" in html
    assert "What happened later" in html


def test_the_page_says_why_a_period_has_no_economy():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY,
                          econ_at=lambda d: None)
    html = _html(a)
    assert "no economic state had been published" in html.lower()
    assert "would be hindsight" in html.lower(), (
        "the page omitted the economic panel silently, so a reader cannot "
        "tell a quiet period from a gap in our record")


def test_the_page_carries_the_state_machine_readably():
    a = HR.bounded_rewind(company="Rubrik", records=SECURITY,
                          econ_at=_econ_from("2022-01-01"))
    html = _html(a)
    assert f'data-econ-state="{HR.ECON_LINKED}"' in html
    assert f'data-econ-state="{HR.ECON_NO_STATE_FOR_DATE}"' in html


# --- the repair must be ON the path -----------------------------------------

def test_the_history_page_actually_passes_an_economic_reader():
    """`econ_at` DEFAULTS TO None. Every behavioural test above passes with a
    call site that never supplies one, and the live page would then render the
    not-attempted branch forever -- the optional-parameter failure this
    product has shipped before."""
    from intent_engine.webapp import app as A
    src = inspect.getsource(A.WebApp._history_page)
    assert "econ_at=" in src, (
        "the history page calls bounded_rewind without an economic reader, so "
        "no stop can ever be placed in its period")
    assert "as_of=" in src, (
        "the reader the page passes is not date-bound, so it would hand every "
        "stop the CURRENT economic state")
