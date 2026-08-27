"""§4: when a figure was actually PUBLISHED, not when it was measured.

THE FAILURE THIS PREVENTS
-------------------------
A monthly panel is worse than a quarterly one if publication timing leaks.
CPI for July is not available on 31 July; payrolls for July are not available
during July; the first GDP estimate for a quarter lands about a month after
the quarter ends. A forecast origin on 15 August that reads "July CPI"
because the period label is <= the origin has read a number that did not
exist. On a quarterly grid the error is usually hidden by the grid's own
coarseness; on a monthly grid it is the difference between a real result and
a fabricated one.

TWO DATES, ALWAYS
-----------------
    observed_at   the period the figure describes
    released_at   when the publisher first put it out

`available_as_of(series, t)` answers ONE question: which periods of this
series had been released by `t`. It never looks at values, so it cannot be
accidentally made value-dependent.

WHY A LAG AND NOT A CALENDAR OF DATES
-------------------------------------
A real release calendar -- every BLS/BEA/Census announcement date since 1960
-- is thousands of dates this engine has no keyless source for. A per-series
lag, applied to the END of the reference period, is coarser and is WRONG IN
THE SAFE DIRECTION as long as it is set to the LATE end of the observed
range: a model told it learned July CPI on 16 August when the real date was
13 August has seen less than it could have, which understates the model
rather than flattering it.

That asymmetry is the whole design. Every lag here is at or beyond the
publisher's typical release, and `LAG_BASIS` records which.

WHY THE REFERENCE POINT IS THE PERIOD'S END
-------------------------------------------
`alfred.to_nodes` computes availability from the FIRST of the month AFTER the
period label, which is the period's end for a MONTHLY series and is a full
quarter early for a QUARTERLY one. Q1 is labelled 1 January; first-of-next-
month is 1 February; a 30-day lag then claims Q1 GDP was available on 3
March, five weeks before the advance estimate exists. That is a leak of a
whole quarter and it was invisible while every origin sat on a quarterly grid
that happened to skip past it.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_release.v1"

MONTHLY, QUARTERLY, DAILY, ANNUAL = "MONTHLY", "QUARTERLY", "DAILY", "ANNUAL"
FREQUENCIES = (DAILY, MONTHLY, QUARTERLY, ANNUAL)

#: Months a period covers, per frequency. Used to find the period's END,
#: which is what a publication lag is measured from.
SPAN_MONTHS = {DAILY: 0, MONTHLY: 1, QUARTERLY: 3, ANNUAL: 12}


class ReleaseLeak(EconError):
    """A value was used before its publisher had released it."""


class InterpolationRefused(EconError):
    """A lower-frequency observation was about to be spread over months."""


@dataclass(frozen=True)
class ReleaseRule:
    """How long after a period ends this publisher puts the figure out."""

    series_id: str
    frequency: str
    #: Days after the END of the reference period. Set at or beyond the
    #: publisher's typical release so the wall errs toward knowing less.
    lag_days: int
    basis: str

    def __post_init__(self) -> None:
        require(self.frequency in FREQUENCIES,
                f"{self.series_id}: unknown frequency {self.frequency!r}")
        require(self.lag_days >= 0,
                f"{self.series_id}: a figure cannot be released before the "
                "period it measures has ended")
        require(bool(self.basis),
                f"{self.series_id}: record WHY this lag, or it is a number "
                "somebody typed")

    def period_end(self, period: str) -> _dt.date:
        """The last day of the period labelled `period`."""
        y, m, d = (int(x) for x in period.split("-"))
        span = SPAN_MONTHS[self.frequency]
        if span == 0:                       # daily: the period IS the day
            return _dt.date(y, m, d)
        total = (m - 1) + span
        ny, nm = y + total // 12, total % 12 + 1
        return _dt.date(ny, nm, 1) - _dt.timedelta(days=1)

    def released_at(self, period: str) -> str:
        return (self.period_end(period)
                + _dt.timedelta(days=self.lag_days)).isoformat()

    def as_dict(self) -> dict:
        return {"series_id": self.series_id, "frequency": self.frequency,
                "lag_days": self.lag_days, "basis": self.basis}


#: Series measured in PERCENTAGE POINTS. Their changes must be arithmetic
#: differences, never relative changes.
#:
#: WHY THIS IS A LIST AND NOT A GUESS. The US personal saving rate was printed
#: NEGATIVE in the 1999 vintages (-1.0, -1.4) and passed through exactly zero
#: on the way. A relative change divides by that base: at three origins the
#: feature was undefined and PSAVERT silently vanished from the block, and at
#: the origins either side of them the "percentage change" of a rate going
#: from -1.4 to +2.0 is a number with no meaning. A rate that can cross zero
#: has no meaningful relative change, and the difference in percentage points
#: is what an economist would have used in the first place.
PERCENTAGE_POINT_SERIES = frozenset({
    "UNRATE", "U6RATE", "CIVPART", "EMRATIO", "PSAVERT", "MICH",
    "DFF", "DGS2", "DGS10", "BAMLH0A0HYM2", "TDSP",
    "DRCCLACBS", "CORCACBS", "DRSFRMACBS", "BOGZ1FL153064486Q",
})


def is_percentage_point(series_id: str) -> bool:
    return series_id in PERCENTAGE_POINT_SERIES


#: Every rule states its basis. The lags are set to the LATE end of the
#: publisher's observed range so that the wall understates what a model knew.
RULES: Tuple[ReleaseRule, ...] = (
    # --- surveys: fast, and never revised -------------------------------
    ReleaseRule("UMCSENT", MONTHLY, 1,
                "final Michigan reading lands in the last week of the "
                "reference month; dated one day after month end"),
    ReleaseRule("MICH", MONTHLY, 1, "published with UMCSENT"),
    ReleaseRule("USACSCICP02STSAM", MONTHLY, 40,
                "OECD composite, compiled from national sources"),

    # --- BLS: household and establishment surveys ------------------------
    ReleaseRule("UNRATE", MONTHLY, 12,
                "employment situation, first Friday after month end plus a "
                "week of margin"),
    ReleaseRule("U6RATE", MONTHLY, 12, "same release as UNRATE"),
    ReleaseRule("CIVPART", MONTHLY, 12, "same release as UNRATE"),
    ReleaseRule("EMRATIO", MONTHLY, 12, "same release as UNRATE"),
    ReleaseRule("CPIAUCSL", MONTHLY, 20,
                "CPI lands around the 13th of the following month; 20 days "
                "after month end is deliberately late"),
    ReleaseRule("JTSQUR", MONTHLY, 40,
                "JOLTS runs about a month behind the employment situation"),

    # --- BEA ------------------------------------------------------------
    ReleaseRule("PSAVERT", MONTHLY, 30,
                "personal income and outlays, roughly four weeks out"),
    ReleaseRule("PCEC96", MONTHLY, 30, "published with PSAVERT"),
    ReleaseRule("GDPC1", QUARTERLY, 30,
                "advance estimate about four weeks after the quarter ENDS -- "
                "measured from the quarter end, not from the quarter label"),

    # --- Federal Reserve --------------------------------------------------
    ReleaseRule("DFF", DAILY, 1, "H.15, next business day"),
    ReleaseRule("DGS2", DAILY, 1, "H.15, next business day"),
    ReleaseRule("DGS10", DAILY, 1, "H.15, next business day"),
    ReleaseRule("INDPRO", MONTHLY, 20,
                "G.17 industrial production, mid-following-month"),
    ReleaseRule("REVOLSL", MONTHLY, 40, "G.19 consumer credit"),
    ReleaseRule("TDSP", QUARTERLY, 70,
                "household debt service ratio, published well after the "
                "quarter it describes"),
    ReleaseRule("DRCCLACBS", QUARTERLY, 60,
                "charge-off and delinquency rates, about two months after "
                "the quarter ends"),
    ReleaseRule("CORCACBS", QUARTERLY, 60, "published with DRCCLACBS"),
    ReleaseRule("DRSFRMACBS", QUARTERLY, 60, "published with DRCCLACBS"),
    ReleaseRule("BOGZ1FL153064486Q", QUARTERLY, 75,
                "Z.1 financial accounts, about ten weeks after quarter end"),

    # --- Census -----------------------------------------------------------
    ReleaseRule("HOUST", MONTHLY, 20, "new residential construction"),
    ReleaseRule("HSN1F", MONTHLY, 25, "new residential sales"),
    ReleaseRule("DGORDER", MONTHLY, 35, "advance durable goods, then full M3"),
    ReleaseRule("BABATOTALSAUS", MONTHLY, 35, "business formation statistics"),

    # --- market data -------------------------------------------------------
    ReleaseRule("BAMLH0A0HYM2", DAILY, 1, "index level, next business day"),
)

BY_ID: Dict[str, ReleaseRule] = {r.series_id: r for r in RULES}


def rule_for(series_id: str) -> ReleaseRule:
    r = BY_ID.get(series_id)
    if r is None:
        raise ReleaseLeak(
            f"{series_id} has no release rule. A series with no publication "
            "timing cannot be walled at a monthly origin: the code would "
            "have to guess, and the guess that feels natural -- 'the period "
            "label is before the origin, so it is available' -- is the leak "
            "this module exists to stop.")
    return r


def released_at(series_id: str, period: str) -> str:
    """When `period` of `series_id` first became public."""
    return rule_for(series_id).released_at(period)


def available_as_of(series_id: str, timestamp: str) -> str:
    """The LATEST period of `series_id` that had been released by `timestamp`.

    Returns "" when nothing had been. This is the function §4 asks for and it
    is the only place the answer is computed, so a break proof that shifts a
    release backward has exactly one thing to break.
    """
    require(bool(timestamp), "available_as_of needs a timestamp")
    rule = rule_for(series_id)
    # Walk back from the timestamp's own month until a period is released.
    y, m = int(timestamp[:4]), int(timestamp[5:7])
    span = max(1, SPAN_MONTHS[rule.frequency])
    for _ in range(0, 400):
        if rule.frequency == QUARTERLY:
            qm = ((m - 1) // 3) * 3 + 1
            period = f"{y}-{qm:02d}-01"
        elif rule.frequency == DAILY:
            period = f"{y}-{m:02d}-01"
        else:
            period = f"{y}-{m:02d}-01"
        if rule.released_at(period) <= timestamp:
            return period
        m -= span
        while m <= 0:
            m += 12
            y -= 1
    return ""


def assert_released(series_id: str, period: str, used_at: str) -> None:
    """Refuse a read of `period` at `used_at` if it was not out yet."""
    r = released_at(series_id, period)
    if r > used_at:
        raise ReleaseLeak(
            f"{series_id} {period} was released {r}; a forecast made "
            f"{used_at} cannot have read it. The period label being earlier "
            "than the origin is not the same thing as the figure existing.")


def refuse_interpolation(series_id: str, periods: Sequence[str]) -> None:
    """A lower-frequency series must not appear at monthly resolution.

    §3: never turn one quarterly observation into three monthly facts. The
    fabricated months look like data, carry no new information, and inflate
    every sample count downstream by a factor of three.
    """
    rule = rule_for(series_id)
    if rule.frequency != QUARTERLY:
        return
    bad = sorted(p for p in periods if int(p[5:7]) not in (1, 4, 7, 10))
    if bad:
        raise InterpolationRefused(
            f"{series_id} is QUARTERLY but carries {len(bad)} observation(s) "
            f"in non-quarter months (e.g. {bad[:3]}). Those are interpolated "
            "months, not observations: they add rows and no information, and "
            "every count computed from them is inflated.")


def summarise() -> dict:
    by_freq: Dict[str, int] = {}
    for r in RULES:
        by_freq[r.frequency] = by_freq.get(r.frequency, 0) + 1
    return {"contract": CONTRACT, "rules": len(RULES),
            "by_frequency": by_freq,
            "series": {r.series_id: r.as_dict() for r in RULES}}
