"""V1.2 strategic reasoning engine — deterministic, evidence-driven.

It consumes structured StrategicObservations (from approved live sources or a
curated validation fixture), matches their controlled-vocabulary signals
against the auditable pattern library, and instantiates strategic hypotheses
with the full reasoning apparatus. It performs retrieval-fed comparative
reasoning and pattern matching — NOT live model training. No network, no LLM,
no randomness: the same evidence always yields the same report.
"""
from __future__ import annotations

from intent_engine.strategic_intelligence.observations import (
    qualifying_signals_of,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY, TENSIONS, statement_for,
)
from intent_engine.strategic_intelligence.records import (
    BlindSpot, MechanismEvidence, StrategicHypothesis, StrategicObservation,
    StrategicQuestion,
    StrategicReport,
)

_CONF_RANK = {"speculative": 0, "low": 1, "moderate": 2, "high": 3}
# source classes that make a report more than one-sided
from intent_engine.strategic_intelligence import evidence_classes as EC

# Kept as aliases so existing readers of these names keep working; the tiers
# themselves now live in one place (`evidence_classes`) because they were
# duplicated across five modules and drifted.
_EXTERNAL_CLASSES = EC.EXTERNAL_CLASSES
_INDEPENDENT_CLASSES = EC.INDEPENDENT_CLASSES


def _signals_present(observations) -> set:
    """Signals that may QUALIFY a hypothesis.

    Weak observations contribute none. This used to union every observation's
    signals, so a marketing snippet full of calls-to-action could push a
    hypothesis over its threshold by itself.
    """
    present = set()
    for o in observations:
        present.update(qualifying_signals_of(o))
    return present


def _obs_with_any(observations, wanted) -> list:
    wanted = set(wanted)
    return [o for o in observations if wanted & set(o.signals)]


# WHOSE ACCOUNT a source is, which is not the same question as what KIND of
# page it is. A company's investor relations page and its product page are two
# source classes and one vantage point: the company, describing itself. Three
# such pages agreeing is not corroboration, it is a company being consistent —
# and counting them as diversity is how a claim about how the market sees a
# company reached "high confidence" on nothing but the company's own writing.
_VANTAGE_OF = {
    "company_owned": "the company",
    "executive_statement": "the company",
    "investor_material": "the company",
    "customer_voice": "its customers",
    "competitor": "a competitor",
    "independent_reporting": "an independent observer",
    "historical_pattern": "a historical pattern",
}


def _vantages(support_classes) -> set:
    return {_VANTAGE_OF.get(c, "an unclassified source")
            for c in support_classes}


def _provenance(support_classes) -> str:
    """How this claim is known, named for the strongest support behind it."""
    classes = set(support_classes)
    if classes & {"independent_reporting", "competitor"}:
        return "independently corroborated"
    if "customer_voice" in classes:
        return "customer-observed"
    if classes & {"company_owned", "executive_statement", "investor_material"}:
        return "company-stated"
    if "historical_pattern" in classes:
        return "pattern-supported"
    return "inferred"


def _confidence(matched_qual, support_classes, counter_count) -> tuple:
    """Return (level, reasons). Confidence rises with the number of qualifying
    signals matched and the number of distinct VANTAGE POINTS supporting them,
    and is tempered when counter-evidence is present."""
    base = len(matched_qual)
    vantages = _vantages(support_classes)
    diversity = len(vantages)
    reasons = [
        f"{base} qualifying signal(s) matched: {', '.join(sorted(matched_qual))}",
        f"supported from {diversity} vantage point(s): "
        f"{', '.join(sorted(vantages))}",
    ]
    only_company = vantages == {"the company"}
    independent = set(support_classes) & set(_INDEPENDENT_CLASSES)
    if only_company:
        reasons.append("all support comes from company-owned pages, which is "
                       "one-sided; independent corroboration is missing")
    elif independent:
        reasons.append("corroborated across an independent vantage point ("
                       + ", ".join(sorted(independent)) + "), not only the "
                       "company's own publishing")
    if counter_count:
        reasons.append(f"{counter_count} observation(s) point the other way "
                       "and are held as explicit counter-evidence")

    if diversity >= 3 and base >= 3:
        level = "high"
    elif diversity >= 2 and base >= 2:
        level = "moderate"
    elif base >= 2:
        level = "low"
    else:
        level = "speculative"
    # High confidence is a claim about the world, and the company's own account
    # of itself cannot establish one however many of its pages agree. This is
    # the hard cap: without a vantage point outside the company, the ceiling is
    # moderate whatever the signal count reaches.
    if not independent and level == "high":
        level = "moderate"
        reasons.append("capped below high: no source outside the company "
                       "corroborates this")
    if counter_count >= max(1, base) and _CONF_RANK[level] > 1:
        level = "low"
    return level, reasons


#: source classes as a reader would say them
_CLASS_IN_WORDS = {
    "executive_statement": "executive statement",
    "investor_material": "investor material",
    "customer_voice": "customer account",
    "competitor": "competitor",
    "independent_reporting": "independent report",
}


#: How each causal mechanism reads in a sentence. A reading that fires on a
#: mechanism SAYS WHICH ONE, so two companies that genuinely qualify differ
#: because their evidence differs — not because the wording was varied. Every
#: phrase here describes only what the signal itself observed.
_MECHANISM_PHRASE = {
    "gov_dedicated_delivery":
        "it runs a separate government or sovereign estate alongside the "
        "commercial one",
    "accreditation_gate":
        "it holds accreditations those buyers require before they may "
        "purchase at all",
    "public_procurement_vehicle":
        "it is bought through public procurement machinery rather than "
        "ordinary sales",
    "disclosed_public_sector_exposure":
        "it has written down what public-sector buyers contribute",
}


