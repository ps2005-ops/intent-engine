"""The evaluation harness — 50+ deterministic product-review situations.

Each case is (persona, scenario, company fixture). Running it composes a real
report through the real pipeline against a deterministic offline site, scores
it, and then asks the PERSONA's question: given how long this reader stays and
what they need to leave with, did this work for them?

A case fails critically when the persona hits one of its deal-breakers, or
cannot answer a question it needs answered. Those are the only failures that
block a release; everything else is a score movement to be traded off
deliberately.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field

from intent_engine.product_eval.personas import (
    PERSONAS, PERSONAS_BY_KEY, SCENARIOS_BY_KEY,
)
from intent_engine.product_eval.scorecard import (
    THRESHOLDS, _words, score_report,
)
from intent_engine.product_eval.sites import SITES, site_transport

EVAL_SET_VERSION = "product-eval.v1"


@dataclass
class CaseResult:
    case_id: str
    persona: str
    scenario: str
    company: str
    outcome: str = ""
    critical: list = field(default_factory=list)
    soft: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return bool(self.critical)

    def as_dict(self) -> dict:
        return asdict(self)


# (persona, scenario, company) — 50+ combinations chosen so every persona and
# every scenario appears, and the awkward pairs (thirty-second reader on a
# sparse company; small-business owner on a multinational) are covered on
# purpose rather than by accident.
CASE_MATRIX = (
    ("busy_founder", "strong_evidence", "shopify"),
    ("busy_founder", "company_owned_only", "palantir"),
    ("busy_founder", "startup_no_filings", "linear"),
    ("enterprise_exec", "strong_evidence", "shopify"),
    ("enterprise_exec", "contradictory", "palantir"),
    ("enterprise_exec", "presentation", "shopify"),
    ("sales_leader", "strong_evidence", "shopify"),
    ("sales_leader", "meeting_prep" if False else "presentation", "palantir"),
    ("sales_leader", "no_customer_evidence", "sony"),
    ("product_manager", "strong_evidence", "shopify"),
    ("product_manager", "js_heavy", "palantir"),
    ("investor", "strong_evidence", "shopify"),
    ("investor", "company_owned_only", "linear"),
    ("investor", "no_financials", "notion"),
    ("consultant", "strong_evidence", "shopify"),
    ("consultant", "contradictory", "palantir"),
    ("market_analyst", "stale", "sony"),
    ("market_analyst", "strong_evidence", "shopify"),
    ("smb_owner", "startup_no_filings", "linear"),
    ("smb_owner", "local_business", "corner_cafe"),
    ("smb_owner", "strong_evidence", "shopify"),
    ("technical_founder", "js_heavy", "palantir"),
    ("technical_founder", "startup_no_filings", "linear"),
    ("sceptical_expert", "company_owned_only", "palantir"),
    ("sceptical_expert", "contradictory", "shopify"),
    ("sceptical_expert", "weak_evidence", "sony"),
    ("first_time_visitor", "strong_evidence", "shopify"),
    ("first_time_visitor", "weak_evidence", "sony"),
    ("first_time_visitor", "startup_no_filings", "linear"),
    ("mobile_user", "presentation", "shopify"),
    ("mobile_user", "strong_evidence", "palantir"),
    ("five_minutes", "strong_evidence", "shopify"),
    ("five_minutes", "js_heavy", "palantir"),
    ("thirty_seconds", "strong_evidence", "shopify"),
    ("thirty_seconds", "weak_evidence", "sony"),
    ("thirty_seconds", "startup_no_filings", "linear"),
    ("knows_company", "strong_evidence", "shopify"),
    ("knows_company", "js_heavy", "palantir"),
    ("knows_nothing", "strong_evidence", "shopify"),
    ("knows_nothing", "startup_no_filings", "notion"),
    ("knows_nothing", "local_business", "corner_cafe"),
    ("competitor_context", "strong_evidence", "shopify"),
    ("competitor_context", "no_customer_evidence", "palantir"),
    ("risk_seeker", "contradictory", "shopify"),
    ("risk_seeker", "company_owned_only", "palantir"),
    ("risk_seeker", "weak_evidence", "sony"),
    ("meeting_prep", "strong_evidence", "shopify"),
    ("meeting_prep", "startup_no_filings", "linear"),
    ("meeting_prep", "js_heavy", "palantir"),
    ("simple_explanation", "strong_evidence", "shopify"),
    ("simple_explanation", "startup_no_filings", "notion"),
    ("simple_explanation", "local_business", "corner_cafe"),
    ("busy_founder", "retrieval_failed", "blocked_co"),
    ("first_time_visitor", "retrieval_failed", "blocked_co"),
    ("investor", "sparse", "ghost_co"),
    ("smb_owner", "sparse", "ghost_co"),
    ("enterprise_exec", "identity_ambiguous", "sony"),
    # --- follow-up conversation --------------------------------------------
    # Four conversation scenarios existed in the scenario list and appeared in
    # no case, so the follow-up path was never asked a question by anything.
    ("busy_founder", "followup_natural", "shopify"),
    ("enterprise_exec", "followup_natural", "palantir"),
    ("sales_leader", "followup_natural", "sony"),
    ("first_time_visitor", "followup_vague", "shopify"),
    ("knows_nothing", "followup_vague", "linear"),
    ("sceptical_expert", "followup_hostile", "shopify"),
    ("investor", "followup_hostile", "palantir"),
    ("risk_seeker", "followup_hostile", "sony"),
    ("simple_explanation", "followup_simplify", "shopify"),
    ("smb_owner", "followup_simplify", "brightledger"),
    ("knows_nothing", "followup_simplify", "palantir"),
    # --- company-kind readers ----------------------------------------------
    ("public_company_tester", "strong_evidence", "shopify"),
    ("public_company_tester", "no_customer_evidence", "sony"),
    ("private_company_tester", "no_financials", "notion"),
    ("private_company_tester", "startup_no_filings", "brightledger"),
    ("startup_tester", "startup_no_filings", "brightledger"),
    ("startup_tester", "weak_evidence", "linear"),
    ("multinational_tester", "identity_ambiguous", "sony"),
    ("multinational_tester", "strong_evidence", "palantir"),
    # --- small and local companies that DO have something to say ------------
    ("smb_owner", "local_business", "bloom_dental"),
    ("simple_explanation", "local_business", "bloom_dental"),
    ("first_time_visitor", "local_business", "bloom_dental"),
    ("meeting_prep", "startup_no_filings", "brightledger"),
    ("investor", "startup_no_filings", "brightledger"),
    # --- adversarial retrieved content --------------------------------------
    ("sceptical_expert", "prompt_injection", "hostile_co"),
    ("first_time_visitor", "prompt_injection", "hostile_co"),
    ("investor", "evidence_poisoning", "hostile_co"),
    ("risk_seeker", "evidence_poisoning", "hostile_co"),
    # --- operational conditions ---------------------------------------------
    ("busy_founder", "cached_low_quality", "shopify"),
    ("enterprise_exec", "pipeline_upgrade", "shopify"),
    ("mobile_user", "low_bandwidth", "palantir"),
    ("thirty_seconds", "cold_start", "shopify"),
    ("mobile_user", "mobile", "shopify"),
    ("first_time_visitor", "mobile", "brightledger"),
)


def build_cases() -> list:
    """The versioned case list. Deterministic and order-stable."""
    cases = []
    for index, (persona, scenario, company) in enumerate(CASE_MATRIX):
        cases.append({
            "case_id": f"c{index:03d}-{persona}-{scenario}-{company}",
            "persona": persona,
            "scenario": scenario,
            "company": company,
        })
    return cases


def _compose(company_key: str):
    """Run the real pipeline against a deterministic offline site."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    from intent_engine.webapp.app import WebApp

    site = SITES[company_key]
    tmp = tempfile.mkdtemp(prefix="peval-")
    ci = CompanyIngestionService(os.path.join(tmp, "ci.jsonl"),
                                 transport=site_transport(site),
                                 resolver=False)
    fi = FounderIntelligenceService(os.path.join(tmp, "fi.jsonl"))
    run = ci.create_run(company_name=site.name, website=site.website,
                        user_id="evaluator",
                        as_of="2026-07-28T00:00:00+00:00")
    run_id = run["run_id"]
    candidates = ci.discover(run_id)
    picked = WebApp._recommended_candidate_ids(
        candidates, refusing_hosts=ci.refusing_hosts(run_id))
    if not picked:
        picked = [c["candidate_id"] for c in candidates[:1]]
    ci.approve(run_id, user_id="evaluator", approved_ids=picked,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in picked])
    ci.fetch_approved(run_id)
    result = ci.compose_with_quality(run_id, fi_service=fi)
    return ci, run_id, result


