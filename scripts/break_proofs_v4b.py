"""Are the V4 session-2 guards load-bearing? Break them and find out.

Same harness, same discipline: mutate the real source, require the bytes to
change, require the named test to turn RED for the stated reason, require an
exact restore. A mutation that changes bytes and breaks nothing is reported
NOT_CAUGHT, which is a finding about the guard and not a failure of the run.

The guards here are the ones session 2 added: the area on a macro figure, the
primary-series rule, the derived spread, the temporal wall around forecasting,
the wall between a discovery and a fact, the research-policy safety wall and
its reward, the thesis structure, the overclaim check, and the two internal
walls.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
MS = S / "macro_state.py"
MI = S / "macro_ingest.py"
ME = S / "macro_expectation.py"
UN = S / "unsupervised.py"
RP = S / "research_policy.py"
ET = S / "economic_thesis.py"
FV = S / "founder_v4_view.py"
IS = S / "internal_state.py"
SE = S / "strategic_export.py"

COV = "tests/test_market_macro_coverage.py"
EXP = "tests/test_market_macro_expectation.py"
UNS = "tests/test_market_unsupervised.py"
POL = "tests/test_market_research_policy.py"
THE = "tests/test_market_economic_thesis.py"
FVT = "tests/test_market_founder_v4_view.py"
ADV = "tests/test_market_v4_adversarial.py"
BRG = "tests/test_market_v4_export_bridge.py"

PROOFS = [
    # --- the economy is more than one economy --------------------------------
    ("v4b-1. two countries share one condition again",
     MS,
     "            if o.state_kind == state_kind and o.area == area]",
     "            if o.state_kind == state_kind]",
     f"{COV}::test_two_countries_do_not_share_one_condition"),

    ("v4b-2. a direction is computed across two economies",
     MS,
     "    if previous.area != current.area:",
     "    if False:",
     f"{COV}::test_a_direction_is_never_computed_across_economies"),

    ("v4b-3. the condition changes identity when a series publishes",
     MS,
     "    chosen = PRIMARY_SERIES.get((area, state_kind))",
     "    chosen = None",
     f"{COV}::"
     "test_the_condition_does_not_change_identity_when_a_series_publishes"),

    ("v4b-4. a spread is built from two different months",
     MS,
     "    shared = sorted(set(longs) & set(shorts))",
     "    shared = sorted(set(longs) | set(shorts))",
     f"{COV}::test_a_spread_refuses_mismatched_periods"),

    ("v4b-5. a derived spread is published as a measurement",
     MS,
     "        measure=lo.measure, standing=INFERRED,",
     "        measure=lo.measure, standing=OBSERVED,",
     f"{COV}::test_a_spread_is_inferred_not_observed"),

    ("v4b-6. the coverage denominator becomes the cross product",
     MS,
     "TRACKED_CONDITIONS = tuple(\n"
     "    [(US, k) for k in _NATIONAL if k not in _WORLDWIDE]",
     "TRACKED_CONDITIONS = tuple(\n"
     "    [(GLOBAL, k) for k in STATE_KINDS]\n"
     "    + [(US, k) for k in _NATIONAL if k not in _WORLDWIDE]",
     f"{COV}::test_tracked_conditions_are_not_the_cross_product"),

    ("v4b-7. three accounting lines become one fiscal series again",
     MI,
     '        if str(row.get("expense_group_desc") or "") != \\\n'
     '                "ACCRUED INTEREST EXPENSE":\n'
     "            continue",
     "        if False:\n            continue",
     f"{COV}::test_the_government_is_not_paid_to_borrow"),

    ("v4b-8. a suppression marker becomes a zero",
     MI,
     "    except (TypeError, ValueError):\n        return None",
     "    except (TypeError, ValueError):\n        return 0.0",
     f"{COV}::test_a_suppressed_cell_is_not_a_zero"),

    # --- forecasting has a temporal wall --------------------------------------
    ("v4b-9. a forecast is scored against a figure it could already read",
     ME,
     "    if actual.published_at[:10] <= expectation.made_at[:10]:",
     "    if False:",
     f"{EXP}::"
     "test_scoring_a_forecast_against_an_already_public_figure_is_refused"),

    ("v4b-10. a forecast reads the period it is forecasting",
     ME,
     "               if o.reference_period < target_period]",
     "               if o.reference_period <= target_period]",
     f"{EXP}::test_a_forecast_cannot_read_the_period_it_forecasts"),

    ("v4b-11. skill is measured against zero instead of the random walk",
     ME,
     'BENCHMARK = RANDOM_WALK',
     'BENCHMARK = HISTORICAL_MEAN',
     f"{EXP}::test_skill_is_measured_against_the_random_walk"),

    # --- a discovery is never a fact --------------------------------------------
    ("v4b-12. a cluster is allowed to become a fact",
     UN,
     "        raise NotEvidence(",
     "        return {'fact': self.label}\n        raise NotEvidence(",
     f"{UNS}::test_a_cluster_cannot_become_a_fact"),

    ("v4b-13. a discovery without a research question is accepted",
     UN,
     "        if not self.research_question:",
     "        if False:",
     f"{UNS}::test_a_discovery_without_a_research_question_is_refused"),

    ("v4b-14. geometry decides whether a discovery is useful",
     UN,
     "        return bool(self.utility is not None and self.utility > 0)",
     "        return bool(self.separation is not None "
     "and self.separation > 0)",
     f"{UNS}::test_geometry_alone_never_makes_a_discovery_useful"),

    ("v4b-15. a series that jumps from flat is invisible again",
     UN,
     "            mean_dev = sum(deviations) / len(deviations)\n"
     "            if mean_dev <= 0:\n                continue\n"
     "            scale = mean_dev",
     "            continue",
     f"{UNS}::test_a_single_jump_is_found_and_carries_a_question"),

    # --- research policy: the wall and the reward ---------------------------------
    ("v4b-16. a research policy can reach a trade",
     RP,
     "    if action_kind in RESTRICTED_ACTIONS:",
     "    if False:",
     f"{POL}::test_a_research_policy_cannot_reach_a_trade"),

    ("v4b-17. an unmeasured discriminating term counts as measured",
     RP,
     "        if getattr(out, term) is True:",
     "        if getattr(out, term) is not False:",
     f"{POL}::"
     "test_an_unmeasured_discriminating_term_earns_nothing_and_costs_nothing"),

    ("v4b-18. an untrustworthy estimate exonerates the reward",
     RP,
     "              if r.mean_reward is not None and r.trustworthy}",
     "              if r.mean_reward is not None}",
     f"{POL}::test_an_untrustworthy_estimate_cannot_exonerate_the_reward"),

    ("v4b-19. a thin overlap is called trustworthy",
     RP,
     "        return self.matched >= 30 and self.overlap >= 0.2",
     "        return True",
     f"{POL}::test_a_thin_overlap_is_never_trustworthy"),

    ("v4b-20. independence is read as a label again",
     RP,
     "        independent = (independence >= INDEPENDENCE_THRESHOLD",
     "        independent = (independence >= 0.0",
     f"{POL}::test_independence_is_read_as_a_score_not_a_label"),

    # --- the thesis structure ------------------------------------------------------
    ("v4b-21. a thesis is asserted with no live alternative",
     ET,
     "        if self.standing in ASSERTABLE and not self.alternatives:",
     "        if False:",
     f"{THE}::test_a_thesis_cannot_be_asserted_without_a_live_alternative"),

    ("v4b-22. a mechanism needs no falsifier",
     ET,
     "        if not self.falsifier.strip():\n"
     "            raise ThesisRejected(\n"
     '                "a mechanism needs a falsifier: one that nothing could "',
     "        if False:\n"
     "            raise ThesisRejected(\n"
     '                "a mechanism needs a falsifier: one that nothing could "',
     f"{THE}::test_a_mechanism_without_a_falsifier_is_refused"),

    ("v4b-23. a tie picks a leader by list order",
     ET,
     "        return top[0] if len(top) == 1 else None",
     "        return top[0]",
     f"{THE}::test_two_equally_supported_rivals_produce_no_leader"),

    ("v4b-24. agreement among sources becomes proof",
     ET,
     "        if self.falsifier_tested and self.independent_sources >= 2 \\\n"
     "                and not self.counterevidence:",
     "        if self.independent_sources >= 2:",
     f"{THE}::test_agreement_among_sources_is_not_proof"),

    ("v4b-25. a refuted hop weakens the path instead of voiding it",
     ET,
     '        "standing": REFUTED if broken else weakest.standing,',
     '        "standing": weakest.standing,',
     f"{THE}::"
     "test_a_refuted_hop_voids_the_rest_rather_than_weakening_it"),

    ("v4b-26. a scenario invents a precise number",
     ET,
     '        if self.magnitude not in ("UNQUANTIFIED", "SMALL", "MODERATE",\n'
     '                                  "LARGE") and not self.calibrated:',
     "        if False:",
     f"{THE}::test_a_number_needs_a_calibrated_parameter_behind_it"),

    ("v4b-27. a surface may say more than its thesis",
     ET,
     "    if _ORDER.get(rendered_standing, 0) > _ORDER.get(thesis.standing, 0):",
     "    if False:",
     f"{THE}::test_a_slide_cannot_be_more_confident_than_its_thesis"),

    ("v4b-28. a deck may drop the alternatives",
     ET,
     "    if drops_alternatives and thesis.alternatives and thesis.assertable:",
     "    if False:",
     f"{THE}::test_dropping_the_alternatives_is_an_overclaim"),

    ("v4b-29. a built thesis is born assertable",
     ET,
     "        standing=PROPOSED,\n"
     "        as_of=as_of or str(getattr(transmission, \"as_of\", \"\")) or \"\",",
     "        standing=SUPPORTED,\n"
     "        as_of=as_of or str(getattr(transmission, \"as_of\", \"\")) or \"\",",
     f"{THE}::test_a_built_thesis_is_never_born_assertable"),

    # --- the CEO conversation --------------------------------------------------------
    ("v4b-30. a leading question gets the conclusion it asked for",
     FV,
     "    if leading and thesis is not None and not thesis.assertable:",
     "    if False:",
     f"{FVT}::test_a_leading_question_on_an_untested_thesis_is_refused"),

    ("v4b-31. an unanswerable question is composed rather than declined",
     FV,
     '    return {"contract": CONTRACT, "refused": True,\n'
     '            "reason": ("no field of this thesis answers that; composing '
     'one "',
     '    return {"contract": CONTRACT, "refused": False,\n'
     '            "reason": ("no field of this thesis answers that; composing '
     'one "',
     f"{FVT}::test_an_unanswerable_question_is_declined_rather_than_composed"),

    ("v4b-32. a longer briefing counts as decision value",
     FV,
     "    if not touched:\n        level = NONE",
     "    if not touched:\n        level = PRESENTATIONAL",
     f"{FVT}::test_nothing_new_scores_none"),

    # --- the internal walls -------------------------------------------------------------
    ("v4b-33. synthetic internals reach a real company's briefing",
     IS,
     "    if bad:\n        raise SyntheticLeak(",
     "    if False:\n        raise SyntheticLeak(",
     f"{ADV}::test_synthetic_internals_cannot_reach_a_real_companys_briefing"),

    ("v4b-34. one company's internals are readable for another",
     IS,
     "    return tuple(f for f in facts if f.company_id == for_company)",
     "    return tuple(facts)",
     f"{ADV}::test_one_companys_internals_are_never_read_for_another"),

    ("v4b-35. a pipeline forecast becomes a firm figure",
     IS,
     "FIRM = frozenset({RECORDED})",
     "FIRM = frozenset({RECORDED, FORECAST})",
     f"{ADV}::test_a_pipeline_is_never_firm"),

    # --- the bridge ------------------------------------------------------------------------
    ("v4b-36. unknown conditions ship as rows and inflate the picture",
     SE,
     '    known = [s for s in states if getattr(s, "known", False)]',
     "    known = list(states)",
     f"{BRG}::test_unknown_conditions_are_counted_and_not_shipped_as_rows"),
]

PROOFS = [Proof(label=p[0], path=p[1], find=p[2], replace=p[3], target=p[4])
          for p in PROOFS]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS))
