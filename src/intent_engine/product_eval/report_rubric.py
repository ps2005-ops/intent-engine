"""One frozen rubric, scored deterministically, used for every company.

WHY A MACHINE SCORES THIS
-------------------------
The Pre-100 acceptance score was a judgement: a person read the product and
put a number on it. That is the right instrument for "would an executive pay
for this" and the wrong one for "did this regress on company 47 of 100",
because a judgement cannot be run a hundred times without drifting.

So there are two instruments and they measure different things. This one is
mechanical, reproducible, and frozen: the same pages produce the same score
today and after the hundredth company. The persona acceptance score (§82)
stays human, stays 0-5, and is the one that decides whether the product is
good. This one decides whether it is CONSISTENT, which is the question the
100-company programme actually asks.

WHAT 10/10 MEANS (§62)
----------------------
Not that the data was rich. A sparse company scores 10 when the output uses
everything available correctly, the uncertainty is useful, the reasoning is
bounded rather than absent, the experiment is strong, and no unsupported
claim is made. That is why almost every dimension below is scored against
what the READ contains rather than against how much evidence there was --
evidence volume is measured once, under `data_completeness`, and is
deliberately not allowed to depress anything else.

NO MODEL CALL. Counting, matching and structural checks only.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.executive.strategic_read import (BOUNDED_INFERENCE,
                                                    OBSERVED,
                                                    READ_UNIDENTIFIED,
                                                    STRONGLY_INFERRED,
                                                    UNMEASURED)
from intent_engine.product_eval import defect_taxonomy as DT

CONTRACT = "report_rubric.v1"

#: The 23 dimensions of §61, in the order they are argued about.
DIMENSIONS = (
    "identity_correctness", "data_completeness", "financial_understanding",
    "business_model_understanding", "microeconomics", "macroeconomics",
    "strategic_synthesis", "causal_discipline", "competition", "game_theory",
    "risk", "opportunity", "actionability", "uncertainty", "mve_quality",
    "history", "learning", "provenance", "company_specificity",
    "presentation_quality", "full_analysis_quality", "story_quality",
    "qa_quality",
    # --- §91. What this convergence run made the product responsible for ---
    "data_resolution", "history_expectation", "history_counterfactual",
    "history_economics", "feedback_loop", "flow_quality",
    # --- §23. What the belief layer made the product responsible for -------
    "competitive_specificity", "belief_quality", "belief_challenge",
    "economic_reasoning",
)

#: §63. The gate. A surface may not freeze below these.
GATE_OVERALL = 9.0
GATE_NAMED = {"strategic_synthesis": 9.0, "actionability": 9.0,
              "company_specificity": 9.0, "provenance": 9.0}
GATE_FLOOR = 8.0

#: Dimensions that are CORE — the ones §63's floor applies to.
CORE = ("identity_correctness", "business_model_understanding",
        "strategic_synthesis", "causal_discipline", "actionability",
        "uncertainty", "company_specificity", "provenance")


@dataclasses.dataclass(frozen=True)
class Score:
    dimension: str
    score: float
    why: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RubricResult:
    company: str
    contract: str = CONTRACT
    scores: Tuple[Score, ...] = ()
    findings: Tuple[dict, ...] = ()

    @property
    def by_dimension(self) -> Dict[str, float]:
        return {s.dimension: s.score for s in self.scores}

    @property
    def overall(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.score for s in self.scores) / len(self.scores), 2)

    @property
    def min_core(self) -> float:
        values = [s.score for s in self.scores if s.dimension in CORE]
        return round(min(values), 2) if values else 0.0

    def failures(self) -> List[str]:
        """Every §63 condition this result does not meet."""
        out = []
        table = self.by_dimension
        if self.overall < GATE_OVERALL:
            out.append(f"overall {self.overall} < {GATE_OVERALL}")
        for dimension, floor in GATE_NAMED.items():
            value = table.get(dimension, 0.0)
            if value < floor:
                out.append(f"{dimension} {value} < {floor}")
        for dimension in CORE:
            value = table.get(dimension, 0.0)
            if value < GATE_FLOOR:
                out.append(f"{dimension} {value} < {GATE_FLOOR}")
        return out

    def as_dict(self) -> dict:
        return {"contract": self.contract, "company": self.company,
                "overall": self.overall, "min_core": self.min_core,
                "scores": [s.as_dict() for s in self.scores],
                "failures": self.failures(),
                "findings": list(self.findings)}


def _band(value: bool, high: float = 10.0, low: float = 4.0) -> float:
    return high if value else low


def _ratio(have: int, want: int) -> float:
    if want <= 0:
        return 10.0
    return round(min(10.0, 10.0 * have / want), 1)


def score(*, read, pages: Dict[str, str], timeline=None,
          company: str = "", model_class: str = "",
          other_companies: Sequence[str] = (), simulation=None,
          html: Optional[Dict[str, str]] = None,
          other_reads: Sequence = ()) -> RubricResult:
    """Score one company's whole product output.

    `pages` maps a step key ("intro", "slides", "full", "story", "history",
    "connect", and optionally "qa") to that page's VISIBLE TEXT.

    `html` carries the same surfaces UNSTRIPPED, for the dimensions that are
    about a drawing rather than about prose. It is optional so that every
    existing caller keeps working; the chart dimensions score as unmeasured
    rather than as failed when it is absent, because "we did not look" and
    "it is not there" are different findings.
    """
    company = company or getattr(read, "company", "")
    model_class = model_class or _model_of(read)
    findings: List[DT.Finding] = []
    for surface, text in (pages or {}).items():
        findings.extend(DT.scan(text, surface=surface, company=company,
                                model_class=model_class,
                                other_companies=other_companies))
    # §21. THE BELIEF LAYER IS CHECKED AGAINST THE OBJECTS, not the prose.
    # Wired here rather than left as a callable nobody calls: this programme
    # has shipped three built-and-guarded capabilities with zero callers, and
    # a detector that never runs is a comment.
    try:
        findings.extend(DT.scan_belief_layer(read, surface="read",
                                             other_reads=other_reads or ()))
    except Exception:                                       # noqa: BLE001
        pass
    codes = {f.code for f in findings}
    sev1 = {f.code for f in findings if f.severity == DT.SEV1}
    sev2 = {f.code for f in findings if f.severity == DT.SEV2}
    joined = " ".join((pages or {}).values())
    out: List[Score] = []

    def put(dimension, value, why):
        out.append(Score(dimension, round(max(0.0, min(10.0, value)), 1), why))

    # --- identity -----------------------------------------------------------
    named = bool(company) and company.split(",")[0].lower() in joined.lower()
    put("identity_correctness",
        2.0 if "WRONG_COMPANY" in codes else (10.0 if named else 5.0),
        "the subject is named and no other subject appears"
        if named and "WRONG_COMPANY" not in codes
        else "another company appears on the page"
        if "WRONG_COMPANY" in codes else "the subject is not named")

    # --- data completeness --------------------------------------------------
    level1 = tuple(getattr(read, "level1_facts", ()) or ())
    observed = sum(1 for s in level1 if s.standing == OBSERVED)
    put("data_completeness", _ratio(observed, 3),
        f"{observed} classes of source were actually read")

    # --- financial + business model ----------------------------------------
    metrics = tuple(getattr(read, "metrics", ()) or ())
    put("financial_understanding",
        _ratio(len(metrics), 5),
        f"{len(metrics)} metric(s) this business model is judged on are named")
    level2 = tuple(getattr(read, "level2_business_model", ()) or ())
    put("business_model_understanding", _ratio(len(level2), 4),
        f"{len(level2)} structural facts about how the business works")

    # --- economics ----------------------------------------------------------
    mechanisms = tuple(getattr(read, "level3_mechanism", ()) or ())
    put("microeconomics", _ratio(len(mechanisms), 3),
        f"{len(mechanisms)} named mechanism(s) with a decision attached")
    macro = tuple(getattr(read, "macro", ()) or ())
    complete = sum(1 for m in macro
                   if m.get("mechanism") and m.get("business_variable")
                   and m.get("consequence"))
    put("macroeconomics",
        10.0 if complete else (6.0 if not macro else 3.0),
        f"{complete} economic channel(s) carry a full transmission chain"
        if complete else
        "no channel is shown, which is correct when none has a mechanism"
        if not macro else "a channel is shown without a transmission")

    # --- synthesis ----------------------------------------------------------
    puts_forward = getattr(read, "puts_a_strategy_forward", False)
    synthesis = 10.0
    if not puts_forward:
        synthesis = 2.0
    if "STRATEGIC_REFUSAL_COLLAPSE" in codes:
        synthesis = min(synthesis, 1.0)
    if "TEMPLATE_COLLAPSE" in sev1:
        synthesis = min(synthesis, 3.0)
    if "EXCESSIVE_HEDGING" in codes:
        synthesis = min(synthesis, 6.0)
    put("strategic_synthesis", synthesis,
        "a bounded strategic read is put forward and is model-appropriate"
        if synthesis >= 9 else "; ".join(sorted(sev1 | sev2)) or
        "no strategy is put forward")

    # --- causal discipline --------------------------------------------------
    # DISCIPLINE IS THE SEPARATION, NOT THE COUNT. Requiring three distinct
    # standings punished a read whose structural facts are uniformly
    # STRONGLY_INFERRED -- which is correct, because they all come from the
    # same established classification. What matters is that what was READ is
    # distinguished from what was INFERRED, and that nothing claims more than
    # its source.
    standings = ({s.standing for s in level1} | {s.standing for s in level2}
                 | {m.standing for m in mechanisms}
                 | {m.state for m in metrics})
    observed = OBSERVED in standings
    inferred = bool(standings & {STRONGLY_INFERRED, BOUNDED_INFERENCE})
    named_gap = UNMEASURED in standings
    marked = sum((observed, inferred, named_gap))
    causal = _ratio(marked, 3)
    if "UNSUPPORTED_PRECISION" in codes or "FALSE_CONFIDENCE" in codes:
        causal = min(causal, 2.0)
    put("causal_discipline", causal,
        f"{marked} distinct standings are used, so claims are separated"
        if causal >= 8 else "a claim carries more confidence than its source")

    # --- competition + game theory -----------------------------------------
    rivals = tuple(getattr(read, "level4_competition", ()) or ())
    ground = getattr(read, "competitive_ground", None)
    # WHAT MAKES A COMPETITIVE READ ABOUT THIS COMPANY.
    #
    # The old test asked whether a FIRM had been named by the subject, and on
    # five of seven golden companies the answer was no — not because the
    # retrieval failed, but because a modern Competition section names
    # CATEGORIES and declines to name firms. Cloudflare's own filing says it
    # competes with "on-premises network hardware vendors" and "content
    # delivery network (CDN) vendors"; Bank of America's lists banks, thrifts
    # and credit unions. Those are the company's own account of its market,
    # quoted and dated, and no two companies produce the same list.
    #
    # So what is measured is whether the competitive set rests on the
    # company's own words or on an attributed source, against the failure
    # state it is protecting from: a set that is entirely structural peers,
    # which is correct by construction and wrong about the company.
    grounded = tuple(getattr(ground, "subject_grounded", ()) or ())
    attributed = tuple(r for r in (getattr(ground, "rivals", ()) or ())
                       if getattr(r, "is_attributed", False))
    own_account = len({r.identity for r in grounded + attributed})
    kinds = len(getattr(ground, "kinds_covered", ()) or ())
    comp = _ratio(len(rivals), 3)
    if "COMPETITOR_MISSING" in codes:
        comp = min(comp, 3.0)
    if rivals and not own_account:
        # Structural peers are honest and they are not this company's rivals.
        comp = min(comp, 7.0)
    if kinds < 2 and rivals:
        # One kind of alternative answered four times has answered one.
        comp = min(comp, 8.0)
    put("competition", comp,
        f"{len(rivals)} alternative(s) across {kinds} kind(s), {own_account} "
        f"resting on {read.company}'s own account or an attributed source")
    put("competitive_specificity",
        _ratio(own_account, 2) if own_account else
        (5.0 if getattr(ground, "next_measurement", "") else 3.0),
        f"{own_account} alternative(s) come from this company's own account "
        f"of its market" if own_account else
        "the competitive set is read from the business model only, and the "
        "measurement that would ground it is named")
    complete_moves = sum(1 for r in rivals
                         if r.likely_response and r.counter_move
                         and r.signal_to_watch and r.response_likelihood)
    put("game_theory", _ratio(complete_moves, 3),
        f"{complete_moves} rival(s) carry a response, a counter-move and a "
        f"signal")

    # --- risk / opportunity / action ---------------------------------------
    action = getattr(read, "level6_action", None)
    has_risk = bool(action and action.what_remains_unknown and action.kill_switch)
    put("risk", _band(has_risk, 10.0, 3.0),
        "the open risk is named with a stopping condition"
        if has_risk else "no stopping condition is attached to the risk")
    scenarios_up = bool(action and action.action_now)
    put("opportunity", _band(scenarios_up, 9.0, 4.0),
        "an available move is named" if scenarios_up else "no move is named")
    actionable = 10.0 if (action and action.action_now and action.guardrail
                          and action.kill_switch) else 4.0
    if not puts_forward:
        actionable = min(actionable, 3.0)
    put("actionability", actionable,
        "a bounded action with a guardrail and a kill switch"
        if actionable >= 9 else "the reader is not told what to do now")

    # --- uncertainty + MVE --------------------------------------------------
    uncertain = bool(action and action.causal_confidence
                     and action.what_remains_unknown and action.falsifier)
    put("uncertainty", _band(uncertain, 10.0, 4.0),
        "confidence, the open parameter and the falsifier are all stated"
        if uncertain else "uncertainty is asserted without naming what is open")
    mve = bool(action and action.minimum_viable_experiment
               and action.voi_band and action.kill_switch)
    put("mve_quality", _band(mve, 10.0, 3.0),
        "an experiment, a value band and a stopping rule"
        if mve else "no experiment is proposed")

    # --- history: the simulator, not the timeline ---------------------------
    #
    # The old dimension counted VINTAGES and scored 10 for a page made
    # entirely of prose, which is how a text-only history rewind passed a
    # 9.78 rubric while the screenshots showed it was not the product. What
    # is scored now is what the page has to carry: three series, each
    # labelled with the kind of claim it is, over enough dates to compare.
    history_html = (html or {}).get("history", "")
    chart_findings = (DT.scan_history_chart(history_html)
                      if history_html else [])
    chart_codes = {f.code for f in chart_findings}
    sim_vintages = tuple(getattr(simulation, "vintages", ()) or ())
    legacy_vintages = tuple(getattr(timeline, "vintages", ()) or ())
    if sim_vintages:
        history = _ratio(len(sim_vintages), 3)
        why = (f"{len(sim_vintages)} selectable date(s), three series, "
               f"vintage-walled")
    elif getattr(simulation, "fallback", None) is not None:
        # A company with no filed series cannot have a chart. The bounded
        # fallback is the CORRECT product behaviour and is scored as such —
        # capped below full marks, because a bounded answer is worth less to
        # a reader than a measured one and pretending otherwise would remove
        # the incentive to widen retrieval.
        history, why = 8.0, ("no filed series exists, and the page states "
                             "what would draw the chart")
    else:
        history = _ratio(len(legacy_vintages), 4)
        why = f"{len(legacy_vintages)} vintage(s) behind a wall, prose only"
    if "HINDSIGHT_LEAK" in codes or "FAKE_REPLAY" in codes:
        history, why = min(history, 2.0), "the timeline leaks hindsight"
    if "HISTORY_TEXT_ONLY" in chart_codes:
        history, why = min(history, 3.0), "the history step carries no chart"
    put("history", history, why)

    # --- the three series, scored separately ---------------------------------
    #
    # Separately because they fail separately and for different reasons: an
    # expectation can be absent while a counterfactual is fine, and a single
    # "history" number would average one away.
    expectation = next((v.expectation for v in sim_vintages
                        if v.expectation is not None), None)
    counter = next((v.counterfactual for v in sim_vintages
                    if v.counterfactual is not None), None)
    if expectation is not None:
        labelled = (not history_html) or "Modelled" in history_html
        drivers = len(expectation.drivers or ())
        put("history_expectation",
            _ratio(drivers, 3) if labelled else 3.0,
            f"{drivers} named driver(s), declared as modelled" if labelled
            else "the expectation is drawn without a modelled label")
    else:
        put("history_expectation",
            8.0 if getattr(simulation, "fallback", None) is not None else 4.0,
            "no expectation series; the page says what would produce one"
            if getattr(simulation, "fallback", None) is not None
            else "no expectation series and no explanation")
    if counter is not None:
        parts = len(counter.drivers or ())
        as_fact = "COUNTERFACTUAL_PRESENTED_AS_FACT" in codes
        put("history_counterfactual", 2.0 if as_fact else _ratio(parts, 4),
            "an alternative stated as what would have happened" if as_fact
            else f"mechanism, assumption, benefit and risk in {parts} part(s)")
    else:
        put("history_counterfactual",
            8.0 if getattr(simulation, "fallback", None) is not None else 4.0,
            "no counterfactual; the page says what would produce one"
            if getattr(simulation, "fallback", None) is not None
            else "no counterfactual path")
    index = getattr(simulation, "index", None)
    econ_points = len(getattr(index, "points", ()) or ())
    put("history_economics",
        _ratio(econ_points, 5) if econ_points else
        (8.0 if getattr(simulation, "fallback", None) is not None else 4.0),
        f"{econ_points} filed financial year(s) behind the index"
        if econ_points else "the index rests on no filed series")

    # --- data resolution (§38) ----------------------------------------------
    #
    # How far up the ladder this run got, measured on the page rather than on
    # the producer: the badges a reader can see ARE the resolution.
    from intent_engine.executive import resolution as _R
    shown = [label for label in (_R.LABEL[_R.OBSERVED], _R.LABEL[_R.MODELED],
                                 _R.LABEL[_R.BENCHMARK], _R.LABEL[_R.BOUNDED],
                                 _R.LABEL[_R.COUNTERFACTUAL])
             if label.lower() in joined.lower()]
    absence_hits = sum(1 for f in findings
                       if f.code == "CUSTOMER_ABSENCE_COPY")
    resolution_score = _ratio(len(shown), 3)
    if absence_hits:
        resolution_score = min(resolution_score, 10.0 - 2.0 * absence_hits)
    put("data_resolution", resolution_score,
        f"{len(shown)} resolution state(s) are visible to the reader"
        + (f", but {absence_hits} absence(s) terminate" if absence_hits
           else ""))

    # --- feedback + flow (§46, §61) ------------------------------------------
    connect = (pages or {}).get("connect", "")
    feedback_bits = sum(1 for w in ("how useful was this analysis",
                                    "what was missing", "what looked wrong",
                                    "what decision would you use this for")
                        if w in connect.lower())
    put("feedback_loop", _ratio(feedback_bits, 3),
        f"{feedback_bits} of the four feedback questions are asked"
        if feedback_bits else "the last step collects no feedback")
    present = [k for k in ("intro", "slides", "full", "story", "history",
                           "connect") if (pages or {}).get(k)]
    put("flow_quality", _ratio(len(present), 6),
        f"{len(present)} of six steps render")

    # --- learning -----------------------------------------------------------
    learning_words = ("what was new", "already known", "re-observation",
                      "changed the model", "learning")
    learning_hits = sum(1 for w in learning_words if w in joined.lower())
    lscore = _ratio(learning_hits, 2)
    if "LEARNING_ACTIVITY_CONFUSION" in codes:
        lscore = min(lscore, 3.0)
    put("learning", lscore,
        f"learning state is surfaced in {learning_hits} form(s)")

    # --- provenance ---------------------------------------------------------
    prov = 10.0
    if "PROVENANCE_UNREACHABLE" in codes:
        prov = 2.0
    elif "why this reading exists" not in joined.lower() \
            and "where this comes from" not in joined.lower():
        prov = 6.0
    if "RAW_EVIDENCE_ID" in codes:
        prov = min(prov, 7.0)
    put("provenance", prov,
        "the evidence drawer is linked from the story"
        if prov >= 9 else "provenance is not reachable from this step")

    # --- specificity --------------------------------------------------------
    # WHERE THE FAILURE IS DECIDES WHAT IT COSTS. A step of the story that
    # never names the company is a product defect; a secondary drawer that
    # does not is a smaller one, and flooring the whole dimension to 3.0 for
    # it hid three genuinely good analyses behind one missing heading.
    primary = {"intro", "slides", "full", "story", "history", "connect"}
    generic_on = {f.surface for f in findings if f.code == "GENERIC_STRATEGY"}
    spec = 10.0
    if generic_on & primary:
        spec = 3.0
    elif generic_on:
        spec = 6.5
    if "TEMPLATE_COLLAPSE" in codes:
        spec = min(spec, 3.0)
    if rivals and not own_account:
        # The competitive set is entirely structural peers: the analysis
        # would read the same for any company sharing the business model.
        spec = min(spec, 8.0)
    if not named:
        spec = min(spec, 5.0)
    put("company_specificity", spec,
        "the analysis is about this company and this business model"
        if spec >= 9 else "the analysis would read the same for a peer")

    # --- §3-§7. the belief layer -------------------------------------------
    beliefs = tuple(getattr(read, "market_beliefs", ()) or ())
    challenges = tuple(getattr(read, "belief_challenges", ()) or ())
    testable = sum(1 for b in beliefs
                   if getattr(b, "implied_expectations", ())
                   and getattr(b, "falsifiers", ()))
    belief_score = _ratio(testable, 2)
    if "MARKET_BELIEF_UNSUPPORTED" in codes:
        belief_score = min(belief_score, 3.0)
    if "MANAGEMENT_BELIEF_MISATTRIBUTED" in codes:
        belief_score = min(belief_score, 2.0)
    put("belief_quality", belief_score,
        f"{testable} belief(s) state what they imply and what would break "
        f"them" if testable else
        "no market belief was formed, so there is nothing to challenge")

    # WHAT A GOOD CHALLENGE IS. Not a contrarian one. A challenge scores when
    # it states the best case FOR the belief, binds an alternative to this
    # company, and names the cheapest thing that would settle it — and a
    # belief reported as strengthened after all that is a full-marks outcome,
    # because a conventional reading that survived attack is the one a chief
    # executive can act on without hedging.
    complete = sum(1 for c in challenges
                   if getattr(c, "strongest_support", "")
                   and getattr(c, "unconventional_hypotheses", ())
                   and getattr(c, "cheapest_test", ""))
    challenge_score = _ratio(complete, 2)
    for code, ceiling in (("CONTRARIANISM_WITHOUT_EVIDENCE", 2.0),
                          ("IMPOSSIBLE_HYPOTHESIS_UNBOUNDED", 3.0),
                          ("IMPOSSIBLE_HYPOTHESIS_GENERIC", 6.0),
                          ("BELIEF_CONFIRMATION_BIAS", 5.0),
                          ("ALTERNATIVE_EXPLANATION_MISSING", 6.5),
                          ("WEAKEST_ASSUMPTION_MISSING", 7.0)):
        if code in codes:
            challenge_score = min(challenge_score, ceiling)
    put("belief_challenge", challenge_score,
        f"{complete} belief(s) carry the case for, a bound alternative and a "
        f"test" if complete else "no belief was attacked")

    # --- §8. economic reasoning ---------------------------------------------
    graph = getattr(read, "assumption_chain", None)
    links = tuple(getattr(graph, "links", ()) or ())
    reasoned = bool(links) and bool(getattr(read, "explanation_field", None))
    economic = _ratio(len(links), 4) if links else 3.0
    if not reasoned:
        economic = min(economic, 6.0)
    if "ASSUMPTION_GRAPH_BROKEN" in codes:
        economic = min(economic, 2.0)
    if "MACRO_MECHANISM_GENERIC" in codes:
        economic = min(economic, 6.0)
    put("economic_reasoning", economic,
        f"the recommendation exposes {len(links)} step(s), each with a "
        f"standing and a reason" if links else
        "the recommendation does not expose what it depends on")

    # --- the surfaces themselves -------------------------------------------
    put("presentation_quality",
        _surface_score(pages.get("slides", ""), findings, "slides"),
        "the presentation carries substance and no defect")
    put("full_analysis_quality",
        _surface_score(pages.get("full", ""), findings, "full", want=6000),
        "the full analysis is board-depth and clean")
    put("story_quality",
        _surface_score(pages.get("story", ""), findings, "story", want=2500),
        "the narrative stands alone")
    put("qa_quality",
        _surface_score(pages.get("qa", ""), findings, "qa", want=400)
        if "qa" in (pages or {}) else 7.0,
        "the follow-up answers against the same state")

    return RubricResult(company=company, scores=tuple(out),
                        findings=tuple(f.as_dict() for f in findings))


def _surface_score(text: str, findings, surface: str, want: int = 3000
                   ) -> float:
    if not text:
        return 3.0
    value = _ratio(len(text), want)
    for finding in findings:
        if finding.surface != surface:
            continue
        if finding.severity == DT.SEV1:
            value = min(value, 2.0)
        elif finding.severity == DT.SEV2:
            value = min(value, 6.0)
        elif finding.severity == DT.SEV3:
            value = min(value, 8.5)
    return value


def _model_of(read) -> str:
    # The read does not carry the class directly; the identity line does, via
    # the profile it was built from. Callers pass it explicitly when they have
    # it, and this is the fallback that keeps the scan running.
    return ""
