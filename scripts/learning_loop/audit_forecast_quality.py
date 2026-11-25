"""Run the forecast-quality gate over every real evaluation ledger (read-only).

    PYTHONPATH=src python scripts/learning_loop/audit_forecast_quality.py OUT.json
Values knowable at creation come from ALFRED (realtime bounded to the cutoff).
"""
import collections, json, os, sqlite3, sys, urllib.parse, urllib.request
from intent_engine.core import forecast_quality as FQ

H = os.path.expanduser("~")


def observer():
    key = os.environ.get("FRED_API_KEY")
    def obs(series, as_of):
        q = {"series_id": series, "api_key": key, "file_type": "json",
             "observation_start": "2025-01-01", "realtime_start": as_of,
             "realtime_end": as_of}
        try:
            with urllib.request.urlopen("https://api.stlouisfed.org/fred/series/"
                                        "observations?" + urllib.parse.urlencode(q),
                                        timeout=30) as r:
                return [float(o["value"]) for o in json.load(r)["observations"]
                        if o["value"] != "."]
        except Exception:
            return None
    return obs if key else None


def main(out_path):
    obs = observer()
    report = {}
    c = sqlite3.connect(f"file:{H}/intent-engine/data/prediction_ledger.db?mode=ro", uri=True)
    july = {}
    for i, ent, data in c.execute("select id, entity_id, data from predictions order by rowid"):
        july.setdefault(i, (ent, json.loads(data)))      # the ORIGINAL registration
    jc = [FQ.from_july(d, classification=FQ.classify_entity(e))
          for e, d in july.values()]
    led = [json.loads(l) for l in open(f"{H}/ie-paper-validation/reports/paper_validation/forward_shadow_ledger.jsonl")]
    pc = [FQ.from_paper(r["payload"]) for r in led if r.get("event") == "REGISTER"]
    first, hist = {}, collections.defaultdict(list)
    for l in open(f"{H}/intent-engine-econ/reports/real_forward_expectations.jsonl"):
        r = json.loads(l); first.setdefault(r["expectation_id"], r); hist[r["expectation_id"]].append(r)
    ec = [FQ.from_econ(r, hist[k]) for k, r in first.items()]
    for name, cs in (("july_prediction_ledger", jc), ("paper_forward_977", pc), ("econ_forward", ec)):
        res = FQ.admit_batch(cs, observe=obs)
        codes = collections.Counter(f.code for k in (FQ.REJECT, FQ.QUARANTINE)
                                    for _, fs in res[k] for f in fs)
        warns = collections.Counter(f.code for _, fs in res[FQ.ADMIT] for f in fs)
        report[name] = {"forecasts": len(cs), "admit": len(res[FQ.ADMIT]),
                        "quarantine": len(res[FQ.QUARANTINE]), "reject": len(res[FQ.REJECT]),
                        "finding_codes": dict(codes), "warnings_on_admitted": dict(warns),
                        "detail": [{"id": c.forecast_id[:24], "verdict": k,
                                    "findings": [f"{f.code}: {f.detail}" for f in fs]}
                                   for k in (FQ.REJECT, FQ.QUARANTINE) for c, fs in res[k]][:40]}
    json.dump(report, open(out_path, "w"), indent=1)
    for k, v in report.items():
        print(k, {x: v[x] for x in ("forecasts", "admit", "quarantine", "reject")}, v["finding_codes"])
    for k in ("paper_forward_977", "econ_forward"):
        print(k, "warnings on admitted:", report[k]["warnings_on_admitted"])
    for d in report["july_prediction_ledger"]["detail"]:
        print("  ", d["id"][:8], d["verdict"], "|", " ; ".join(d["findings"])[:230])


if __name__ == "__main__":
    main(sys.argv[1])
