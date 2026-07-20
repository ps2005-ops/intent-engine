"""CLI entrypoint: `premortem` — a business decision as text + context -> structured risk audit.

Usage:
    premortem --input path/to/decision.json --entity-id "Acme Inc"
    premortem --decision "We're expanding into Asia with $2M over 18 months" \\
        --entity-id "Acme Inc" \\
        --revenue "$40k MRR" --growth-rate "12%/mo" --team-size 8 --runway-months 14 \\
        --market "B2B SaaS" --competitive-position "two well-funded competitors" \\
        --founder-goals "grow fast, raise Series A in 12 months"

--entity-id is required: every run writes an EntityMemoryRecord to entity memory,
tagged to the entity (founder/company) this decision is about. Free-text input is
fine -- e.g. "Acme Inc" and "acme inc." both accumulate under the same normalized
entity_id (see core/entity_memory.normalize_entity_id).

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

from ..core.entity_memory import EntityMemoryRecord, SqliteEntityMemoryWriter, normalize_entity_id
from ..core.schemas import RiskAudit, StructuredIntent
from .context_schema import BusinessContext
from .pipeline import run_premortem
from .schemas import ScenarioSet


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="premortem", description="Run a pre-mortem risk audit on a business decision.")
    parser.add_argument("--entity-id", required=True, help="Who/what this decision is about (founder or company name) -- tags the entity-memory record.")
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
    parser.add_argument(
        "--mechanisms", action="store_true",
        help="T005: also run the isolated structural-mechanism extraction (1 extra call) and, when "
             "anything genuinely matches, append the 'Structural mechanisms possibly in play' section. "
             "No match -> no section (correct silence). Off by default: zero extra calls.")
    parser.add_argument(
        "--explain", action="store_true",
        help="T007: with --mechanisms, render the fuller 'Why this may be in play' explanation "
             "(matched conditions + verbatim documented causal chain + cited historical precedent) "
             "instead of the one-line section. Deterministic, 0 extra calls. No match -> no section.")
    parser.add_argument(
        "--record-predictions", action="store_true",
        help="T006: also derive 1-3 resolvable predictions from the audit's failure modes and "
             "record them to the append-only ledger (source=premortem; 1 extra isolated call; "
             "recording is code, the model has no record field). Off by default: zero extra calls.")
    return parser


def _record_confirmation(n: int) -> str:
    """T006 bar (e): a plain recording confirmation -- no forecast/accuracy
    framing (tested by word-boundary grep)."""
    return f"Recorded {n} prediction(s) to the ledger (source=premortem)."


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

    mechanism_client = None
    if args.mechanisms:
        from ..core.llm_client import LLMClient
        from .mechanism_section import FAST_MODEL
        mechanism_client = LLMClient(model=FAST_MODEL)

    bridge_client = None
    if args.record_predictions:
        from ..core.llm_client import LLMClient
        from ..core.premortem_prediction_bridge import FAST_MODEL as BRIDGE_FAST_MODEL
        bridge_client = LLMClient(model=BRIDGE_FAST_MODEL)

    result = run_premortem(
        decision_text, context, mechanism_client=mechanism_client,
        bridge_client=bridge_client, bridge_entity_id=args.entity_id)

    if args.json:
        payload = {
            "intent": result.intent.model_dump(),
            "risk_audit": result.risk_audit.model_dump(),
            "scenario_set": result.scenario_set.model_dump(),
            "elapsed_seconds": result.elapsed_seconds,
        }
        if result.ranked_mechanisms is not None:
            payload["mechanisms"] = [
                {"name": r.mechanism.name, "confidence_tier": r.mechanism.confidence_tier,
                 "matched_conditions": list(r.matched_conditions),
                 "historical_instance": {"case": r.mechanism.historical_instances[0].case,
                                          "year": r.mechanism.historical_instances[0].year}}
                for r in result.ranked_mechanisms
            ]
        print(json.dumps(payload, indent=2))
    else:
        print(_format_report(decision_text, result.intent, result.risk_audit, result.scenario_set, result.elapsed_seconds))
        if result.ranked_mechanisms:
            if args.explain:
                from .mechanism_section import render_mechanism_explanation
                section = render_mechanism_explanation(result.ranked_mechanisms)
            else:
                from .mechanism_section import render_mechanism_section
                section = render_mechanism_section(result.ranked_mechanisms)
            if section:
                print("\n" + section)

    # Entity-memory write happens here, after run_premortem() returns -- not inside
    # run_premortem() itself, so callers that use run_premortem() directly
    # (tests/test_simulator_e2e.py, scripts/run_examples.py) are unaffected by this
    # CLI-only behavior, per the Weeks 1-4 call-site audit.
    record = EntityMemoryRecord(
        entity_id=args.entity_id,
        source="simulator",
        decision_text=decision_text,
        goals=result.intent.goals,
        constraints=result.intent.constraints,
        risk_tolerance=result.intent.risk_tolerance,
        primary_priority=result.scenario_set.primary_priority,
    )
    SqliteEntityMemoryWriter().write(record)
    print(f"Saved to entity memory: {normalize_entity_id(args.entity_id)}", file=sys.stderr)

    # T006: plain recording confirmation (bar e -- no forecast/accuracy
    # framing; stderr, same convention as the entity-memory line).
    if result.ledgered_predictions is not None:
        print(_record_confirmation(len(result.ledgered_predictions)), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
