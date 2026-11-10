"""Score an identity probe file against PROSPECT_REGISTRY.yaml.

Per prospect, the typed listed name is judged on two surfaces:

  entry   what /analyze does with the typed name:
          CORRECT      opens on the right company (or, for an absorbed /
                       closed company, says so; or, for a shared name, asks)
          WRONG        opens on, or identifies, a DIFFERENT company
          NOT_FOUND    says it cannot identify the company
  search  the first suggestion: CORRECT / WRONG / EMPTY

WRONG is the critical gate. A row existing is not a row being right.

Usage:
  python scripts/prospect100/score_identity.py PROBES.json [--label NAME]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

REG = Path("docs/engineering/prospect100/PROSPECT_REGISTRY.yaml")


def _host(url: str) -> str:
    return (url or "").split("//")[-1].split("/")[0].lower().removeprefix("www.")


def judge(probe: dict, exp: dict) -> tuple:
    p = probe["probes"][0]
    dom = (exp.get("primary_domain") or "").lower().removeprefix("www.")
    cik = str(exp.get("sec_cik") or "")
    eid = exp.get("entity_id")
    state = p["resolve_state"]
    stop = exp.get("entry_readiness") == "STOP_NO_LONGER_INDEPENDENT"
    group = exp.get("disambiguation_group")
    if state == "COMPANY_NOT_FOUND":
        entry = "NOT_FOUND"
    elif state == "AMBIGUOUS_COMPANY":
        ids = [c.get("entity_id") for c in p.get("choices", [])] \
            if p.get("choices") else []
        entry = "CORRECT" if (group and (not ids or eid in ids)) else "WRONG"
    elif state == "NO_LONGER_INDEPENDENT":
        entry = "CORRECT" if stop and p.get("resolve_company_id") == eid \
            else "WRONG"
    elif state == "IDENTIFIED_NO_DOMAIN":
        entry = "CORRECT" if cik and p.get("resolve_company_id") == cik \
            else "WRONG"
    else:
        ok = (_host(p["resolve_website"]) == dom
              or p.get("resolve_company_id") == eid)
        entry = "CORRECT" if ok and not stop else "WRONG"
    sug = p["suggestions"]
    if not sug:
        search = "EMPTY"
    else:
        top = sug[0]
        ok = (top.get("entity_id") == eid
              or (dom and _host(top.get("domain", "")) == dom)
              or (cik and str(top.get("cik", "")).lstrip("0") == cik))
        search = "CORRECT" if ok else "WRONG"
    return entry, search


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("probes")
    ap.add_argument("--label", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    reg = {r["prospect_id"]: r for r in
           yaml.safe_load(REG.read_text())["prospects"]}
    rows = json.loads(Path(args.probes).read_text())
    per, e_count, s_count, by_tier = [], Counter(), Counter(), {}
    for r in rows:
        exp = reg[r["prospect_id"]]
        if exp.get("register") == "validation manifest":
            exp = {**exp, "primary_domain": "workday.com"}
        entry, search = judge(r, exp)
        e_count[entry] += 1
        s_count[search] += 1
        t = by_tier.setdefault(exp["tier"], Counter())
        t[entry] += 1
        per.append({"prospect_id": r["prospect_id"],
                    "name": r["name_as_listed"], "entry": entry,
                    "search": search,
                    "resolved_as": r["probes"][0]["resolve_name"],
                    "suggest_ms": r["probes"][0]["suggest_ms"]})
    ms = sorted(x["suggest_ms"] for x in per)
    summary = {"label": args.label, "entry": dict(e_count),
               "search_top1": dict(s_count),
               "entry_by_tier": {k: dict(v) for k, v in sorted(by_tier.items())},
               "suggest_ms_p50": ms[len(ms) // 2],
               "suggest_ms_p95": ms[int(len(ms) * 0.95) - 1],
               "wrong_company": [x for x in per
                                 if "WRONG" in (x["entry"], x["search"])]}
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "wrong_company"}, indent=1))
    for x in summary["wrong_company"]:
        print("  WRONG:", x["prospect_id"], x["name"], "->", x["resolved_as"],
              f'(entry={x["entry"]}, search={x["search"]})')
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary,
                                              "per_prospect": per}, indent=1))


if __name__ == "__main__":
    main()
