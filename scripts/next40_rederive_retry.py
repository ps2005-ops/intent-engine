#!/usr/bin/env python3
"""Re-derive FAILURE_OFFERS_A_RETRY from the captures already on disk.

The gate greped for wording the product does not use, so a bounded run that
DID offer a retry was recorded as failing and lost its terminal
classification. The captures hold the answer, so this costs no analysis.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
UI = ROOT / "reports/next40_ui"


def main() -> int:
    path = ROOT / "reports/next40_state.json"
    state = json.loads(path.read_text())
    changed = []
    for row in state["rows"].values():
        if not row.get("bounded_page"):
            continue
        if row.get("gates", {}).get("FAILURE_OFFERS_A_RETRY"):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(row["company"]).lower()).strip("-")
        raw = ""
        for key in ("intro", "result"):
            p = UI / f"{slug}-{key}.html"
            if p.exists():
                raw += p.read_text()
        if re.search(r'action="[^"]*/retry"', raw):
            row["gates"]["FAILURE_OFFERS_A_RETRY"] = True
            row["failed_gates"] = [g for g in (row.get("failed_gates") or ())
                                   if g != "FAILURE_OFFERS_A_RETRY"]
            row["defects"] = [d for d in (row.get("defects") or ())
                              if "FAILURE_OFFERS_A_RETRY" not in
                              str(d.get("detail", ""))]
            if not row["failed_gates"]:
                row["result"] = "PASS"
                row["final_class"] = "RETRIEVAL_LIMITATION_HANDLED_CORRECTLY"
            row["retry_regate"] = ("re-derived from the capture: the page "
                                   "posts to /runs/<id>/retry")
            changed.append(row["company"])
    if changed:
        path.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"re-derived for: {changed or 'nobody'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
