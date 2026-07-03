#!/usr/bin/env python
"""Run all 5 test business decisions through the pipeline and print the output for review.

This is the "read it yourself" complement to the automated tests: pytest checks shape and
latency, this script is how you judge whether the risk audits are actually any good.

Usage: python scripts/run_examples.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_PATH = REPO_ROOT / "tests" / "fixtures" / "business_decisions.json"

sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.simulator.cli import _format_report  # noqa: E402
from intent_engine.simulator.context_schema import BusinessContext  # noqa: E402
from intent_engine.simulator.pipeline import run_premortem  # noqa: E402


def main():
    with open(FIXTURES_PATH) as f:
        fixtures = json.load(f)

    total_elapsed = 0.0
    for fixture in fixtures:
        print("=" * 80)
        print(f"[{fixture['id']}]")
        context = BusinessContext(**fixture["context"])
        result = run_premortem(fixture["decision_text"], context)
        print(_format_report(fixture["decision_text"], result.intent, result.risk_audit, result.elapsed_seconds))
        total_elapsed += result.elapsed_seconds
        print()

    print("=" * 80)
    print(f"Ran {len(fixtures)} decisions, {total_elapsed:.1f}s total, {total_elapsed / len(fixtures):.1f}s avg.")


if __name__ == "__main__":
    main()