def _brief_and_slides(result, documents=()):
    report = result.get("strategic_report")
    if not report:
        return None, []
    from intent_engine.strategic_intelligence.brief import build_brief
    from intent_engine.strategic_intelligence.slides import build_slides
    brief = build_brief(report, as_of="2026-07-28",
                        analysis_version="eval", documents=documents)
    # `documents` is not optional in practice: without it the factual slides
    # (what the company does, its products, its customers) are built from the
    # much smaller observation set and come out empty, so the deck the
    # evaluation scored was shorter than the one a reader is served. The
    # harness measured a product nobody uses.
    slides = build_slides(report, as_of="2026-07-28",
                          analysis_version="eval", brief=brief,
                          documents=documents)
    return brief, slides


# What each of the ten standard questions LOOKS like in a composed analysis.
# A persona declaring it must answer "what decision could this affect" is only
# a gate if something checks that the answer is on the page; otherwise the
# persona list is documentation. Each entry is (brief field, slide ids) — the
# reader can be served by either layer, because either is where they might
# land.
_ANSWERED_BY = {
    "what does this company do": (("thesis",), ("company", "market")),
    "what appears to be changing": ((), ("changed", "signals")),
    "the most important strategic hypothesis": (("thesis",), ("view",)),
    "why it matters": (("decision", "tension"), ("view", "tension")),
    "what evidence supports it": ((), ("signals", "market", "evidence")),
    "what evidence weakens it": (("counterpoint",), ("tension", "evidence")),
    "what decision it could affect": (("decision",), ("view",)),
    "what to investigate next": (("questions",), ("questions", "opportunity")),
    "how confident to be": ((), ("view", "evidence")),
    "what could not be determined": (("limitation",), ("evidence",)),
}


