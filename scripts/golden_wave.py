#!/usr/bin/env python3
"""Drive several companies through the whole product and score the wave.

    python scripts/golden_wave.py --set golden --out reports/wave/a
    python scripts/golden_wave.py --set golden --live https://... --out ...

WHY A WAVE AND NOT SIX INVOCATIONS
----------------------------------
Three of the measurements that matter are only defined ACROSS companies, and
running one company at a time cannot produce any of them:

    §78  is the historical explanation the same for a bank and a miner?
    §66  which defects cluster, and on what shared attribute?
    §71  what does the WORST company score, not the mean?

The last is the one that keeps being lost. A mean rises when the easy
companies get easier; the company a customer actually finds is the worst one,
because they did not pick from our list.

This is the harness the 100-company programme runs on. It is exercised on six
companies now so that the framework is proven before a hundred runs are spent
discovering that it is not.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from intent_engine.product_eval import company_matrix as CM       # noqa: E402
from intent_engine.product_eval import defect_taxonomy as DT      # noqa: E402
from intent_engine.product_eval import executive_personas as EP   # noqa: E402

#: §55. The golden six, by the name a customer would type.
GOLDEN = (
    ("Cloudflare", "https://www.cloudflare.com"),
    ("Caterpillar", "https://www.caterpillar.com"),
    ("Shopify", "https://www.shopify.com"),
    ("Johnson & Johnson", "https://www.jnj.com"),
    ("Bank of America", "https://www.bankofamerica.com"),
    ("Stripe", "https://stripe.com"),
)

#: §73. Palantir is the deployed walkthrough's fourth company and is included
#: in the live set even though it is not one of the golden six.
LIVE_EXTRA = (("Palantir", "https://www.palantir.com"),)

SETS = {"golden": GOLDEN, "live": GOLDEN + LIVE_EXTRA,
        "pair": GOLDEN[:2]}


def run_one(name, website, out_dir, live, token):
    cmd = [sys.executable, str(HERE / "golden_cycle.py"), name, website,
           "--out", str(out_dir)]
    if live:
        cmd += ["--live", live]
    if token:
        cmd += ["--token", token]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - started, 1)
    return proc, elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="which", default="golden",
                    choices=sorted(SETS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", default="")
    ap.add_argument("--token", default="")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, persona_results, history_pages = [], [], {}

    for name, website in SETS[args.which]:
        slug = name.lower().replace(" ", "-").replace("&", "and")
        company_dir = out / slug
        proc, elapsed = run_one(name, website, company_dir, args.live,
                                args.token)
        score_path = company_dir / "score.json"
        if not score_path.exists():
            print(f"  {name:20} NO SCORE ({elapsed}s)")
            print("   " + (proc.stderr or proc.stdout)[-500:])
            rows.append(CM.CompanyRow(company=name, latency_s=elapsed))
            continue
        payload = json.loads(score_path.read_text())
        scores = {s["dimension"]: s["score"] for s in payload["scores"]}
        scores["overall"] = payload["overall"]
        defects = tuple((f["code"], f["surface"])
                        for f in payload.get("findings", []))
        rows.append(CM.CompanyRow(
            company=name, model_class=payload.get("model_class", ""),
            scores=scores, defects=defects, latency_s=elapsed,
            run_id=payload.get("run_id", ""),
            at=_dt.datetime.now(_dt.timezone.utc).isoformat()))
        pages = {k: (company_dir / f"{k}.txt").read_text()
                 for k in ("intro", "slides", "full", "story", "history",
                           "connect")
                 if (company_dir / f"{k}.txt").exists()}
        history_pages[name] = pages.get("history", "")
        persona_results.append(EP.score(company=name, pages=pages))
        sev1 = sum(1 for f in payload.get("findings", [])
                   if f["severity"] == "SEV1")
        sev2 = sum(1 for f in payload.get("findings", [])
                   if f["severity"] == "SEV2")
        print(f"  {name:20} {payload['overall']:5.2f}  "
              f"min-core {payload['min_core']:4.1f}  "
              f"SEV1 {sev1}  SEV2 {sev2}  {elapsed:6.1f}s")

    wave = CM.WaveResult(
        wave=args.label or args.which, rows=tuple(rows),
        at=_dt.datetime.now(_dt.timezone.utc).isoformat())
    persona = EP.aggregate(persona_results)
    # §78. Two companies whose history reads the same is a template, and it
    # is invisible from either company's own page.
    templated = DT.history_is_templated(history_pages)

    payload = wave.as_dict()
    payload["persona"] = persona
    payload["history_template_pairs"] = templated
    (out / "wave.json").write_text(json.dumps(payload, indent=2))

    print(f"\n  WAVE {wave.wave}: mean {wave.mean}/10, "
          f"worst {payload['worst']} at {payload['worst_score']}, "
          f"{wave.defects_per_company} defects/company")
    for dimension in ("history", "history_expectation",
                      "history_counterfactual", "strategic_synthesis",
                      "full_analysis_quality", "flow_quality",
                      "identity_correctness", "data_resolution"):
        print(f"    {dimension:28} {wave.dimension_mean(dimension):5.2f}")
    print(f"  PERSONA (simulated, not customers): {persona['overall']}/5 "
          f"worst {persona['worst_company']} {persona['worst_overall']}")
    for dimension, value in sorted(persona["by_dimension"].items(),
                                   key=lambda kv: kv[1])[:5]:
        print(f"    {dimension:28} {value}")
    if templated:
        print(f"  !! HISTORY TEMPLATE COLLAPSE: {templated}")
    for cluster in CM.cluster(wave.rows)[:6]:
        print(f"  cluster {cluster.code:32} x{len(cluster.companies)} "
              f"{cluster.scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
