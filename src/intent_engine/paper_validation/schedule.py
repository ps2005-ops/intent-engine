"""When a forward forecast is due, decided once, at registration.

WHY THIS EXISTS
---------------
The resolver used to find a forecast's exit session by counting 21 bars in
the benchmark's price feed (`spy.dates[si + HORIZON]`). The due date was never
written down, so it was re-derived on every run from whatever the feed held
that day. One missing bar anywhere in the window moved every open forecast one
session later, and nothing could notice, because there was no original date to
compare against.

Now the schedule comes from an exchange calendar, not from a data feed:

* `scheduled_window(decision_date, horizon)` gives the entry and exit sessions.
  It needs no prices, so it can run at registration time.
* New registrations store the result (`scheduled_entry_session`,
  `scheduled_exit_session`, `schedule_calendar`) inside the hash-chained
  record, where nothing can move it.
* Records registered before this module (the 2026-11-09 cohort) carry no
  stored schedule. Their schedule is recomputed from the same rules, and a
  test pins it to the dates it had on the day they were registered.

A resolver that cannot find a bar on the scheduled session waits, then voids
with the reason. It never scores the forecast on a later session.

THE CALENDAR IS RULES, NOT A TABLE
----------------------------------
A hand-maintained holiday table runs out (the runtime's ends in 2027), and a
table that has run out silently treats the next Thanksgiving as a session.
NYSE full-day closures follow fixed rules, so they are computed for any year.
Unscheduled closures (a national day of mourning, a hurricane) cannot be
predicted. The known ones are listed; a future one would make the scheduled
exit a day with no bar, and the forecast is voided with that reason instead
of being moved.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from typing import FrozenSet, Optional, Tuple

#: NYSE full-day closures that no rule produces.
SPECIAL_CLOSURES = frozenset({
    "2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14",   # September 11
    "2004-06-11",                                             # Reagan
    "2007-01-02",                                             # Ford
    "2012-10-29", "2012-10-30",                               # Hurricane Sandy
    "2018-12-05",                                             # G. H. W. Bush
    "2025-01-09",                                             # Carter
})

MIN_YEAR, MAX_YEAR = 1998, 2100


class CalendarOutOfRange(ValueError):
    """Asked about a year the rules were not written for."""


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    d = _dt.date(year, month, 1)
    d += _dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + _dt.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> _dt.date:
    nxt = _dt.date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> _dt.date:
    """Anonymous Gregorian algorithm."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return _dt.date(year, month, day)


def _observed(d: _dt.date) -> Optional[_dt.date]:
    """Saturday holidays close the Friday before, Sunday ones the Monday after."""
    if d.weekday() == 5:
        return d - _dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + _dt.timedelta(days=1)
    return d


def nyse_holidays(year: int) -> FrozenSet[str]:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise CalendarOutOfRange(f"no NYSE rules for {year}")
    out = set()
    ny = _dt.date(year, 1, 1)
    if ny.weekday() == 6:
        out.add(_dt.date(year, 1, 2))
    elif ny.weekday() < 5:
        out.add(ny)
    # NYSE rule: a Saturday New Year's Day is NOT observed on the Friday
    # before, so the year-end session stays open.
    out.add(_nth_weekday(year, 1, 0, 3))              # Martin Luther King Jr.
    out.add(_nth_weekday(year, 2, 0, 3))              # Washington's Birthday
    out.add(_easter(year) - _dt.timedelta(days=2))    # Good Friday
    out.add(_last_weekday(year, 5, 0))                # Memorial Day
    if year >= 2022:
        out.add(_observed(_dt.date(year, 6, 19)))     # Juneteenth
    out.add(_observed(_dt.date(year, 7, 4)))          # Independence Day
    out.add(_nth_weekday(year, 9, 0, 1))              # Labor Day
    out.add(_nth_weekday(year, 11, 3, 4))             # Thanksgiving
    out.add(_observed(_dt.date(year, 12, 25)))        # Christmas
    return frozenset(d.isoformat() for d in out)


class NyseCalendar:
    calendar_id = "nyse_rules.v1+special:" + hashlib.sha256(
        ",".join(sorted(SPECIAL_CLOSURES)).encode()).hexdigest()[:12]

    def is_session(self, day: str) -> bool:
        d = _dt.date.fromisoformat(day[:10])
        return (d.weekday() < 5 and day[:10] not in nyse_holidays(d.year)
                and day[:10] not in SPECIAL_CLOSURES)


class WeekdayCalendar:
    """Every weekday is a session. For synthetic test fixtures only, whose
    random-walk bars exist on every weekday including real holidays."""
    calendar_id = "weekdays.v1"

    def is_session(self, day: str) -> bool:
        return _dt.date.fromisoformat(day[:10]).weekday() < 5


NYSE = NyseCalendar()
WEEKDAYS = WeekdayCalendar()
CALENDARS = {NYSE.calendar_id: NYSE, WEEKDAYS.calendar_id: WEEKDAYS}
DEFAULT = NYSE


def sessions_after(day: str, n: int, calendar=None) -> Tuple[str, ...]:
    """The first n sessions strictly after `day`."""
    cal = calendar or DEFAULT
    d = _dt.date.fromisoformat(day[:10])
    out = []
    while len(out) < n:
        d += _dt.timedelta(days=1)
        if cal.is_session(d.isoformat()):
            out.append(d.isoformat())
    return tuple(out)


def scheduled_window(decision_date: str, horizon: int,
                     calendar=None) -> Tuple[str, str]:
    """(entry, exit): entry is the first session after the decision date and
    exit is `horizon` sessions after entry -- the protocol's entry and exit
    rules, computed without looking at a single price."""
    if not isinstance(horizon, int) or horizon < 1:
        raise ValueError(f"horizon must be a positive int, got {horizon!r}")
    s = sessions_after(decision_date, horizon + 1, calendar)
    return s[0], s[horizon]


def resolvable_from(exit_session: str) -> str:
    """The first New York date on which the ledger accepts a resolution: the
    day after the exit session, because the exit open must have printed and
    the ledger refuses an exit date that is not strictly in the past."""
    return (_dt.date.fromisoformat(exit_session[:10])
            + _dt.timedelta(days=1)).isoformat()


def schedule_of(registration: dict) -> Tuple[str, str, str]:
    """(entry, exit, calendar_id) for a registered forecast.

    A stored schedule wins, always. Only a record registered before schedules
    were stored is recomputed, from the NYSE rules.
    """
    stored = registration.get("scheduled_exit_session")
    if stored:
        return (registration["scheduled_entry_session"], stored,
                registration.get("schedule_calendar", ""))
    entry, exit_ = scheduled_window(registration["decision_date"],
                                    int(registration["horizon_sessions"]),
                                    NYSE)
    return entry, exit_, NYSE.calendar_id
