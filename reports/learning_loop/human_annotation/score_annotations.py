"""Import human labels for the 19 ambiguous examples and score the readers on them.

    PYTHONPATH=src python reports/learning_loop/human_annotation/score_annotations.py \
        ANSWER_SHEET_reviewer1.csv [ANSWER_SHEET_reviewer2.csv]

Validates labels, records disagreements, and scores v1 (direction_of) and
v2.1 (demand_reading) ONLY on examples where reviewers agree and the label is
not INSUFFICIENT. These 19 were never used to tune v2.1; they must not be
used to tune it now either -- any reader change after seeing them needs a
fresh held-out sample.
"""
import csv, json, sys, pathlib, collections
from intent_engine.market import belief_formation as BF, demand_reading as DR
HERE = pathlib.Path(__file__).parent
OK = {"S", "W", "PS", "NS", "N", "INSUFFICIENT"}
ex = {e["example_id"]: e for e in json.load(open(HERE / "examples.json"))}
sheets = []
for p in sys.argv[1:]:
    rows = {r["example_id"]: r for r in csv.DictReader(open(p))}
    bad = [k for k, r in rows.items() if r["label"].strip().upper() not in OK]
    if bad: sys.exit(f"{p}: invalid or missing labels for {bad}")
    sheets.append({k: r["label"].strip().upper() for k, r in rows.items()})
agree, disagree = {}, []
for k in ex:
    labs = {s[k] for s in sheets}
    (agree.__setitem__(k, labs.pop()) if len(labs) == 1 else disagree.append((k, [s[k] for s in sheets])))
v1 = lambda t, ty: {"UP": "S", "DOWN": "W"}.get(BF.direction_of(t), "N") if ty in ("EARNINGS_RESULT", "EARNINGS_SURPRISE", "GUIDANCE_REVISION") else "N"
MAP = {DR.STRENGTHENING: "S", DR.WEAKENING: "W", DR.SURPRISE_POS: "PS", DR.SURPRISE_NEG: "NS", DR.ABSTAIN: "N"}
scored = {k: v for k, v in agree.items() if v != "INSUFFICIENT"}
res = {}
for name, fn in (("v1", lambda e: v1(e["passage"], e["evidence_type_as_classified"])),
                 ("v2.1", lambda e: MAP[DR.read(e["passage"]).family])):
    pred = {k: fn(ex[k]) for k in scored}
    claims = [k for k in scored if pred[k] in ("S", "W")]
    res[name] = {"accuracy": round(sum(pred[k] == scored[k] for k in scored) / max(1, len(scored)), 3),
                 "demand_claims": len(claims), "false_demand_claims": sum(pred[k] != scored[k] for k in claims),
                 "asserted_on_INSUFFICIENT": sum(fn(ex[k]) in ("S", "W") for k, v in agree.items() if v == "INSUFFICIENT")}
out = {"reviewers": len(sheets), "agreed": len(agree), "disagreements": disagree,
       "insufficient": sum(v == "INSUFFICIENT" for v in agree.values()), "scored": len(scored), "results": res}
(HERE / "RESULTS.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