def _mechanism_phrase(pattern, present):
    """The mechanisms this reading actually read off, in a reader's words."""
    matched = [s for s in pattern.required_any_signals if s in present]
    phrases = [_MECHANISM_PHRASE[s] for s in matched if s in _MECHANISM_PHRASE]
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return ", and ".join([", ".join(phrases[:-1]), phrases[-1]])


def _mechanism_evidence(pattern, observations):
    """The sentences that actually established this reading's mechanism.

    Built HERE because this is the last place that knows which signal
    qualified the pattern. Downstream, a surface has only the hypothesis and a
    list of observations, and cannot tell which of a document's eighteen
    signals the reading was about — so it showed the document's opening
    instead. See `records.MechanismEvidence`.

    An observation whose span could not be resolved is skipped rather than
    quoted from its excerpt: the excerpt is chosen for the document, and
    passing it off as the evidence for this signal is the defect, not the fix.
    """
    from intent_engine.strategic_intelligence.observations import (
        _NEUTRAL_LABEL, _NEUTRAL_SIGNAL_KEYWORDS, _SIGNAL_KEYWORDS,
        phrase_span,
    )
    # MECHANISM BEFORE SUBJECT. Surfaces quote the first item, and the first
    # item should be the half that explains the consequence. Measured on
    # `portfolio_run_as_one`, which requires both: the reader was shown
    # "Segment results are reported" — true, and the least surprising thing
    # about the company — while the coupling that actually makes the
    # businesses one ("customers use one account across our products, with
    # unified billing") sat second and went unread.
    wanted = tuple(pattern.required_any_signals) + tuple(
        pattern.required_signals)
    out, seen = [], set()
    for signal in wanted:
        if signal in seen:
            continue
        phrases = (_NEUTRAL_SIGNAL_KEYWORDS.get(signal)
                   or _SIGNAL_KEYWORDS.get(signal) or ())
        for observation in observations:
            if signal not in (observation.signals or ()):
                continue
            quote = (getattr(observation, "signal_spans", None)
                     or {}).get(signal, "")
            if not quote:
                # NOT A FALLBACK TO THE EXCERPT — that is the defect this
                # whole module exists to remove, and a break proof asserts it
                # stays removed. This searches the excerpt for the PHRASE and
                # quotes only the sentence containing it, which is the same
                # rule as `signal_spans`, applied late.
                #
                # Needed because spans are captured during detection, and not
                # every observation is built that way: fixtures, cached
                # records and the stored path all construct
                # `StrategicObservation` directly. Without this, a reading
                # backed by real evidence went silent purely because of where
                # its observation was assembled — measured as narrative
                # overlap RISING between two unrelated companies, since what
                # was dropped was the company-specific half of the page.
                quote = phrase_span(
                    f"{observation.excerpt or ''} {observation.text or ''}",
                    phrases)
            if not quote:
                continue
            seen.add(signal)
            out.append(MechanismEvidence(
                signal=signal,
                label=_NEUTRAL_LABEL.get(signal, ""),
                quote=quote,
                observation_id=observation.observation_id,
                source_title=observation.source_title,
                origin=observation.origin,
                source_class=observation.source_class))
            break
    return tuple(out)


def _rank_evidence(observations):
    """Order evidence by strategic value: independent vantage first, then
    dated, then strong (not weak), then more specific (longer excerpt)."""
    def score(o):
        return (1 if o.source_class in _INDEPENDENT_CLASSES else 0,
                1 if o.date else 0,
                0 if o.weak else 1,
                len(o.excerpt or ""))
    return sorted(observations, key=score, reverse=True)


