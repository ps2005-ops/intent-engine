"""A walk that says the same thing four times is one stop, not four (§P1-4/5/7).

WHAT THIS PINS
--------------
MEASURED across cohort A on 8495b00c, counting identical sentences on each
company's own LEVEL B history page:

    the lesson     Cohesity x4, project44 x3, Boomi x3, Kinaxis x2
    the economics  Dataminr x5, Boomi x5, SnapLogic x5, Adastra x3, HYCU x2

The lesson had already been repaired ONCE -- for the cadence branch, because
Cohesity's data exercised that branch and not its siblings. `_bounded_lesson`
has five branches and four of them could still return one sentence for every
stop in a walk. Fixing the branch in front of you and leaving its siblings is
how one defect is found four times.

The economic note had the same history: it was suppressed when NO stop could
be placed in its period, and left repeating when SOME could.

AND ONE THING NO READER SHOULD EVER HAVE SEEN. The condition list was built
with `str(v)` where `v` is the signal record, so project44's and Nasuni's
history pages printed a Python dict at the reader:

    recorded consumer demand {'as_of': '2026-06-01', 'direction': 'UP',
    'node_id': 'panel:PCEC96:2026-06-01', 'standing': 'OBSERVED', ...}
"""
from __future__ import annotations

import datetime as _dt

from intent_engine.executive import history_rewind as HR
from intent_engine.executive.history_rewind import (
    DatedRecord, _bounded_lesson, _condition_english, bounded_rewind,
)


def _rec(day, title, kind="page"):
    return DatedRecord(date=_dt.date(2026, 1, day), title=title,
                       url=f"https://example.com/{day}", kind=kind)


# --- the leaked dict --------------------------------------------------------

_SIGNAL = {"as_of": "2026-06-01", "direction": "UP", "kind": "consumer_demand",
           "known": True, "moved": True,
           "node_id": "panel:PCEC96:2026-06-01", "prior_value": 16466.3,
           "publisher": "FRED (Federal Reserve Bank of St. Louis)",
           "reason": "", "standing": "OBSERVED", "unit": "billions",
           "value": 16885.2}


def test_a_measured_condition_is_rendered_as_english():
    said = _condition_english("consumer_demand", _SIGNAL)
    assert "{" not in said and "'" not in said, said
    assert "consumer demand" in said
    assert "up" in said
    assert "16885.2" in said


def test_no_internal_field_name_reaches_the_reader():
    said = _condition_english("consumer_demand", _SIGNAL)
    for leaked in ("node_id", "standing", "OBSERVED", "prior_value",
                   "as_of'", "panel:"):
        assert leaked not in said, leaked


def test_a_scalar_condition_still_renders():
    assert _condition_english("policy_rate", "4.25%") == "policy rate 4.25%"


def test_the_economic_sentence_itself_never_carries_a_dict():
    """Asserted on the SENTENCE the page prints, not on the helper alone.

    A helper that renders English is not a repair if the sentence is still
    built with `str(v)`; that call site is where the dict reached the reader.
    """
    class _Ctx:
        available = True
        as_of = "2026-01-05"
        area = "US"
        conditions = {"consumer_demand": _SIGNAL}
        shocks = ()

    said, state = HR._economic_then(lambda _d: _Ctx(), _dt.date(2026, 1, 6),
                                    "Example, Inc.")
    assert state == HR.ECON_LINKED
    assert "consumer demand" in said, said
    for leaked in ("{", "}", "node_id", "'standing'", "OBSERVED"):
        assert leaked not in said, (leaked, said)


def test_an_unknown_condition_is_not_named_as_a_reading():
    class _Ctx:
        available = True
        as_of = "2026-01-05"
        area = "US"
        conditions = {"consumer_demand": dict(_SIGNAL, known=False)}
        shocks = ()

    said, state = HR._economic_then(lambda _d: _Ctx(), _dt.date(2026, 1, 6),
                                    "Example, Inc.")
    assert "consumer demand" not in said, said
    assert "carried no condition" in said


# --- every branch of the lesson --------------------------------------------

