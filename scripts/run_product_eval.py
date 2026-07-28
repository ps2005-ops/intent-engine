#!/usr/bin/env python3
"""Run the product-evaluation suite and print the failure clusters."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from intent_engine.product_eval.harness import build_cases, run_cases

def main():
    out = run_cases(build_cases())
    print(f"cases={out['total_cases']} failed={out['failed_cases']} "
          f"pass_rate={out['pass_rate']}")
    print("\nFAILURE CLUSTERS (most common first):")
    for name, info in out["failure_clusters"].items():
        print(f"  {info['count']:>3}  {name}")
    print("\nBY PERSONA (failed/total):")
    for k, v in sorted(out["by_persona"].items(),
                       key=lambda kv: -kv[1]["failed"]):
        if v["failed"]:
            print(f"  {v['failed']:>2}/{v['total']:<3} {k}")
    path = sys.argv[1] if len(sys.argv) > 1 else "reports/product_eval.json"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(out, open(path, "w"), indent=2)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
