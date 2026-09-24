"""§6: how far back can each series be read WITHOUT leaking a revision?

TWO DIFFERENT QUESTIONS, ASKED SEPARATELY
-----------------------------------------
1. EARLIEST OBSERVED DATE -- when the series starts. Cheap, already in the
   panel, and not the binding constraint.

2. EARLIEST VINTAGE-SAFE DATE -- the earliest origin at which the series can
   be read without using a value published later. That is a different date
   and it is the one that limits the experiment.

For a series ALFRED serves vintages for, (2) is ALFRED's earliest vintage.
For a series measured STABLE, (2) is its start date -- but ONLY if the
stability measurement covers the period being claimed. `acquire_panel`
measured stability between the 2015 and 2024 vintages, which says nothing
about whether the 1975 print of the unemployment rate matches today's. So
this probe re-measures stability against an EARLY vintage as well, and a
series that revises against an early vintage loses its shortcut before 1998
even though it keeps it after.

WHY THIS IS A PROBE AND NOT A TABLE
-----------------------------------
`ignored-source-is-invisible-loss` and `measure-the-premise-before-building`:
the previous run's stated ceiling ("~92 usable quarterly origins") was an
inference from the grid that had been fetched, not a measurement of what the
publisher would serve. INDPRO turns out to have vintages back to at least
1966. That was not knowable without asking.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.market import alfred as AL               # noqa: E402
from intent_engine.market import alfred_cache as AC         # noqa: E402

OUT = pathlib.Path("reports/panel/historical_depth.json")

#: The search window for the earliest vintage. It has to reach the PRESENT,
#: not the start of the origin grid.
#:
#: The first version searched [1960, 1998] and returned "" -- read downstream
#: as "no vintage history at all" -- for any series whose record starts after
#: 1998. Eleven series were excluded from the panel on that basis, including
#: every credit and JOLTS series, when their vintages begin in 2000-2011 and
#: are perfectly usable. A search window that cannot express "later than the
#: window" answers a different question from the one asked.
SEARCH_LO, SEARCH_HI = 1960, 2026

#: The early vintage a STABLE series is re-checked against. Chosen because it
#: is inside ALFRED's coverage for the long series and old enough that a
#: benchmark revision would have happened by now if one was going to.
EARLY_CHECK = "1998-02-15"


def _has_vintage(sid: str, when: str) -> bool:
    try:
        AC.fetch_one(sid, when)
        return True
    except AC.SeriesAbsent:
        return False
    except Exception:                                       # noqa: BLE001
        return False


def earliest_vintage(sid: str) -> str:
    """Bisect for the first year ALFRED will serve a vintage of `sid`.

    Returns "" only when the LATEST probe date also has no vintage, which is
    the real "this series has no vintage record" case.
    """
    if not _has_vintage(sid, f"{SEARCH_HI}-02-15"):
        return ""
    lo, hi = SEARCH_LO, SEARCH_HI
    if _has_vintage(sid, f"{lo}-02-15"):
        return f"{lo}-02-15"
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _has_vintage(sid, f"{mid}-02-15"):
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


def stability_against_early(sid: str, early: str) -> dict:
    """Does the CURRENT series still match how it read at `early`?

    The shortcut this checks is the one `acquire_panel` takes for a STABLE
    series: use today's values, dated by publication lag. That is only safe
    where the values did not move, and it was measured over 2015-2024 only.
    """
    try:
        cur = _parse(AC.fetch_one(sid, "")[0])
        old = _parse(AC.fetch_one(sid, early)[0])
    except Exception as e:                                  # noqa: BLE001
        return {"checked": False, "why": f"{type(e).__name__}: {e}"[:160]}
    common = [k for k in old if k in cur]
    if not common:
        return {"checked": False, "why": "no overlapping observations"}
    diff = [k for k in common if abs(old[k] - cur[k]) > 1e-9]
    mx = max((abs(cur[k] - old[k]) / max(1e-9, abs(old[k])) for k in diff),
             default=0.0)
    frac = len(diff) / len(common)
    stable = (frac < AC.MIN_REVISED_FRACTION or mx < AC.MIN_REVISED_MAGNITUDE)
    return {"checked": True, "vintage": early, "overlap": len(common),
            "differing": len(diff), "differing_fraction": round(frac, 4),
            "max_relative_change": round(mx, 6),
            "stable_against_early": stable}


def main() -> int:
    profiles = {p["series_id"]: p for p in json.loads(
        (pathlib.Path("reports/panel/revision_profiles.json")).read_text())}
    rows = {}
    print(f"{'series':<22}{'behaviour':<12}{'earliest vintage':<18}"
          f"{'stable vs 1998':<16}")
    for spec in AL.REGISTRY:
        sid = spec.series_id
        prof = profiles.get(sid, {})
        ev = earliest_vintage(sid)
        st = (stability_against_early(sid, EARLY_CHECK)
              if prof.get("behaviour") == "STABLE" else
              {"checked": False, "why": "series revises; vintages required"})
        rows[sid] = {
            "series_id": sid, "kind": spec.kind,
            "node_class": spec.node_class,
            "publication_lag_days": spec.publication_lag_days,
            "revision_behaviour": prof.get("behaviour", "UNKNOWN"),
            "earliest_alfred_vintage": ev,
            "early_stability": st}
        flag = ("n/a" if not st.get("checked")
                else ("YES" if st["stable_against_early"] else "NO"))
        print(f"  {sid:<20}{prof.get('behaviour','?'):<12}"
              f"{ev or 'none':<18}{flag:<16}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"contract": "econ_historical_depth.v1",
         "probed_at": _dt.date.today().isoformat(),
         "early_check_vintage": EARLY_CHECK,
         "series": rows}, indent=2, sort_keys=True))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
