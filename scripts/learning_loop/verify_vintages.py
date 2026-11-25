"""Live re-verification of the six July FRED observations: latest value and ALFRED first-release date."""
import json, os, sys, urllib.request, urllib.parse, urllib.error
for line in open(os.path.expanduser("~/intent-engine/.env")):
    if line.startswith("FRED_API_KEY="):
        os.environ["FRED_API_KEY"] = line.split("=",1)[1].strip().strip('"').strip("'")
KEY = os.environ.get("FRED_API_KEY")
assert KEY, "no FRED key"
def q(series, d, **extra):
    p = {"series_id": series, "api_key": KEY, "file_type": "json",
         "observation_start": d, "observation_end": d, **extra}
    try:
        with urllib.request.urlopen("https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(p), timeout=30) as r:
            return json.load(r)["observations"]
    except urllib.error.HTTPError as e:
        return [{"error": e.code, "msg": e.read().decode()[:200]}]
out = []
for l in open(sys.argv[1]):
    r = json.loads(l); rule = r["original"]["resolution_rule"]; o = r["observation"]
    s, d = rule["series"], o["date"]
    latest = q(s, d)
    first = q(s, d, output_type=4, realtime_start="1776-07-04", realtime_end="9999-12-31")
    allv = q(s, d, realtime_start="1776-07-04", realtime_end="9999-12-31")
    out.append({"id": r["prediction_id"][:8], "series": s, "obs_date": d, "rule": f'{rule["op"]} {rule["value"]} by {rule["by"]}',
                "p": r["original"]["probability"], "created": r["original"]["created_at"][:10],
                "latest_now": latest[0]["value"] if latest else None,
                "audit_latest": o["value_latest"],
                "first_release_now": first[0].get("value", first[0].get("msg")) if first else None,
                "first_published_now": first[0].get("realtime_start") if first else None,
                "audit_first_published": o["first_published"],
                "n_vintages": len(allv), "vintage_values": sorted({str(v.get("value", v.get("msg"))) for v in allv}),
                "original_failure": r["ledger_state"]["note"][:160], "failed_at": r["ledger_state"]["resolved_at"][:10],
                "audit_outcome": r["audit_outcome"]})
print(json.dumps(out, indent=1))
