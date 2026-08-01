"""Market session awareness — what kind of day this actually is.

WHY THIS EXISTS
---------------
An unattended cycle runs every calendar day. Sixteen days of manual operation
never had to answer "was there a market session today?", because a human
started the run and knew. An unattended run does not know, and the failure mode
is specific and quiet: **ingest Friday's close again on Saturday and Sunday and
count it as three market observations.** Nothing errors. The sample size
inflates by 40%, every confidence interval narrows, and the narrowing is pure
fiction.

So a cycle must be able to say, before it does anything: is this a trading day,
and is the bar I am about to read a NEW one?

REUSES THE EXISTING CALENDAR
----------------------------
`runtime.market_calendar` already curates NYSE closures and gives tz-aware
"now". This adds the two distinctions a daily unattended loop needs and that
module deliberately does not make — early closes, and whether the completed bar
is new, late, or stale.

WHAT IT REFUSES TO DO
---------------------
It never infers that a bar exists. `bar_state` is computed from a bar date that
was actually observed, or from the absence of one. A missing close is reported
as missing; it is never carried forward, interpolated, or assumed from the
calendar. The calendar says whether a session *should* have happened, which is
a different claim from whether data *did* arrive, and conflating the two is how
a system fabricates a trading day.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from intent_engine.runtime.market_calendar import (
    is_market_day, is_weekend, previous_market_day,
)

try:
    from zoneinfo import ZoneInfo
    _TORONTO = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover - zoneinfo is stdlib on 3.9+
    _TORONTO = None

# The operating timezone, stated once. Every run identity, schedule window and
# report timestamp is expressed in it, so a machine in another timezone (or a
# machine whose timezone changes) cannot silently shift the operating day.
TIMEZONE = "America/Toronto"

# --- session states ---------------------------------------------------------
TRADING_DAY = "TRADING_DAY"
EARLY_CLOSE = "EARLY_CLOSE"
WEEKEND = "WEEKEND"
HOLIDAY = "HOLIDAY"

# --- bar (completed daily close) states -------------------------------------
BAR_AVAILABLE = "BAR_AVAILABLE"                    # a new completed bar
BAR_NOT_YET_PUBLISHED = "BAR_NOT_YET_PUBLISHED"    # session open/just closed
BAR_STALE = "BAR_STALE"                            # older than it should be
BAR_UNCHANGED = "BAR_UNCHANGED"                    # same bar as the last cycle
BAR_UNAVAILABLE = "BAR_UNAVAILABLE"                # no bar at all

# NYSE 1:00pm ET early closes. Curated and auditable, exactly like the holiday
# set it complements. A year outside this set degrades to a full trading day --
# never to a crash, and never to a fabricated early close.
_EARLY_CLOSES = {
    "2025-07-03", "2025-11-28", "2025-12-24",
    "2026-11-27", "2026-12-24",
    "2027-11-26",
}

# How long after the close a bar may be missing before it is late rather than
# simply unpublished. Vendors publish the daily close within a few hours; past
# that, silence is a source problem worth reporting.
_PUBLISH_GRACE_HOURS = 4


def now_local() -> datetime:
    """Timezone-aware 'now' in the OPERATING timezone.

    Explicit, never the machine's local zone. A laptop that travels, or a
    server in UTC, must not shift which calendar day a cycle belongs to.
    """
    if _TORONTO is not None:
        return datetime.now(_TORONTO)
    return datetime.now()  # pragma: no cover - zoneinfo always available


def today_local() -> date:
    return now_local().date()


def is_early_close(day: date) -> bool:
    return day.isoformat() in _EARLY_CLOSES


def session_state(day: date) -> str:
    """What kind of calendar day this is. Weekend is distinguished from holiday
    because they are different facts, and a report that says "closed" for both
    cannot tell you the calendar is wrong."""
    if is_weekend(day):
        return WEEKEND
    if not is_market_day(day):
        return HOLIDAY
    if is_early_close(day):
        return EARLY_CLOSE
    return TRADING_DAY


def expected_bar_date(day: date) -> date:
    """The most recent session whose close should exist by now.

    On a trading day the session has not closed until the evening, so the
    newest COMPLETED bar is the previous market day. This is what stops a
    pre-market cycle from expecting a bar that the market has not printed yet.
    """
    if session_state(day) in (TRADING_DAY, EARLY_CLOSE):
        return previous_market_day(day)
    return previous_market_day(day + timedelta(days=1))


def bar_state(*, latest_bar: Optional[str], day: date,
              hour: Optional[int] = None,
              previous_cycle_bar: Optional[str] = None) -> str:
    """Classify the newest completed bar actually observed.

    `latest_bar` is a date that came back from a price source. None means the
    source returned nothing -- which is reported as unavailable, never quietly
    replaced with the previous close.

    `previous_cycle_bar` is what the last cycle already ingested. When they
    match, this is the SAME market observation seen twice, and saying so is the
    whole point: re-reading Friday's close on Sunday must not count as a new
    observation.
    """
    if not latest_bar:
        return BAR_UNAVAILABLE
    expected = expected_bar_date(day).isoformat()
    if previous_cycle_bar and latest_bar == previous_cycle_bar:
        return BAR_UNCHANGED
    if latest_bar >= expected:
        return BAR_AVAILABLE
    # One session behind on a trading day, early enough that the vendor has
    # plausibly not published: late, not stale.
    behind = (date.fromisoformat(expected) - date.fromisoformat(latest_bar)).days
    if behind <= 4 and hour is not None and hour < _PUBLISH_GRACE_HOURS + 12:
        return BAR_NOT_YET_PUBLISHED
    return BAR_STALE


@dataclass(frozen=True)
class MarketSession:
    """One cycle's reading of the calendar and the data behind it."""
    day: str
    timezone: str
    state: str
    bar: str
    latest_bar: Optional[str]
    expected_bar: str
    previous_cycle_bar: Optional[str] = None

    @property
    def is_open_session(self) -> bool:
        return self.state in (TRADING_DAY, EARLY_CLOSE)

    @property
    def has_new_market_observation(self) -> bool:
        """The ONLY property that may increment a market sample size.

        Everything else -- evidence ingestion, replay, reporting, health --
        runs regardless. This gates statistics only.
        """
        return self.bar == BAR_AVAILABLE

    @property
    def reason(self) -> str:
        if self.bar == BAR_UNCHANGED:
            return (f"the newest completed bar ({self.latest_bar}) is the one "
                    f"the previous cycle already ingested — not a new "
                    f"market observation")
        if self.bar == BAR_UNAVAILABLE:
            return "no completed bar could be retrieved"
        if self.bar == BAR_STALE:
            return (f"newest bar {self.latest_bar} is behind the expected "
                    f"{self.expected_bar}")
        if self.bar == BAR_NOT_YET_PUBLISHED:
            return f"bar for {self.expected_bar} has not been published yet"
        if self.state == WEEKEND:
            return "weekend — evidence and research cycle only"
        if self.state == HOLIDAY:
            return "market holiday — evidence and research cycle only"
        if self.state == EARLY_CLOSE:
            return "early close (1:00pm ET)"
        return "normal trading day"

    def as_dict(self) -> dict:
        return {"day": self.day, "timezone": self.timezone,
                "state": self.state, "bar": self.bar,
                "latest_bar": self.latest_bar,
                "expected_bar": self.expected_bar,
                "previous_cycle_bar": self.previous_cycle_bar,
                "is_open_session": self.is_open_session,
                "has_new_market_observation":
                    self.has_new_market_observation,
                "reason": self.reason}