def _hypothesis_for(pattern, scaffold, observations, company_name):
    present = _signals_present(observations)
    matched_qual = tuple(s for s in pattern.qualifying_signals if s in present)
    if len(matched_qual) < scaffold.get("threshold", 2):
        return None
    # A threshold counts evidence; it cannot tell which evidence the reading is
    # ABOUT. Without this, two of `services_to_product`'s three qualifying
    # signals were enough, and "multi_product + developer_surface" — an API
    # page and a product page, on any software company — asserted that the
    # company "delivers work alongside customers". Measured on the deployed
    # preview: five of seven full results (Datadog, MongoDB, Cloudflare,
    # HubSpot, Visa) reached the SAME conclusion, none of which had retrieved
    # a services signal. See `ComparablePattern.required_signals`.
    if any(s not in present for s in pattern.required_signals):
        return None
    # A READING NEEDS A REASON TO BE TRUE, NOT JUST VOCABULARY FOR IT.
    # `buyer_concentration_exposure` qualified on "regulated industries" copy
    # plus a case-studies page, so HubSpot — whose only regulated-buyer
    # evidence was the phrase "defense-in-depth" on its security page —
    # received the same dominant conclusion as Snowflake, which runs GovCloud
    # regions at DoD IL5. One of those companies has a public-sector
    # mechanism. See `ComparablePattern.required_any_signals`.
    if pattern.required_any_signals and not any(
            s in present for s in pattern.required_any_signals):
        return None
    matched_disc = tuple(s for s in pattern.disconfirming_signals
                         if s in present)
    # support: prefer STRONG observations carrying a qualifying signal
    support_all = _obs_with_any(observations, matched_qual)
    support = [o for o in support_all if not o.weak] or support_all
    if not support:
        return None
    support_ids = {o.observation_id for o in support}
    # counter: observations carrying a disconfirming signal, EXCLUDING anything
    # already counted as support — the same observation is never listed as both
    # support and contradiction (fixes the wholesale-copy failure).
    counter_all = [o for o in _obs_with_any(observations, matched_disc)
                   if o.observation_id not in support_ids]
    counter = [o for o in counter_all if not o.weak] or counter_all
    support_classes = {o.source_class for o in support}

    level, reasons = _confidence(matched_qual, support_classes, len(counter))
    if _CONF_RANK[level] > _CONF_RANK[pattern.confidence]:
        level = pattern.confidence
        reasons.append(f"capped at the pattern's reliability ({level}); the "
                       "historical analogue is not more certain than this")

    # CLEAN reasoning for the executive view; internal signal detail goes to a
    # separate trace shown only in the technical appendix.
    reasoning = scaffold["reasoning"]
    signal_trace = ("signals matched: " + ", ".join(matched_qual)
                    + " · reads off: "
                    + "; ".join(f'"{o.text}"' for o in support[:3]))

    strongest_support = _rank_evidence(support)[:3]
    strongest_counter = _rank_evidence(counter)[:2]
    dated = sorted((o for o in support if o.date),
                   key=lambda o: o.date, reverse=True)
    why_now = (f"Recent public signal ({dated[0].date}, "
               f"{dated[0].source_title}) keeps this timely."
               if dated else "Timeliness limited: no dated evidence retrieved.")

    gaps = list(scaffold["gaps"])
    # SCOPED TO WHAT THE RUN RETRIEVED, not to what supports this one
    # hypothesis. Live on the preview after SEC periodic reports started
    # arriving: the executive brief listed "Filings and investor material · 1"
    # and, four lines down, "no investor material ... has corroborated this
    # yet". Both were computed correctly and the page contradicted itself,
    # because this sentence reads to a founder as a statement about the run.
    retrieved_classes = {o.source_class for o in observations}
    missing_external = [c for c in _EXTERNAL_CLASSES
                        if c not in support_classes
                        and c not in retrieved_classes]
    if missing_external:
        # Named in a reader's words. The enum spellings are the pipeline's
        # own, and the deployed deck printed "no investor_material /
        # customer_voice / competitor / independent_reporting source
        # corroborates this yet" to a founder.
        gaps.append("no " + ", ".join(_CLASS_IN_WORDS.get(c, c)
                                      for c in missing_external)
                    + " has corroborated this yet")

    strong_ids = {o.observation_id for o in strongest_support}
    roles = ([(o.observation_id, "direct_support") for o in strongest_support]
             + [(o.observation_id, "indirect_support") for o in support
                if o.observation_id not in strong_ids]
             + [(o.observation_id, "contradiction") for o in counter])
    h = StrategicHypothesis(
        hypothesis_id=f"hyp-{pattern.pattern_id}",
        title=scaffold["title"],
        statement=statement_for(
            scaffold, company=company_name,
            mechanism=_mechanism_phrase(pattern, present)),
        reasoning=reasoning,
        supporting_observation_ids=[o.observation_id for o in support],
        counter_observation_ids=[o.observation_id for o in counter],
        alternative_explanations=list(scaffold["alternatives"]),
        confidence=level,
        confidence_reasons=reasons,
        evidence_gaps=gaps,
        decision_implications=list(scaffold["implications"]),
        falsification_questions=list(scaffold["falsification"]),
        pattern_id=pattern.pattern_id,
        source_classes=tuple(sorted(support_classes)),
        why_now=why_now, signal_trace=signal_trace,
        strongest_support_ids=tuple(o.observation_id
                                    for o in strongest_support),
        strongest_counter_ids=tuple(o.observation_id for o in strongest_counter),
        comparables=tuple(e.get("name", "")
                          for e in pattern.historical_examples),
        evidence_roles=tuple(roles),
        provenance=_provenance(support_classes),
        mechanism_evidence=_mechanism_evidence(pattern, support),
    )
    h.validate()
    return h


def _build_shifts(observations):
    """Meaningful, dated changes — the fixture/derivation dates exactly the
    observations that represent a movement, so we surface those."""
    shifts, seen_types = [], set()
    dated = [o for o in observations if o.date]
    dated.sort(key=lambda o: (o.date, o.observation_id), reverse=True)
    for o in dated:
        if o.observation_type in seen_types:
            continue
        seen_types.add(o.observation_type)
        shifts.append({
            "title": o.text, "evidence": o.excerpt or o.text,
            "date": o.date, "source_class": o.source_class,
            "observation_id": o.observation_id})
        if len(shifts) >= 5:
            break
    return shifts


def _build_blind_spots(observations):
    present = _signals_present(observations)
    blind = []
    for t in TENSIONS:
        left = [s for s in t["left"] if s in present]
        right = [s for s in t["right"] if s in present]
        if not (left and right):
            continue                      # a tension needs BOTH sides observed
        supp = [o.observation_id for o in
                _obs_with_any(observations, t["left"] + t["right"])]
        blind.append(BlindSpot(
            blind_spot_id=f"blind-{t['tension_id']}",
            observed_tension=t["observed_tension"],
            why_it_may_matter=t["why_it_may_matter"],
            counter_explanation=t["counter_explanation"],
            evidence_needed=list(t["evidence_needed"]),
            decision_affected=t["decision_affected"],
            supporting_observation_ids=supp))
    return blind


# --- portfolio selection ------------------------------------------------------
# Showing five hypotheses because five pattern rules matched is not analysis,
# it is a search result. The observed complaint was precise: the same evidence
# reappeared under several headings, the same mechanism was restated, and the
# strongest insight ended up buried among near-duplicates.
#
# A reader can hold one central view and a couple of things that qualify it.
# So the portfolio is capped, and a hypothesis earns its place only by adding
# something the ones above it did not already say.
MAX_DISPLAYED_HYPOTHESES = 3
# Sharing evidence is normal and often correct — two real forces can rest on
# the same facts. What is NOT useful is a hypothesis that rests on almost
# exactly the same evidence AND leads to the same decision: that is one
# hypothesis printed twice, and it is what buried the strong insight.
NEAR_IDENTICAL_EVIDENCE = 0.85


def _decision_key(hypothesis) -> str:
    first = (hypothesis.decision_implications or [""])[0]
    return " ".join(str(first).lower().split())[:80]