def test_the_gained_branch_names_the_page_that_came_later():
    before = [_rec(1, "About us", "about")]
    after = [_rec(9, "Our customers", "customers"),
             _rec(10, "More customers", "customers")]
    said = _bounded_lesson("Example, Inc.", before, after, [], 0)
    assert "customers material came later" in said
    assert "Our customers" in said, said


def test_two_stops_with_the_same_missing_kind_do_not_repeat():
    """The defect itself: the gained KINDS change slowly, the pages do not."""
    records = [_rec(1, "About us", "about"), _rec(2, "Leadership", "about"),
               _rec(8, "Customer one", "customers"),
               _rec(9, "Customer two", "customers")]
    lessons = []
    for cut in (1, 2):
        before = [r for r in records if r.date.day <= cut]
        after = [r for r in records if r.date.day > cut]
        lessons.append(_bounded_lesson("Example, Inc.", before, after, [], 0))
    assert lessons[0] != lessons[1], lessons


def test_the_since_branch_names_what_arrived():
    since = [_rec(5, "A new page", "page")]
    said = _bounded_lesson("Example, Inc.", [_rec(1, "Old", "page")],
                           [_rec(9, "Later", "page")], since, 0)
    assert "A new page" in said, said


def test_the_quiet_branch_names_how_long_the_quiet_was():
    a = _bounded_lesson("Example, Inc.", [_rec(1, "Old", "page")],
                        [_rec(9, "Later", "page")], [], 7)
    b = _bounded_lesson("Example, Inc.", [_rec(1, "Old", "page")],
                        [_rec(9, "Later", "page")], [], 30)
    assert "7 day(s)" in a
    assert "30 day(s)" in b
    assert a != b


def test_the_end_of_the_record_says_so_once():
    said = _bounded_lesson("Example, Inc.", [_rec(1, "Old", "page")], [], [],
                           7)
    assert "end of" in said


# --- the walk as a whole, which is what a reader sees ----------------------

def test_no_two_stops_in_a_walk_teach_the_same_lesson():
    records = [_rec(1, "About us", "about"), _rec(3, "Leadership", "about"),
               _rec(6, "Press release", "news"),
               _rec(11, "Customer one", "customers"),
               _rec(17, "Customer two", "customers"),
               _rec(24, "Pricing page", "pricing")]
    walk = bounded_rewind(company="Example, Inc.", records=records)
    lessons = [s.lesson for s in walk.stops]
    assert len(lessons) >= 4
    assert len(set(lessons)) == len(lessons), lessons


def test_the_unplaced_economic_note_is_stated_once_per_walk():
    """Rendered, not just composed: the repeat was in the renderer."""
    from intent_engine.founder_brief import steps as S

    class _Ctx:
        available = True
        area = "US"
        conditions = {"consumer_demand": _SIGNAL}
        shocks = ()

        def __init__(self, as_of):
            self.as_of = as_of

    def econ_at(iso):
        # Nothing published before the 15th: the early stops cannot be placed.
        return _Ctx(iso) if iso >= "2026-01-15" else None

    records = [_rec(1, "A", "about"), _rec(5, "B", "news"),
               _rec(9, "C", "news"), _rec(13, "D", "news"),
               _rec(20, "E", "customers"), _rec(26, "F", "pricing")]
    walk = bounded_rewind(company="Example, Inc.", records=records,
                          econ_at=econ_at)
    unplaced = [s for s in walk.stops
                if s.economic_state == HR.ECON_NO_STATE_FOR_DATE]
    assert len(unplaced) >= 2, "the fixture must exercise the repeat"
    html = S._bounded_rewind(walk, "Example, Inc.")
    assert html, "the renderer must produce the walk this test measures"
    # THE POSITIVE CONTROL FIRST: the note must still be reachable at all,
    # or "stated once" would pass by being stated never.
    assert html.count("no economic state had been published") == 1, \
        "the note informs once and pads thereafter"
    # And the stops it applies to are really there.
    assert html.count("data-econ-state=") == len(walk.stops)
    # The economics that WERE placed are still rendered, in English.
    assert "consumer demand" in html
    assert "{" not in html.split("hcards")[1]
