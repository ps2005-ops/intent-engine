"""Migrate the Research Asset Ledger from markdown into the durable ledger.

Day 15 and 16 kept the ledger as a hand-maintained table in
`docs/RESEARCH_ASSETS.md`. That was honest and it is not durable: an unattended
system writes to it every night, and a table a process rewrites has no memory
of what it used to say.

This carries the thirteen existing assets across WITH their real first-observed
and last-validated dates, so no history is invented and none is lost. The
markdown stays as the human-readable narrative; the JSONL becomes the record
of what is believed and why.

IDEMPOTENT: `declare` returns the existing asset rather than duplicating it, so
re-running this is safe and appends nothing.

    python scripts/seed_research_assets.py [--path reports/market/research_assets.jsonl]
"""
import argparse

from intent_engine.market.assets import (
    ACCEPTED, ARCHITECTURE_PRINCIPLE, AssetLedger, DEFAULT_PATH,
    INTEGRITY_FAILURE, MEASUREMENT_TECHNIQUE, OPERATIONAL_PRINCIPLE,
    VALIDATED_NEGATIVE, VALIDATED_POSITIVE,
)

# Day N -> the real calendar date it happened on. Phase 2 day 1 was 2026-07-15.
DAY = {1: "2026-07-15", 3: "2026-07-17", 4: "2026-07-18", 5: "2026-07-19",
       7: "2026-07-21", 8: "2026-07-22", 10: "2026-07-24", 11: "2026-07-25",
       12: "2026-07-26", 14: "2026-07-28", 15: "2026-07-29",
       16: "2026-07-30", 17: "2026-07-31"}

