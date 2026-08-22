"""The V4 readiness scorecard, session 3, computed from what was measured.

Every reason below is a number this session actually produced. A status with a
reason that could have been written before the run is a status somebody chose,
and `scorecard` reports those separately for exactly that reason.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.market import v4_readiness as R  # noqa: E402

A = R.AxisStatus

AXES = [
    A("MACRO_STATE", R.PARTIAL,
      "15 of 30 tracked conditions known across 3 areas (13 OBSERVED, 2 "
      "INFERRED spreads), up from 1 of 17; the 15 gaps are US series behind "
      "a key or a 503"),
    A("TEMPORAL_TRUTH", R.PASS,
      "every figure carries reference period, publication and retrieval; "
      "StatCan supplies a real release date and every other adapter assumes "
      "one late; forecast scoring refuses an already-published target"),
    A("ECONOMIC_MEMORY", R.PASS,
      "macro observations persist as a durable record kind and rehydrate; "
      "24 monthly figures plus 520 daily observations per BoC series"),
    A("CAPITAL_INTELLIGENCE", R.PARTIAL,
      "policy rate, 2y and 10y yields, two derived term spreads and federal "
      "interest expense; no corporate credit spread is reachable keyless"),
    A("COMPANY_EXPOSURE", R.PARTIAL,
      "26 companies x 10 dimensions, 3 rated; filing-derived OBSERVED kept "
      "apart from reporting-derived INFERRED"),
    A("SUPPLY_CHAIN", R.BLOCKED_DATA,
      "no document in the corpus names a counterparty; unchanged from "
      "session 1 and not addressable by effort"),
    A("DEMAND_CHAIN", R.PARTIAL,
      "nine states, per-link standing and a refusal to speak for demand from "
      "a backlog figure; live, 15 of 26 companies show any state and 21 of "
      "260 states are measured, so every chain reads UNKNOWN overall"),
    A("EXPECTATIONS", R.PASS,
      "6 baselines with vintage-correct origins; AR1 beats the random walk "
      "0.40 on the Treasury note rate and nothing beats it on Canadian "
      "unemployment"),
    A("SURPRISE", R.PARTIAL,
      "expected/observed/surprise with a standardised magnitude and interval "
      "coverage; no company-side expectation source (guidance, consensus) is "
      "wired in"),
    A("CAUSAL_TRANSMISSION", R.PARTIAL,
      "7 dated falsifiable hypotheses, up from 2, each with provenance to a "
      "series and to the company's own words; 0 tested, none due until 2027"),
    A("MULTI_HOP_REASONING", R.PARTIAL,
      "7-node chain with weakest-link standing that names its own weakest "
      "link; propagate() voids a path below a refuted hop rather than "
      "weakening it"),
    A("SECOND_ORDER_EFFECTS", R.PARTIAL,
      "ConsequenceHypothesis exists, requires a named dependency past hop 1, "
      "and reaches the founder briefing; no second-order hop is populated "
      "from live evidence because no counterparty is named"),
    A("THIRD_ORDER", R.PARTIAL,
      "modelled and capped at order 3 with a stated reason; unpopulated for "
      "the same reason as second order"),
    A("REGIME_AWARENESS", R.PARTIAL,
      "a stated rule partitions 23 months into 5 groups and is the only "
      "partition with positive held-out utility (+0.23)"),
    A("REGIME_DISCOVERY", R.PARTIAL,
      "KMeans and a Gaussian mixture both fit; both score 0.46 silhouette "
      "and NEGATIVE utility, so neither is economically useful and both are "
      "reported rather than dropped"),
    A("UNSUPERVISED_DISCOVERY", R.PASS,
      "regimes, exposure clusters and 14 anomalies, every one carrying a "
      "research question and none with a path to becoming a fact"),
    A("ACTIVE_LEARNING", R.PARTIAL,
      "state, action, observation and reward are stated; a contextual bandit "
      "and 5 baselines are scored offline; nothing is deployable because the "
      "log contains no exploration"),
    A("EVIDENCE_LINKAGE", R.PASS,
      "316 of 316 evidence rows attributed, zero unattributed; 201 changed "
      "something and 115 changed nothing, and a changing effect whose before "
      "and after are equal is refused"),
    A("RESEARCH_REWARD", R.PARTIAL,
      "three of four positive terms are now measured off the effect log; "
      "REWARD_HACKABLE=False because the volume attack changes MORE per "
      "action (0.76) than the VOI heuristic (0.52), which is the reward "
      "working rather than failing"),
    A("PROSPECTIVE_RESEARCH_LOG", R.NO,
      "the log is still reconstructed from evidence that survived, so every "
      "action that returned nothing is missing; no learned policy can be "
      "trusted until choices are logged before their outcomes"),
    A("ACTIVE_RESEARCH", R.PARTIAL,
      "the session-1 name for what ACTIVE_LEARNING and RESEARCH_POLICY now "
      "split; kept so the axis list has no hole, and scored as the weaker of "
      "the two"),
    A("RESEARCH_POLICY", R.PARTIAL,
      "316-row log priced by knowledge effects; independent reporting has the "
      "highest change rate (0.76) and lowest duplication (0.03) while "
      "regulatory filings repeat a known fact 75% of the time, which is why "
      "the VOI heuristic loses on this corpus"),
    A("CAUSAL_METHODS", R.PARTIAL,
      "6 forecast methods benchmarked against the random walk per series; no "
      "DiD, synthetic control or local projection, because no treated and "
      "control pair exists in the corpus"),
    A("METHOD_PERFORMANCE", R.PARTIAL,
      "per-series MAE, RMSE, bias, interval coverage and skill are computed "
      "each run; not yet persisted across runs, so no trend exists"),
    A("COUNTERFACTUALS", R.PARTIAL,
      "every thesis carries 3 alternative explanations with their own "
      "falsifiers; none has been adjudicated"),
    A("SCENARIOS", R.PARTIAL,
      "4 scenario kinds, a refusal of uncalibrated numbers, and a "
      "consistency check that flags 3 assumption pairs needing a mechanism; "
      "not generated from live state"),
    A("INTERNAL_COMPANY_MODEL", R.PARTIAL,
      "14 internal kinds, 4 standings, a permission wall and a provenance "
      "wall; populated only by the synthetic enterprise, which is the "
      "correct state with no customer data supplied"),
    A("THESIS_ENGINE", R.PASS,
      "7 live theses built from measured transmissions, 3 alternatives each, "
      "28 falsifiers, 5 competitions of which 2 are contested; no CONFIRMED "
      "standing exists"),
    A("PROOF_ENGINE", R.PASS,
      "proof status is decided by whether the falsifier was tested and "
      "whether sources are independent, not by how many agree; all 7 live "
      "proofs read BOUNDED"),
    A("FOUNDER_CONSUMPTION", R.PARTIAL,
      "the economic block crosses strategic_market_intel.v1 and is consumed: "
      "13 conditions and 3 theses arrived for america_movil and a thesis "
      "without rivals was downgraded on arrival; no deployed page renders it "
      "yet"),
    A("FOUNDER_DECISION_VALUE", R.PARTIAL,
      "DecisionImpact scores named components and refuses to count a longer "
      "briefing; the live theses populate falsifier, timing, monitoring and "
      "recommendation, which scores DECISION_CHANGING against an empty base "
      "— an architecture measurement, not a customer one"),
    A("CEO_CONVERSATION", R.PARTIAL,
      "9 question forms answered from named fields, a refusal for anything "
      "no field answers, and a challenge mode that declines a leading "
      "question and returns the argument instead; no multi-turn state"),
    A("PRESENTATION", R.PASS,
      "12 sections generated from the thesis, every slide naming the field it "
      "renders, the headline verb bound to the standing by table, and the "
      "alternatives and falsifier slides required; check() re-verifies an "
      "edited deck"),
    A("CALIBRATION", R.PARTIAL,
      "forecast calibration is real and measured; thesis calibration has "
      "nothing to score because no falsifier is due before 2027-05-05"),
    A("META_LEARNING", R.PARTIAL,
      "method skill and discovery utility are measured each run; predicted "
      "against realised VOI is not, because predicted VOI is not stored"),
    A("RETENTION", R.PASS,
      "macro observations survive a fresh process; the knowledge payload "
      "persists as a bounded projection instead of dying with the cycle"),
    A("PRODUCT_RELIABILITY", R.PASS,
      "market suite green, founder suite 4665 passed / 16 skipped, V4b "
      "break proofs 36/36, V4 session 1 12/12"),
    A("PAPER", R.PASS,
      "TRADING_MODE=PAPER in all three plists; the research policy's "
      "restricted-action wall raises on place_trade and six other actions"),
]

if __name__ == "__main__":
    card = R.scorecard(AXES)
    print(json.dumps({k: card[k] for k in
                      ("axes", "by_status", "missing_axes", "blocking",
                       "axes_without_a_measured_reason")}, indent=1))
    for row in card["detail"]:
        print(f"  {row['status']:14} {row['axis']}")