def _unanswered(persona, brief, slides) -> list:
    """The questions this reader needs that the analysis does not answer."""
    from intent_engine.strategic_intelligence.editorial import is_meaningful
    filled = {s.get("id") for s in slides or ()
              if s.get("bullets") or s.get("body")}
    missing = []
    for question in persona.must_answer:
        fields, slide_ids = _ANSWERED_BY.get(question, ((), ()))
        by_brief = any(_field_present(brief, f) for f in fields)
        by_slide = bool(filled & set(slide_ids))
        if not (by_brief or by_slide):
            missing.append(question)
    return missing


def _headline_stands_alone(headline) -> bool:
    """Whether the opening lines are a complete answer rather than a fragment.

    Both halves have to be there. "What is changing" without "what this
    company is" is unusable to a reader who arrived knowing nothing, and it is
    exactly the reader with thirty seconds who most often did.
    """
    from intent_engine.strategic_intelligence.editorial import is_meaningful
    does = getattr(headline, "does", "")
    view = getattr(headline, "view", "")
    if not (is_meaningful(does) and is_meaningful(view)):
        return False
    # A "we could not find this" line is honest, but it is not an answer.
    return "not described on any page" not in does.lower()


def _field_present(brief, field_name) -> bool:
    from intent_engine.strategic_intelligence.editorial import is_meaningful
    if brief is None:
        return False
    value = getattr(brief, field_name, None)
    if isinstance(value, (list, tuple)):
        return any(is_meaningful(v if isinstance(v, str) else
                                 (v or {}).get("text", "")) for v in value)
    return is_meaningful(value)


