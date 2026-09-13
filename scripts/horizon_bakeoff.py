"""Day 4: each hypothesis at the horizon its mechanism implies.

Horizons are pre-registered and justified before running (see
PREREGISTRATION_day4_horizons.md), fixed for the whole evaluation, and never
chosen for power. Where a mechanism resolves slowly, a low n_eff is a true
statement about how much evidence exists.

Reports time-to-resolution alongside n_eff, because the two are the same
trade-off seen from opposite ends.
"""
import collections
import json
import pathlib
import sys
import time
import urllib.request
from datetime import date, timedelta

from intent_engine.market.prices import PriceUnavailable, fetch_series
from intent_engine.market.sampling import band, measure
from intent_engine.universe.companies import default_universe

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/day4")
OUT.mkdir(parents=True, exist_ok=True)
_UA = {"User-Agent": "intent-engine research (contact: ops@example.com)"}
RANGE = "10y"

# (forms, horizon_days, mechanism) — horizon justified in the pre-registration
# and NOT tunable here. Changing one is a new pre-registration, not a knob.
HYPOTHESES = {
    "report_drift.v1":   ({"10-Q", "10-K", "20-F", "40-F"}, 5),
    "event_drift.v1":    ({"8-K", "6-K"}, 3),
    "insider_buy.v1":    ({"4"}, 90),
    "activist_stake.v1": ({"SC 13D", "SC 13D/A"}, 120),
    "proxy_drift.v1":    ({"DEF 14A", "DEFA14A"}, 90),
}


def _cik_map():
    req = urllib.request.Request(
        "https://www.sec.gov/files/company_tickers.json", headers=_UA)
    rows = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in rows.values()}


def _filings(cik10):
    req = urllib.request.Request(
        f"https://data.sec.gov/submissions/CIK{cik10}.json", headers=_UA)
    recent = json.loads(urllib.request.urlopen(
        req, timeout=25).read().decode())["filings"]["recent"]
    return list(zip(recent["form"], recent["filingDate"]))


def main():
    universe = [c for c in default_universe().prediction_companies()
                if c.tradable_instrument]
    cik = _cik_map()
    acc = {n: {"n": 0, "correct": 0, "rows": [], "days": []}
           for n in HYPOTHESES}

    for company in universe:
        symbol = company.tradable_instrument
        k = cik.get(symbol.upper())
        if not k:
            continue
        try:
            series = fetch_series(symbol, range_=RANGE)
            filings = _filings(k)
        except Exception:                                # noqa: BLE001
            continue
        time.sleep(0.15)
        first = min(series.closes) if series.closes else None
        if not first:
            continue

        for name, (forms, horizon) in HYPOTHESES.items():
            for form, filed in filings:
                if form not in forms or filed < first:
                    continue
                base_day = (date.fromisoformat(filed)
                            - timedelta(days=5)).isoformat()
                prior, base = series.on(filed), series.on(base_day)
                if prior is None or base is None or prior == base:
                    continue
                later = sorted(d for d in series.closes if d > filed)
                if not later:
                    continue
                entry_day = later[0]
                entry = series.closes[entry_day]
                exit_day = (date.fromisoformat(entry_day)
                            + timedelta(days=horizon)).isoformat()
                if series.as_of is None or exit_day > series.as_of:
                    continue
                exit_price = series.on(exit_day)
                if exit_price is None:
                    continue
                direction = "up" if prior - base > 0 else "down"
                move = (exit_price - entry) / entry
                right = (move > 0) if direction == "up" else (move < 0)
                acc[name]["n"] += 1
                acc[name]["correct"] += 1 if right else 0
                acc[name]["days"].append(horizon)
                acc[name]["rows"].append({
                    "company_id": company.company_id, "entry_day": entry_day,
                    "exit_day": exit_day,
                    "event_key": f"{company.company_id}:{form}:{filed}"})

    print("=" * 84)
    print("DAY 4 — hypothesis-specific horizons, pre-registered and fixed")
    print("=" * 84)
    print(f"{'hypothesis':<20}{'horiz':>6}{'rows':>7}{'events':>8}"
          f"{'windows':>9}{'n_eff':>7}{'DE':>8}{'acc':>8}  verdict")
    out = []
    for name, (forms, horizon) in HYPOTHESES.items():
        r = acc[name]
        n, c = r["n"], r["correct"]
        a = round(c / n, 4) if n else None
        size = measure(r["rows"])
        v = band(a, size)
        retire = ("RETIRE — unmeasurable" if size.n_eff < 30 else
                  "RETIRE — on baseline"
                  if "indistinguishable" in v["verdict"] else "KEEP")
        out.append({"hypothesis": name, "horizon_days": horizon,
                    "retire": retire, **v})
        print(f"{name:<20}{horizon:>5}d{size.observations:>7}{size.events:>8}"
              f"{size.windows:>9}{size.n_eff:>7}"
              f"{str(size.design_effect):>8}"
              f"{(a if a is not None else '—'):>8}  {retire}")

    print(f"\n{'hypothesis':<20}{'2σ band on n_eff':>22}"
          f"{'naive band':>22}")
    for row in out:
        if row.get("band"):
            print(f"{row['hypothesis']:<20}{str(row['band']):>22}"
                  f"{str(row.get('naive_band')):>22}")

    total_windows = sum(measure(acc[n]["rows"]).windows for n in HYPOTHESES)
    measurable = sum(1 for r in out if r["n_eff"] >= 30)
    print(f"\nmeasurable hypotheses (n_eff>=30): {measurable}/{len(out)}")
    print(f"total independent windows across all: {total_windows}")
    (OUT / "day4.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main()
