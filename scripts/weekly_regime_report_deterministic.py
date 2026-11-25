#!/usr/bin/env python
"""Weekly regime report, deterministic. Replaces the LLM-dependent
`generate_weekly_regime_report.py` (failing on Anthropic credit since August).

WHAT IT DOES
  Reads the five series `econ.regime.classify` uses from ALFRED, AS KNOWN on
  the report date (realtime bounded to that date), and prints every regime
  label together with the quantity, the threshold and the margin.

WHAT IT DELIBERATELY DOES NOT DO
  * No predictions. The old report drafted market forecasts through an LLM;
    those became the defective July contracts. Forecasts now come only from
    the preregistered paper protocol, through the forecast-quality gate.
  * No causal claims and no "mechanisms in play". A regime label is a
    threshold on a standard quantity, not an explanation.
  * No label without its number. A value within 10% of its threshold is
    marked BORDERLINE, because "INFLATION_SHOCK" at 4.02% against a 4.00%
    line is a different statement from 6%.

DFF is requested as a MONTHLY AVERAGE (FRED `frequency=m`,
`aggregation_method=avg`), the convention of the historical panel the
thresholds were fixed on; `classify` counts periods, and a daily series
would make "a year" twelve days.

    PYTHONPATH=src python scripts/weekly_regime_report_deterministic.py --output FILE
"""
import argparse, datetime as dt, json, os, sys, urllib.parse, urllib.request

from intent_engine.econ import regime as RG
from intent_engine.econ.panel import Cell, Panel

SERIES = {"DRCCLACBS": {}, "UNRATE": {}, "CPIAUCSL": {}, "DGS2": {}, "DGS10": {},
          "DFF": {"frequency": "m", "aggregation_method": "avg"}}
# label -> (evidence key, threshold key, direction)
RULES = {
    RG.CREDIT_STRESS: ("delinquency_yoy", "credit_delinquency_yoy", ">="),
    RG.LABOUR_DETERIORATION: ("unemployment_change_pp", "unemployment_rise_pp", ">="),
    RG.RECOVERY: ("unemployment_change_pp", "unemployment_fall_pp", "<="),
    RG.INFLATION_SHOCK: ("inflation_yoy", "inflation_high", ">="),
    RG.DISINFLATION: ("inflation_yoy", "inflation_low", "<="),
    RG.POLICY_TIGHTENING: ("policy_change_pp", "policy_move_pp", ">="),
    RG.POLICY_EASING: ("policy_change_pp", "policy_move_pp", "<=-"),
    RG.LIQUIDITY_STRESS: ("curve_slope_pp", "curve_inversion_pp", "<"),
}
BORDER = 0.10


def _key():
    k = os.environ.get("FRED_API_KEY")
    if not k:
        from dotenv import load_dotenv
        load_dotenv()
        k = os.environ.get("FRED_API_KEY")
    if not k:
        raise SystemExit("FRED_API_KEY is not set")
    return k


def fetch(sid, as_of, extra, key):
    start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=3 * 365)).isoformat()
    q = {"series_id": sid, "api_key": key, "file_type": "json",
         "observation_start": start, "realtime_start": as_of,
         "realtime_end": as_of, **extra}
    with urllib.request.urlopen("https://api.stlouisfed.org/fred/series/observations?"
                                + urllib.parse.urlencode(q), timeout=30) as r:
        return [o for o in json.load(r)["observations"] if o["value"] != "."]


def build(as_of, fetcher=None):
    key = None if fetcher else _key()
    p, vint = Panel(), {}
    for sid, extra in SERIES.items():
        obs = (fetcher or (lambda s, a, e: fetch(s, a, e, key)))(sid, as_of, extra)
        for o in obs:
            # The value as known on `as_of`; its realtime_start is when that
            # vintage began, never later than as_of.
            p.add(Cell(series_id=sid, observed_at=o["date"],
                       vintage_at=max(o["date"], min(o["realtime_start"], as_of)),
                       value=float(o["value"]), source="ALFRED"))
        vint[sid] = obs[-1]["date"] if obs else None
    return p.finalise(), vint


def margin_line(label, ev):
    ek, tk, op = RULES[label]
    v, t = ev.get(ek), RG.THRESHOLDS[tk]
    t = -t if op == "<=-" else t
    if v is None:
        return f"{label}: input {ek} unavailable"
    span = abs(t) if t else 0.1
    border = abs(v - t) <= BORDER * span
    return (f"{label:22s} {ek} = {v:+.4f}  threshold {op.strip('-')} {t:+.4f}  "
            f"margin {v - t:+.4f}{'  BORDERLINE' if border else ''}")


def render(as_of, fetcher=None):
    panel, vint = build(as_of, fetcher)
    r = RG.classify(panel, as_of)
    lines = [f"REGIME READING (deterministic, {RG.CONTRACT}) as of {as_of}",
             "=" * 72,
             "Inputs as known on the report date (latest period per series):"]
    lines += [f"  {sid:10s} latest period {d}" for sid, d in vint.items()]
    lines += ["", "Regimes that hold:"]
    lines += [f"  {margin_line(x, r.evidence)}" for x in r.regimes if x in RULES] or ["  none"]
    if RG.LOW_VOL_EXPANSION in r.regimes:
        lines.append(f"  LOW_VOL_EXPANSION      no stress condition among "
                     f"{r.stress_families_evaluated} of 4 evaluated families")
    near = [x for x in RULES if x not in r.regimes and RULES[x][0] in r.evidence
            and abs(r.evidence[RULES[x][0]] - RG.THRESHOLDS[RULES[x][1]]
                    * (-1 if RULES[x][2] == "<=-" else 1))
            <= BORDER * (abs(RG.THRESHOLDS[RULES[x][1]]) or 0.1)]
    lines += ["", "Near a threshold but not holding:"]
    lines += [f"  {margin_line(x, r.evidence)}" for x in near] or ["  none"]
    lines += ["", f"Missing inputs: {', '.join(r.missing) or 'none'}",
              f"Stress families evaluated: {r.stress_families_evaluated} of 4", "",
              "WHAT THIS CANNOT TELL YOU",
              "  * It makes no forecast and records no prediction.",
              "  * A label is a fixed threshold on one standard quantity, not a",
              "    cause, a market call or an assessment of any company.",
              "  * Thresholds were fixed before results (econ/regime.py); they are",
              "    rules of thumb, not estimated breakpoints.",
              "  * In the 20-year replay, regime features did not improve forecasts",
              "    (logit_D below logit_B in every family)."]
    return "\n".join(lines) + "\n", r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    ap.add_argument("--output")
    a = ap.parse_args(argv)
    text, r = render(a.as_of)
    if a.output:
        if os.path.exists(a.output):
            raise SystemExit(f"refusing to overwrite {a.output}")
        open(a.output, "w").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