def _evaluate(case, ci, run_id, result) -> CaseResult:
    persona = PERSONAS_BY_KEY[case["persona"]]
    scenario = SCENARIOS_BY_KEY[case["scenario"]]
    out = CaseResult(case_id=case["case_id"], persona=persona.key,
                     scenario=scenario.key, company=case["company"])

    documents = ci.store.retrieved(run_id)
    brief, slides = _brief_and_slides(result, documents)
    score = score_report(brief=brief, slides=slides,
                         report=result.get("strategic_report"),
                         documents=documents,
                         quality=result.get("quality"),
                         readiness=result.get("readiness"))
    out.outcome = score.outcome
    out.metrics = score.metrics

    # A scenario that SHOULD refuse is not failing when it refuses.
    refused = score.outcome == "INSUFFICIENT_EVIDENCE"
    if scenario.expects_refusal:
        if not refused:
            out.critical.append(
                "produced a confident-looking report where the evidence does "
                "not support one")
        return out
    if refused:
        if scenario.expects_limited:
            return out
        out.critical.append("refused on a scenario that has usable evidence")
        return out

    # Structural failures are critical for everyone.
    out.critical.extend(score.failures)
    out.soft.extend(score.warnings)

    # Follow-up questions, asked for real. The single most concrete piece of
    # observed feedback was that a normal question came back as an internal
    # result, and no case in this suite had ever typed one.
    out.critical.extend(
        _evaluate_conversation(scenario, result.get("strategic_report")))

    # What a page that argues with the system must not achieve.
    out.critical.extend(_evaluate_adversarial(
        scenario, documents, result.get("strategic_report"), brief, slides,
        score))

    # What a small screen makes unusable.
    out.critical.extend(_evaluate_on_a_small_screen(scenario, slides))

    # The last read before a stranger sees it. Anything the critic blocks on
    # is something a sceptical reader would catch, so it is a failure here.
    if result.get("strategic_report") is not None:
        from intent_engine.strategic_intelligence.critic import critique
        verdict = critique(result["strategic_report"], documents=documents)
        out.metrics["critic_findings"] = len(verdict["findings"])
        for finding in verdict["findings"]:
            if finding["severity"] == "block":
                out.critical.append(f"critic: {finding['message']}")
            else:
                out.soft.append(f"critic: {finding['message']}")

    # The questions this reader came with. This is the difference between "the
    # pipeline finished" and "the person got what they came for".
    for question in _unanswered(persona, brief, slides):
        out.critical.append(
            f"{persona.label} cannot answer: {question}")
    out.metrics["unanswered_questions"] = len(
        _unanswered(persona, brief, slides))

    # Persona-specific expectations.
    #
    # What this reader can afford is not always the whole brief. A reader with
    # thirty seconds meets the headline — one complete unit, sixty words —
    # and either stops there satisfied or reads on. Measuring them against the
    # full brief said the product failed them; measuring them against a
    # truncation would say it served them when it had only cut them off. So
    # the headline is measured as the whole thing it is, and it still has to
    # answer that reader's questions on its own.
    headline = getattr(brief, "headline", None)
    headline_words = getattr(headline, "word_count", 0)
    brief_words = score.metrics.get("brief_words", 0)
    brief_seconds = score.metrics.get("brief_reading_seconds", 0)
    from intent_engine.product_eval.scorecard import reading_seconds
    over_budget = (brief_words > persona.word_budget
                   or brief_seconds > persona.patience_s)
    headline_seconds = reading_seconds(
        " ".join(filter(None, (getattr(headline, "does", ""),
                               getattr(headline, "view", ""),
                               getattr(headline, "confidence", "")))))
    reads_headline_only = (headline_words and over_budget
                           and headline_words <= persona.word_budget
                           and headline_seconds <= persona.patience_s)
    out.metrics["headline_words"] = headline_words
    out.metrics["reads_headline_only"] = bool(reads_headline_only)

    if reads_headline_only:
        if not _headline_stands_alone(headline):
            out.critical.append(
                f"{persona.label} only reaches the opening lines, and they do "
                f"not say what the company does or what is thought to be "
                f"happening")
    else:
        if brief_words > persona.word_budget:
            out.critical.append(
                f"{persona.label} reads ~{persona.word_budget} words; the "
                f"brief is {brief_words}")
        if brief_seconds > persona.patience_s:
            out.critical.append(
                f"{persona.label} gives it {persona.patience_s}s; the brief "
                f"needs {brief_seconds}s")

    for breaker in persona.deal_breakers:
        if breaker == "jargon without explanation" and \
                score.metrics.get("jargon_per_100_words", 0) > 2.0:
            out.critical.append(f"{persona.label}: {breaker}")
        if breaker == "generic risk boilerplate" and \
                score.metrics.get("thesis_generic"):
            out.critical.append(f"{persona.label}: {breaker}")
        if breaker == "confidence unsupported by independent evidence" and \
                score.metrics.get("high_confidence_count", 0) and \
                score.metrics.get("independent_share", 0) < 0.2:
            out.critical.append(f"{persona.label}: {breaker}")
        if breaker == "claim stronger than its source" and \
                score.metrics.get("metadata_only_documents", 0) and \
                score.metrics.get("hypothesis_count", 0):
            out.critical.append(f"{persona.label}: {breaker}")
        if breaker == "assumes public filings exist" and \
                scenario.company_type != "public" and \
                any("investor" in f for f in score.failures):
            out.critical.append(f"{persona.label}: {breaker}")

    # Startup/local companies must never be judged against filings.
    if scenario.company_type != "public":
        if any("investor" in str(f).lower() or "filing" in str(f).lower()
               for f in out.critical):
            out.critical.append(
                "a private company is being held to public-company evidence")
    return out


