"""§29: exactly two questions, and permission to stop on either.

A. a vintage-correct household credit archive before 2012
B. a housing baseline that beats a constant, using MORTGAGE30US and PERMIT

NOT a reopening of behavioural research. Both were named in the previous run's
information-priority ranking with scores of 9, and both are cheap. If A has no
accessible archive it is recorded BLOCKED_DATA and the search stops there --
"we looked and it is not available" is a finding, and continuing to look is
how a bounded gap becomes an open-ended programme.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.market import alfred_cache as AC           # noqa: E402

OUT = pathlib.Path("reports/panel/two_gaps.json")

#: A. every keyless household-credit-stress series with a plausible archive.
CREDIT = {
    "DRCLACBS": "delinquency rate on all consumer loans, all commercial banks",
    "DRALACBN": "delinquency rate on all loans, all commercial banks (NSA)",
    "CORCACBN": "charge-off rate on credit card loans (NSA)",
    "DRCCLACBN": "credit card delinquency, not seasonally adjusted",
    "NPTLTL": "nonperforming total loans to total loans",
    "TOTCI": "commercial and industrial loans, all commercial banks",
    "DRTSCILM": "net share of banks tightening standards, C&I loans",
    "DRTSCLCC": "net share of banks tightening standards, credit cards",
}

#: B. the housing baseline candidates.
HOUSING = {
    "MORTGAGE30US": "30-year fixed mortgage rate, weekly from 1971",
    "PERMIT": "new private housing units authorised by building permits",
    "HSN1F": "new one-family houses sold",
    "MSACSR": "monthly supply of new houses",
}

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


def probe(catalogue, label):
    rows = {}
    print(f"\n=== {label} ===")
    print(f"  {'series':<16}{'start':<12}{'vintage':<12}{'revision':<10}"
          f"{'usable_from':<12}")
    for sid, why in sorted(catalogue.items()):
        try:
            body = AC.fetch_one(sid, "")[0]
        except Exception as e:                              # noqa: BLE001
            rows[sid] = {"series_id": sid, "why": why,
                         "status": "NOT_SERVED",
                         "detail": f"{type(e).__name__}: {e}"[:120]}
            print(f"  {sid:<16}{'-':<12}{'-':<12}{'-':<10}{'-':<12} "
                  f"NOT_SERVED")
            continue
        obs = {}
        for line in body.strip().splitlines()[1:]:
            p = line.split(",")
            if len(p) >= 2:
                try:
                    obs[p[0].strip()] = float(p[1])
                except ValueError:
                    continue
        start = min(obs) if obs else ""
        ev = earliest_vintage(sid)
        prof = AC.probe_revisions([sid], early="2015-05-15",
                                  late="2024-05-15")[0]
        never = prof.differing == 0 and prof.overlap > 0
        usable = start if never else (ev or "")
        rows[sid] = {"series_id": sid, "why": why, "start": start,
                     "earliest_alfred_vintage": ev,
                     "revision_behaviour": prof.behaviour,
                     "differing": prof.differing, "overlap": prof.overlap,
                     "never_revised": never, "usable_from": usable,
                     "observations": len(obs),
                     "status": ("USABLE_PRE_2012"
                                if usable and usable < "2012-01-01"
                                else "NO_EARLIER_ARCHIVE")}
        print(f"  {sid:<16}{start:<12}{(ev or '-'):<12}"
              f"{prof.behaviour:<10}{(usable or '-'):<12} "
              f"{rows[sid]['status']}")
    return rows


def main() -> int:
    credit = probe(CREDIT, "A. PRE-2012 HOUSEHOLD CREDIT ARCHIVE")
    housing = probe(HOUSING, "B. HOUSING BASELINE CANDIDATES")

    a_hits = [s for s, r in credit.items()
              if r.get("status") == "USABLE_PRE_2012"]
    b_hits = [s for s, r in housing.items()
              if r.get("status") == "USABLE_PRE_2012"]

    verdict_a = ("CANDIDATES_FOUND" if a_hits else "BLOCKED_DATA")
    detail_a = a_hits or "no keyless archive reaches before 2012"
    print(f"\n  A: {verdict_a} — {detail_a}")
    if not a_hits:
        print("     recorded and STOPPED. The search does not continue into "
              "licensed or FOIA routes in this run.")
    print(f"  B: {len(b_hits)} candidate(s) usable before 2012: {b_hits}")

    payload = {"contract": "econ_two_gaps.v1",
               "probed_at": _dt.date.today().isoformat(),
               "gap_a_pre2012_credit": {
                   "verdict": verdict_a, "usable": a_hits,
                   "candidates": credit,
                   "note": ("BLOCKED_DATA means no KEYLESS vintage archive "
                            "reaches before 2012. A licensed bank panel or "
                            "an FOIA route may exist; neither was pursued, "
                            "and that is a scope decision rather than a "
                            "finding about the data."
                            if not a_hits else "")},
               "gap_b_housing_baseline": {
                   "usable": b_hits, "candidates": housing,
                   "note": ("admission still depends on the baseline ladder: "
                            "a longer series that does not make the macro "
                            "model beat a constant leaves housing "
                            "BASELINE_INVALID.")}}
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"\n  wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
