"""Score the production reader (v1: belief_formation.direction_of + _ROUTES) and
demand_reading.v2 on the held-out labelled sample. Ambiguous items are excluded from
precision/recall and listed for human review."""
import json, sys, collections
from intent_engine.market import belief_formation as BF, demand_reading as DR
S = json.load(open(sys.argv[1])); G = json.load(open(sys.argv[2]))
DEMAND_TYPES = ("EARNINGS_RESULT", "EARNINGS_SURPRISE", "GUIDANCE_REVISION", "COMMITTED_DEMAND")
def v1(item):
    if item["type"] not in DEMAND_TYPES: return "N"
    d = BF.direction_of(item["fact"])
    return {"UP": "S", "DOWN": "W"}.get(d, "N")
MAP = {DR.STRENGTHENING: "S", DR.WEAKENING: "W", DR.SURPRISE_POS: "PS", DR.SURPRISE_NEG: "NS", DR.ABSTAIN: "N"}
def v2(item): return MAP[DR.read(item["fact"]).family]
def score(fn, name):
    rows = []
    for it in S:
        g = G[str(it["i"])]; gs = set(g if isinstance(g, list) else [g]); p = fn(it)
        rows.append((it, gs, p))
    amb = [r for r in rows if "A" in r[1]]; cl = [r for r in rows if "A" not in r[1]]
    claims = [r for r in cl if r[2] in ("S", "W")]
    gold_d = [r for r in cl if gs_has(r[1], ("S", "W"))]
    tp = sum(1 for r in claims if r[2] in r[1])
    false_claims = [r for r in claims if r[2] not in r[1]]
    rec = sum(1 for r in gold_d if r[2] in r[1])
    surpr = [r for r in cl if gs_has(r[1], ("PS", "NS"))]
    abst_ok = sum(1 for r in cl if r[2] == "N" and "N" in r[1]); abst_n = sum(1 for r in cl if "N" in r[1])
    acc = sum(1 for r in cl if r[2] in r[1])
    print(f"{name}: clear items {len(cl)}, ambiguous {len(amb)}")
    print(f"   exact accuracy {acc}/{len(cl)} = {acc/len(cl):.2f}")
    print(f"   demand claims made {len(claims)}: precision {tp}/{len(claims)} = {tp/max(1,len(claims)):.2f}; FALSE demand claims {len(false_claims)}")
    print(f"   demand recall {rec}/{len(gold_d)} = {rec/max(1,len(gold_d)):.2f}")
    print(f"   surprises identified {sum(1 for r in surpr if r[2] in r[1])}/{len(surpr)}")
    print(f"   correct abstention {abst_ok}/{abst_n}")
    on_amb = collections.Counter(r[2] for r in amb); print(f"   on ambiguous items it asserted: {dict(on_amb)}")
    for r in false_claims[:8]: print(f"     FALSE {r[2]} (gold {sorted(r[1])}): {r[0]['fact'][:100]}")
    return rows
def gs_has(gs, labs): return bool(set(labs) & gs) and not (gs - set(labs) - {"PS", "NS"} and gs & {"N"})
r1 = score(v1, "v1 production (direction_of)"); print(); r2 = score(v2, "v2 demand_reading (shadow)")
print("\nHUMAN REVIEW (ambiguous):", [it["i"] for it, gs, _ in r1 if "A" in gs])
print("v2 misses on clear demand items:", [(it["i"], sorted(gs), p) for it, gs, p in r2 if "A" not in gs and gs_has(gs, ("S","W")) and p not in gs])