def _is_restatement(candidate, chosen) -> bool:
    """True when a candidate adds neither new evidence nor a new decision."""
    mine = set(candidate.supporting_observation_ids)
    if not mine:
        return True
    for other in chosen:
        theirs = set(other.supporting_observation_ids)
        if not theirs:
            continue
        overlap = len(mine & theirs) / len(mine)
        if overlap >= NEAR_IDENTICAL_EVIDENCE and \
                _decision_key(candidate) == _decision_key(other):
            return True
    return False


def select_portfolio(hypotheses, *, limit=MAX_DISPLAYED_HYPOTHESES) -> list:
    """One primary thesis, then hypotheses that add something new.

    Ordered by confidence and evidence weight, then filtered so a reader is
    never handed the same claim twice under different pattern names.
    Deterministic: same inputs, same portfolio.
    """
    # NOTE ON COUNTER-EVIDENCE AND RANK. Do not add a blanket penalty for
    # `counter_observation_ids` here: it was tried, and it broke the property
    # the product deliberately has — the flagship reading is supposed to carry
    # real counter-evidence, because a lead hypothesis nobody has argued with
    # is one nobody has tested. Disconfirmation that should cost a reading its
    # PLACE is declared per pattern instead; see `_demote_contested`.
    ranked = sorted(
        hypotheses,
        key=lambda h: (_CONF_RANK[h.confidence],
                       len(h.supporting_observation_ids),
                       len(h.counter_observation_ids),
                       h.pattern_id),
        reverse=True)
    chosen = []
    for candidate in ranked:
        if len(chosen) >= limit:
            break
        if chosen and _is_restatement(candidate, chosen):
            continue
        chosen.append(candidate)
    return chosen


def _demote_contested(hypotheses, patterns_by_id, present):
    """A reading its own pattern calls contradicted may not LEAD.

    Disconfirming signals only ever softened the confidence wording, so a
    reading the evidence argues with could still be the first line on the page
    — and the first line is the one most readers take away. `services_to_product`
    declares `pricing_published` as blocking: published self-serve pricing is
    the plainest evidence that the product is already sold without the
    engagement, so that reading must not lead when another one is available.

    Blocking is declared per pattern, never global: a blanket penalty on
    counter-evidence removes the property that the flagship reading has been
    argued with, which is the point of showing counter-evidence at all.

    The reading is not deleted. It keeps its place in the portfolio as a
    secondary hypothesis, which is where a contested reading belongs.
    """
    if len(hypotheses) < 2:
        return hypotheses

    def blocked(hypothesis):
        pattern = patterns_by_id.get(hypothesis.pattern_id)
        return bool(pattern and any(
            s in present for s in getattr(pattern, "blocking_signals", ())))

    if not blocked(hypotheses[0]):
        return hypotheses
    for index, candidate in enumerate(hypotheses[1:], 1):
        if not blocked(candidate):
            return ([candidate] + hypotheses[:index]
                    + hypotheses[index + 1:])
    return hypotheses                    # every reading is contested; keep order


def _build_questions(hypotheses, observations):
    obs_by_id = {o.observation_id: o for o in observations}
    questions = []
    for h in hypotheses:
        trigger = [obs_by_id[i].excerpt or obs_by_id[i].text
                   for i in h.supporting_observation_ids[:2]
                   if i in obs_by_id]
        q = StrategicQuestion(
            question=h.falsification_questions[0],
            why_it_matters=(f"It directly tests the hypothesis that "
                            f"{h.title.lower()}; if it fails, that view is "
                            f"wrong. " + h.confidence_reasons[0]),
            evidence_that_triggered_it=trigger,
            possible_answer_paths=[
                "Evidence confirms the transition → invest ahead of it.",
                "Evidence is mixed → stage investment and watch indicators.",
                "Evidence disconfirms → the hypothesis is rejected.",
            ],
            decision_affected=h.decision_implications[0],
            source_refs=[{"observation_id": i}
                         for i in h.supporting_observation_ids[:3]])
        q.validate()
        questions.append(q)
    return questions


