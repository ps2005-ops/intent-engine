"""Rebuild the replay's observation rows exactly as replay.run does (read-only) and pickle them."""
import pickle, sys, time
from intent_engine.paper_validation.__main__ import load_inputs
from intent_engine.paper_validation import observations as OB, universe as U
from intent_engine.paper_validation.protocol import PROTOCOL
t0 = time.time()
inp = load_inputs(log=lambda s: None)
spy = inp["bars"][U.BENCHMARK]
dates = [s for s in OB.schedule(spy, anchor=PROTOCOL["replay"]["anchor"]) if s[3]]
rows, voids = OB.build(bars=inp["bars"], instruments=list(inp["etfs"]) + list(inp["companies"]),
                       panel=inp["panel"], dates=dates, profiles=inp["profiles"])
rows = [o for o in rows if o.resolved]
pickle.dump({"rows": rows, "dates": dates, "bars": inp["bars"]}, open(sys.argv[1], "wb"))
print(len(dates), "dates", len(rows), "rows", f"{time.time()-t0:.0f}s")
