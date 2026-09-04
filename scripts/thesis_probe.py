"""Four contrasting companies, and the exact headline decision each receives.

WHY FOUR AND NOT TEN. The repair predicts a DIFFERENT outcome for each of
these business models, so four rows falsify it faster and cheaper than ten:

    Synopsys   SUBSCRIPTION_SOFTWARE     must NOT get capacity_ahead_of_demand
    Emerson    DESIGN_AND_MANUFACTURE    MAY legitimately keep it
    BlackRock  BALANCE_SHEET_OR_NETWORK  must NOT get it
    SLB        energy services           a fourth distinct class

The pass condition is NOT "four different answers". Forcing novelty would be
its own defect. It is that the classes whose own pattern definition excludes
a scaffold stop receiving it, while the class that qualifies keeps it.

Reads the rendered Q1 rather than the model class, because a correct
classification is not evidence that the customer-facing sentence changed --
this programme has shipped an inert repair before.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from final_ten_qualification import (                        # noqa: E402
    DEEP_PENDING_MARK, POLL_S, _opener, _req, visible,
)

FOUR = [("Synopsys", "synopsys.com"), ("Emerson Electric", "emerson.com"),
        ("BlackRock", "blackrock.com"), ("SLB", "slb.com")]

#: The scaffold that collapsed. Its own excluded_model_classes names
#: SUBSCRIPTION_SOFTWARE and SCALE_RETAIL.
COLLAPSE_MARK = "supply commitment should be treated as fixed or renegotiable"
Q1 = "What is the most important strategic implication?"


def probe(name, domain, *, budget=320.0):
    op, _ = _opener()
    row = {"company": name}
    _s, entry, _u, _d = _req(op, "/demo")
    csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry).group(1)
    st, body, url, ack = _req(op, "/analyze",
                              {"consent": "on", "csrf": csrf,
                               "company_name": name,
                               "website": f"https://{domain}"}, timeout=300)
    row["ack"] = round(ack, 2)
    if st in (429, 503):
        row["result"] = "QUOTA" if st == 429 else "CAPACITY"
        return row
    m = (re.search(r"/runs/([A-Za-z0-9_-]+)", url)
         or re.search(r"/runs/([A-Za-z0-9_-]+)", body))
    if not m:
        row["result"] = "NO_RUN"
        return row
    run_id = row["run_id"] = m.group(1)
    began = time.monotonic()
    while time.monotonic() - began < budget:
        st, _p, u, _d = _req(op, f"/runs/{run_id}/progress", timeout=60)
        if "/progress" not in u and st == 200:
            row["core_s"] = round(time.monotonic() - began, 1)
            break
        time.sleep(POLL_S)
    brief = ""
    while time.monotonic() - began < budget:
        st, brief, _u, _d = _req(op, f"/runs/{run_id}/brief", timeout=90)
        if st == 200 and len(brief) > 2000 and \
                DEEP_PENDING_MARK not in visible(brief).lower():
            row["deep_s"] = round(time.monotonic() - began, 1)
            break
        time.sleep(POLL_S)
    st, tel, _u, _d = _req(op, f"/runs/{run_id}/telemetry", timeout=60)
    if st == 200:
        data = json.loads(tel)
        row["documents"] = (data.get("evidence_roles") or {}).get("documents")
        row["roles"] = (data.get("evidence_roles") or {}).get("filled")
        row["reading"] = data.get("reading")
    token = (re.search(r'name="csrf"\s+value="([^"]+)"', brief)
             or re.search(r'name="csrf"\s+value="([^"]+)"', entry)).group(1)
    st, ans, _u, dt = _req(op, f"/runs/{run_id}/conversation",
                           {"csrf": token, "question": Q1}, timeout=120)
    text = visible(ans)
    core = text.split(Q1)[-1].split("Ask a follow-up")[0]
    row["q1"] = " ".join(core.split())[:400]
    row["collapsed"] = COLLAPSE_MARK in row["q1"].lower()
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pace", type=float, default=400.0)
    args = ap.parse_args()
    rows = []
    for index, (name, domain) in enumerate(FOUR, 1):
        started = time.monotonic()
        row = probe(name, domain)
        rows.append(row)
        pathlib.Path(args.out).write_text(json.dumps(rows, indent=2), "utf-8")
        print(f"[{index}/4] {name:<20} core={row.get('core_s')} "
              f"deep={row.get('deep_s')} docs={row.get('documents')} "
              f"collapsed={row.get('collapsed')}", flush=True)
        print(f"       Q1: {row.get('q1','')[:200]}", flush=True)
        if index < len(FOUR):
            rest = args.pace - (time.monotonic() - started)
            if rest > 0:
                time.sleep(rest)
    collapsed = [r["company"] for r in rows if r.get("collapsed")]
    print(f"\n  collapsed onto the capacity template: {collapsed or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
