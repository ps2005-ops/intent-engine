"""Prospect-100 analysis pass on the LIVE preview, through the proven harness.

Reuses scripts/next40_qualification.py unchanged -- its journey, its §8
outcome classes, its quota wait that reads the refusal page's own window, and
its one-writer lock -- and swaps in only what differs:

  the cohort   95 prospects that open a run, tiers interleaved so a partial
               pass is representative (the 5 absorbed/closed companies open no
               run; `--status-pages` checks those for free)
  the state    reports/prospect100_pass2/state.json
  captures     reports/prospect100_pass2/reports/next40_ui/   (raw HTML, not
               committed -- ~10 MB)
  the lock     reports/prospect100_pass2/owner.json

The typed name is the company's common name -- what a person types -- and the
journey confirms the suggestion carrying the registry's entity id, exactly as
the browser does.

DO NOT PUSH while this runs: a push redeploys the preview and wipes in-flight
guest runs (memory: a-docs-push-is-a-deploy).

LOCAL PASS (no preview, no quota): point the same journey at a local server
with JOURNEY_BASE, give each shard its own state with --out, and split the
cohort with --shard i/n so shards never share a writer:

  JOURNEY_BASE=http://127.0.0.1:8601 .venv/bin/python \
      scripts/prospect100/live_pass.py --cohort ALL \
      --out reports/prospect100_pass3/s1 --shard 1/3

Usage:
  .venv/bin/python scripts/prospect100/live_pass.py --cohort ALL --wait-quota
  .venv/bin/python scripts/prospect100/live_pass.py --only 1         # smoke
  .venv/bin/python scripts/prospect100/live_pass.py --status-pages   # free
"""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

import yaml  # noqa: E402

import next40_owner as OWNER  # noqa: E402
import next40_qualification as NQ  # noqa: E402

OUT = ROOT / "reports/prospect100_pass2"
REG = ROOT / "docs/engineering/prospect100/PROSPECT_REGISTRY.yaml"
TYPED = {82: "eSentire", 58: "Workday"}


def _prefixes(name: str):
    n = name.strip()
    return [n[:max(3, len(n) // 2)], n.lower(), n.upper()]


def cohort_rows():
    reg = yaml.safe_load(REG.read_text())["prospects"]
    rows, stops = [], []
    for r in reg:
        pid = r["prospect_id"]
        if r.get("entry_readiness") == "STOP_NO_LONGER_INDEPENDENT":
            stops.append(r)
            continue
        typed = TYPED.get(pid) or r.get("common_name") or r["name_as_listed"]
        rows.append((pid, typed, r["entity_id"], _prefixes(typed),
                     f"T{r['tier']}"))
    # Interleave tiers: 1,26,51,76,2,27,... so any prefix of the pass covers
    # all four tiers.
    by_tier = {t: [x for x in rows if x[4] == f"T{t}"] for t in (1, 2, 3, 4)}
    order = []
    for i in range(max(len(v) for v in by_tier.values())):
        for t in (1, 2, 3, 4):
            if i < len(by_tier[t]):
                order.append(by_tier[t][i])
    return order, stops


def status_pages(stops) -> int:
    """The five that must NOT open a run: typed name -> status page, free."""
    import public_journey_ten as PJT  # noqa: E402
    from perf_progressive_matrix import _req, visible  # noqa: E402
    import re

    op, _jar = PJT._opener()
    _st, page, *_ = _req(op, "/demo")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    out = {}
    for r in stops:
        st, html, url, _t, _h = _req(op, "/analyze", {
            # The legal name: "Observe" alone is a shared name and correctly
            # asks which company first; "Observe, Inc." names exactly one.
            "company_name": r["legal_name"], "consent": "1",
            "csrf": csrf})
        text = visible(html)
        out[r["entity_id"]] = {
            "status": st, "final_url": url,
            "says_no_longer_independent": bool(re.search(
                r"is now part of|no longer operates", text)),
            "opened_run": "/runs/" in (url or "")}
        print(r["common_name"], out[r["entity_id"]], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "status_pages.json").write_text(json.dumps(out, indent=1))
    ok = all(v["says_no_longer_independent"] and not v["opened_run"]
             for v in out.values())
    print("STATUS PAGES", "OK" if ok else "FAIL", flush=True)
    return 0 if ok else 1


def _take_option(name: str):
    """Remove `name VALUE` from argv (NQ parses the rest) and return VALUE."""
    if name not in sys.argv:
        return None
    i = sys.argv.index(name)
    value = sys.argv[i + 1]
    del sys.argv[i:i + 2]
    return value


def main() -> int:
    global OUT
    out = _take_option("--out")
    shard = _take_option("--shard")
    if out:
        OUT = (ROOT / out) if not pathlib.Path(out).is_absolute() \
            else pathlib.Path(out)
    order, stops = cohort_rows()
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        order = order[i - 1::n]
    if "--status-pages" in sys.argv:
        return status_pages(stops)
    OUT.mkdir(parents=True, exist_ok=True)
    NQ.FORTY = order
    NQ.COHORTS = {"ALL": [r[0] for r in order],
                  **{f"T{t}": [r[0] for r in order if r[4] == f"T{t}"]
                     for t in (1, 2, 3, 4)}}
    NQ.STATE = OUT / "state.json"
    NQ.ROOT = OUT                      # captures -> OUT/reports/next40_ui
    OWNER.LOCK = OUT / "owner.json"
    print(f"prospect100 live pass: {len(order)} companies, "
          f"{len(stops)} status-only", flush=True)
    return NQ.main()


if __name__ == "__main__":
    raise SystemExit(main())
