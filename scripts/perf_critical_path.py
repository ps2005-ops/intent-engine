"""§4/§5/§6/§7: the interactive analysis critical path, measured not guessed.

WHY THIS EXISTS
---------------
A real customer watched "Reading current company evidence" for 4m54s on the
deployed preview and got nothing. Every hypothesis about that stall -- slow
provider, retries, Render contention, parsing -- is equally plausible from the
outside, and optimizing from the most plausible one is how you spend a day
making the wrong thing faster.

So this measures. It wraps the ONE function every outbound request goes
through (`safe_fetch`, re-exported into three modules) and records the wall
time, host, status and byte count of every call, attributed to the pipeline
stage that was running when it started. Nothing here changes a decision: a
profiled run and an unprofiled run fetch the same URLs in the same order.

The output is a critical-path report: total wall time, then every stage ranked
by exclusive time, then every host ranked by the seconds it cost.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

_LOCAL = threading.local()
CALLS: list = []
STAGES: list = []
_LOCK = threading.Lock()


def _stage() -> str:
    return getattr(_LOCAL, "stage", "unattributed")


class stage:
    """Mark the pipeline stage every fetch below is attributed to."""

    def __init__(self, name):
        self.name, self.prev = name, None

    def __enter__(self):
        self.prev = _stage()
        _LOCAL.stage = self.name
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        dt = time.monotonic() - self.t0
        with _LOCK:
            STAGES.append({"stage": self.name, "seconds": round(dt, 3),
                           "failed": exc[0] is not None})
        _LOCAL.stage = self.prev
        return False


def install_probe():
    """Wrap safe_fetch everywhere it is BOUND, not only where it is defined.

    `from ... import safe_fetch` copies the reference, so patching the
    defining module alone leaves the pipeline calling the original. The three
    call sites that matter (service, edgar, third_party_filings) each hold
    their own name.
    """
    from intent_engine.company_ingestion import fetch as F
    original = F.safe_fetch

    def probed(url, *a, **kw):
        t0 = time.monotonic()
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
        except Exception:                                    # noqa: BLE001
            pass
        try:
            result = original(url, *a, **kw)
            return result
        finally:
            dt = time.monotonic() - t0
            try:
                ok = bool(result.get("ok"))
                ftype = result.get("failure_type") or ""
                code = result.get("status_code")
                nbytes = len(result.get("body") or b"")
            except Exception:                                # noqa: BLE001
                ok, ftype, code, nbytes = False, "raised", None, 0
            with _LOCK:
                CALLS.append({"stage": _stage(), "host": host, "url": url[:180],
                              "seconds": round(dt, 3), "ok": ok,
                              "failure": ftype, "status": code,
                              "bytes": nbytes})

    F.safe_fetch = probed
    import intent_engine.company_ingestion.service as S
    import intent_engine.company_ingestion.edgar as E
    import intent_engine.company_ingestion.third_party_filings as T
    for mod in (S, E, T):
        if hasattr(mod, "safe_fetch"):
            mod.safe_fetch = probed
    return original


def run(company: str, website: str, *, out: pathlib.Path, store: pathlib.Path,
        warm: bool = False):
    """Drive the PRODUCTION worker, not a hand-rolled imitation of it.

    `_run_analysis` is the function the deployed service submits to its pool.
    Reproducing its steps here by hand would measure a pipeline no customer
    receives -- and the source-selection step (`_recommended_candidate_ids`,
    capped at 14) is exactly the kind of thing a hand-rolled harness gets
    wrong and then reports as a product number.
    """
    install_probe()
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    store.parent.mkdir(parents=True, exist_ok=True)
    config = AppConfig(env="development", secret="x" * 40,
                       web_store_path=store.parent / "web.jsonl",
                       fi_store_path=store.parent / "fi.jsonl",
                       ci_store_path=store)
    app = WebApp(config)
    ci = app.ci

    t_all = time.monotonic()
    import datetime as _dt
    with stage("create_run"):
        opened = ci.create_run(company_name=company, website=website,
                               user_id="perf",
                               as_of=_dt.date.today().isoformat())
    run_id = opened["run_id"] if isinstance(opened, dict) else opened

    # The worker's own stages, timed by wrapping the three calls it makes.
    real_discover, real_fetch, real_compose = \
        ci.discover, ci.fetch_approved, app._compose

    def timed_discover(rid, *a, **kw):
        with stage("discover"):
            return real_discover(rid, *a, **kw)

    def timed_fetch(rid, *a, **kw):
        with stage("fetch_approved"):
            return real_fetch(rid, *a, **kw)

    def timed_compose(rid, *a, **kw):
        with stage("compose"):
            return real_compose(rid, *a, **kw)

    ci.discover, ci.fetch_approved, app._compose = \
        timed_discover, timed_fetch, timed_compose
    with stage("total"):
        app._run_analysis("perf", run_id)
    total = time.monotonic() - t_all

    candidates = ci.store.candidates(run_id)
    approval = ci.store.approval(run_id) or {}
    retrieved = ci.store.retrieved(run_id)
    result = app._results.get(run_id) or {}
    state = ci.store.run_state(run_id)

    by_stage: dict = {}
    for s_ in STAGES:
        by_stage[s_["stage"]] = by_stage.get(s_["stage"], 0.0) + s_["seconds"]
    net_by_stage: dict = {}
    for c in CALLS:
        net_by_stage[c["stage"]] = net_by_stage.get(c["stage"], 0.0) + c["seconds"]
    by_host: dict = {}
    for c in CALLS:
        h = by_host.setdefault(c["host"], {"calls": 0, "seconds": 0.0,
                                           "ok": 0, "failed": 0})
        h["calls"] += 1
        h["seconds"] = round(h["seconds"] + c["seconds"], 2)
        h["ok" if c["ok"] else "failed"] += 1
    # §11: the same URL fetched more than once inside ONE analysis.
    seen: dict = {}
    for c in CALLS:
        seen[c["url"]] = seen.get(c["url"], 0) + 1
    dupes = {u: n for u, n in seen.items() if n > 1}

    net = sum(c["seconds"] for c in CALLS)
    report = {
        "company": company, "website": website, "run_id": run_id,
        "warm": warm, "run_state": state,
        "total_seconds": round(total, 2),
        "candidates": len(candidates),
        "approved": len(approval.get("approved_candidate_ids") or []),
        "retrieved": len(retrieved),
        "network_calls": len(CALLS),
        "network_seconds": round(net, 2),
        "network_share": round(net / total, 3) if total else 0,
        "cpu_seconds": round(total - net, 2),
        "duplicate_urls": dupes,
        "duplicate_fetch_seconds": round(
            sum(c["seconds"] for c in CALLS if seen[c["url"]] > 1
                ) - sum(max(cc["seconds"] for cc in CALLS if cc["url"] == u)
                        for u in dupes), 2),
        "stage_inclusive": {k: round(v, 2) for k, v in
                            sorted(by_stage.items(), key=lambda kv: -kv[1])},
        "stage_network": {k: round(v, 2) for k, v in
                          sorted(net_by_stage.items(), key=lambda kv: -kv[1])},
        "by_host": dict(sorted(by_host.items(),
                               key=lambda kv: -kv[1]["seconds"])),
        "slowest_calls": sorted(CALLS, key=lambda c: -c["seconds"])[:25],
        "documents": len((result or {}).get("documents") or []),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items()
                      if k != "slowest_calls"}, indent=2))
    print("\n--- SLOWEST CALLS ---")
    for c in report["slowest_calls"][:15]:
        print(f'  {c["seconds"]:7.2f}s  {c["stage"]:16s} '
              f'{"ok" if c["ok"] else (c["failure"] or "fail"):16s} {c["url"][:90]}')
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--company", required=True)
    p.add_argument("--website", default="")
    p.add_argument("--out", default="reports/perf/critical_path.json")
    p.add_argument("--store", default="")
    a = p.parse_args()
    import tempfile
    store = pathlib.Path(a.store) if a.store else \
        pathlib.Path(tempfile.mkdtemp(prefix="perf-")) / "ci.jsonl"
    run(a.company, a.website, out=pathlib.Path(a.out), store=store)