def _build_thesis(company_name, hypotheses, blind_spots, observations=(),
                  evidence_gaps=(), economic_history=None):
    from intent_engine.strategic_intelligence.decision import (
        compose_decision, decide_across,
    )

    # WHAT WAS VERIFIED, in the company's own retrieved words. Carried on the
    # decision because the honest investigation state is unreadable without
    # it: "this cannot be concluded" means nothing to a reader who was never
    # told what COULD be.
    verified = tuple(
        (o.excerpt or o.text) for o in (observations or ())
        if not getattr(o, "weak", False) and (o.excerpt or o.text))[:3]

    if not hypotheses:
        # Flagged rather than left for a caller to recognise by its wording.
        # Downstream gates need to tell "the product declined to form a view
        # and said so" apart from "the product formed a view", and matching on
        # the sentence would break the moment the sentence is edited.
        # "Approved strategic evidence" and "defensible outside-in view" are
        # the pipeline's words for its own steps. The reader needs the fact,
        # which is that the public record did not carry enough to read from.
        # NEVER A NAMELESS SENTENCE. Measured live on Caterpillar, whose
        # brief opened "what has published is not enough to read a strategy
        # from" -- the single most-read line in the product, ungrammatical,
        # because `company_name` arrived empty on the domainless path while
        # the page title resolved the name from elsewhere.
        #
        # This degrades the wording; it does not repair the emptiness, which
        # is a separate upstream defect and is recorded as one. A subject
        # that cannot be named still must not be printed as a hole.
        subject = str(company_name or "").strip() or "this company"
        # THE ONE DECISION OBJECT, built once and carrying the measured
        # history state. Composing it twice was how the surfaces and the
        # withheld sentence started describing different runs.
        _withheld = compose_decision(
            company_name, None, blind_spots, evidence_gaps=evidence_gaps,
            verified=verified)
        if isinstance(economic_history, dict) and economic_history:
            _withheld.economic_history = dict(economic_history)
        # THIS SENTENCE MAY DESCRIBE THIS PASS. IT MAY NOT DESCRIBE THE
        # PRODUCT.
        #
        # It used to read "What X has published is not enough to read a
        # strategy from, so none is put forward here." Both halves were
        # wrong. The first is a claim about the company's disclosure when
        # what actually happened is that the curated pattern library matched
        # no transition -- a fact about a twelve-entry library, not about a
        # public company's filings. The second became false outright once
        # `executive.strategic_read` began composing a bounded read for every
        # identified operating company: a strategy IS put forward, three
        # clicks of this same product away.
        #
        # Gating the library by business model made this MORE frequent, not
        # less: Cloudflare stopped being handed an industrial capacity
        # mechanism, and a clean no-match is the correct outcome. So the
        # sentence now says what this stage did and stops there. The strategic
        # reading is elsewhere, and this sentence no longer denies it.
        return {"view": f"No curated transition pattern matched {subject} in "
                        f"this pass, so the reading below is not built from "
                        f"one.",
                "transition": "", "tension": "", "why_care": "",
                "view_withheld": True,
                "decision": _withheld.as_dict()}
    top = hypotheses[0]
    # NO FABRICATED TENSION.
    #
    # This fell back to the literal string "how much to invest ahead of the
    # transition" whenever no tension was observed -- a noun phrase, not a
    # consequence. The founder brief renders `tension` under the heading "Why
    # this matters", so a company with no observed tension told its reader
    # that what mattered was "how much to invest ahead of the transition",
    # which asserts nothing and was measured on the deployed preview
    # (Palantir, 2026-08-03). An absent tension is now absent, and the
    # consumers below choose a real sentence instead.
    tension = blind_spots[0].observed_tension if blind_spots else ""
    # The blind spot already carries the CONSEQUENCE of its tension, and
    # nothing downstream had ever read it. That is the sentence "why this
    # matters" wants: "the complexity that wins enterprise deals can erode
    # the ease that won the SMB base", rather than the tension restated.
    why_it_may_matter = (blind_spots[0].why_it_may_matter if blind_spots
                         else "")
    return {
        "view": (f"{company_name} appears to be {top.title[0].lower()}"
                 f"{top.title[1:]}. The evidence supports this as a "
                 f"{top.confidence}-confidence hypothesis, not a settled "
                 f"fact."),
        "transition": top.statement,
        "tension": tension,
        "why_it_may_matter": why_it_may_matter,
        # THE TOPIC, KEPT AS THE TOPIC.
        #
        # `why_care` is `implications[0]`, which is a decision TOPIC -- a
        # question -- and every surface printed it as the finished decision.
        # It stays here because the reasoning layer legitimately needs to know
        # WHICH decision the evidence bears on; what changed is that the
        # answer now lives in `decision` and the surfaces render that instead.
        "why_care": top.decision_implications[0],
        "decision": decide_across(
            company_name, hypotheses, blind_spots,
            evidence_gaps=evidence_gaps, verified=verified).as_dict(),
    }


def _decision_implications(hypotheses, blind_spots):
    out = []
    for h in hypotheses[:5]:
        out.append({
            "decision": h.decision_implications[0],
            "options": h.alternative_explanations,
            "evidence_needed": h.evidence_gaps,
            "watch": h.falsification_questions,
            "hypothesis_id": h.hypothesis_id})
    for b in blind_spots:
        out.append({
            "decision": b.decision_affected,
            "options": [b.observed_tension, b.counter_explanation],
            "evidence_needed": b.evidence_needed,
            "watch": b.evidence_needed,
            "blind_spot_id": b.blind_spot_id})
    return out


def _build_evidence_graph(company_name, observations, hypotheses, patterns,
                          blind_spots, questions) -> dict:
    """A typed evidence graph linking sources → observations → hypotheses →
    patterns / counter-observations / questions / decisions. This single
    structure drives the report, the conversation, and downstream analytics —
    there is no second representation."""
    nodes, edges = [], []
    seen_sources = set()
    for o in observations:
        nodes.append({"id": o.observation_id, "type": "observation",
                      "label": o.text, "source_class": o.source_class,
                      "directly_observed": o.directly_observed})
        src = o.origin or o.source_title or o.source_class
        if src and src not in seen_sources:
            seen_sources.add(src)
            nodes.append({"id": f"src:{src}", "type": "source",
                          "label": o.source_title or src,
                          "source_class": o.source_class})
        if src:
            edges.append({"from": o.observation_id, "to": f"src:{src}",
                          "type": "from_source"})
    for h in hypotheses:
        nodes.append({"id": h.hypothesis_id, "type": "hypothesis",
                      "label": h.title, "confidence": h.confidence})
        for oid in h.supporting_observation_ids:
            edges.append({"from": oid, "to": h.hypothesis_id,
                          "type": "supports"})
        for oid in h.counter_observation_ids:
            edges.append({"from": oid, "to": h.hypothesis_id,
                          "type": "contradicts"})
        if h.pattern_id:
            edges.append({"from": h.hypothesis_id, "to": f"pat:{h.pattern_id}",
                          "type": "matches_pattern"})
    for p in patterns:
        nodes.append({"id": f"pat:{p.pattern_id}", "type": "pattern",
                      "label": p.name})
    for b in blind_spots:
        nodes.append({"id": b.blind_spot_id, "type": "blind_spot",
                      "label": b.observed_tension})
        for oid in b.supporting_observation_ids:
            edges.append({"from": oid, "to": b.blind_spot_id,
                          "type": "reveals_tension"})
    for i, q in enumerate(questions):
        qid = f"q:{i}"
        nodes.append({"id": qid, "type": "question", "label": q.question})
        for ref in q.source_refs:
            oid = ref.get("observation_id")
            if oid:
                edges.append({"from": oid, "to": qid, "type": "raises"})
    return {"nodes": nodes, "edges": edges,
            "counts": {"observations": len(observations),
                       "hypotheses": len(hypotheses),
                       "patterns": len(patterns),
                       "edges": len(edges)}}


