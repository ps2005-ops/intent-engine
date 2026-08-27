"""§3-§6: the MONTHLY vintage-safe panel, and how deep it can honestly go.

WHAT CHANGED FROM THE QUARTERLY VERSION
---------------------------------------
1. THE ORIGIN GRID IS MONTHLY, and it is DECLARED here rather than inferred
   from whatever dates happen to appear in the panel. The previous
   experiment inferred it with `v.endswith("-15")` and got 344 origins where
   the acquisition had planned 115, because one quarterly series publishes on
   the fifteenth.

2. THE STABLE-SERIES SHORTCUT IS SCOPED. A series read from one current
   fetch, dated by its publication lag, is CLAIMING that today's value equals
   what a model would have seen. That claim was verified over 2015 vs 2024
   and applied back to 1998. Measured against a 1998 vintage:

       REVOLSL   100% of observations differ, by up to 105016%
       HOUST       7.7% of observations differ, by up to 4.4%

   REVOLSL was redefined; HOUST revises. Both were feeding walled reads with
   present-day numbers. `alfred_cache.shortcut_allowed` now requires the
   measurement to cover the origin window, and both moved to real vintages.

3. THERE ARE TWO ARMS, because the honest answer to "how far back" differs
   by series. MODERN runs from 1998-02 with the full block. DEEP runs from
   1978-01 with the series that have vintages (or a never-revised record)
   that far back -- a NARROWER block, reported as narrower, bought for the
   only thing that was ever scarce: independent episodes.

NEVER INTERPOLATED
------------------
A monthly grid is a grid of ORIGINS, not of observations. A quarterly series
contributes new information at one origin in three and repeats at the other
two, which is what actually happened and is why `Panel.assert_frequency_
honoured` refuses a quarterly series carrying non-quarter months.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import panel as PN                  # noqa: E402
from intent_engine.econ import release as RL                # noqa: E402
from intent_engine.market import alfred as AL               # noqa: E402
from intent_engine.market import alfred_cache as AC         # noqa: E402

OUT = pathlib.Path("reports/panel")
PANEL_PATH = OUT / "historical_panel.jsonl"
PROFILE_PATH = OUT / "revision_profiles.json"
DEPTH_PATH = OUT / "historical_depth.json"

#: MODERN: every series that has a vintage record. DEEP: only what can be
#: read that far back without an unverifiable assumption.
MODERN_START = "1998-02-15"
DEEP_START = "1978-01-15"

#: The two vintages the revision probe compares.
PROBE_EARLY, PROBE_LATE = "2015-05-15", "2024-05-15"


def monthly_origins(start: str, end: str = ""):
    """The 15th of every month in [start, end]. Declared, not inferred."""
    end = end or _dt.date.today().isoformat()
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while True:
        d = f"{y}-{m:02d}-15"
        if d > end:
            break
        if d >= start:
            out.append(d)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _depth() -> dict:
    if not DEPTH_PATH.exists():
        raise SystemExit(
            f"{DEPTH_PATH} is missing. Run scripts/probe_historical_depth.py "
            "first: the shortcut policy needs to know the earliest vintage "
            "each series has, and guessing it is the assumption this whole "
            "file exists to remove.")
    return json.loads(DEPTH_PATH.read_text())["series"]


def policy(profiles, depth, earliest_origin: str) -> dict:
    """series -> (mode, reason) for origins at or after `earliest_origin`."""
    out = {}
    for p in profiles:
        d = depth.get(p.series_id, {})
        es = d.get("early_stability", {})
        ok, why = AC.shortcut_allowed(
            p, earliest_origin=earliest_origin,
            verified_from=(es.get("vintage", "") if es.get("checked") else ""),
            early_max_relative_change=es.get("max_relative_change"))
        ev = d.get("earliest_alfred_vintage", "")
        if ok:
            out[p.series_id] = ("SHORTCUT", why, ev)
        elif ev:
            out[p.series_id] = ("VINTAGES", why, ev)
        else:
            out[p.series_id] = ("EXCLUDED",
                                why + "; and no vintage exists to fall back "
                                      "on, so it cannot be a walled input",
                                "")
    return out


def build_requests(pol, origins_modern, origins_deep):
    """One request per (series, origin) that is both needed and possible."""
    reqs, per_series = [], {}
    for sid, (mode, why, ev) in sorted(pol.items()):
        if mode == "SHORTCUT":
            reqs.append(AC.Request(sid, "", f"shortcut: {why}"))
            per_series[sid] = 1
            continue
        if mode == "EXCLUDED":
            per_series[sid] = 0
            continue
        wanted = [o for o in (origins_deep + origins_modern) if o >= ev]
        for o in wanted:
            reqs.append(AC.Request(sid, o, f"vintages required: {why[:120]}"))
        per_series[sid] = len(wanted)
    return reqs, per_series


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    modern = monthly_origins(MODERN_START)
    deep = monthly_origins(DEEP_START, "1998-01-15")
    all_origins = deep + modern
    series = [s.series_id for s in AL.REGISTRY]

    print(f"=== 1. REVISION PROBE ({len(series)} series) ===")
    t0 = time.time()
    profiles = AC.probe_revisions(series, early=PROBE_EARLY, late=PROBE_LATE)
    PROFILE_PATH.write_text(json.dumps([p.as_dict() for p in profiles],
                                       indent=2, sort_keys=True))
    print(f"  probe took {time.time() - t0:.1f}s")

    depth = _depth()
    pol = policy(profiles, depth, MODERN_START)
    print(f"\n=== 2. POLICY (earliest origin {MODERN_START}) ===")
    for sid, (mode, why, ev) in sorted(pol.items()):
        print(f"  {mode:<9} {sid:<20} from {ev or '-':<12} {why[:74]}")

    print(f"\n=== 3. GRID ===")
    print(f"  deep   {len(deep):>4} origins  {deep[0]} .. {deep[-1]}")
    print(f"  modern {len(modern):>4} origins  {modern[0]} .. {modern[-1]}")
    print(f"  total  {len(all_origins):>4} monthly origins")

    reqs, per_series = build_requests(pol, modern, deep)
    print(f"\n=== 4. PLAN ===")
    print(f"  requests planned : {len(reqs)}")
    print(f"  naive            : {len(series) * len(all_origins)}")

    print(f"\n=== 5. ACQUIRE (concurrency {AC.CONCURRENCY}) ===")
    t0 = time.time()

    def prog(done, failed, already, total):
        print(f"    {done + failed + already:>5}/{total}  ok={done} "
              f"fail={failed} cached={already}  {time.time() - t0:.0f}s",
              flush=True)

    result = AC.acquire(reqs, progress=prog)
    result["origins"] = all_origins
    result["origins_modern"] = modern
    result["origins_deep"] = deep
    result["policy"] = {k: {"mode": v[0], "reason": v[1],
                            "earliest_vintage": v[2]}
                        for k, v in pol.items()}
    result["requests_per_series"] = per_series
    result["profiles"] = [p.as_dict() for p in profiles]
    result["elapsed_seconds"] = round(time.time() - t0, 1)
    AC.write_manifest(result)
    print(f"  requested={result['requested']} cached={result['already_cached']}"
          f" fetched={result['fetched']} failed={result['failed']} "
          f"in {result['elapsed_seconds']}s")

    print(f"\n=== 6. BUILD PANEL ===")
    panel = build_panel(pol, all_origins)
    s = panel.summarise()
    panel.write(PANEL_PATH)
    print(f"  series {s['series']}  cells {s['cells']}  "
          f"real-revisions {s['periods_with_more_than_one_vintage']}")
    print(f"  by state {s['cells_by_revision_state']}")
    print(f"  span {s['earliest']} .. {s['latest']}")
    print(f"  content_hash {s['content_hash']}")
    print(f"  wrote {PANEL_PATH}")
    return 0


def build_panel(pol, origins) -> PN.Panel:
    """Assemble the panel from cache, stamping every §3 field."""
    panel = PN.Panel()
    for spec in AL.REGISTRY:
        sid = spec.series_id
        mode, why, _ev = pol.get(sid, ("EXCLUDED", "not in policy", ""))
        if mode == "EXCLUDED":
            continue
        rule = RL.BY_ID.get(sid)
        freq = rule.frequency if rule else ""
        if mode == "SHORTCUT":
            body = AC.cached(sid, "")
            if not body:
                continue
            _col, rows = AL._parse_csv(body)
            for period, value in rows:
                rel = RL.released_at(sid, period) if rule else ""
                panel.add(PN.Cell(
                    series_id=sid, observed_at=period,
                    vintage_at=rel or period, value=value,
                    unit=spec.unit, kind=spec.kind,
                    node_class=spec.node_class, released_at=rel,
                    frequency=freq, source="FRED current + release calendar",
                    revision_state=PN.MEASURED_STABLE))
            continue
        for v in origins:
            body = AC.cached(sid, v)
            if not body:
                continue
            try:
                _col, rows = AL._parse_csv(body)
            except Exception:                               # noqa: BLE001
                continue
            for period, value in rows:
                rel = RL.released_at(sid, period) if rule else ""
                # The vintage is the publisher's own answer. The release date
                # is when the period FIRST appeared, which is earlier for a
                # revised value -- both are kept, neither is inferred from
                # the other.
                panel.add(PN.Cell(
                    series_id=sid, observed_at=period, vintage_at=v,
                    value=value, unit=spec.unit, kind=spec.kind,
                    node_class=spec.node_class, released_at=rel,
                    frequency=freq, source="ALFRED vintage",
                    revision_state=PN.PUBLISHER_VINTAGE))
    panel.finalise()
    panel.compact()
    panel.assert_frequency_honoured()
    revising = [sid for sid, (m, _w, _e) in pol.items() if m == "VINTAGES"]
    panel.assert_no_assumed_lag(revising)
    return panel


if __name__ == "__main__":
    raise SystemExit(main())
