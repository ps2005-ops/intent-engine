#!/usr/bin/env python3
"""Run the whole 50-company gauntlet unattended, on ONE deployed SHA. §18-§25.

WHY THIS EXISTS RATHER THAN A LOOP IN THE CONVERSATION
------------------------------------------------------
The previous waves spent one session per handful of companies, because the
conversation waited on each analysis. A deployed run takes minutes; there is
nothing for a reader to learn from watching one. So this is detached: it
picks the next eligible company, runs it, persists everything, SCORES IT
IMMEDIATELY, and moves on. The session it was launched from is free to score
earlier captures and repair offline defects while it works.

QUOTA
-----
The preview enforces a rolling-hour demo quota per IP. Exceeding it does not
fail politely -- it returns the quota page, which would be captured as if it
were an analysis and scored as a defect in the product. So the budget is
respected in the harness: at most `--per-window` starts inside any rolling
`--window` seconds, and a quota page seen anyway stops the batch rather than
being written as a capture.

RESUMABLE
---------
Every company writes its own directory the moment it finishes. A batch that
is interrupted -- by quota, by a restart, by the container being destroyed --
is re-run by invoking this again with the same OUTDIR: anything already
captured for this SHA is skipped. Nothing is held only in memory.

Usage:
  python scripts/pre100_convergence_batch.py OUTDIR [--per-window 10]
       [--window 3600] [--concurrency 2] [--only NAME,NAME] [--limit N]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import pre100_batch_journey as J                            # noqa: E402

UNIVERSE = ROOT / "docs/execution/v5/pre100_50/UNIVERSE.json"

#: Copy the preview shows when the demo quota is spent. Captured as an
#: analysis it would score as a product defect; it is a fact about us.
#:
#: PHRASES, AND READ FROM THE PAGE TEXT ONLY. The first version included the
#: bare word "quota" and was matched against `json.dumps(row)` -- which
#: contains the key `"quota_block": false`. The detector read its own field
#: name and stopped the canary after a company that had completed in 146
#: seconds with nine surfaces captured. A marker that can match the
#: instrument's own vocabulary is not a marker.
QUOTA_MARKERS = ("demo limit", "too many analyses",
                 "analysis limit", "come back in an hour",
                 "you have reached the limit")


def quota_blocked(row: dict) -> bool:
    """Did the SERVICE refuse this run for quota?

    The journey harness already decides this from the response it got, so
    that verdict is authoritative and is asked first. The phrase scan is a
    backstop and runs over the captured PAGE TEXT -- never over the
    serialized record, whose keys are ours.
    """
    if (row.get("reliability") or {}).get("quota_block"):
        return True
    pages = []
    for value in (row.get("routes") or {}).values():
        if isinstance(value, dict):
            pages.append(str(value.get("text") or ""))
    blob = " ".join(pages).lower()
    return any(m in blob for m in QUOTA_MARKERS)


def _slug(name: str) -> str:
    """EXACTLY the journey harness's slug.

    A second implementation of the same rule is a second place for it to be
    wrong: a per-character map plus one `replace("__", "_")` does not collapse
    three underscores, so "J.P. Morgan & Co." would land in a directory this
    orchestrator then reported as never captured, and re-run it every window
    until the quota was gone.
    """
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")


def load_universe(only=None, limit=0):
    data = json.loads(UNIVERSE.read_text("utf-8"))
    rows = [c for c in data["companies"] if c.get("resolvable", True)]
    if only:
        wanted = {o.strip().lower() for o in only if o.strip()}
        rows = [c for c in rows
                if c["entry_name"].lower() in wanted
                or str(c.get("ticker", "")).lower() in wanted]
    return rows[:limit] if limit else rows


def already_captured(outdir: pathlib.Path, name: str) -> bool:
    """A company counts as captured only when it has TEXT on disk.

    An interrupted run leaves a directory and a manifest with no surfaces,
    and treating that as done is how five complete captures were once
    replaced by nothing and the core mean moved for no product reason.
    """
    d = outdir / _slug(name)
    if not d.is_dir():
        return False
    return bool(list(d.glob("*.txt"))) and (d / "run.json").exists()


class Window:
    """A rolling-window rate limiter. Blocks rather than overruns."""

    def __init__(self, per_window: int, seconds: int) -> None:
        self.per_window, self.seconds = per_window, seconds
        self._starts = collections.deque()
        self._lock = threading.Lock()

    def wait_for_slot(self, log) -> None:
        while True:
            with self._lock:
                now = time.time()
                while self._starts and now - self._starts[0] >= self.seconds:
                    self._starts.popleft()
                if len(self._starts) < self.per_window:
                    self._starts.append(now)
                    return
                sleep_for = self.seconds - (now - self._starts[0]) + 5
            log(f"quota window full; next slot in {int(sleep_for)}s")
            time.sleep(min(sleep_for, 300))


def write_manifest(company_dir: pathlib.Path, name: str, row: dict,
                   sha: str) -> None:
    """The manifest the scorer and the matrix both read.

    `pre100_batch_journey` writes `run.json`; every scoring path in this
    programme keys off `manifest.json` -- the company's canonical NAME, the
    SHA it was captured on, and the outcome. Without it `score_company` falls
    back to the directory slug and the matrix skips the company entirely, so
    a complete batch would produce an empty matrix.
    """
    routes = row.get("routes") or {}
    manifest = {
        "company": name,
        "deployed_sha": sha,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": row.get("run_id", ""),
        "outcome": (routes.get("intro") or {}).get("outcome", ""),
        "routes": routes,
        "seconds": row.get("seconds"),
        "reliability": row.get("reliability") or {},
    }
    (company_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1), "utf-8")


def deployed_sha() -> str:
    """The SHA actually serving, read from the service. §18 requires ONE."""
    import urllib.request
    try:
        with urllib.request.urlopen(
                J.BASE + "/version", timeout=30) as fh:
            return str(json.loads(fh.read().decode())
                       .get("commit", ""))[:7]
    except Exception:                                       # noqa: BLE001
        return ""


def score_capture(company_dir: pathlib.Path, tickers=()) -> dict:
    """Score this company the moment it lands (§25), not at the end."""
    try:
        from intent_engine.pre100 import quality as Q
        row = Q.score_company(company_dir, tickers=tickers)
    except Exception as exc:                                # noqa: BLE001
        row = {"error": f"{type(exc).__name__}: {exc}"}
    (company_dir / "quality.json").write_text(
        json.dumps(row, indent=1), "utf-8")
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--per-window", type=int, default=10)
    ap.add_argument("--window", type=int, default=3600)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / "batch.log"

    lock = threading.Lock()

    def log(message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        with lock:
            with log_path.open("a") as fh:
                fh.write(line + "\n")
            print(line, flush=True)

    sha = deployed_sha()
    if not sha:
        log("REFUSING: /version did not answer, so the SHA under test is "
            "unknown. §18 requires all fifty on ONE deployed SHA.")
        return 2
    log(f"deployed_sha={sha}")
    # A COMMA IS PART OF THE NAME. "Cloudflare, Inc." and "Meta Platforms,
    # Inc." both carry one, so splitting the selector on commas turned a
    # three-company canary into a one-company canary silently -- and a
    # selector that quietly narrows is worse than one that errors, because
    # the batch still reports success. Semicolon separates; tickers work too.
    selector = None
    if args.only:
        parts = args.only.split(";") if ";" in args.only \
            else args.only.split(",")
        selector = [o.strip() for o in parts if o.strip()]
    companies = load_universe(selector, args.limit)
    if selector and len(companies) != len(selector):
        log(f"SELECTOR MATCHED {len(companies)} of {len(selector)}: "
            f"{[c['entry_name'] for c in companies]}")
    todo = [c for c in companies
            if not already_captured(outdir, c["entry_name"])]
    log(f"universe={len(companies)} todo={len(todo)} "
        f"per_window={args.per_window}/{args.window}s "
        f"concurrency={args.concurrency}")

    window = Window(args.per_window, args.window)
    queue = collections.deque(todo)
    results = []
    stop = threading.Event()

    def progress() -> None:
        done = [c["entry_name"] for c in companies
                if already_captured(outdir, c["entry_name"])]
        (outdir / "progress.json").write_text(json.dumps({
            "universe": len(companies), "captured": len(done),
            "remaining": len(companies) - len(done),
            "stopped": stop.is_set(),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "captured_companies": done,
        }, indent=1), "utf-8")

    def worker() -> None:
        while not stop.is_set():
            with lock:
                if not queue:
                    return
                company = queue.popleft()
            name = company["entry_name"]
            window.wait_for_slot(log)
            if stop.is_set():
                return
            log(f"START {name}")
            started = time.time()
            try:
                row = J.run_company(name, str(company.get("cik") or ""),
                                    str(company.get("ticker") or ""),
                                    str(outdir))
            except Exception as exc:                        # noqa: BLE001
                log(f"ERROR {name}: {type(exc).__name__}: {exc}")
                log(traceback.format_exc()[-800:])
                row = {"company": name,
                       "error": f"{type(exc).__name__}: {exc}"}
            # A QUOTA PAGE IS NOT A CAPTURE. §21 says interrupt for quota
            # exhaustion; scoring the quota page as the product would put a
            # defect on the matrix that belongs to the harness.
            if quota_blocked(row):
                log(f"QUOTA reached on {name}; stopping the batch")
                stop.set()
                return
            company_dir = outdir / _slug(name)
            write_manifest(company_dir, name, row, sha)
            quality = score_capture(
                company_dir, tickers=(company.get("ticker"),)
                if company.get("ticker") else ())
            with lock:
                results.append({
                    "company": name,
                    "seconds": round(time.time() - started, 1),
                    "run_id": row.get("run_id", ""),
                    "outcome": (row.get("routes", {}).get("intro", {})
                                .get("outcome", "")),
                    "error": row.get("error", ""),
                    "core_mean": quality.get("core_mean"),
                    "core_min": quality.get("core_min"),
                })
                (outdir / "batch.json").write_text(
                    json.dumps(results, indent=1), "utf-8")
            progress()
            log(f"DONE  {name} in {round(time.time() - started)}s "
                f"core_mean={quality.get('core_mean')}")

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(max(1, args.concurrency))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    progress()
    log(f"BATCH END captured={len(results)} stopped={stop.is_set()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
