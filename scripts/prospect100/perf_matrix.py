"""Server-side performance of the local demo, measured through the product.

Test conditions (stated in every output): the local development server on
127.0.0.1, this machine, the code in the working tree, real network for the
analysis itself. These are NOT preview numbers -- the free preview runs on a
~15% CPU share and its pages took 4-11s each in Pass 1.

  search      every prospect's four typed queries over HTTP to
              /api/companies (the endpoint the combobox calls)
  navigation  for one company per tier: the real journey (type, pick,
              submit, wait), then every surface fetched six times on the
              owning session -- the first is the first view of a finished
              run, the next five are cached navigation
  status      the corporate-status page for an absorbed company (no run)

Writes the measurements and, for the browser vitals step (vitals.py), the
session cookies and run ids. The cookies are guest-demo cookies for a local
server that exists only for this test.

Usage: JOURNEY_BASE=http://127.0.0.1:8601 PYTHONPATH=src \
       .venv/bin/python scripts/prospect100/perf_matrix.py --out DIR
"""
from __future__ import annotations

import json
import os
import pathlib
import statistics
import sys
import time
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import yaml  # noqa: E402

import public_journey_ten as PJT  # noqa: E402
from live_pass import TYPED, _prefixes  # noqa: E402
from perf_progressive_matrix import _opener, _req  # noqa: E402

ROOT = HERE.parent.parent
REG = ROOT / "docs/engineering/prospect100/PROSPECT_REGISTRY.yaml"
REPRESENTATIVE = (7, 33, 58, 77)      # Matillion, Moody's, Workday, Kaseya
SURFACES = ("intro", "story", "full", "brief", "history", "evidence",
            "sources", "connect", "xray")


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(round(p / 100 * len(xs) + 0.5)) - 1))
    return round(xs[k] * 1000, 1)


def main() -> int:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    reg = {r["prospect_id"]: r for r in
           yaml.safe_load(REG.read_text())["prospects"]}

    # ---- search over HTTP --------------------------------------------------
    op, _jar = _opener()
    _req(op, "/demo")
    times = []
    for pid, r in sorted(reg.items()):
        typed = TYPED.get(pid) or r.get("common_name") or r["name_as_listed"]
        for q in _prefixes(typed) + [typed]:
            _rows, took, _st = PJT.suggest_live(op, q)
            times.append(took)
    search = {"queries": len(times), "p50_ms": pct(times, 50),
              "p95_ms": pct(times, 95), "max_ms": round(max(times) * 1000, 1)}
    print("search", search, flush=True)

    # ---- status page (no run) ---------------------------------------------
    st_op, _ = _opener()
    _st, page, *_ = _req(st_op, "/demo")
    csrf = PJT._csrf(page)
    status_t = []
    for _ in range(5):
        t = time.monotonic()
        _req(st_op, "/analyze", {"company_name": "Red Canary, Inc.",
                                 "consent": "1", "csrf": csrf})
        status_t.append(time.monotonic() - t)

    # ---- navigation on finished runs --------------------------------------
    sessions, nav = [], {}

    def hook_for(pid):
        def extra(op, run_id, row, surfaces):
            jar = next(h.cookiejar for h in op.handlers
                       if hasattr(h, "cookiejar"))
            sessions.append({
                "prospect_id": pid, "company": row["company"],
                "run_id": run_id,
                "cookies": [{"name": c.name, "value": c.value,
                             "domain": c.domain or "127.0.0.1",
                             "path": c.path or "/"} for c in jar]})
            per = {}
            for s in SURFACES:
                laps = []
                for _ in range(6):
                    t = time.monotonic()
                    code, *_r = _req(op, f"/runs/{run_id}/{s}", timeout=120)
                    laps.append((time.monotonic() - t, code))
                per[s] = {"first_ms": round(laps[0][0] * 1000, 1),
                          "cached_ms": [round(x * 1000, 1) for x, _ in laps[1:]],
                          "status": [c for _, c in laps]}
            nav[row["company"]] = per
        return extra

    for pid in REPRESENTATIVE:
        r = reg[pid]
        typed = TYPED.get(pid) or r.get("common_name") or r["name_as_listed"]
        PJT.PREFIXES[typed] = [typed]
        row = PJT.journey(typed, r["entity_id"], verbose=False,
                          extra=hook_for(pid))
        print(pid, typed, row.get("result"), row.get("core_s"), flush=True)

    first = [v["first_ms"] / 1000 for c in nav.values() for v in c.values()]
    cached = [x / 1000 for c in nav.values() for v in c.values()
              for x in v["cached_ms"]]
    by_surface = {s: {"first_p50_ms": pct([nav[c][s]["first_ms"] / 1000
                                            for c in nav], 50),
                      "cached_p50_ms": pct([x / 1000 for c in nav
                                            for x in nav[c][s]["cached_ms"]], 50),
                      "cached_p95_ms": pct([x / 1000 for c in nav
                                            for x in nav[c][s]["cached_ms"]], 95)}
                  for s in SURFACES}
    result = {
        "conditions": ("local development server on 127.0.0.1, this machine, "
                       "working-tree code, measured "
                       + time.strftime("%Y-%m-%d %H:%M %Z")
                       + "; the analysis shards were running concurrently"),
        "base": os.environ.get("JOURNEY_BASE"),
        "search_http": search,
        "status_page": {"p50_ms": pct(status_t, 50), "p95_ms": pct(status_t, 95)},
        "navigation": {"companies": list(nav), "requests_first": len(first),
                       "requests_cached": len(cached),
                       "first_view_p50_ms": pct(first, 50),
                       "first_view_p95_ms": pct(first, 95),
                       "cached_p50_ms": pct(cached, 50),
                       "cached_p95_ms": pct(cached, 95),
                       "by_surface": by_surface},
        "raw": nav,
    }
    (out / "perf.json").write_text(json.dumps(result, indent=1))
    (out / "sessions.json").write_text(json.dumps(sessions, indent=1))
    print(json.dumps({k: result[k] for k in ("search_http", "status_page")}),
          flush=True)
    print(json.dumps({k: v for k, v in result["navigation"].items()
                      if k != "by_surface"}), flush=True)
    for s, v in by_surface.items():
        print(f"  {s:9s} {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
