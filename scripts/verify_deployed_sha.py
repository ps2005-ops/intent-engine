#!/usr/bin/env python3
"""LOCAL == ORIGIN == LIVE, or say which pair disagrees.

A qualification run is only about the code it says it is about. This is the
check that makes the claim, and it is separate from the deploy because a push
that succeeded and a service that restarted are different events -- the
recorded failure is a repair that landed and shipped inert, where a green
suite and a completed deploy were both true and the deployed page was
unchanged.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request

BASE = "https://intent-engine-preview-bridge.onrender.com"


def _git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True,
                          text=True).stdout.strip()


def _live(base):
    try:
        with urllib.request.urlopen(base + "/version", timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as exc:                                 # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--branch", default="v6/unified")
    ap.add_argument("--wait", type=float, default=0.0,
                    help="seconds to keep polling for the live SHA to match")
    a = ap.parse_args()

    local = _git("rev-parse", "HEAD")
    origin = _git("rev-parse", f"origin/{a.branch}")
    deadline = time.monotonic() + a.wait
    while True:
        live = _live(a.base)
        served = live.get("commit", "")
        boot = (live.get("process") or {}).get("boot_id", "")
        agree = (local == origin == served)
        print(f"LOCAL  {local}\nORIGIN {origin}\nLIVE   {served or live}"
              f"\nboot   {boot}\n{'ALL THREE AGREE' if agree else 'MISMATCH'}")
        if agree or time.monotonic() > deadline:
            break
        print("  waiting for the deploy to serve it ...", flush=True)
        time.sleep(20)
    if local != origin:
        print("  local and origin differ: the branch was not pushed, or was "
              "pushed from another worktree")
    if origin != served and served:
        print("  origin and live differ: the service has not restarted on "
              "this commit yet, or it deploys a different branch")
    return 0 if agree else 1


if __name__ == "__main__":
    raise SystemExit(main())
