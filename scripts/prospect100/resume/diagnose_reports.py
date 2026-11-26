"""Why does a run have no strategic report (or no deck)? Per company, from the store.

Opens a COPY of a round's store in-process, exactly as rerender_pass does,
and for every run records what decided the deck's availability:

  readiness       may_synthesize, the reason, and the readiness inputs
                  (documents composed vs usable, families present)
  report          whether `strategic_report` exists, and its deep_status
  availability    the app's own `_availability` (state, has_report, slides_ready)

No analysis is run, nothing is fetched, no model is called.

  ZERO_ANTHROPIC=1 PYTHONPATH=src python scripts/prospect100/resume/diagnose_reports.py \
      --store reports/prospect100_resume/r5_store \
      --states 'reports/prospect100_resume/r5/s*/state.json' \
      --out docs/engineering/prospect100/resume/report_availability_r5.json
"""
from __future__ import annotations

import collections
import glob
import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> int:
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    store = pathlib.Path(os.path.expanduser(_arg("--store")))
    work = pathlib.Path(tempfile.mkdtemp(prefix="diag_store_"))
    shutil.copytree(store, work, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.lock"))
    os.environ["RUNTIME_ROOT"] = str(work / "runtime")
    os.environ["ACQUISITION_MEMORY_DIR"] = str(work / "acq")
    os.environ["SEC_FILING_CACHE_DIR"] = str(work / "sec")
    app = WebApp(AppConfig(env="development", secret="d" * 64, demo_mode=True,
                           web_store_path=work / "w.jsonl",
                           fi_store_path=work / "fi.jsonl",
                           ci_store_path=work / "ci.jsonl"))
    rows = []
    for f in sorted(glob.glob(os.path.expanduser(_arg("--states")))):
        rows += [r for r in json.loads(pathlib.Path(f).read_text())["rows"].values()
                 if r.get("run_id")]
    out, why = {}, collections.Counter()
    for r in sorted(rows, key=lambda r: r.get("n") or 0):
        rid = r["run_id"]
        rec = {"prospect_id": r.get("n"), "run_id": rid,
               "final_class": r.get("final_class")}
        try:
            res = app._real_result(rid) or {}
            rd = res.get("readiness") or {}
            rep = res.get("strategic_report")
            av = app._availability(rid)
            rec.update(
                may_synthesize=rd.get("may_synthesize"),
                readiness_state=rd.get("state") or rd.get("status"),
                readiness_reason=rd.get("reason") or rd.get("explanation"),
                readiness_inputs=res.get("readiness_inputs"),
                has_report=rep is not None,
                deep_status=(rep or {}).get("deep_status"),
                availability={k: av.get(k) for k in
                              ("state", "has_report", "slides_ready")},
            )
            if not av.get("slides_ready"):
                key = ("no_report:" + str(rec["readiness_state"])
                       if rep is None else "report_not_settled")
                why[key] += 1
        except Exception as exc:                              # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
            why["error"] += 1
        out[r["company"]] = rec
    dest = pathlib.Path(_arg("--out"))
    dest.write_text(json.dumps({"why_no_deck": dict(why), "companies": out},
                               indent=1, default=str) + "\n")
    print(json.dumps(dict(why), indent=1))
    print("no deck:", [c for c, v in out.items()
                       if not (v.get("availability") or {}).get("slides_ready")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