_FUNCTION_FOR_SIGNAL = {
    "product_breadth": "Product", "storefront_creation": "Product",
    "agentic_commerce": "Product / AI", "distribution_shift": "Growth / GTM",
    "enterprise_expansion": "Enterprise Sales / GTM",
    "checkout_identity_rails": "Payments / Platform",
    "platform_control": "Platform", "data_network": "Data / Platform",
    "partner_ecosystem_enablement": "Partnerships",
    "infrastructure_positioning": "Platform / Strategy",
    "smb_simplicity": "SMB / Product", "merchant_outcome_positioning": "Marketing",
    "investor_material": "Finance / IR",
}


def _affected_functions(signals) -> list:
    fns = []
    for s in signals:
        f = _FUNCTION_FOR_SIGNAL.get(s)
        if f and f not in fns:
            fns.append(f)
    return fns or ["Strategy"]


def _build_timeline(observations) -> list:
    """A chronological strategic timeline from dated evidence."""
    dated = [o for o in observations if o.date]
    dated.sort(key=lambda o: (o.date, o.observation_id))
    return [{"date": o.date, "event": o.text, "source_class": o.source_class,
             "source_title": o.source_title, "observation_id": o.observation_id,
             "kind": o.observation_type} for o in dated]


def _build_agenda(observations, hypotheses) -> list:
    """Infer likely-current leadership discussions from combinations of timely
    public signals. Explicitly labeled as inference — never a claim of private
    meeting knowledge."""
    from intent_engine.strategic_intelligence.insights import _mr_label
    obs_by_id = {o.observation_id: o for o in observations}
    agenda = []
    for h in hypotheses[:4]:
        supp = [obs_by_id[i] for i in h.supporting_observation_ids
                if i in obs_by_id]
        recent = sorted((o for o in supp if o.date),
                        key=lambda o: o.date, reverse=True)[:3]
        signals = set()
        for o in supp:
            signals.update(o.signals)
        # a likely agenda item needs a CLUSTER: >= 2 distinct signals AND
        # at least one dated (timely) signal — not a single keyword.
        if len(signals) < 2 or not recent:
            continue
        classes = {o.source_class for o in supp}
        independent = bool(classes & set(_INDEPENDENT_CLASSES))
        exec_attention = "executive_statement" in classes
        label, why = _mr_label(len(signals), bool(recent), exec_attention,
                               independent)
        against = [obs_by_id[i].text for i in h.counter_observation_ids
                   if i in obs_by_id][:2]
        agenda.append({
            "inferred_discussion": f"How aggressively to act on: {h.title}",
            "why_timely": h.why_now,
            "evidence_cluster": [f"{o.source_title} ({o.source_class}, {o.date})"
                                 for o in recent],
            "public_signals": [f"{o.source_title} ({o.source_class}, {o.date})"
                               for o in recent],
            "likely_deciding": h.decision_implications[0],
            "affected_functions": _affected_functions(signals),
            "external_trigger": ("independent reporting on the shift"
                                 if independent else
                                 "the company's own recent announcements"),
            "counter_explanation": (h.alternative_explanations or [""])[0],
            "evidence_against": against or ["no strong disconfirming evidence "
                                            "retrieved yet"],
            "likely_decision": h.decision_implications[0],
            "confidence": h.confidence,
            "meeting_relevance": label, "meeting_relevance_why": why,
            "what_would_confirm": h.falsification_questions[0],
        })
        if len(agenda) >= 3:
            break
    return agenda


def _build_source_library(observations, hypotheses) -> dict:
    """Every considered source, grouped by how it was used — for auditability.
    The executive report surfaces only the strongest evidence; this is where
    the rest remains inspectable."""
    role_by_obs = {}
    affected = {}
    for h in hypotheses:
        for oid, role in h.evidence_roles:
            # a stronger role wins if an observation is used by several
            rank = {"direct_support": 3, "contradiction": 2,
                    "indirect_support": 1}.get(role, 0)
            if rank >= role_by_obs.get(oid, (None, -1))[1]:
                role_by_obs[oid] = (role, rank)
            affected.setdefault(oid, []).append(h.hypothesis_id)

    groups = {"used_in_reasoning": [], "corroborating": [], "contradicting": [],
              "contextual": [], "rejected_low_relevance": []}
    for o in observations:
        role = role_by_obs.get(o.observation_id, (None, -1))[0]
        entry = {"title": o.source_title, "publisher": o.origin,
                 "source_class": o.source_class, "date": o.date,
                 "evidence_quality": o.evidence_quality,
                 "affected_hypotheses": affected.get(o.observation_id, []),
                 "role": role or ("weak_or_irrelevant" if o.weak
                                  else "contextual_only")}
        if role == "contradiction":
            groups["contradicting"].append(entry)
        elif role in ("direct_support", "indirect_support"):
            groups["used_in_reasoning"].append(entry)
            if o.source_class in _INDEPENDENT_CLASSES:
                groups["corroborating"].append(entry)
        elif o.weak:
            groups["rejected_low_relevance"].append(entry)
        else:
            groups["contextual"].append(entry)
    return groups


def _rehydrate_model(model_dict):
    """Reconstruct a CompanyMentalModel from a persisted dict for diffing."""
    from intent_engine.strategic_intelligence.model import (
        CompanyMentalModel, ModelComponent,
    )
    comps = {k: ModelComponent(**v)
             for k, v in (model_dict.get("components") or {}).items()}
    return CompanyMentalModel(
        company=model_dict.get("company", ""),
        version=model_dict.get("version", 1),
        created_at=model_dict.get("created_at", ""), components=comps,
        priorities=model_dict.get("priorities", []),
        tensions=model_dict.get("tensions", []))