ASSETS = [
    dict(asset_id="N1", asset_class=VALIDATED_NEGATIVE,
         title="Price-transform signals have no edge on this universe",
         claim="Momentum, mean reversion, strong-trend and calm-trend are all "
               "indistinguishable from 0.500.",
         confidence=0.9, first=1, last=15, sample_size=66,
         effective_sample_size=66,
         scope="the 28-company universe, daily bars, 21-day horizon",
         limitations="does not generalise beyond price transforms",
         contradiction="a price transform clearing 0.500 at n_eff >= 30 under "
                       "walk-forward evaluation",
         impact="price transforms are closed as a FAMILY, not one at a time",
         evidence=("signal_bakeoff", "horizon_bakeoff")),
    dict(asset_id="N2", asset_class=VALIDATED_NEGATIVE,
         title="8-K/6-K event drift does not exist at a detectable magnitude",
         claim="Post-event drift measures 0.4912 at n_eff 400.",
         confidence=0.95, first=4, last=15, sample_size=1200,
         effective_sample_size=400,
         scope="8-K/6-K filings, 2016-2026",
         limitations="US and cross-listed filers only",
         contradiction="a subclass of event showing drift at n_eff >= 100",
         impact="best-powered result in the project; event drift is closed",
         evidence=("event_bakeoff",)),
    dict(asset_id="N3", asset_class=VALIDATED_NEGATIVE,
         title="Periodic-report drift does not exist",
         claim="0.5019 at n_eff 49 over ten years.",
         confidence=0.75, first=4, last=15, sample_size=210,
         effective_sample_size=49,
         scope="10-K/10-Q/annual reports",
         limitations="n_eff 49 is modest; a small effect could hide",
         contradiction="drift at n_eff >= 100",
         impact="deprioritised, not closed", evidence=("event_bakeoff",)),
    dict(asset_id="N4", asset_class=VALIDATED_NEGATIVE,
         title="Slow-mechanism hypotheses are unmeasurable at reachable depth",
         claim="Insider buying, activist stakes and proxy drift reach n_eff 1, "
               "3 and 10; design effect up to 4352x.",
         confidence=0.9, first=4, last=15, sample_size=4352,
         effective_sample_size=1,
         scope="slow corporate-action mechanisms",
         limitations="a statement about DATA DEPTH, not about the mechanisms",
         contradiction="a data source giving n_eff >= 30 for one of them",
         impact="stop proposing them until data depth changes",
         evidence=("event_bakeoff", "sampling.design_effect")),
    dict(asset_id="P1", asset_class=VALIDATED_POSITIVE,
         title="Industry evidence causally unlocks decisions",
         claim="Ablation: 2 of 2 positions flip to WATCH when industry "
               "evidence is removed; 0 spuriously unlocked.",
         confidence=0.55, first=10, last=12, sample_size=2,
         effective_sample_size=2,
         scope="live path only — replay depth is 87 days",
         limitations="n=2. Cannot validate a signal, only unlock live "
                     "decisions.",
         contradiction="an ablation showing positions survive removal",
         impact="the only positive result in the ledger",
         evidence=("industry ablation day 10",)),
    dict(asset_id="M1", asset_class=MEASUREMENT_TECHNIQUE,
         title="Effective sample size, not row count",
         claim="Overlapping windows are merged before any rate is reported.",
         confidence=0.95, first=3, last=15,
         scope="every statistical claim in the project",
         limitations="none known",
         contradiction="a case where naive n is the honest denominator",
         impact="caught the 0.359 false discovery on day 3",
         evidence=("sampling.merge_windows",)),
    dict(asset_id="M2", asset_class=OPERATIONAL_PRINCIPLE,
         title="Event frequency is the enemy of independence",
         claim="More companies raise effective evidence only when they add "
               "independent cross-sectional events.",
         confidence=0.9, first=3, last=5,
         scope="universe expansion decisions", limitations="",
         contradiction="a universe expansion that raises n_eff proportionally",
         impact="stopped 'add more companies' being treated as free power",
         evidence=("day 5 measurement",)),
    dict(asset_id="M3", asset_class=OPERATIONAL_PRINCIPLE,
         title="Fixtures are insufficient for ranking bottlenecks",
         claim="A simulation that omits a wired component will conclude the "
               "component does nothing.",
         confidence=0.9, first=8, last=8,
         scope="bottleneck ranking",
         limitations="learned from ONE incident; not re-validated since",
         contradiction="a fixture-based ranking later confirmed live",
         impact="day 8's conclusion was retracted on day 9",
         evidence=("day 8 error, day 9 correction")),
    dict(asset_id="M4", asset_class=ARCHITECTURE_PRINCIPLE,
         title="Independence and relevance are separate conditions",
         claim="Corroboration requires an author other than the subject AND a "
               "category that can speak to the claim. Never traded off.",
         confidence=0.9, first=7, last=11,
         scope="the evidence model", limitations="",
         contradiction="a claim corroborated by satisfying only one",
         impact="made relabelling-to-unlock structurally impossible",
         evidence=("corroboration.REQUIREMENTS",)),
    dict(asset_id="M5", asset_class=ARCHITECTURE_PRINCIPLE,
         title="Authorship is not subject",
         claim="13 of 175 real documents express a source that differs from "
               "their subject; 19% carry more than one subject.",
         confidence=0.9, first=11, last=11, sample_size=175,
         scope="evidence semantics",
         limitations="measured once, on one corpus; not re-validated since",
         contradiction="a corpus where source and subject always agree",
         impact="two-dimensional evidence semantics; changed no decision",
         evidence=("day 11 measurement",)),
    dict(asset_id="M6", asset_class=MEASUREMENT_TECHNIQUE,
         title="Calendar time is not evidence",
         claim="Three days of 3%, 8%, 4% satisfies a three-day rule and "
               "establishes nothing. The test is dispersion, not duration.",
         confidence=0.95, first=14, last=16,
         scope="bottleneck promotion", limitations="",
         contradiction="a stable conclusion reached on duration alone",
         impact="replaced the calendar rule with CV <= 40% and n >= 5",
         evidence=("funnel.promote_bottleneck",)),
    dict(asset_id="M7", asset_class=OPERATIONAL_PRINCIPLE,
         title="Horizons belong to mechanisms, never to statistical power",
         claim="A horizon is never shortened to increase power.",
         confidence=0.9, first=4, last=4,
         scope="hypothesis design",
         limitations="asserted as doctrine; not re-validated since",
         contradiction="a mechanism whose natural horizon is genuinely "
                       "ambiguous",
         impact="blocks the most tempting form of p-hacking here",
         evidence=("PREREGISTRATION_day4_horizons.md",)),
    # --- Day 17 ------------------------------------------------------------
    dict(asset_id="I1", asset_class=INTEGRITY_FAILURE,
         title="Point-in-time guards must compare timezone-consistent frames",
         claim="The leakage guard compared a UTC retrieval stamp against an "
               "as_of expressed in the operating timezone. Between 20:00 and "
               "midnight America/Toronto, UTC has rolled over, so every "
               "freshly-retrieved observation was dated tomorrow and dropped. "
               "The symptom was `evidence: 0` -- indistinguishable from "
               "'nothing was published today'.",
         confidence=0.95, first=17, last=17,
         scope="every point-in-time guard in the project",
         limitations="found on the live path; replay was never affected",
         contradiction="a guard that is correct without a timezone frame",
         impact="the 20:30 night cycle sits inside the broken window nightly; "
                "an integrity guard can fail by being too strict, and that "
                "failure mode is SILENT because it produces a plausible zero",
         evidence=("tests/test_market_session.py::"
                   "test_a_live_run_late_in_the_evening_does_not_discard"
                   "_todays_evidence",
                   "session.leakage_cutoff")),
    dict(asset_id="M9", asset_class=MEASUREMENT_TECHNIQUE,
         title="Statistical stability is not desirability",
         claim="A coefficient of variation answers whether a number is "
               "reliable, never whether it is good. Reported as two columns.",
         confidence=0.85, first=17, last=17,
         scope="every stability report",
         limitations="the degraded threshold (0.25) is a labelling choice and "
                     "is never optimised against",
         contradiction="a case where stability alone implies health",
         impact="stops a column of green STABLE labels hiding "
                "`signal_fired = 0.00`",
         evidence=("funnel.interpret",)),
    dict(asset_id="M8", asset_class=MEASUREMENT_TECHNIQUE,
         title="Intuition about this system's bottlenecks is ~14% accurate",
         claim="1 of 7 engineering predictions has been correct.",
         confidence=0.6, first=3, last=16, sample_size=7,
         effective_sample_size=7,
         scope="engineering predictions in this project",
         limitations="n=7. Measures THIS project's intuition, nothing else.",
         contradiction="accuracy rising above 50% over the next 10 predictions",
         impact="the reason measurement precedes building, every cycle",
         evidence=("docs/BOTTLENECK_LOG.md",)),
]


