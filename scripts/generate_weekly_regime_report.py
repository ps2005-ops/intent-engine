#!/usr/bin/env python
"""Task M7 (market-engine-execution-plan.md): the weekly regime report --
the user-facing product of this phase.

Real end-to-end pipeline: fetch the current regime snapshot (M1 FRED +
M6 Tiingo, real data) -> compute it (M2, pure code) -> extract a
trigger-condition profile (one real, isolated LLM call, the exact
prompt/schema design M4's reliability gate verified) -> match against
the mechanism library (M3, deterministic) -> draft 1-3 resolvable market
predictions (one real, isolated LLM call, house pattern: model drafts,
code validates + records) -> render the full report, with a code-level
language-wall check on the final rendered text before it's ever printed.

Headline input is a human/upstream responsibility, not something this
script fetches itself -- no news-ingestion vendor is wired into this
phase (out of scope per the plan's own Part C-M), so real headlines are
passed in via --headline (repeatable).

Usage:
  python scripts/generate_weekly_regime_report.py --entity-id "macro-watch" \
      --headline "..." --headline "..." [--output reports/weekly_regime_report.txt]
"""

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))  # for the additive --founder-html renderer import

from intent_engine.core.mechanism_library import match_mechanisms  # noqa: E402
from intent_engine.core.prediction_ledger import DEFAULT_LEDGER_PATH  # noqa: E402
from intent_engine.core.regime_engine import regime_snapshot  # noqa: E402
from intent_engine.core.regime_report import (  # noqa: E402
    draft_market_predictions,
    extract_trigger_conditions,
    fetch_current_series_data,
    render_data_gaps_section,
    render_full_report,
    render_mechanisms_section,
    render_snapshot_numbers_for_extraction,
)


def generate_report(entity_id: str, headlines: list, path=DEFAULT_LEDGER_PATH, as_of: date = None) -> str:
    as_of = as_of or date.today()

    series_data, price_series = fetch_current_series_data(as_of)
    snapshot = regime_snapshot(as_of.isoformat(), series_data, price_series=price_series)

    extraction_text = render_snapshot_numbers_for_extraction(series_data, price_series, as_of)
    trigger_conditions = extract_trigger_conditions(extraction_text, headlines)
    ranked = match_mechanisms(trigger_conditions)
    mechanisms_text = render_mechanisms_section(ranked)

    predictions = draft_market_predictions(entity_id, extraction_text, mechanisms_text, ledger_path=path, as_of=as_of)

    return render_full_report(snapshot, mechanisms_text, predictions, ledger_path=path,
                              data_gaps_text=render_data_gaps_section(series_data))


# LEGACY CONTAINMENT (2026-08-12). This pipeline was once mistaken for the
# market intelligence system of record: an exploration read its ledger, found
# it twenty-three days stale, and reported that the learning system had learned
# nothing. The banner is printed by main() so the mistake cannot be repeated
# by anyone — human or agent — who runs this file and reads its output.
def _legacy_banner() -> None:
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from intent_engine.market import system_of_record as SOR
    banner = SOR.legacy_banner("daily_market_predictions")
    if banner:
        print(banner)


def main(argv=None):
    _legacy_banner()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--headline", action="append", default=[], help="A real current headline (repeatable).")
    parser.add_argument(
        "--headlines-from-feeds", action="store_true",
        help="Source headlines from the approved RSS allowlist (core.headline_feed) instead of --headline. "
             "Deterministic top-K with provenance in the report header; zero qualifying headlines -> "
             "numeric-only mode (item 3, docs/BA_ACCELERATION_PROPOSAL.md, approved 2026-07-18).")
    parser.add_argument("--path", default=str(DEFAULT_LEDGER_PATH))
    parser.add_argument("--output", default=None, help="Optional file to save the rendered report to.")
    parser.add_argument(
        "--founder-html", action="store_true",
        help="Also emit the presentation-grade founder-readable HTML next to --output "
             "(<output>.founder.html), via scripts/render_founder_report. Additive: same data, "
             "zero new claims (approved 2026-07-19 decision 3). Requires --output.")
    args = parser.parse_args(argv)

    headlines = args.headline
    provenance_block = None
    if args.headlines_from_feeds:
        if args.headline:
            parser.error("--headline and --headlines-from-feeds are mutually exclusive -- pick one input path.")
        from intent_engine.core.headline_feed import fetch_feeds, render_provenance, select_headlines
        as_of = date.today()
        selected = select_headlines(fetch_feeds(), as_of)
        headlines = [h.title for h in selected]
        provenance_block = render_provenance(selected, as_of)

    report = generate_report(args.entity_id, headlines, path=args.path)
    if provenance_block is not None:
        report = provenance_block + "\n\n" + report
    print(report)
    if args.output:
        Path(args.output).write_text(report)
        if args.founder_html:
            from render_founder_report import parse_report, render
            founder_path = Path(args.output).with_suffix(".founder.html")
            founder_path.write_text(render(parse_report(report)))
            print(f"founder-readable HTML written: {founder_path}", file=sys.stderr)
    elif args.founder_html:
        parser.error("--founder-html requires --output (the HTML is written next to it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
