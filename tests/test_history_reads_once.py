"""History Rewind: one economy per period, and no call to action as a record."""
from __future__ import annotations

import datetime

from intent_engine.executive import history_rewind as HR
from intent_engine.strategic_intelligence.concrete import _is_call_to_action


def _r(day, title):
    return HR.DatedRecord(date=datetime.date(2026, 9, day), title=title,
                          url=f"https://x.example/{day}", kind="page",
                          source_class="company_owned", date_source="metadata")


def test_a_call_to_action_is_not_the_company_s_words():
    got = HR._titles_of([_r(1, "Book a demo."),
                         _r(2, "Identify opportunities and reduce risk."),
                         _r(3, "Rystad Energy - All energies")])
    assert got == "Rystad Energy - All energies"


def test_a_reported_action_is_not_a_call_to_action():
    """CONTROL."""
    assert not _is_call_to_action("Sentry acquired Codecov.")
    assert not _is_call_to_action("Rystad Energy - All energies")


def test_the_same_releases_are_said_once(monkeypatch):
    from types import SimpleNamespace
    from intent_engine.founder_brief import steps
    stop = lambda d: SimpleNamespace(
        date=d, label=d, record_then="r", knowable="k", unknowable="u",
        later="", economic_then="CPI up at 334.98 as at 2026-08-01.",
        economic_state=HR.ECON_RECONSTRUCTED, lesson="", count_before=1,
        count_after=0)
    bounded = SimpleNamespace(stops=(stop("24 September 2026"),
                                     stop("28 September 2026")),
                              available=True, company="Acme", span="",
                              coverage_note="", open_question="",
                              what_would_upgrade="", economic_links=0,
                              economic_note="")
    html = steps._bounded_rewind(bounded, "Acme")
    assert html.count("CPI up at 334.98") == 1
    assert "unchanged since the previous stop" in html