def _build_feed(changes, agenda, when) -> list:
    """Intelligence feed items from model changes (and new agenda items)."""
    feed = []
    for ch in changes:
        feed.append({
            "date": when, "component": ch["component"],
            "new_evidence": ch["reason"],
            "model_change": (f"{ch['component']}: "
                             f"{ch['previous_view'][:60]} → {ch['new_view'][:60]}"
                             if ch["kind"] == "updated"
                             else f"{ch['component']} {ch['kind']}"),
            "confidence_change": f"{ch['old_confidence']} → {ch['new_confidence']}",
            "importance": "high" if ch["kind"] != "unchanged" else "low"})
    return feed


def _analytics_events(observations, hypotheses, agenda, status,
                      surprises=(), opportunities=(), vulnerabilities=(),
                      changes=()) -> list:
    """Report-attached analytics; the web layer republishes these to the
    persistent strategic-event store (idempotently)."""
    ev = [{"event": "source_selected", "id": o.observation_id,
           "source_class": o.source_class}
          for o in observations if not o.weak]
    ev += [{"event": "evidence_rejected", "id": o.observation_id,
            "reason": "weak_or_irrelevant"} for o in observations if o.weak]
    for h in hypotheses:
        ev.append({"event": "hypothesis_created", "id": h.hypothesis_id,
                   "confidence": h.confidence})
        if h.counter_observation_ids:
            ev.append({"event": "contradiction_detected",
                       "hypothesis": h.hypothesis_id,
                       "count": len(h.counter_observation_ids)})
    ev += [{"event": "likely_agenda_item_detected",
            "item": a["inferred_discussion"]} for a in agenda]
    ev += [{"event": "strategic_surprise_detected", "finding": s["finding"]}
           for s in surprises]
    ev += [{"event": "opportunity_detected", "statement": o["statement"]}
           for o in opportunities]
    ev += [{"event": "vulnerability_detected", "layer": v["exposed_layer"]}
           for v in vulnerabilities]
    ev += [{"event": "confidence_changed", "component": c["component"],
            "to": c["new_confidence"]} for c in changes]
    ev.append({"event": "report_completed", "status": status})
    return ev


def _latest_date(observations):
    dates = [o.date for o in observations if o.date]
    return max(dates) if dates else ""


