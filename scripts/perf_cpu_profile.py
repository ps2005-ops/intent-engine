"""§31: where the CPU actually goes, by cProfile, on the real pipeline.

The critical-path probe showed Apple spending 74% of its wall time NOT in the
network. That is the opposite of the assumed bottleneck, so it is the half
worth profiling. This re-runs the same production worker under cProfile and
reports cumulative time by function, filtered to our own package so the
report is a list of things we can change.
"""
from __future__ import annotations

import argparse
import cProfile
import datetime as _dt
import io
import pathlib
import pstats
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--company", required=True)
    p.add_argument("--website", default="")
    p.add_argument("--store", required=True)
    p.add_argument("--out", default="reports/perf/cpu_profile.txt")
    p.add_argument("--phase", default="all", choices=("all", "compose"))
    a = p.parse_args()

    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    store = pathlib.Path(a.store)
    store.parent.mkdir(parents=True, exist_ok=True)
    app = WebApp(AppConfig(env="development", secret="x" * 40,
                           web_store_path=store.parent / "web.jsonl",
                           fi_store_path=store.parent / "fi.jsonl",
                           ci_store_path=store))
    opened = app.ci.create_run(company_name=a.company, website=a.website,
                               user_id="perf",
                               as_of=_dt.date.today().isoformat())
    run_id = opened["run_id"] if isinstance(opened, dict) else opened

    prof = cProfile.Profile()
    t0 = time.monotonic()
    prof.enable()
    app._run_analysis("perf", run_id)
    prof.disable()
    wall = time.monotonic() - t0

    buf = io.StringIO()
    st = pstats.Stats(prof, stream=buf).sort_stats("cumulative")
    st.print_stats(60)
    text = buf.getvalue()
    own = io.StringIO()
    st2 = pstats.Stats(prof, stream=own).sort_stats("tottime")
    st2.print_stats("intent_engine", 45)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"wall={wall:.2f}s run={run_id} state="
                   f"{app.ci.store.run_state(run_id)}\n\n"
                   f"=== CUMULATIVE (all) ===\n{text}\n"
                   f"=== TOTTIME (intent_engine only) ===\n{own.getvalue()}")
    print(f"wall={wall:.2f}s  -> {out}")
    print(own.getvalue()[:6000])


if __name__ == "__main__":
    main()
