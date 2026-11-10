"""Day 2: SEC filing events as a signal source, tested point-in-time.

Genuinely different information from Day 1. A filing date from EDGAR is the
date the document became public, so conditioning on it introduces no knowledge
that did not exist then — unlike a company website, which shows today's content
and cannot be used to reconstruct a historical decision.

Lookahead is refused in three places:
  * entry is the NEXT close after the filing date, because a filing published
    after the session is not tradable at that session's close;
  * `PriceSeries.on` never returns a close after the date requested;
  * a horizon that has not elapsed is skipped, never graded against the latest
    available price.
"""
import collections
import json
import math
import pathlib
import sys
import time
import urllib.request
from datetime import date, timedelta

from intent_engine.market.prices import PriceUnavailable, fetch_series
from intent_engine.market.sampling import band, measure
from intent_engine.universe.companies import default_universe

HORIZON = 21
EVENT_FORMS = {"8-K", "6-K"}
REPORT_FORMS = {"10-Q", "10-K", "20-F", "40-F"}
# Day 3: more event TYPES, because each is a different information shock and
# therefore a different independent event -- not merely more rows of the same
# kind. Ownership and proxy filings were excluded on Day 2 for no reason
# beyond not having thought of them.
OWNERSHIP_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "4"}
PROXY_FORMS = {"DEF 14A", "DEFA14A", "8-K/A", "10-Q/A", "10-K/A"}
ALL_FORMS = EVENT_FORMS | REPORT_FORMS | OWNERSHIP_FORMS | PROXY_FORMS
HISTORY_RANGE = "10y"
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/eventbake")
OUT.mkdir(parents=True, exist_ok=True)
_UA = {"User-Agent": "intent-engine research (contact: ops@example.com)"}


def _tickers_to_cik():
    req = urllib.request.Request(
        "https://www.sec.gov/files/company_tickers.json", headers=_UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        rows = json.loads(r.read().decode())
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in rows.values()}


def _filings(cik10):
    req = urllib.request.Request(
        f"https://data.sec.gov/submissions/CIK{cik10}.json", headers=_UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        recent = json.loads(r.read().decode())["filings"]["recent"]
    return list(zip(recent["form"], recent["filingDate"]))


def _next_close_after(series, day):
    """The first close strictly AFTER `day` — the earliest tradable price for a
    filing that may have been published after the session."""
    later = sorted(d for d in series.closes if d > day)
    return (later[0], series.closes[later[0]]) if later else (None, None)


def main():
    universe = [c for c in default_universe().prediction_companies()
                if c.tradable_instrument]
    try:
        cik_map = _tickers_to_cik()
    except Exception as exc:                            # noqa: BLE001
        print(f"EDGAR ticker map unavailable: {exc}")
        return []

    results = {name: {"n": 0, "correct": 0, "rows": []}
               for name in ("event_drift.v1", "report_drift.v1",
                            "ownership_drift.v1", "proxy_drift.v1")}
    per_form = collections.defaultdict(lambda: [0, 0])
    skipped = collections.Counter()
    covered = 0

    for company in universe:
        symbol = company.tradable_instrument
        cik = cik_map.get(symbol.upper())
        if not cik:
            skipped["no_cik"] += 1
            continue
        try:
            series = fetch_series(symbol, range_=HISTORY_RANGE)
            filings = _filings(cik)
        except (PriceUnavailable, Exception) as exc:    # noqa: BLE001
            skipped["fetch_failed"] += 1
            continue
        time.sleep(0.15)                                # SEC fair-access
        covered += 1

        first_close = min(series.closes) if series.closes else None
        for form, filed in filings:
            if form not in ALL_FORMS:
                continue
            if first_close is None or filed < first_close:
                skipped["before_price_history"] += 1
                continue
            prior = series.on(filed)
            entry_day, entry = _next_close_after(series, filed)
            if prior is None or entry is None:
                skipped["no_price"] += 1
                continue
            reaction = (prior - series.on(
                (date.fromisoformat(filed) - timedelta(days=5)).isoformat()
            )) if series.on(
                (date.fromisoformat(filed) - timedelta(days=5)).isoformat()
            ) else None
            if not reaction:
                skipped["no_reaction"] += 1
                continue
            exit_day = (date.fromisoformat(entry_day)
                        + timedelta(days=HORIZON)).isoformat()
            if series.as_of is None or exit_day > series.as_of:
                skipped["horizon_not_elapsed"] += 1
                continue
            exit_price = series.on(exit_day)
            if exit_price is None:
                skipped["no_exit"] += 1
                continue

            direction = "up" if reaction > 0 else "down"
            move = (exit_price - entry) / entry
            right = (move > 0) if direction == "up" else (move < 0)
            name = ("event_drift.v1" if form in EVENT_FORMS
                    else "report_drift.v1" if form in REPORT_FORMS
                    else "ownership_drift.v1" if form in OWNERSHIP_FORMS
                    else "proxy_drift.v1")
            results[name]["n"] += 1
            results[name]["correct"] += 1 if right else 0
            results[name]["rows"].append({
                "company_id": company.company_id, "entry_day": entry_day,
                "exit_day": exit_day,
                "event_key": f"{company.company_id}:{form}:{filed}"})
            per_form[form][0] += 1
            per_form[form][1] += 1 if right else 0

    print("=" * 72)
    print("DAY 2 — SEC FILING EVENTS, point-in-time")
    print("=" * 72)
    print(f"companies with CIK + prices: {covered}/{len(universe)}")
    print(f"skipped: {dict(skipped)}\n")
    print(f"{'signal':<20}{'rows':>6}{'events':>8}{'windows':>9}{'n_eff':>7}"
          f"{'DE':>6}{'acc':>8}  verdict")
    rows = []
    for name, r in results.items():
        n, c = r["n"], r["correct"]
        acc = round(c / n, 4) if n else None
        size = measure(r["rows"])
        verdict = band(acc, size)
        rows.append({"signal": name, **verdict})
        print(f"{name:<20}{size.observations:>6}{size.events:>8}"
              f"{size.windows:>9}{size.n_eff:>7}"
              f"{str(size.design_effect):>6}"
              f"{(acc if acc is not None else '—'):>8}  {verdict['verdict']}")

    print("\nby form type:")
    for form, (n, c) in sorted(per_form.items()):
        print(f"  {form:<8}n={n:<5}{round(c/n,3) if n else '—'}")
    (OUT / "events.json").write_text(json.dumps(
        {"results": rows, "by_form": {k: v for k, v in per_form.items()},
         "skipped": dict(skipped)}, indent=1))
    return rows


if __name__ == "__main__":
    main()