def main(path=DEFAULT_PATH) -> int:
    ledger = AssetLedger(path)
    before = len(ledger.all())
    for spec in ASSETS:
        ledger.declare(
            asset_id=spec["asset_id"], title=spec["title"],
            asset_class=spec["asset_class"], claim=spec["claim"],
            confidence=spec["confidence"],
            first_observed=DAY[spec["first"]], evidence=spec.get("evidence", ()),
            scope=spec.get("scope", ""),
            limitations=spec.get("limitations", ""),
            contradiction_conditions=spec.get("contradiction", ""),
            impact=spec.get("impact", ""),
            sample_size=spec.get("sample_size"),
            effective_sample_size=spec.get("effective_sample_size"),
            cycle_id="seed:day-16-ledger")
        # The LAST VALIDATED date is real history, not today. An asset that has
        # not been re-tested since day 4 must not acquire a fresh timestamp
        # merely because it was migrated -- that would be exactly the
        # age-for-evidence substitution the Knowledge Decay principle forbids.
        last = DAY[spec["last"]]
        asset = ledger.get(spec["asset_id"])
        if len(asset.revisions) == 1 and spec["last"] != spec["first"]:
            ledger.revise(asset_id=spec["asset_id"], status=ACCEPTED,
                          confidence=spec["confidence"],
                          reason=f"re-validated on day {spec['last']}",
                          evidence=spec.get("evidence", ()),
                          at=f"{last}T12:00:00+00:00",
                          cycle_id="seed:day-16-ledger")
    after = ledger.all()
    print(f"assets: {before} -> {len(after)}")
    summary = ledger.summary()
    print(f"still believed : {summary['still_believed']}")
    print(f"by status      : {summary['by_status']}")
    print(f"never re-validated: {summary['never_revalidated']}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=DEFAULT_PATH)
    raise SystemExit(main(parser.parse_args().path))
