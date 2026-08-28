"""§3/§4: candidate substitutes for the behavioural evidence that stops in 2011.

WHAT THE CEILING ACTUALLY IS
----------------------------
Not the origin grid, and not the data's start date. ALFRED's REAL-TIME ARCHIVE
for the credit and labour-flow series begins in 2011-2012, while the series
themselves run back to 1985-1991. So the modern construct is measurable and
un-walled before 2012, which is the same thing as unusable.

Two ways out, and only two:

  1. a series measuring the same construct whose ALFRED archive starts
     earlier;
  2. a series that is NEVER REVISED, for which the current values dated by
     publication lag are what a model would have seen -- the shortcut
     `alfred_cache.shortcut_allowed` already grants on measured evidence.

Market-priced quantities (corporate bond yields, Treasury spreads) fall in
the second class by construction: a closing yield is not restated. That is
why they dominate this candidate list even though none of them is a survey.

WHAT THIS SCRIPT REFUSES TO DO
------------------------------
Add a series because it goes back further. Every candidate names the construct
it is standing in for, and §4's overlap test decides whether it may. A proxy
that disagrees with the modern series during the years both exist is not a
longer version of it.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.market import alfred_cache as AC          # noqa: E402

OUT = pathlib.Path("reports/panel/behavioural_depth.json")

DIRECT_MEASURE = "DIRECT_MEASURE"
DEFENSIBLE_PROXY = "DEFENSIBLE_PROXY"
WEAK_PROXY = "WEAK_PROXY"
UNUSABLE = "UNUSABLE"
NO_VINTAGE_HISTORY = "NO_VINTAGE_HISTORY"

#: candidate -> (construct, the modern series it stands in for, why)
#:
#: Every entry names an INCUMBENT. A candidate with no incumbent cannot be
#: equivalence-tested and would be an addition on faith.
CANDIDATES = {
    # --- credit stress -------------------------------------------------
    "BAA10Y": ("credit_stress", "DRCCLACBS",
               "Moody's Baa corporate yield over the 10-year Treasury. A "
               "market price, so it is published once and never restated; "
               "daily from 1986 and the underlying Baa series from 1919"),
    "AAA10Y": ("credit_stress", "DRCCLACBS",
               "the investment-grade end of the same spread; a control on "
               "BAA10Y -- if only the low-grade spread moves, that is credit "
               "risk rather than the level of rates"),
    "BAA": ("credit_stress", "DRCCLACBS",
            "Moody's Baa yield itself, monthly from 1919, for the decades "
            "where the 10-year Treasury does not exist"),
    "TOTALSL": ("credit_conditions", "REVOLSL",
                "total consumer credit outstanding, G.19, from 1943"),
    "NONREVSL": ("credit_conditions", "REVOLSL",
                 "non-revolving consumer credit, the auto and student half"),
    "DRSFRMACBS": ("credit_stress", "DRCCLACBS",
                   "the incumbent's sibling; probed again for its own "
                   "earliest vintage"),

    # --- household balance sheet ---------------------------------------
    "CDSP": ("debt_service_burden", "TDSP",
             "consumer debt service payments as a share of disposable "
             "income; the same publication as TDSP and from 1980"),
    "HDTGPDUSQ163N": ("debt_service_burden", "TDSP",
                      "household debt to GDP; a stock where TDSP is a flow, "
                      "so it moves earlier and slower"),

    # --- labour flows --------------------------------------------------
    "UEMPMEAN": ("labour_mobility", "JTSQUR",
                 "mean duration of unemployment, from 1948. Long duration is "
                 "the mirror of low hiring, which is what the quits rate "
                 "reads from the other side"),
    "UEMP15OV": ("labour_mobility", "JTSQUR",
                 "unemployed 15 weeks and over, from 1948"),
    "ICSA": ("labour_flows", "JTSQUR",
             "initial jobless claims, weekly from 1967. An administrative "
             "count, revised once the following week and then fixed"),
    "CCSA": ("labour_flows", "JTSQUR",
             "continued claims; the stock to ICSA's flow"),
    "LNS13023621": ("labour_mobility", "JTSQUR",
                    "job losers on temporary layoff -- separations that are "
                    "expected to reverse, which behaves very differently "
                    "from a quit"),
    "LNS13023705": ("labour_mobility", "JTSQUR",
                    "job leavers: people who quit. The closest pre-JOLTS "
                    "reading of voluntary mobility there is, from 1967"),

    # --- financial stress / risk appetite -------------------------------
    "NFCI": ("financial_conditions", "BAMLH0A0HYM2",
             "Chicago Fed national financial conditions index, weekly from "
             "1971"),
    "ANFCI": ("financial_conditions", "BAMLH0A0HYM2",
              "the same index adjusted for the state of the real economy, "
              "which is the version that is not just a growth proxy"),
    "STLFSI4": ("financial_conditions", "BAMLH0A0HYM2",
                "St Louis Fed financial stress index, from 1993"),
    "T10Y3M": ("financial_conditions", "BAMLH0A0HYM2",
               "the 10-year minus 3-month term spread, daily from 1982"),

    # --- consumer expectations ------------------------------------------
    "UMCSENT1": ("survey_expectation", "UMCSENT",
                 "the Michigan expectations component, as distinct from the "
                 "current-conditions component. If the lead on housing is "
                 "real it should live here rather than in the headline"),
    "CSCICP03USM665S": ("survey_expectation", "USACSCICP02STSAM",
                        "OECD composite consumer confidence for the US"),
}

PROBE_EARLY, PROBE_LATE = "2015-05-15", "2024-05-15"
SEARCH_LO, SEARCH_HI = 1960, 2026


def _has(sid, when):
    try:
        AC.fetch_one(sid, when)
        return True
    except Exception:                                       # noqa: BLE001
        return False


def earliest_vintage(sid):
    if not _has(sid, f"{SEARCH_HI}-02-15"):
        return ""
    lo, hi = SEARCH_LO, SEARCH_HI
    if _has(sid, f"{lo}-02-15"):
        return f"{lo}-02-15"
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _has(sid, f"{mid}-02-15"):
            hi = mid
        else:
            lo = mid
    return f"{hi}-02-15"


def _parse(body):
    out = {}
    for line in body.strip().splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 2:
            try:
                out[p[0].strip()] = float(p[1])
            except ValueError:
                continue
    return out


def main() -> int:
    rows = {}
    print(f"{'candidate':<18}{'construct':<22}{'start':<12}{'vintage':<12}"
          f"{'revision':<10}  class")
    for sid, (construct, incumbent, why) in sorted(CANDIDATES.items()):
        try:
            cur = _parse(AC.fetch_one(sid, "")[0])
        except Exception as e:                              # noqa: BLE001
            rows[sid] = {"series_id": sid, "construct": construct,
                         "incumbent": incumbent, "rationale": why,
                         "classification": UNUSABLE,
                         "why_not": f"{type(e).__name__}: {e}"[:160]}
            print(f"  {sid:<16}{construct:<22}{'-':<12}{'-':<12}{'-':<10}  "
                  f"{UNUSABLE}")
            continue
        start = min(cur) if cur else ""
        ev = earliest_vintage(sid)
        prof = AC.probe_revisions([sid], early=PROBE_EARLY,
                                  late=PROBE_LATE)[0]
        never_revised = prof.differing == 0 and prof.overlap > 0
        # A candidate is usable back to the EARLIER of its own vintage
        # archive and -- when it is never revised -- its start date.
        usable_from = (start if never_revised else (ev or ""))
        rows[sid] = {
            "series_id": sid, "construct": construct, "incumbent": incumbent,
            "rationale": why, "start": start,
            "earliest_alfred_vintage": ev,
            "revision_behaviour": prof.behaviour,
            "differing": prof.differing, "overlap": prof.overlap,
            "max_relative_change": round(prof.max_relative_change, 6),
            "never_revised": never_revised,
            "usable_from": usable_from,
            "observations": len(cur)}
        # Classification here is PROVISIONAL: the equivalence test decides.
        if not usable_from:
            cls = NO_VINTAGE_HISTORY
        elif usable_from > "2011-01-01":
            cls = UNUSABLE   # no earlier than the incumbent; buys nothing
        else:
            cls = "CANDIDATE_PENDING_EQUIVALENCE"
        rows[sid]["classification"] = cls
        print(f"  {sid:<16}{construct:<22}{start:<12}"
              f"{(ev or '-'):<12}{prof.behaviour:<10}  {cls}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"contract": "econ_behavioural_depth.v1",
         "probed_at": _dt.date.today().isoformat(),
         "candidates": rows}, indent=2, sort_keys=True))
    usable = [s for s, r in rows.items()
              if r["classification"] == "CANDIDATE_PENDING_EQUIVALENCE"]
    print(f"\n  {len(usable)} of {len(rows)} reach earlier than 2011 and go "
          f"to the equivalence test")
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
