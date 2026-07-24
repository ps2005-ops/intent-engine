"""US equity market calendar — market-calendar awareness for scheduled jobs.

Stdlib only (A3), deterministic. Weekends are closed; a curated NYSE holiday
set covers the years the platform runs. This is intentionally simple and
auditable — it is used to decide "should the daily market job run today",
not to time intraday execution (there is no execution — paper only).

If a year is not covered, `is_market_day` still excludes weekends and the
job's own freshness checks catch a stale/holiday day; unknown-year holidays
degrade to "treat as open", never to a crash.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - zoneinfo always present on 3.9+ backport
    _NY = None

# NYSE full-day closures, 2024-2027 (New Year, MLK, Washington, Good Friday,
# Memorial, Juneteenth, Independence, Labor, Thanksgiving, Christmas — with
# observed-date shifts). Curated, not computed, so it is auditable.
_HOLIDAYS = {
    # 2025
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def now_ny() -> datetime:
    """Timezone-aware 'now' in market time. Jobs must be tz-aware, not
    laptop-local."""
    if _NY is not None:
        return datetime.now(_NY)
    return datetime.utcnow()


def today_ny() -> date:
    return now_ny().date()


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_market_day(d: date | None = None) -> bool:
    d = d or today_ny()
    if is_weekend(d):
        return False
    return d.isoformat() not in _HOLIDAYS


def previous_market_day(d: date | None = None) -> date:
    d = d or today_ny()
    cur = d - timedelta(days=1)
    for _ in range(10):
        if is_market_day(cur):
            return cur
        cur -= timedelta(days=1)
    return cur  # pragma: no cover - >10 consecutive closed days impossible