def build_strategic_report(*, company_name, observations,
                           patterns=None, scaffolds=None,
                           user_accepts_limited_scope=False,
                           previous_model=None, now=None,
                           discovery_coverage=None,
                           retrieval_failures=None,
                           economic_history=None,
                           source_coverage=None) -> StrategicReport:
    """Compose a StrategicReport from structured observations. Status is left
    to the quality gate (:func:`quality.evaluate_report`), which the caller
    should apply; this function sets a provisional status of the gate result."""
    patterns = patterns if patterns is not None else PATTERN_LIBRARY
    scaffolds = scaffolds if scaffolds is not None else HYPOTHESIS_SCAFFOLDS
    for o in observations:
        _require_obs(o)

    coverage = {}
    for o in observations:
        coverage[o.source_class] = coverage.get(o.source_class, 0) + 1
    # WAS A FILING ACTUALLY READ. Not "is there an investor-material source" --
    # `discovery.py` gives that class to any URL containing "investor" or
    # "/ir", so an ordinary investor-relations page claimed the accountability
    # of a 10-K. Measured live: Constellation Software, a TSX-only issuer with
    # no SEC filing in the run, was told its filings carried the reading.
    #
    # THE URL IS ON THE OBSERVATION, NOT IN ITS REFS. `observations.py` builds
    # every production `source_refs` entry as
    # `{subsystem, artifact_type, artifact_id, source_class}` -- there is no
    # url/source_url/final_url key in it, and there never was. Reading refs
    # alone therefore answered "no filing" for EVERY run, so the tier this
    # module exists to grant could not be reached in production: measured live
    # on Datadog (preview c57af3b), whose brief cited "SEC 10-K (2026-02-18)"
    # and whose limitation still read "every source here is published by the
    # company itself". `origin` carries the retrieved `final_url`, which is
    # what `service.py` already tests for sec.gov elsewhere. Refs are still
    # consulted so callers that DO carry a URL there keep working.
    def _filing_urls(o):
        yield str(getattr(o, "origin", "") or "")
        for ref in (o.source_refs or ()):
            if isinstance(ref, dict):
                yield str(ref.get("url") or ref.get("source_url")
                          or ref.get("final_url") or "")

    has_filing = any(EC.is_regulatory_filing(url)
                     for o in observations for url in _filing_urls(o))

    patterns_by_id = {p.pattern_id: p for p in patterns}
    hypotheses = []
    for pattern in patterns:
        scaffold = scaffolds.get(pattern.pattern_id)
        if not scaffold:
            continue
        h = _hypothesis_for(pattern, scaffold, observations, company_name)
        if h is not None:
            hypotheses.append(h)

    # Dominance filter: drop a hypothesis when its own disconfirming signals are
    # the QUALIFYING signals of a strictly higher-confidence hypothesis that
    # also fired — i.e. the same evidence more strongly supports the opposite
    # reading, so surfacing the weaker one would mislead.
    present = _signals_present(observations)
    kept = []
    for h in hypotheses:
        pat = patterns_by_id[h.pattern_id]
        disc_here = {s for s in pat.disconfirming_signals if s in present}
        dominated = any(
            disc_here & set(patterns_by_id[g.pattern_id].qualifying_signals)
            and _CONF_RANK[g.confidence] > _CONF_RANK[h.confidence]
            for g in hypotheses if g is not h)
        if not dominated:
            kept.append(h)
    hypotheses = kept

    hypotheses = select_portfolio(hypotheses)
    hypotheses = _demote_contested(hypotheses, patterns_by_id, present)

    fired_pattern_ids = {h.pattern_id for h in hypotheses}
    used_patterns = [p for p in patterns if p.pattern_id in fired_pattern_ids]

    blind_spots = _build_blind_spots(observations)
    questions = _build_questions(hypotheses, observations)
    shifts = _build_shifts(observations)

    evidence_gaps = []
    for h in hypotheses:
        for g in h.evidence_gaps:
            if g not in evidence_gaps:
                evidence_gaps.append(g)
    # Three tiers, not two. A regulatory filing is management-authored but is
    # made under securities law, so it is not the same evidence as a marketing
    # page -- and treating the two alike is what made a run that HAD retrieved
    # the 10-K report "every source here is published by the company itself"
    # and withhold every option. See `evidence_classes` for the measurement.
    limitation = EC.standing_limitation(coverage, has_filing=has_filing)
    if limitation:
        evidence_gaps.insert(0, limitation)

    # WHAT THIS RUN NEARLY CONCLUDED, AND WHY IT DID NOT.
    #
    # A gated reading that fails is invisible: the founder cannot tell whether
    # the analysis looked and found nothing, or never looked. Where the run
    # holds real supporting evidence and exactly the mechanism is unverified,
    # that is a decision-relevant gap and it is named. One canonical object,
    # built here; the surfaces render it and none of them re-decides what a
    # refusal meant. See `sufficiency.near_misses`.
    from intent_engine.strategic_intelligence import sufficiency as SUF
    misses = SUF.near_misses(company_name, patterns, observations,
                             fired_ids=fired_pattern_ids)
    # INSERTED NEAR THE FRONT, NOT APPENDED. Every surface truncates this list
    # — the founder view takes two, the deck's gaps screen three — and a near
    # miss appended after the scaffold's generic unknowns was measured live at
    # c472e1f as reaching no page at all. It outranks them: a scaffold gap
    # says something is unknowable from outside, while this names one specific
    # missing fact, why it matters, and which source would settle it.
    #
    # Index 1 keeps the standing source-mix limitation first, which is the one
    # thing a reader needs before anything else.
    for miss in reversed(misses):
        if miss["safe_explanation"]:
            evidence_gaps.insert(1 if evidence_gaps else 0,
                                 miss["safe_explanation"])

    # Built AFTER the gaps, not before: the decision has to name what is
    # missing, and the two coverage gaps inserted above are the most important
    # things missing in a typical run. Composing the decision first meant the
    # one field a founder needs to judge it by was the one field it could not
    # see.
    thesis = _build_thesis(company_name, hypotheses, blind_spots,
                           observations=observations,
                           evidence_gaps=evidence_gaps,
                           economic_history=economic_history)

    graph = _build_evidence_graph(company_name, observations, hypotheses,
                                  used_patterns, blind_spots, questions)
    timeline = _build_timeline(observations)
    agenda = _build_agenda(observations, hypotheses)
    source_library = _build_source_library(observations, hypotheses)

    # V1.3: the persistent mental model + executive insights. The report is a
    # VIEW over the model, not a separate artifact.
    from intent_engine.strategic_intelligence import insights as _ins
    from intent_engine.strategic_intelligence.model import (
        build_mental_model, diff_models,
    )
    when = now or _latest_date(observations) or "1970-01-01"
    prev = None
    if previous_model:
        from intent_engine.strategic_intelligence.model import CompanyMentalModel
        prev = _rehydrate_model(previous_model)
    model = build_mental_model(company_name, observations, hypotheses,
                               now=when, previous=prev, blind_spots=blind_spots)
    surprises = [s.as_dict() for s in
                 _ins.detect_surprises(company_name, observations, hypotheses)]
    opportunities = [o.as_dict() for o in
                     _ins.detect_opportunities(company_name, observations,
                                               hypotheses)]
    vulnerabilities = [v.as_dict() for v in
                       _ins.detect_vulnerabilities(company_name, observations,
                                                   hypotheses)]
    underexamined = [q.as_dict() for q in _ins.underexamined_questions(
        company_name, observations, hypotheses, blind_spots)]
    changes = diff_models(prev, model) if prev else []
    feed = _build_feed(changes, agenda, when)

    report = StrategicReport(
        company_name=company_name, status="",
        thesis=thesis, shifts=shifts, hypotheses=hypotheses,
        patterns=used_patterns, blind_spots=blind_spots, questions=questions,
        evidence_gaps=evidence_gaps, near_misses=misses,
        decision_implications=_decision_implications(hypotheses, blind_spots),
        observations=list(observations), source_class_coverage=coverage,
        # Carried, never derived here: this layer reasons over evidence and
        # has no standing to say how hard the search for it worked.
        discovery_coverage=(discovery_coverage
                            if isinstance(discovery_coverage, dict) else {}),
        retrieval_failures=(retrieval_failures
                            if isinstance(retrieval_failures, dict) else {}),
        source_coverage=(source_coverage
                         if isinstance(source_coverage, dict) else {}),
        limited_scope_accepted=user_accepts_limited_scope, evidence_graph=graph,
        timeline=timeline, agenda=agenda, source_library=source_library,
        mental_model=model.as_dict(), surprises=surprises,
        opportunities=opportunities, vulnerabilities=vulnerabilities,
        underexamined_questions=underexamined, what_changed=changes, feed=feed)

    # provisional status via the quality gate (importing here avoids a cycle)
    from intent_engine.strategic_intelligence.quality import evaluate_report
    report.status, report.quality_findings = evaluate_report(report)
    report.analytics_events = _analytics_events(observations, hypotheses,
                                                agenda, report.status,
                                                surprises, opportunities,
                                                vulnerabilities, changes)
    return report


def _require_obs(o):
    if not isinstance(o, StrategicObservation):
        raise TypeError("observations must be StrategicObservation instances")
    o.validate()
