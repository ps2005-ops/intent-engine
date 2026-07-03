"""CLI entrypoint: `premortem` — a business decision as text + context -> structured risk audit.

Usage:
    premortem --input path/to/decision.json
    premortem --decision "We're expanding into Asia with $2M over 18 months" \\
        --revenue "$40k MRR" --growth-rate "12%/mo" --team-size 8 --runway-months 14 \\
        --market "B2B SaaS" --competitive-position "two well-funded competitors" \\
        --founder-goals "grow fast, raise Series A in 12 months"

decision.json shape:
    {
      "decision_text": "...",
      "context": {
        "revenue": "...", "growth_rate": "...", "team_size": 8, "runway_months": 14,
        "market": "...", "competitive_position": "...", "founder_goals": "...",
        "stated_priorities": ["..."]
      }
    }
"""

import argparse
import json
import sys

from ..core.schemas import RiskAudit, StructuredIntent
from .context_schema import BusinessContext
from .pipeline import run_premortem
from .schemas import ScenarioSet


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="premortem", description="Run a pre-mortem risk audit on a business decision.")
    parser.add_argument("--input", help="Path to a JSON file with decision_text + context.")
    parser.add_argument("--decision", help="The business decision as free text (alternative to --input).")
    parser.add_argument("--revenue")
    parser.add_argument("--growth-rate")
    parser.add_argument("--team-size", type=int)
    parser.add_argument("--runway-months", type=int)
    parser.add_argument("--market")
    parser.add_argument("--competitive-position")
    parser.add_argument("--founder-goals")
    parser.add_argument("--stated-priority", action="append", dest="stated_priorities", default=[])
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of formatted text.")
    return parser


def _load_from_args(args: argparse.Namespace):
    if args.input:
        with open(args.input) as f:
            payload = json.load(f)
        decision_text = payload["decision_text"]
        context = BusinessContext(**payload.get("context", {}))
        return decision_text, context

    if not args.decision:
        raise SystemExit("Provide either --input or --decision.")

    context = BusinessContext(
        revenue=args.revenue,
        growth_rate=args.growth_rate,
        team_size=args.team_size,
        runway_months=args.runway_months,
        market=args.market,
        competitive_position=args.competitive_position,
        founder_goals=args.founder_goals,
        stated_priorities=args.stated_priorities,
    )
    return args.decision, context


def _format_report(
    decision_text: str,
    intent: StructuredIntent,
    audit: RiskAudit,
    scenario_set: ScenarioSet,
    elapsed_seconds: float,
) -> str:
    lines = [
        f"DECISION: {decision_text}",
        "",
        "** " + audit.narrative_summary + " **",
        "",
        f"INFERRED INTENT: {intent.decision_summary}",
        f"  Goals: {', '.join(intent.goals) or '(none extracted)'}",
        f"  Constraints: {', '.join(intent.constraints) or '(none extracted)'}",
        f"  Risk tolerance: {intent.risk_tolerance}",
        "",
        f"PRIMARY PRIORITY: {scenario_set.primary_priority}",
        "",
        "SCENARIOS",
    ]
    for scenario in scenario_set.scenarios:
        lines.append(f"  {scenario.name.upper()} ({scenario.tag}): {scenario.key_deltas}")
    lines.append("")
    lines.append("RISK AUDIT")
    for i, fm in enumerate(audit.failure_modes, 1):
        lines.append(f"  {i}. [{fm.likelihood}] {fm.description}")
        lines.append(f"     -> {fm.rationale}")
    lines.append("")
    lines.append(f"KEY SENSITIVITY: {audit.key_sensitivity}")
    lines.append("")
    lines.append("RECOMMENDED STRESS-TESTS")
    for st in audit.recommended_stress_tests:
        lines.append(f"  - {st}")
    lines.append("")
    lines.append(f"({elapsed_seconds:.1f}s end-to-end)")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    decision_text, context = _load_from_args(args)

    # Typical latency is 7-9s; occasional calls (~5% in testing) take 11-13s due to
    # API-side variance unrelated to content length -- printed upfront so a slower
    # call reads as "still working," not "hung." Goes to stderr so --json output
    # piped to a file or another process stays clean.
    print("Running pre-mortem analysis (typically 7-9s, occasionally longer)...", file=sys.stderr)

    result = run_premortem(decision_text, context)

    if args.json:
        print(
            json.dumps(
                {
                    "intent": result.intent.model_dump(),
                    "risk_audit": result.risk_audit.model_dump(),
                    "scenario_set": result.scenario_set.model_dump(),
                    "elapsed_seconds": result.elapsed_seconds,
                },
                indent=2,
            )
        )
    else:
        print(_format_report(decision_text, result.intent, result.risk_audit, result.scenario_set, result.elapsed_seconds))

    return 0


if __name__ == "__main__":
    sys.exit(main())
