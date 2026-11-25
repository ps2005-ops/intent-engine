"""Run a market cycle and record every intent_engine function actually CALLED (real invocation trace)."""
import sys, runpy, json, collections, threading
OUT = sys.argv[1]; sys.argv = ["intent_engine.market"] + sys.argv[2:]
calls = collections.Counter()
def prof(frame, event, arg):
    if event == "call":
        f = frame.f_globals.get("__name__", "")
        if f.startswith("intent_engine."):
            calls[(f, frame.f_code.co_name)] += 1
sys.setprofile(prof); threading.setprofile(prof)
code = 0
try:
    runpy.run_module("intent_engine.market", run_name="__main__")
except SystemExit as e:
    code = e.code
finally:
    sys.setprofile(None)
    mods = collections.Counter()
    for (m, fn), n in calls.items(): mods[m] += n
    json.dump({"exit": code, "modules": dict(mods), "functions": {f"{m}:{fn}": n for (m, fn), n in calls.items()}},
              open(OUT, "w"), indent=0, sort_keys=True)