def run_cases(cases=None, *, stop_on_first=False) -> dict:
    """Run every case and summarise. Pure offline; no network, no model."""
    cases = cases or build_cases()
    results, by_persona = [], {}
    composed_cache = {}
    for case in cases:
        key = case["company"]
        if key not in composed_cache:
            composed_cache[key] = _compose(key)
        ci, run_id, result = composed_cache[key]
        outcome = _evaluate(case, ci, run_id, result)
        results.append(outcome)
        bucket = by_persona.setdefault(outcome.persona,
                                       {"total": 0, "failed": 0})
        bucket["total"] += 1
        bucket["failed"] += 1 if outcome.failed else 0
        if stop_on_first and outcome.failed:
            break

    failed = [r for r in results if r.failed]
    clusters = {}
    for r in failed:
        for reason in r.critical:
            key = _cluster_key(reason)
            clusters.setdefault(key, {"count": 0, "cases": []})
            clusters[key]["count"] += 1
            clusters[key]["cases"].append(r.case_id)
    return {
        "eval_set_version": EVAL_SET_VERSION,
        "total_cases": len(results),
        "failed_cases": len(failed),
        "pass_rate": round(1 - len(failed) / max(1, len(results)), 3),
        "by_persona": by_persona,
        "failure_clusters": dict(sorted(clusters.items(),
                                        key=lambda kv: -kv[1]["count"])),
        "results": [r.as_dict() for r in results],
    }


# The questions a reader actually types, per conversation scenario. Four
# scenarios existed for these and none of them asked anything — the follow-up
# path was declared covered and never exercised, which is how "Intent:
# UNSUPPORTED" reached a tester in the first place.
FOLLOW_UP_QUESTIONS = {
    "followup_natural": (
        "why does this matter?",
        "so what?",
        "what should I monitor?",
        "what changed recently?",
        "how confident should I be in this?",
    ),
    "followup_vague": (
        "hm",
        "tell me more",
        "and?",
    ),
    "followup_hostile": (
        "this seems like a stretch — what argues against it?",
        "what would prove this wrong?",
        "isn't this true of every company in the sector?",
    ),
    "followup_simplify": (
        "explain this without jargon",
        "explain it like I run a small business",
        "what does this company actually do?",
    ),
}

# Vocabulary that belongs to the code, not to a reader. Any of these reaching
# a visible answer is a critical failure regardless of how good the answer is.
INTERNAL_VOCABULARY = (
    "unsupported", "unmatched", "explained", "comparison_answer",
    "hypothesis_id", "observation_id", "obs-", "hyp-", "pattern_id",
    "qualifying_signal", "intent:", "operation:", "scaffold",
    "strategic_pattern_library", "source_class", "_signal",
)


def _ask(question: str, report) -> dict:
    """One follow-up turn, taken the way the product takes it."""
    from intent_engine.strategic_intelligence.conversation import (
        answer_strategic,
    )
    return answer_strategic(question, report)


