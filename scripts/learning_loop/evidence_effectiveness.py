"""Evidence-source effectiveness over the 47 graded business expectations (market runtime).
Joins reconciliation -> expectation (evidence_basis) -> evidence (source_role, type, independence).
Effective-sample notes: expectations cluster by subject; results reported per subject too."""
import json, collections, random, sys, urllib.parse
recs = [json.loads(l) for l in open(sys.argv[1])]
ev = {}; seen = collections.defaultdict(set)
for r in recs:
    if r.get("record") == "evidence": ev.setdefault(r["evidence_id"], r)
    if r.get("record") == "evidence_seen": seen[r["evidence_id"]].add(r.get("source"))
exp = {r["expectation_id"]: r for r in recs if r.get("record") == "expectation"}
rec = {}
for r in recs:
    if r.get("record") == "reconciliation": rec.setdefault(r["expectation_id"], r)   # first grade is the grade
def fam(eid):
    e = ev.get(eid)
    if e: return e.get("source_role") or "unknown_role"
    s = seen.get(eid); return ("seen:" + sorted(s)[0]) if s else "unknown"
def host(eid):
    e = ev.get(eid); return urllib.parse.urlparse(e["source"]).netloc if e and e.get("source","").startswith("http") else "?"
rows = []
for xid, g in rec.items():
    x = exp.get(xid, {})
    basis = x.get("evidence_basis", []); recon = g.get("evidence_ids", [])
    rows.append({"subject": g["subject"], "metric": x.get("metric"), "dir": x.get("expected_direction"),
                 "ok": g["outcome"] == "CONFIRMED", "outcome": g["outcome"], "uncertainty": x.get("uncertainty"),
                 "basis_roles": sorted({fam(e) for e in basis}), "basis_types": sorted({(ev.get(e) or {}).get("evidence_type","?") for e in basis}),
                 "recon_roles": sorted({fam(e) for e in recon}), "recon_hosts": sorted({host(e) for e in recon}),
                 "n_basis": len(basis), "self_authored_basis": any((ev.get(e) or {}).get("self_authored") for e in basis),
                 "same_doc": bool(set(basis) & set(recon))})
print("graded", len(rows), collections.Counter(r["outcome"] for r in rows))
def tab(key, label):
    t = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        v = r[key]; vs = v if isinstance(v, list) else [v]
        for k in vs or ["none"]: t[str(k)][0] += r["ok"]; t[str(k)][1] += 1
    print(f"-- {label}")
    for k, (a, n) in sorted(t.items(), key=lambda x: -x[1][1]): print(f"   {k:45s} {a:2d}/{n:2d} = {a/n:.2f}")
tab("subject", "by subject (the cluster unit)"); tab("metric", "by mechanism/metric"); tab("dir", "by expected direction")
tab("basis_roles", "by source role of the PREDICTING evidence"); tab("basis_types", "by evidence type of the predicting evidence")
tab("recon_roles", "by source role of the GRADING evidence"); tab("same_doc", "graded by the same document that formed it")
tab("self_authored_basis", "basis includes company-authored evidence")
div = lambda r: len(r["basis_roles"])
tab_rows = collections.defaultdict(lambda: [0, 0])
for r in rows: tab_rows[min(div(r), 2)][0] += r["ok"]; tab_rows[min(div(r), 2)][1] += 1
print("-- source diversity of predicting evidence (distinct roles, 2 = 2+)", dict(tab_rows))
u = sorted(rows, key=lambda r: r["uncertainty"] or 0)
h = len(u) // 2
print("-- stated uncertainty: lower half confirmed", sum(r["ok"] for r in u[:h]), "/", h, "; upper half", sum(r["ok"] for r in u[h:]), "/", len(u) - h)
subj = collections.defaultdict(list)
for r in rows: subj[r["subject"]].append(r["ok"])
keys = list(subj); random.seed(1); bs = []
for _ in range(4000):
    s = [x for k in random.choices(keys, k=len(keys)) for x in subj[k]]; bs.append(sum(s) / len(s))
bs.sort(); print(f"confirmed rate {sum(r['ok'] for r in rows)/len(rows):.3f}; cluster bootstrap over {len(keys)} subjects 95% CI {bs[100]:.3f}-{bs[3900]:.3f}")
json.dump(rows, open(sys.argv[2], "w"), indent=1)
