"""Freeze the 70/14/14 development / validation / untouched-evaluation split.

Runs BEFORE any identity work, research or tuning on the 98 companies, so the
assignment cannot depend on any result. Stratification labels are PRIORS
(listed ownership as understood before verification), recorded as such; the
identity pass may later correct an ownership label, but the split is never
recomputed -- a corrected label is reported beside the frozen assignment.

Rules:
  * per category: C1 28 -> 20/4/4, C2 27 -> 19/4/4, C3 21 -> 15/3/3, C4 22 -> 16/3/3
  * within a category, public and private are allocated separately so both
    held-out sets carry public filers (history is SEC-filer-bound, measured R4-R12)
  * a company already analysed in an earlier program (EXPOSED) is never
    eligible for the untouched evaluation set
  * the shuffle seed is the SHA-256 of UNIVERSE_AS_LISTED.tsv: reproducible,
    and fixed by the list itself rather than chosen
"""
from __future__ import annotations
import csv, hashlib, json, pathlib, random

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = ROOT / "docs/engineering/prospect98"
UNI = D / "UNIVERSE_AS_LISTED.tsv"

# Ownership PRIOR (pre-verification). P = believed listed on a public exchange.
PUBLIC_PRIOR = {2, 14, 26, 33, 53, 54, 56, 68, 69, 74, 83, 84, 85, 90, 92}
# Analysed before on earlier code (unseen-20 universe, retired R12).
EXPOSED = {12: "unseen20:Glean", 29: "unseen20:Coupa", 70: "unseen20:Celonis"}
QUOTA = {"C1": (20, 4, 4), "C2": (19, 4, 4), "C3": (15, 3, 3), "C4": (16, 3, 3)}


def main():
    raw = UNI.read_bytes()
    seed = hashlib.sha256(raw).hexdigest()
    rng = random.Random(int(seed, 16))
    rows = list(csv.DictReader(raw.decode().splitlines(), delimiter="\t"))
    assert len(rows) == 98 and [int(r["position"]) for r in rows] == list(range(1, 99))
    out = {}
    for cat, (nd, nv, nf) in QUOTA.items():
        cr = [r for r in rows if r["category"] == cat]
        assert len(cr) == nd + nv + nf, (cat, len(cr))
        pub = [int(r["position"]) for r in cr if int(r["position"]) in PUBLIC_PRIOR]
        prv = [int(r["position"]) for r in cr if int(r["position"]) not in PUBLIC_PRIOR]
        rng.shuffle(pub); rng.shuffle(prv)
        # held-out sets each take one public company when the category has >= 3
        final, val = [], []
        if len(pub) >= 3:
            final.append(pub.pop()); val.append(pub.pop())
        pool = [p for p in prv if p not in EXPOSED]
        exposed_prv = [p for p in prv if p in EXPOSED]
        while len(final) < nf:
            final.append(pool.pop())
        rest = pool + exposed_prv + pub
        rng.shuffle(rest)
        while len(val) < nv:
            val.append(rest.pop())
        for p in final: out[p] = "FINAL_UNTOUCHED"
        for p in val: out[p] = "VALIDATION"
        for p in rest: out[p] = "DEVELOPMENT"
    assert len(out) == 98
    assign = []
    for r in rows:
        p = int(r["position"])
        assign.append({"position": p, "category": r["category"],
                       "name_as_listed": r["name_as_listed"], "split": out[p],
                       "ownership_prior": "public" if p in PUBLIC_PRIOR else "private",
                       "exposed_before": EXPOSED.get(p)})
    body = {"program": "prospect98", "frozen_before": "identity, research and tuning",
            "universe_sha256": seed, "rules": __doc__.strip(),
            "counts": {s: sum(a["split"] == s for a in assign)
                       for s in ("DEVELOPMENT", "VALIDATION", "FINAL_UNTOUCHED")},
            "assignment": assign}
    txt = json.dumps(body, indent=1, ensure_ascii=False)
    (D / "SPLIT_FROZEN.json").write_text(txt)
    (D / "SPLIT_FROZEN.sha256").write_text(
        hashlib.sha256(txt.encode()).hexdigest() + "  SPLIT_FROZEN.json\n")
    print(body["counts"])
    for s in ("VALIDATION", "FINAL_UNTOUCHED"):
        print(s, [(a["position"], a["name_as_listed"]) for a in assign if a["split"] == s])


if __name__ == "__main__":
    main()