def _visible_text(answer: dict) -> str:
    """Everything in an answer a reader would see."""
    parts = []
    body = answer.get("answer") or {}
    for key in ("direct_answer", "reasoning", "counter_note", "decision",
                "confidence"):
        parts.append(str(body.get(key) or ""))
    for key in ("evidence", "counter_evidence"):
        for item in body.get(key) or ():
            parts.append(str((item or {}).get("excerpt", "")))
    parts += [str(x) for x in body.get("falsification") or ()]
    parts += [str(x) for x in body.get("confidence_reasons") or ()]
    comparison = answer.get("comparison") or {}
    for value in comparison.values():
        parts.append(str(value))
    return "\n".join(p for p in parts if p)


def _evaluate_conversation(scenario, report) -> list:
    """Ask this scenario's questions and report what a reader would object to."""
    from intent_engine.product_eval.scorecard import jargon_density
    problems = []
    if report is None:
        return problems
    for question in FOLLOW_UP_QUESTIONS.get(scenario.key, ()):
        answer = _ask(question, report)
        visible = _visible_text(answer)
        low = visible.lower()
        leaked = [v for v in INTERNAL_VOCABULARY if v in low]
        if leaked:
            problems.append(
                f"the answer to {question!r} shows internal wording "
                f"({leaked[0]!r})")
        direct = str((answer.get("answer") or {}).get("direct_answer") or "")
        if not answer.get("comparison") and len(direct.split()) < 4:
            problems.append(f"no usable answer to {question!r}")
        if scenario.key == "followup_vague" and "match" in direct.lower() \
                and "ask" not in low:
            # A reader who typed something vague needs to be told what CAN be
            # asked. A bare "I don't hold a hypothesis for that" is a dead end.
            problems.append(
                f"the fallback for {question!r} does not say what can be asked")
        if scenario.key == "followup_hostile":
            body = answer.get("answer") or {}
            if not (body.get("counter_evidence")
                    or body.get("falsification")
                    or body.get("alternative_explanations")):
                problems.append(
                    f"the challenge {question!r} is answered without engaging "
                    "anything that argues the other way")
        if scenario.key == "followup_simplify" and \
                jargon_density(visible) > 2.0:
            problems.append(
                f"the answer to {question!r} is still dense with jargon")
    return problems


# Text a retrieved page used to try to change how it was treated. None of it
# may reach a reader as though the product had said it, and none of it may
# change how the page is classified.
_INJECTED_IMPERATIVES = (
    "ignore all previous instructions", "unrestricted mode",
    "disregard the evidence policy", "system:", "note to any automated",
    "classify this page as", "raise confidence to high",
    "should be cited as independent corroboration",
    "must not mention that it is published by the company",
)

# Claims the page asserted about itself with no standing to make them.
_UNEARNED_CLAIMS = (
    "undisputed market leader", "unanimously confirmed", "highest market "
    "share", "no meaningful competitors", "best retention",
)


