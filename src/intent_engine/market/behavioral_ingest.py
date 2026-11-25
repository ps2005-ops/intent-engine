"""Public behavioural observations, from publishers that answer without a key.

WHY THIS IS SEPARATE FROM `macro_ingest`
----------------------------------------
Not squeamishness about file size. A behavioural observation is a measurement
OF PEOPLE, and Section 4 keeps that family typed apart from the macro family
precisely so the engine can ask whether people showed something the
aggregates had not. If quits arrived through the macro adapter and were filed
as MACRO/labour, the question would be unaskable: the collective-state layer
would be reading the same rows the economic layer already used, and every
comparison would be a model against itself.

WHAT IS ACTUALLY READABLE
-------------------------
Less than the vocabulary would suggest, and `econ.series.behavioural_coverage`
says so. The genuinely keyless, genuinely public behavioural series are the
BLS ones: JOLTS quits and labour-force participation. Everything else in the
declared family is either proprietary (trust barometers, retail order flow),
licence-restricted (search trends), or has no direct series at all
(trade-down). Those are marked UNAVAILABLE with reasons rather than
approximated, because an approximated behavioural series is indistinguishable
from an invented one once it is in the store.

NO FABRICATION, AND NO SILENT SHORTFALL
---------------------------------------
`collect` reports what failed. A publisher that refuses must not look like a
population that did not move.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from intent_engine.econ import evidence as EV
from intent_engine.econ import vocabulary as V

CONTRACT = "behavioral_ingest.v1"

_BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

#: BLS series id -> (behavioural kind, label, unit, publication lag days).
#: Every one of these is a REVEALED-PREFERENCE measure: what people did, not
#: what they told a pollster. That is deliberate -- the stated-preference
#: instruments in the vocabulary are the ones with the widest declared noise.
BLS_BEHAVIOURAL: Dict[str, Tuple[str, str, str, int]] = {
    "JTS000000000000000QUR": (
        "quits", "US quits rate, total nonfarm", "%", 40),
    "LNS11300000": (
        "labour_participation", "US labour force participation rate", "%", 20),
}

_MONTHS = {f"M{n:02d}": n for n in range(1, 13)}


def _http_post(url: str, payload):  # pragma: no cover - live path
    import json
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "intent-engine research (contact in repo)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _as_float(raw) -> Optional[float]:
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _published(period: str, lag_days: int) -> str:
    """When this figure became knowable, assumed from the publication lag.

    An ASSUMPTION, and recorded as one on the node. `replay.assert_vintage`
    reads `available_at`, so getting this wrong leaks hindsight into every
    historical comparison -- which is why the lag is per-series rather than
    one constant.
    """
    import datetime as _dt
    y, m, d = (int(x) for x in period.split("-"))
    # End of the reference month, plus the lag.
    nxt = _dt.date(y + (m == 12), (m % 12) + 1, 1)
    return (nxt + _dt.timedelta(days=lag_days)).isoformat()


def bureau_of_labor_statistics(*, retrieved_at: str, periods: int = 24,
                               fetcher: Optional[Callable] = None
                               ) -> List[EV.EconomicNode]:
    """JOLTS quits and labour participation, as BEHAVIORAL evidence nodes."""
    post = fetcher or _http_post
    year = int(retrieved_at[:4])
    body = post(_BLS, {"seriesid": sorted(BLS_BEHAVIOURAL),
                       "startyear": str(year - max(1, periods // 12)),
                       "endyear": str(year)})
    if (body or {}).get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(
            "BLS refused the request: "
            f"{(body or {}).get('status')} {(body or {}).get('message')}")
    out: List[EV.EconomicNode] = []
    for series in ((body.get("Results") or {}).get("series") or []):
        spec = BLS_BEHAVIOURAL.get(series.get("seriesID"))
        if not spec:
            continue
        kind, label, unit, lag = spec
        for point in series.get("data") or []:
            month = _MONTHS.get(str(point.get("period") or ""))
            value = _as_float(point.get("value"))
            if not month or value is None:
                continue
            period = f"{point.get('year')}-{month:02d}-01"
            available = _published(period, lag)
            out.append(EV.node(
                node_class=V.BEHAVIORAL, kind=kind,
                subject="US_households", standing=V.OBSERVED,
                occurred_at=period, available_at=available, value=value,
                unit=unit, statement=f"{label}: {value}{unit} for {period}",
                publisher="US Bureau of Labor Statistics",
                venue="api.bls.gov",
                document_id=str(series.get("seriesID")),
                producer=CONTRACT,
                confidence=0.85, retrieved_at=retrieved_at))
    return out


#: BLS series -> its exact FRED mirror. Used ONLY when BLS refuses.
#:
#: WHY: from the production runtime BLS answers "the daily threshold for ...
#: registration key '' has been reached" -- the adapter calls without a key,
#: the anonymous quota is shared with the macro adapter, and the collective
#: layer received ZERO behavioural nodes, so `econ.bayes.update` never ran
#: (traced 2026-11-25). FRED republishes the same BLS series under a key the
#: runtime already has, and ALFRED supplies the REAL first-publication date,
#: which replaces the assumed lag rather than adding a second copy.
FRED_MIRRORS: Dict[str, str] = {"JTS000000000000000QUR": "JTSQUR",
                                "LNS11300000": "CIVPART"}


def _fred_get(series_id: str, start: str, end: str):  # pragma: no cover - live
    import json, os, urllib.parse, urllib.request
    key = os.environ.get("FRED_API_KEY")
    if not key:
        from dotenv import load_dotenv
        load_dotenv()
        key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is not set")
    q = {"series_id": series_id, "api_key": key, "file_type": "json",
         "observation_start": start, "realtime_start": "1776-07-04",
         "realtime_end": end, "output_type": "4"}   # 4 = first release only
    with urllib.request.urlopen("https://api.stlouisfed.org/fred/series/"
                                "observations?" + urllib.parse.urlencode(q),
                                timeout=30) as r:
        return json.load(r)["observations"]


def fred_mirror_of_bls(*, retrieved_at: str, periods: int = 24,
                       fetcher: Optional[Callable] = None
                       ) -> List[EV.EconomicNode]:
    """The BLS behavioural series as first released, via FRED/ALFRED."""
    import datetime as _dt
    get = fetcher or _fred_get
    start = (_dt.date.fromisoformat(retrieved_at[:10])
             - _dt.timedelta(days=31 * (periods + 1))).isoformat()
    out: List[EV.EconomicNode] = []
    for bls_id, fred_id in sorted(FRED_MIRRORS.items()):
        kind, label, unit, _lag = BLS_BEHAVIOURAL[bls_id]
        for o in get(fred_id, start, retrieved_at[:10]):
            value = _as_float(o.get("value"))
            if value is None:
                continue
            published = str(o.get("realtime_start") or "")
            if not published or published > retrieved_at[:10]:
                continue                      # not knowable yet
            out.append(EV.node(
                node_class=V.BEHAVIORAL, kind=kind, subject="US_households",
                standing=V.OBSERVED, occurred_at=o["date"],
                available_at=published, value=value, unit=unit,
                statement=f"{label}: {value}{unit} for {o['date']} "
                          f"(first release {published})",
                publisher="US Bureau of Labor Statistics",
                venue=f"api.stlouisfed.org (FRED mirror {fred_id} of BLS {bls_id})",
                document_id=bls_id, producer=CONTRACT, confidence=0.85,
                retrieved_at=retrieved_at))
    return out


def bls_with_fred_fallback(*, retrieved_at: str, periods: int = 24,
                           fetcher: Optional[Callable] = None,
                           fred_fetcher: Optional[Callable] = None
                           ) -> List[EV.EconomicNode]:
    """BLS first; the FRED mirror only if BLS refuses. Never both, so one
    observation can never arrive twice under two venues."""
    try:
        return bureau_of_labor_statistics(retrieved_at=retrieved_at,
                                          periods=periods, fetcher=fetcher)
    except RuntimeError as exc:
        # An injected BLS double with no FRED double is a test of the BLS
        # path: never reach a live network from it.
        if "refused" not in str(exc) or (fetcher is not None
                                         and fred_fetcher is None):
            raise
        return fred_mirror_of_bls(retrieved_at=retrieved_at, periods=periods,
                                  fetcher=fred_fetcher)


#: key -> builder. A new keyless behavioural publisher is one entry here.
SOURCES: Dict[str, Callable] = {
    "bureau_of_labor_statistics": bls_with_fred_fallback,
}

#: Which adapters speak POST. Same trap as `macro_ingest.POST_SERIES`: an
#: injected double called with the wrong arity TypeErrors against half the
#: sources, and a test using one would pass against the other half.
POST_SOURCES = frozenset({"bureau_of_labor_statistics"})


def collect(*, retrieved_at: str, only: Sequence[str] = (),
            poster: Optional[Callable] = None) -> dict:
    """Fetch every configured behavioural source, reporting what failed."""
    wanted = [k for k in SOURCES if not only or k in only]
    nodes: List[EV.EconomicNode] = []
    failures: Dict[str, str] = {}
    for key in wanted:
        injected = poster if key in POST_SOURCES else None
        try:
            nodes.extend(SOURCES[key](retrieved_at=retrieved_at,
                                      fetcher=injected))
        except Exception as exc:  # noqa: BLE001 - a feed must not fail a cycle
            failures[key] = f"{type(exc).__name__}: {exc}"
    by_kind: Dict[str, int] = {}
    for n in nodes:
        by_kind[n.kind] = by_kind.get(n.kind, 0) + 1
    return {"contract": CONTRACT, "nodes": nodes,
            "collected": len(nodes), "by_kind": by_kind,
            "sources_attempted": len(wanted),
            "sources_failed": failures,
            # Named so an empty result is never ambiguous between "the
            # publisher had nothing" and "the adapter is broken".
            "empty_because": ("" if nodes else
                              ("every source failed" if failures else
                               "sources answered with no usable rows"))}
