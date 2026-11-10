"""§4: score every V3 candidate against the incumbent it claims to extend."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import episodes as EPI               # noqa: E402
from intent_engine.econ import equivalence as EQ             # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402
from intent_engine.market import alfred as AL                # noqa: E402
from intent_engine.market import alfred_cache as AC          # noqa: E402

OUT = pathlib.Path("reports/panel/equivalence.json")

#: candidate -> (incumbent, construct, expected sign)
#:
#: The SIGN is declared here, before scoring. A credit spread RISES when
#: household credit stress rises, so it is +1 against delinquency. Mean
#: unemployment duration rises when the quits rate FALLS, so it is -1 against
#: JTSQUR. Getting a sign backwards would turn a good proxy into a refused
#: one and vice versa, which is why they are written down rather than fitted.
PAIRS = [
    ("BAA10Y", "DRCCLACBS", "credit_stress", 1),
    ("AAA10Y", "DRCCLACBS", "credit_stress", 1),
    ("BAA", "DRCCLACBS", "credit_stress", 1),
    ("T10Y3M", "BAMLH0A0HYM2", "financial_conditions", -1),
    ("UMCSENT1", "UMCSENT", "survey_expectation", 1),
    ("UEMPMEAN", "JTSQUR", "labour_mobility", -1),
    ("UEMP15OV", "JTSQUR", "labour_mobility", -1),
    # A CANDIDATE IS SCORED AGAINST THE INCUMBENT IT WOULD ACTUALLY REPLACE.
    #
    # The two duration series were first scored against JTSQUR because the
    # candidate list called them a pre-JOLTS quits proxy. They are not:
    # duration measures how long a spell lasts, and the quits rate measures
    # how willingly people leave. The construct they belong to is
    # UNDEREMPLOYMENT, whose live instrument is U6RATE -- so they are scored
    # against that as well, and BOTH pairings are reported. Testing against
    # one incumbent and reporting the other would be choosing the comparison
    # after seeing it.
    ("UEMPMEAN", "U6RATE", "underemployment", 1),
    ("UEMP15OV", "U6RATE", "underemployment", 1),
]


def _series(sid):
    """Current values, monthly-aligned. Equivalence is about SHAPE, so the
    current vintage is the right read: both sides get the same treatment and
    neither is being used as a walled model input here."""
    try:
        body = AC.fetch_one(sid, "")[0]
    except Exception:                                       # noqa: BLE001
        return []
    _col, rows = AL._parse_csv(body)
    by_month = {}
    for period, value in rows:
        by_month[period[:7] + "-01"] = value      # last reading in a month
    return sorted(by_month.items())


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    man = json.loads(pathlib.Path(
        "reports/panel/historical_acquisition_manifest.json").read_text())
    origins = man["origins_deep"] + man["origins_modern"]
    readings = RG.classify_many(panel, origins)
    eps = EPI.discover(readings)
    crisis = sorted({o[:7] + "-01" for e in eps for o in e.origins})
    print(f"=== §4 EQUIVALENCE === {len(eps)} episodes, "
          f"{len(crisis)} stressed months as the crisis window\n")

    results = []
    for cand, inc, construct, sign in PAIRS:
        a, b = _series(cand), _series(inc)
        r = EQ.compare(candidate=cand, incumbent=inc, construct=construct,
                       candidate_series=a, incumbent_series=b,
                       expected_sign=sign, crisis_periods=crisis)
        results.append(r)
        print(f"  {r.statement()}")
        print()

    s = EQ.summarise(results)
    OUT.write_text(json.dumps(s, indent=2, sort_keys=True))
    print(f"  by verdict: {json.dumps(s['by_verdict'])}")
    print(f"  splice allowed: {s['splice_allowed'] or 'none'}")
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
