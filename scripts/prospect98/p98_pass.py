"""Run prospect-98 companies through the proven public journey on a LOCAL server.

The companies are NOT in the curated catalog (by design: the baseline measures
what an unfamiliar company gets). A real visitor types the name; when search
offers nothing, they type the website. Exactly as unseen_pass.py: a suggestion
carrying the verified domain is used unchanged, otherwise the submission
carries the name and the verified domain, and the miss is recorded.

Held-out companies are SEALED: `--split VALIDATION` or `FINAL_UNTOUCHED`
refuses to run unless `--sealed` is given, and a sealed run writes only to a
`sealed_*` directory that no scorer reads until its wave. Freezing is checked:
the split file must match its recorded SHA-256.

  JOURNEY_BASE=http://127.0.0.1:8701 PYTHONPATH=src python \
     scripts/prospect98/p98_pass.py --split DEVELOPMENT --out reports/prospect98/baseline/s1 --shard 1/2
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import next40_owner as OWNER  # noqa: E402
import next40_qualification as NQ  # noqa: E402
import public_journey_ten as PJT  # noqa: E402

D = ROOT / "docs/engineering/prospect98"
TYPED = {59: "Runway Financial", 48: "Safe Security", 63: "Chargebee", 2: "Domo"}


def _frozen():
    want = (D / "SPLIT_FROZEN.sha256").read_text().split()[0]
    if hashlib.sha256((D / "SPLIT_FROZEN.json").read_bytes()).hexdigest() != want:
        raise SystemExit("SPLIT_FROZEN.json changed after it was frozen")
    return json.loads((D / "IDENTITY_REGISTRY.json").read_text())["companies"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["DEVELOPMENT", "VALIDATION", "FINAL_UNTOUCHED"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--shard", default="1/1")
    ap.add_argument("--only", type=int, action="append")
    ap.add_argument("--sealed", action="store_true")
    ap.add_argument("--registered", action="store_true",
                    help="the tree carries the prospect-98 catalog: type the name and its "
                         "prefixes exactly as live_pass does and confirm the suggestion that "
                         "carries the catalog entity id (no website fallback)")
    a = ap.parse_args()
    if a.split != "DEVELOPMENT" and not a.sealed:
        raise SystemExit(f"{a.split} is held out: pass --sealed (results are not scored until its wave)")
    out = pathlib.Path(a.out); out = out if out.is_absolute() else ROOT / out
    if a.sealed and not out.name.startswith("sealed_") and not out.parent.name.startswith("sealed_"):
        raise SystemExit("a sealed run writes under a sealed_* directory")
    out.mkdir(parents=True, exist_ok=True)
    i, n = map(int, a.shard.split("/"))
    rows = [c for c in _frozen() if c["split"] == a.split and (not a.only or c["position"] in a.only)]
    rows = [c for k, c in enumerate(rows) if k % n == i - 1]
    typed = {c["position"]: TYPED.get(c["position"], c["analysis_target"]) for c in rows}
    domains = {typed[c["position"]].lower(): c["primary_domain"] for c in rows}
    found = {}
    real = PJT.suggest_live

    def suggest(op, t):
        res, took, st = real(op, t)
        dom = domains.get(t.strip().lower())
        if dom is None:
            return res, took, st
        hit = [r for r in res if dom in str(r.get("domain") or "")]
        found[t] = {"offered": len(res), "domain_hit": bool(hit),
                    "first": (res[0].get("legal_name") or res[0].get("common_name")) if res else None}
        if not hit:
            res = [{"legal_name": t, "common_name": t, "domain": dom, "entity_id": "", "cik": "",
                    "ticker": "", "country": "", "source": "typed website (no suggestion offered)"}]
        else:
            res = [dict(hit[0], entity_id="")]
        return res, took, st

    if a.registered:
        from intent_engine.company_ingestion.catalog_prospects98 import PROSPECT98_CATALOG
        sys.path.insert(0, str(ROOT / "scripts/prospect100"))
        from live_pass import _prefixes
        eid = {r["prospect98_position"]: r["entity_id"] for r in PROSPECT98_CATALOG}
        order = [(c["position"], typed[c["position"]], eid[c["position"]],
                  _prefixes(typed[c["position"]]), c["category"]) for c in rows]
        for _p, name, _e, pre, _c in order:
            PJT.PREFIXES[name] = pre
    else:
        PJT.suggest_live = suggest
        order = [(c["position"], typed[c["position"]], "", [typed[c["position"]]], c["category"]) for c in rows]
        for _p, name, _e, _x, _c in order:
            PJT.PREFIXES[name] = []
    NQ.FORTY = order
    NQ.COHORTS = {"ALL": [r[0] for r in order]}
    NQ.STATE = out / "state.json"
    NQ.ROOT = out
    OWNER.LOCK = out / "owner.json"
    sys.argv = [sys.argv[0], "--cohort", "ALL"]
    rc = NQ.main()
    (out / "search_offers.json").write_text(json.dumps(found, indent=1))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