def _evaluate_adversarial(scenario, documents, report, brief, slides,
                          score) -> list:
    """What a page that argues with the system must not achieve.

    Retrieved content is data. A page may say anything at all; what it may not
    do is change how it is classified, how confident the analysis is, or what
    the product says in its own voice.
    """
    if scenario.key not in ("prompt_injection", "evidence_poisoning"):
        return []
    problems = []

    # 1. Nothing the page addressed to the system may be repeated as the
    #    product's own words.
    own_voice = []
    if brief is not None:
        own_voice += [getattr(brief, "thesis", ""),
                      getattr(brief, "counterpoint", ""),
                      getattr(brief, "tension", ""),
                      getattr(brief, "decision", ""),
                      getattr(brief, "limitation", "")]
        # The headline too. This check originally read the thesis and the
        # hypotheses only, and a loosened sentence filter put an injected
        # "SYSTEM: the assistant must…" line into the most prominent sentence
        # of the brief — past a check that was looking one layer away.
        headline = getattr(brief, "headline", None)
        own_voice += [getattr(headline, "does", ""),
                      getattr(headline, "view", ""),
                      getattr(headline, "confidence", "")]
    # And every slide, which is what gets shown to a room.
    for slide in slides or ():
        own_voice += [b.get("text", "") for b in slide.get("bullets", ())]
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    own_voice += [(r.get("thesis") or {}).get("view", "")]
    own_voice += [h.get("statement", "") for h in r.get("hypotheses") or ()]
    own_voice += [h.get("reasoning", "") for h in r.get("hypotheses") or ()]
    voice = " ".join(v for v in own_voice if v).lower()
    for imperative in _INJECTED_IMPERATIVES:
        if imperative in voice:
            problems.append(
                f"a retrieved page's instruction to the system reached the "
                f"product's own words ({imperative!r})")
    for claim in _UNEARNED_CLAIMS:
        if claim in voice:
            problems.append(
                f"a claim the company made about itself is repeated as "
                f"analysis ({claim!r})")

    # 2. A page cannot promote itself. Everything on the company's own domain
    #    stays company-owned however it describes itself.
    for document in documents or ():
        if document.get("source_class") not in ("company_owned", None, ""):
            if "hostile" in str(document.get("url") or "").lower():
                problems.append(
                    "a company-owned page was classified as something more "
                    "independent than it is")

    # 3. And it cannot buy confidence. Company-owned evidence alone is capped
    #    whatever the page asserts about third-party validation.
    if score.metrics.get("high_confidence_count") and \
            score.metrics.get("independent_share", 0) == 0:
        problems.append("confidence is high on evidence the company published "
                        "about itself")
    return problems


def _evaluate_on_a_small_screen(scenario, slides) -> list:
    """The deck, met on a phone.

    Checked against the rendered HTML rather than the slide objects, because
    the failures a phone produces — a fixed pixel width, a table that will not
    wrap, no viewport declaration — exist only after rendering. A structural
    check would pass a deck that scrolls sideways.
    """
    if "layout" not in scenario.tags or not slides:
        return []
    import re

    from intent_engine.strategic_intelligence.slides import render_deck
    html = render_deck(slides, company="Evaluated Co", as_of="2026-07-28",
                       analysis_version="eval")
    low = html.lower()
    problems = []
    # A FIXED width scrolls sideways; a max-width is the fix for it, so the
    # pattern has to exclude max- and min- rather than match "width" anywhere.
    # (An earlier version of this check did not, and reported `max-width:900px`
    # — the responsive rule — as the defect.)
    for match in re.finditer(r"(?<![a-z-])width:\s*(\d+)px", low):
        if int(match.group(1)) > 480:
            problems.append(f"the deck sets a fixed width of "
                            f"{match.group(1)}px, which scrolls sideways on a "
                            f"phone")
    if "@media (max-width" not in low.replace(" ", " "):
        problems.append("the deck has no small-screen rules at all")
    if "<table" in low and "overflow-x" not in low:
        problems.append("a table can exceed the screen with nothing to "
                        "scroll it")
    return problems


def _cluster_key(reason: str) -> str:
    """Group failure reasons that are the same defect wearing different
    numbers, so the ledger points at causes rather than instances."""
    low = reason.lower()
    # An unanswered question clusters by the QUESTION, not by who asked it —
    # five personas failing on "what evidence weakens it" is one defect.
    if "cannot answer:" in low:
        return "unanswered: " + reason.split("cannot answer:")[-1].strip()
    for marker, key in (
            ("words; the standard", "brief too long (absolute)"),
            ("reads ~", "brief too long for this persona"),
            ("gives it", "brief too slow for this persona"),
            ("repeats text", "repetition"),
            ("re-cited across", "evidence reuse"),
            ("hypotheses shown", "too many hypotheses"),
            ("true of any company", "generic thesis"),
            ("high-confidence on company-owned", "confidence miscalibrated"),
            ("slide(s) have no content", "empty slides"),
            ("exceed", "overfull slides"),
            ("jargon", "jargon"),
            ("refused on a scenario", "over-refusal"),
            ("confident-looking report", "under-refusal"),
            ("public-company evidence", "wrong evidence model"),
            ("claim stronger than its source", "thin evidence, strong claim"),
    ):
        if marker in low:
            return key
    return reason[:60]
