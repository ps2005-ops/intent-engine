"""Per-company before/after between two rounds' journey states (DEVELOPMENT)."""
import glob, json, sys, collections
def load(r):
    out = {}
    for f in glob.glob(f"reports/prospect98/{r}/s*/state.json"):
        for v in json.load(open(f))["rows"].values():
            out[v["n"]] = v
    return out
a, b = load(sys.argv[1]), load(sys.argv[2])
f = lambda r: ((r.get("discovery") or {}).get("independent_origins"), r.get("final_class", "")[:14],
               (r.get("generalization") or {}).get("decision_force"), r.get("history_level"), r.get("core_s"))
mv = collections.Counter()
for n in sorted(b):
    if n in a:
        x, y = f(a[n]), f(b[n])
        mv[(x[0] or 0) < (y[0] or 0), (x[0] or 0) > (y[0] or 0)] += 1
        print(f"{n:3d} {b[n]['company'][:22]:22s} orig {x[0]}->{y[0]}  {x[1]:14s}->{y[1]:14s} force {x[2]}->{y[2]} hist {x[3]}->{y[3]} core {x[4]}->{y[4]}")
print("origins up/down:", {"up": mv[(True, False)], "down": mv[(False, True)], "same": mv[(False, False)]})
