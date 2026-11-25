"""Daily FX4 job: register new intent-vs-behaviour forecasts, resolve due ones.

Reads the market evidence ledger (read-only) and SEC XBRL; appends to its OWN
ledger (single writer: the learning cycle). Every new forecast passes the
forecast-quality gate first.

    python -m intent_engine.market.intent_behaviour_job \\
        --evidence ~/intent-engine-market/reports/market/learning_ledger.jsonl \\
        --audit ~/intent-engine-market/reports/market/signal_audit.jsonl \\
        --ledger reports/experiments/fx4_intent_behaviour.jsonl [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import pathlib
import urllib.request

from intent_engine.core import forecast_quality as FQ
from intent_engine.market import intent_behaviour as IB

REV = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
       "SalesRevenueNet", "RevenuesNetOfInterestExpense")


def _sec(url):  # pragma: no cover - live
    from intent_engine.company_ingestion.third_party_filings import _sec_user_agent
    req = urllib.request.Request(url, headers={"User-Agent": _sec_user_agent(),
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
        return json.loads(gzip.decompress(b) if r.headers.get(
            "Content-Encoding") == "gzip" else b)


def revenue_facts_live():  # pragma: no cover - live
    ciks, cache = {}, {}

    def facts(sym):
        if not ciks:
            for v in _sec("https://www.sec.gov/files/company_tickers.json").values():
                ciks[v["ticker"].upper()] = int(v["cik_str"])
        cik = ciks.get(sym.upper())
        if cik is None:
            return []
        if sym not in cache:
            g = _sec(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
                     ).get("facts", {}).get("us-gaap", {})
            out = []
            for c in REV:
                for unit, vals in (g.get(c, {}).get("units") or {}).items():
                    if unit != "USD":
                        continue
                    for v in vals:
                        if "start" in v and 80 <= (_dt.date.fromisoformat(v["end"])
                                - _dt.date.fromisoformat(v["start"])).days <= 100:
                            out.append((v["end"], v["filed"], float(v["val"])))
            cache[sym] = out
        return cache[sym]
    return facts


def _read(path):
    p = pathlib.Path(path)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] \
        if p.exists() else []


def _gate(f) -> list:
    c = FQ.Contract(
        ledger="fx4", forecast_id=f["forecast_id"], created_at=f["created_at"],
        information_cutoff=f["information_cutoff"], target=f["target"],
        prediction=f["prediction"], horizon="next reported quarter",
        resolve_on="", resolution_rule={"type": "xbrl_acceleration_sign"},
        outcome_source=f["outcome_source"], mechanism=f["mechanism"],
        baseline=",".join(f["baselines"]), model_version=f["model_version"],
        evidence_provenance=[f["trigger_evidence_id"]],
        invalidation=f["invalidation"], evidence_dates=[f["information_cutoff"]],
        identity=(f["symbol"], f["last_known_quarter_end"]))
    return FQ.check(c)


def run(*, evidence_path, audit_path, ledger_path, today, facts_fn, write=True):
    led = _read(ledger_path)
    state = {}
    for r in led:
        state[r["forecast_id"]] = r
    ev = {}
    for r in _read(evidence_path):
        if r.get("record") == "evidence":
            ev.setdefault(r["evidence_id"], r)
    sym = {}
    for r in _read(audit_path):
        sym[r["company_id"]] = r["instrument"]
    company_of = lambda e: sym.get((e.get("subject_company") or "")
                                   .replace("_", "-")) or sym.get(e.get("subject_company"))
    new = IB.register(ev.values(), revenue_facts=facts_fn, company_of=company_of,
                      today=today, existing_ids=list(state))
    admitted, held = [], []
    for f in new:
        fs = _gate(f)
        (admitted if FQ.verdict(fs) == FQ.ADMIT else held).append((f, fs))
    resolved = []
    for fid, f in state.items():
        if f.get("state") in ("RESOLVED", "EXPIRED"):
            continue
        r = IB.resolve(f, facts_fn(f["symbol"]), today=today)
        if r:
            resolved.append(r)
    rows = [f for f, _ in admitted] + resolved
    if write and rows:
        p = pathlib.Path(ledger_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, sort_keys=True) + "\n")
    return {"contract": IB.CONTRACT, "today": today, "registered": len(admitted),
            "quality_held": [(f["forecast_id"], [x.code for x in fs]) for f, fs in held],
            "resolved": len(resolved), "open": sum(1 for f in state.values()
                                                   if f.get("state") is None),
            "first_trigger_date": IB.FIRST_TRIGGER_DATE, "dry_run": not write}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    out = run(evidence_path=a.evidence, audit_path=a.audit, ledger_path=a.ledger,
              today=_dt.date.today().isoformat(), facts_fn=revenue_facts_live(),
              write=not a.dry_run)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
