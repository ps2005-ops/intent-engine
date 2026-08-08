"""Real economic figures, from keyless public publishers.

WHAT THIS IS FOR
----------------
`macro_state` can hold a dated opinion about the economy. Until something
fills it, every economic chain in the engine starts at an UNKNOWN
MACRO_STATE node and no link below it can ever reach SUPPORTED. This is the
part that fills it.

WHY THESE SOURCES
-----------------
Treasury FiscalData is keyless, versioned, deep, and publishes the one thing
almost every transmission story starts from — the cost of money. It is chosen
because it is REACHABLE without an owner action, not because it is the most
informative series available. FRED would be better and needs a key the
environment does not have; when that key exists, adding it is a new entry in
`SERIES` and nothing else changes.

THE HONEST PART
---------------
FiscalData gives `record_date` — the month the figure describes — and no
release date at all. Neither easy answer is acceptable: an empty publication
date makes the figure unusable at any as-of, and treating `record_date` as the
release date claims the engine knew July's average rate on the 31st of July.

So publication is ASSUMED, with a deliberately generous lag, and the
assumption is carried on the observation rather than hidden in it. Erring late
can only make the engine look like it knew less than it did — which is the
safe direction, because the failure being guarded against is foresight the
engine never had.
"""
from __future__ import annotations

import datetime
import json
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Sequence

from . import macro_state as MS

CONTRACT = "macro_ingest.v1"

_FISCAL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
           "/v2/accounting/od/avg_interest_rates")

_TIMEOUT = 30
_HEADERS = {"User-Agent": "intent-engine/4.0 (economic world model)"}

#: How late a monthly Treasury dataset is ASSUMED to have been released.
#: The real release is a handful of business days into the following month;
#: 30 days is comfortably later than that, and later is the safe direction.
MONTHLY_PUBLICATION_LAG_DAYS = 30


def _http_get(url: str):  # pragma: no cover - exercised by the live path
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _assumed_publication(reference_period: str, lag_days: int) -> str:
    """A release date the engine is willing to be wrong about in one direction.

    Later than the truth means the engine under-claims what it knew. Earlier
    would mean it claims a figure before the publisher had it, which is
    exactly the leak `known_at` exists to stop.
    """
    day = datetime.date.fromisoformat(reference_period[:10])
    return (day + datetime.timedelta(days=lag_days)).isoformat()


def _rows(body) -> List[dict]:
    return [r for r in ((body or {}).get("data") or []) if isinstance(r, dict)]


def treasury_note_rate(*, retrieved_at: str, periods: int = 24,
                       fetcher: Optional[Callable] = None
                       ) -> List[MS.MacroObservation]:
    """Average interest rate on outstanding Treasury notes, by month.

    This is a MARKET_RATE, not a POLICY_RATE. The distinction matters: the
    average rate the Treasury actually pays reflects the whole outstanding
    stock and moves slowly, while a policy rate is set. Calling this a policy
    rate would let a slow-moving average be read as a central-bank decision.
    """
    get = fetcher or _http_get
    query = urllib.parse.urlencode({
        "filter": "security_desc:eq:Treasury Notes",
        "sort": "-record_date", "page[size]": str(periods)})
    body = get(f"{_FISCAL}?{query}")

    out: List[MS.MacroObservation] = []
    for row in _rows(body):
        period = str(row.get("record_date") or "")
        raw = row.get("avg_interest_rate_amt")
        if not period or raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        out.append(MS.MacroObservation(
            state_kind=MS.MARKET_RATE,
            series_id="TREASURY_NOTES_AVG_RATE",
            label="Average interest rate on outstanding Treasury notes",
            value=value, unit="%", measure=MS.LEVEL,
            standing=MS.OBSERVED,
            reference_period=period,
            published_at=_assumed_publication(
                period, MONTHLY_PUBLICATION_LAG_DAYS),
            publication_basis=MS.ASSUMED_LAG,
            retrieved_at=retrieved_at,
            source="US Treasury, FiscalData",
            note=("release date not published by the source; assumed "
                  f"{MONTHLY_PUBLICATION_LAG_DAYS} days after period end")))
    return out


#: series key -> builder. A new keyless publisher is one entry here.
SERIES = {
    "treasury_note_rate": treasury_note_rate,
}


def collect(*, retrieved_at: str, only: Sequence[str] = (),
            fetcher: Optional[Callable] = None) -> dict:
    """Fetch every configured series, and report what failed rather than
    silently returning fewer observations.

    A source that errors must not look like a source that had nothing to say:
    the first is a broken adapter and the second is an economy that did not
    move, and treating them alike is how a dead feed goes unnoticed for weeks.
    """
    wanted = [k for k in SERIES if not only or k in only]
    observations: List[MS.MacroObservation] = []
    failures = {}
    for key in wanted:
        try:
            observations.extend(
                SERIES[key](retrieved_at=retrieved_at, fetcher=fetcher))
        except Exception as exc:  # noqa: BLE001 - a feed must not fail a cycle
            failures[key] = f"{type(exc).__name__}: {exc}"
    return {
        "contract": CONTRACT,
        "series_attempted": len(wanted),
        "series_failed": sorted(failures),
        "failures": failures,
        "observations": observations,
        "observation_count": len(observations),
        "periods_covered": sorted({o.reference_period for o in observations}),
    }
