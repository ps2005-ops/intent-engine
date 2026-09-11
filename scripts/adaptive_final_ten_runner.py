#!/usr/bin/env python3
"""Drive the exact ten against the FROZEN deployed product, one at a time.

Retries exist for exactly one reason and it is written down: the demo allows
ten analyses per client IP per rolling hour, and a run refused by that quota
never reached the product at all. A quota refusal is INFRASTRUCTURE, it is
recorded as such, and the same company is re-run unchanged once the window
has moved. Nothing here re-runs a company because its RESULT was unwelcome.
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-econ")
PY = str(ROOT / ".venv" / "bin" / "python")
OUT = ROOT / "reports" / "adaptive_ten_matrix.json"
TEN = ["Highspot", "BigID", "Cyera", "Monte Carlo Data", "Veeam", "Druva",
       "Slalom", "Sigma Computing", "ZoomInfo", "Point B"]
PART = ROOT / "reports" / "final_ten_parts"
PART.mkdir(parents=True, exist_ok=True)

MAX_QUOTA_WAITS = 4
QUOTA_WAIT_S = 600


def run_one(name: str) -> dict:
    part = PART / (name.lower().replace(" ", "-") + ".json")
    cmd = [PY, "scripts/adaptive_ten_matrix.py", "--only", name,
           "--out", str(part.relative_to(ROOT))]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(p.stdout[-700:])
    if p.returncode not in (0, 1):
        sys.stdout.write(p.stderr[-700:])
    try:
        return json.loads(part.read_text())["rows"][0]
    except Exception as exc:                                 # noqa: BLE001
        return {"company": name, "result": "INSTRUMENT_DEFECT",
                "defects": [{"kind": "INSTRUMENT_DEFECT",
                             "detail": f"no row persisted: {exc}"}]}


def is_quota(row: dict) -> bool:
    for d in row.get("defects") or ():
        detail = (d.get("detail") or "").lower()
        if d.get("kind") == "INFRASTRUCTURE" and (
                "too many" in detail or "429" in detail):
            return True
    return False


def served_identity() -> tuple:
    """The SHA the service is ACTUALLY serving, recorded with the results.

    A matrix whose rows cannot name the build they were measured against is
    not a qualification of anything.
    """
    base = "https://intent-engine-preview-bridge.onrender.com"
    try:
        with urllib.request.urlopen(base + "/version", timeout=90) as r:
            return base, json.loads(r.read().decode())
    except Exception:                                        # noqa: BLE001
        return base, {}


def main() -> int:
    only = sys.argv[1:] or TEN
    BASE, version = served_identity()
    LIVE = str(version.get("commit", ""))
    print(f"base {BASE}\nlive {LIVE or '?'}\n", flush=True)
    rows, waits = [], 0
    if OUT.exists():
        try:
            rows = json.loads(OUT.read_text()).get("rows", [])
        except Exception:                                    # noqa: BLE001
            rows = []
    done = {r["company"] for r in rows
            if r.get("result") not in (None, "", "INFRASTRUCTURE")}
    for index, name in enumerate(only, start=1):
        if name in done:
            print(f"[{index}/{len(only)}] {name}: already recorded, skipping")
            continue
        while True:
            print(f"[{index}/{len(only)}] {name}", flush=True)
            row = run_one(name)
            if is_quota(row) and waits < MAX_QUOTA_WAITS:
                waits += 1
                print(f"      QUOTA — waiting {QUOTA_WAIT_S}s "
                      f"(wait {waits}/{MAX_QUOTA_WAITS}), product unchanged",
                      flush=True)
                time.sleep(QUOTA_WAIT_S)
                continue
            break
        rows = [r for r in rows if r.get("company") != name] + [row]
        order = {n: i for i, n in enumerate(TEN)}
        rows.sort(key=lambda r: order.get(r.get("company"), 99))
        OUT.write_text(json.dumps(
            {"live_commit": LIVE, "base": BASE, "rows": rows}, indent=2))
        print(f"      -> {row.get('result')}  "
              f"lens={row.get('primary_lens', '-')} "
              f"model={row.get('business_model', '-')} "
              f"reading={row.get('decision_reading_available')}", flush=True)
    print(f"\n{len(rows)} rows in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