def classify(day: date, *, latest_bar: Optional[str] = None,
             hour: Optional[int] = None,
             previous_cycle_bar: Optional[str] = None) -> MarketSession:
    """The one entry point a cycle calls before it does anything else."""
    return MarketSession(
        day=day.isoformat(), timezone=TIMEZONE, state=session_state(day),
        bar=bar_state(latest_bar=latest_bar, day=day, hour=hour,
                      previous_cycle_bar=previous_cycle_bar),
        latest_bar=latest_bar, expected_bar=expected_bar_date(day).isoformat(),
        previous_cycle_bar=previous_cycle_bar)


def leakage_cutoff(as_of: str, *, utc_today: Optional[str] = None) -> str:
    """The latest publication date that is NOT future information at `as_of`.

    THE BUG THIS FIXES (measured, Day 17)
    -------------------------------------
    Ingestion stamps an otherwise-undated observation with the RETRIEVAL time
    in **UTC**. The leakage guard compared that against `as_of`, which is a
    calendar day in the **operating timezone**. Between 20:00 and midnight in
    America/Toronto, UTC has already rolled over, so every freshly-retrieved
    observation was dated *tomorrow* relative to `as_of` and the guard dropped
    all of it.

    The result was not an error. It was `evidence: 0` -- a number that reads
    exactly like "nothing was published today" and would have entered the
    rolling means as a real measurement. The night cycle is scheduled for
    20:30, which is inside that window every single night.

    THE RULE
    --------
    The honest boundary is the *instant* the decision is made, not a naive
    calendar date:

    * **Live run** (`as_of` is the current operating day): the decision instant
      is now, so anything retrievable now existed at decision time. The cutoff
      extends to the current UTC date, which may be `as_of + 1`.
    * **Replay** (`as_of` is in the past): the cutoff is `as_of`, exactly and
      strictly. Unchanged.

    This does NOT weaken the guard. Replay -- the only path on which a signal
    can be evaluated, and therefore the only path where lookahead could flatter
    a result -- is untouched. What changes is that a live run stops discarding
    evidence that genuinely existed when it looked.
    """
    day = as_of[:10]
    if day != today_local().isoformat():
        return day                      # replay: strict, unchanged
    utc_today = utc_today or datetime.now(timezone.utc).date().isoformat()
    return max(day, utc_today)


def within_window(now: datetime, hour: int, minute: int,
                  tolerance_minutes: int = 90) -> bool:
    """Is `now` inside the scheduled local-time window?

    THE DAYLIGHT-SAVING GUARD. launchd fires on the MACHINE's local time. If
    that is not the operating timezone -- or if a DST transition shifts the
    wall clock -- a job can fire at the wrong hour, or twice. This is checked
    before the lock is taken so a mistimed fire costs nothing.

    Note this is a WINDOW check, not a duplicate check. Duplicate protection is
    the run identity (one record per operating day per cycle type), which is
    what actually makes a repeated 1:30am hour during a fall-back transition
    harmless.
    """
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return abs((now - target).total_seconds()) <= tolerance_minutes * 60
