#!/usr/bin/env python3
"""Break proofs for the adaptive strategic intelligence layer.

Every guard below is one this session either built or repaired, and each
mutation is the exact defect that was measured before the repair -- not an
invented one. A proof whose mutation never happened in practice proves that
the code can be broken, which was never in doubt; a proof that replays a real
defect proves the guard would have caught it.

Run through `break_proof_harness`, so a mutation that changes the source and
not the behaviour is reported NOT_CAUGHT rather than counted as held, and no
mutation is ever written to the shared tree.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, ROOT, run_all           # noqa: E402

SRC = ROOT / "src" / "intent_engine"

PROOFS = [
    Proof(
        label="a domain word alone classifies a business model",
        path=SRC / "adaptive" / "classify.py",
        find="    model_weight = sum(w for _p, k, w in hits[top] "
             "if k == \"MODEL\")\n    if model_weight < FLOOR:",
        replace="    model_weight = sum(w for _p, k, w in hits[top])\n"
                "    if model_weight < FLOOR:",
        target="tests/test_adaptive_intelligence.py::"
               "test_subject_matter_alone_never_classifies_a_business_model",
        expect_failure_contains="assert not c.known",
    ),
    Proof(
        label="two unseparated readings are rounded to the higher one",
        path=SRC / "adaptive" / "classify.py",
        find="    if second and second_score >= top_score * MARGIN_SHARE:",
        replace="    if second and second_score >= top_score * 5.0:",
        target="tests/test_adaptive_intelligence.py::"
               "test_two_readings_within_the_margin_are_refused_not_rounded",
        expect_failure_contains="assert not c.known",
    ),
    Proof(
        label="a lens is scored outside the business models it can describe",
        path=SRC / "adaptive" / "lens.py",
        find="        eligible = (not model) or "
             "(model in lens.eligible_business_models)",
        replace="        eligible = True",
        target="tests/test_adaptive_guards.py::"
               "test_the_lens_gate_refuses_by_business_model_before_it_scores",
        expect_failure_contains="assert not entry.eligible",
    ),
    Proof(
        label="naming missing evidence is charged as an absolute penalty",
        path=SRC / "adaptive" / "opportunity.py",
        find="    return round(base * (1.0 - 0.5 * generic) "
             "* (1.0 - 0.15 * gap), 4)",
        replace="    return round(max(0.0, base - (0.25 * uncertainty) "
                "- (0.20 * gap) - (0.35 * generic)), 4)",
        target="tests/test_adaptive_intelligence.py::"
               "test_naming_missing_evidence_does_not_destroy_a_decisions_"
               "priority",
        expect_failure_contains="decision_priority",
    ),
    Proof(
        label="an uncited decision keeps the confidence label it gave itself",
        path=SRC / "adaptive" / "opportunity.py",
        find="    if not citations:\n        evidence = min(evidence, 0.3)",
        replace="    if not citations:\n        evidence = evidence",
        target="tests/test_adaptive_intelligence.py::"
               "test_an_uncited_decision_cannot_outrank_a_cited_one",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a generic causal link ships unflagged",
        path=SRC / "adaptive" / "causal.py",
        find="    if len(macro) >= 2:\n        return True, (",
        replace="    if len(macro) >= 99:\n        return True, (",
        target="tests/test_adaptive_intelligence.py::"
               "test_a_generic_link_is_flagged_rather_than_hidden",
        expect_failure_contains="general economic vocabulary",
    ),
    Proof(
        label="an inflected word breaks the company vocabulary match",
        path=SRC / "adaptive" / "causal.py",
        find="    stems = {w[:5] for w in vocab if len(w) >= 4}\n"
             "    hits = [w for w in words if w[:5] in stems]",
        replace="    stems = set(vocab)\n"
                "    hits = [w for w in words if w in stems]",
        target="tests/test_adaptive_intelligence.py::"
               "test_a_link_built_from_this_companys_own_words_is_not_flagged",
        expect_failure_contains="assert not generic",
    ),
    Proof(
        label="the collapse detector deletes the content it should compare",
        path=SRC / "adaptive" / "differentiation.py",
        find="    body = re.sub(r\"https?://\\S+|\\b[\\w.-]+\\."
             "(?:com|io|ai|net|org)\\b\", \" \",\n"
             "                  body, flags=re.I)",
        replace="    body = re.sub(r\"\\b[A-Z][A-Za-z0-9]{2,}\\b\", \" \", body)\n"
                "    body = re.sub(r\"https?://\\S+|\\b[\\w.-]+\\."
                "(?:com|io|ai|net|org)\\b\", \" \",\n"
                "                  body, flags=re.I)",
        target="tests/test_adaptive_intelligence.py::"
               "test_normalising_removes_the_subject_and_keeps_the_content",
        expect_failure_contains="snowflake",
    ),
    Proof(
        label="the collapse detector can no longer fire",
        path=SRC / "adaptive" / "differentiation.py",
        find="    collapsed = ratio >= COLLAPSE_RATIO or len(shared) >= 3",
        replace="    collapsed = False",
        target="tests/test_adaptive_intelligence.py::"
               "test_the_collapse_detector_catches_an_actual_template",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a role drops a module the composer included",
        path=SRC / "adaptive" / "roles.py",
        find="    rest = [m for m in present if m not in front]",
        replace="    rest = []",
        target="tests/test_adaptive_guards.py::"
               "test_a_role_may_not_drop_a_module_from_the_report",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a composition decision cites no input",
        path=SRC / "adaptive" / "composer.py",
        find="        if reasons:\n            explained += 1",
        replace="        if False:\n            explained += 1",
        target="tests/test_adaptive_intelligence.py::"
               "test_every_inclusion_decision_names_the_input_that_decided_it",
        expect_failure_contains="explained",
    ),
    Proof(
        label="an excluded module vanishes instead of saying why",
        path=SRC / "adaptive" / "composer.py",
        find="                reason=f\"Not shown: {failed[0]}.\", "
             "rank=module.base_rank))",
        replace="                reason=\"\", rank=module.base_rank))",
        target="tests/test_adaptive_intelligence.py::"
               "test_a_module_that_cannot_be_shown_says_why_rather_than_"
               "vanishing",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the epistemic modules can be dropped when an input is missing",
        path=SRC / "adaptive" / "composer.py",
        find="        if failed and not module.always:",
        replace="        if failed:",
        target="tests/test_adaptive_intelligence.py::"
               "test_the_epistemic_modules_are_always_present",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the industry code stops outranking the company's own page",
        path=SRC / "executive" / "company_profile.py",
        # THE GUARD IS AN ORDERING, AND IT IS A PAIR OF CONDITIONS. Mutating
        # either half alone is inert -- one controls whether the evidence
        # read is COMPUTED, the other whether it is USED, and each still
        # refuses when the other is removed. The harness reported both as
        # NOT_CAUGHT, correctly: neither single edit changes an outcome.
        #
        # What the pair protects is the ORDER, so the mutation removes the
        # rung above it. With the industry code discarded, a consultancy's
        # marketing copy classifies a prepackaged-software filer -- which is
        # exactly the defect the ordering exists to prevent.
        find="        derived = classify_sic(sic)",
        replace="        derived = None",
        target="tests/test_adaptive_guards.py::"
               "test_an_industry_code_outranks_the_companys_own_marketing",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the class prior is counted as a company-specific finding",
        path=SRC / "adaptive" / "profile.py",
        find="COMPANY_SPECIFIC = (SUBJECT_EVIDENCE, ANALYST)",
        replace="COMPANY_SPECIFIC = (SUBJECT_EVIDENCE, ANALYST, CLASS_PRIOR)",
        target="tests/test_adaptive_guards.py::"
               "test_a_class_prior_is_never_counted_as_a_company_specific_"
               "finding",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the internal artifact's name returns to customer-facing text",
        path=SRC / "executive" / "company_profile.py",
        find="                    f\"asking. What would settle it is one page "
             "or filing \"\n                    f\"stating where the revenue "
             "comes from.\"),",
        replace="                    f\"asking. Adding this company to the \"\n"
                "                    f\"validation manifest would resolve "
                "it.\"),",
        target="tests/test_universe_alignment.py::"
               "test_no_registrant_at_all_is_sparse_and_says_why",
        expect_failure_contains="manifest",
    ),
    # --- evidence spans: every one replays the live Highspot defect -------
    Proof(
        label="a consultancy's own words are missing from the services "
              "vocabulary",
        path=SRC / "adaptive" / "classify.py",
        find='        Signal("consulting services", "MODEL", 3.0),',
        replace="",
        target="tests/test_adaptive_guards.py::"
               "test_a_consultancy_is_read_as_services_from_its_own_words",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the abstention claims more than it means, over a "
              "recommendation rendered below it",
        path=SRC / "adaptive" / "render.py",
        find="'<p>Which of these is live for this management, or which way '",
        replace="'<p>What this management should actually do. Knowing what '",
        target="tests/test_adaptive_guards.py::"
               "test_an_abstention_does_not_contradict_the_recommendation"
               "_below_it",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a newsletter call to action is quoted as evidence",
        path=(SRC / "strategic_intelligence" / "evidence_text.py"),
        find='    "stay informed", "stay up-to-date", "stay up to date", '
             '"never miss",',
        replace="",
        target="tests/test_adaptive_guards.py::"
               "test_a_newsletter_call_to_action_is_not_evidence",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the strategic read resolves a second business model for the "
              "same run",
        path=SRC / "webapp" / "app.py",
        find="                published_text=self._subject_published_text("
             "run_id))",
        replace="                )",
        target="tests/test_adaptive_guards.py::"
               "test_one_run_resolves_one_business_model_on_every_surface",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the decision composer resolves its own profile instead of "
              "the run's canonical one",
        path=SRC / "executive" / "decision_synthesis.py",
        find="    selection = _select(dossier, hidden, registrant, "
             "profile=profile)",
        replace="    selection = _select(dossier, hidden, registrant)",
        target="tests/test_adaptive_guards.py::"
               "test_one_run_resolves_one_profile_for_every_surface",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the X-Ray stops reading the canonical selection",
        path=SRC / "webapp" / "app.py",
        find="        canonical = self._canonical_selection(\n"
             "            run_id, name, str(meta.get(\"domain\") or \"\"))",
        replace="        canonical = None",
        target="tests/test_adaptive_guards.py::"
               "test_one_run_resolves_one_profile_for_every_surface",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the subject corpus goes back to excerpts only",
        path=SRC / "webapp" / "app.py",
        find='        subject = "\\n".join([t for t in ([filings] + lead + owned) if t])',
        replace='        subject = "\\n".join([t for t in ([filings] + owned) if t])',
        target="tests/test_adaptive_guards.py::"
               "test_the_subject_corpus_leads_with_the_company_own_description",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a company describing itself through its product is not read "
              "as a self-description",
        path=SRC / "adaptive" / "profile.py",
        find='    r"\\b{name}(?:\'s|\\u2019s)\\s+"',
        replace='    r"\\bNEVERMATCHES{name}(?:\'s|\\u2019s)\\s+"',
        target="tests/test_adaptive_guards.py::"
               "test_a_company_describing_itself_through_its_product_is_a_"
               "self_description",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the no-chain state borrows the decision-grade heading",
        path=SRC / "adaptive" / "render.py",
        find='        C.NO_CHAIN: "No supported chain yet",',
        replace="",
        target="tests/test_adaptive_guards.py::"
               "test_the_chain_heading_states_the_epistemic_state",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a bullet fragment is quoted as a sentence",
        path=SRC / "adaptive" / "spans.py",
        find="    if text[0] in _BULLETS:\n        return False",
        replace="    if False:\n        return False",
        target="tests/test_adaptive_guards.py::"
               "test_a_bullet_fragment_is_never_quoted_as_a_sentence",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the same passage is quoted twice at two different lengths",
        path=SRC / "adaptive" / "spans.py",
        find="            if key.startswith(existing_key) or existing_key."
             "startswith(key):",
        replace="            if key == existing_key:",
        target="tests/test_adaptive_guards.py::"
               "test_the_same_passage_is_never_quoted_twice",
        expect_failure_contains="assert",
    ),
    Proof(
        label="long provenance URLs stop wrapping and overflow the page",
        path=SRC / "webapp" / "app.py",
        find="code,.src,.prov{overflow-wrap:anywhere;word-break:break-word}",
        replace="code,.src,.prov{}",
        target="tests/test_adaptive_guards.py::"
               "test_long_provenance_urls_wrap_rather_than_overflow",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the same passage is quoted twice in two different sections",
        path=SRC / "adaptive" / "render.py",
        find='    return _one_quote_per_passage("".join(p for p in parts if p))',
        replace='    return "".join(p for p in parts if p)',
        target="tests/test_adaptive_guards.py::"
               "test_one_quotation_per_passage_on_the_whole_page",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the peer-set absence blames the business model again",
        path=SRC / "founder_brief" / "xray.py",
        find='        known = bool((d.get("company_profile") or {}).get("known"))',
        replace="        known = False",
        target="tests/test_adaptive_guards.py::"
               "test_the_peer_set_absence_does_not_contradict_an_established_"
               "model",
        expect_failure_contains="assert",
    ),
    Proof(
        label="an evidence producer cuts its own span instead of using the "
              "selector",
        path=SRC / "adaptive" / "profile.py",
        find="             evidence=_quote(body, _ai_hit.start(), "
             "_ai_hit.end(),\n                             max_chars=280))",
        replace="             evidence=\" \".join("
                "body[_ai_hit.start()-120:_ai_hit.end()+160].split())[:280])",
        target="tests/test_adaptive_guards.py::"
               "test_every_evidence_producer_quotes_through_the_selector",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a self-description is refused for being slightly too long",
        path=SRC / "adaptive" / "profile.py",
        find="_SELF_MAX = 240",
        replace="_SELF_MAX = 150",
        target="tests/test_adaptive_guards.py::"
               "test_a_self_description_is_not_refused_for_being_slightly_long",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the subject is extracted as its own critical dependency",
        path=SRC / "adaptive" / "profile.py",
        find="        if not _is_the_subject(phrase, company))",
        replace="        )",
        target="tests/test_adaptive_guards.py::"
               "test_a_company_is_never_its_own_critical_dependency",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a quoted passage is cut by arithmetic and begins mid-word",
        path=SRC / "adaptive" / "spans.py",
        find="            chosen = trim_to_word(clean, max_chars)",
        replace="            chosen = _word_snapped(body, start, end, "
                "max_chars)[3:]",
        target="tests/test_adaptive_guards.py::"
               "test_a_quoted_passage_never_begins_or_ends_mid_word",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a quoted passage is truncated by arithmetic and ends mid-word",
        path=SRC / "adaptive" / "spans.py",
        find="            chosen = trim_to_word(clean, max_chars)",
        replace="            chosen = clean[:max_chars]",
        target="tests/test_adaptive_guards.py::"
               "test_a_quoted_passage_never_begins_or_ends_mid_word",
        expect_failure_contains="assert",
    ),
    Proof(
        label="page furniture is quoted in place of a real sentence",
        path=SRC / "adaptive" / "spans.py",
        find="        if len(clean) < 30 or furniture_reason(clean):",
        replace="        if len(clean) < 30:",
        target="tests/test_adaptive_guards.py::"
               "test_page_furniture_never_wins_over_a_substantive_passage",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a span that found only furniture returns a fragment anyway",
        path=SRC / "adaptive" / "spans.py",
        find="    if best is None:\n        return \"\"",
        replace="    if best is None:\n        return _word_snapped("
                "body, start, end, max_chars)",
        target="tests/test_adaptive_guards.py::"
               "test_everything_nearby_being_furniture_returns_nothing",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a quotation is attributed to the wrong document",
        path=SRC / "adaptive" / "corpus.py",
        find="        if source is not None and passage and passage not in "
             "source.text:",
        replace="        if False:",
        target="tests/test_adaptive_guards.py::"
               "test_a_span_may_not_cross_from_one_document_into_another",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a third party's passage is labelled as the company's own",
        path=SRC / "adaptive" / "corpus.py",
        find="            return THIRD_PARTY",
        replace="            return SUBJECT_PUBLISHED",
        target="tests/test_adaptive_guards.py::"
               "test_a_third_party_passage_is_never_labelled_as_the_"
               "companys_own",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a paraphrase is rendered as though it were a quotation",
        path=SRC / "adaptive" / "corpus.py",
        find="            role=role, is_quote=bool(passage))",
        replace="            role=role, is_quote=True)",
        target="tests/test_adaptive_guards.py::"
               "test_a_paraphrase_is_never_dressed_as_a_quotation",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a rival's text stays in the corpus the subject is read from",
        path=SRC / "adaptive" / "corpus.py",
        find="        return Corpus([s for s in self.sources "
             "if s.subject_owned])",
        replace="        return Corpus(list(self.sources))",
        target="tests/test_adaptive_guards.py::"
               "test_the_subject_only_corpus_removes_third_parties_rather_"
               "than_reordering",
        expect_failure_contains="assert",
    ),

    # --- the three reading states ----------------------------------------
    Proof(
        label="a potential domain is promoted to a recommendation",
        path=SRC / "adaptive" / "opportunity.py",
        find="    if kept:\n        return DecisionOpportunityMap(\n"
             "            opportunities=tuple(kept[:3]), "
             "state=DECISION_READING,",
        replace="    if True:\n        return DecisionOpportunityMap(\n"
                "            opportunities=tuple(kept[:3]), "
                "state=DECISION_READING,",
        target="tests/test_adaptive_guards.py::"
               "test_understanding_a_company_is_not_the_same_as_advising_it",
        expect_failure_contains="assert",
    ),
    Proof(
        label="a bounded run shows an empty decision card again",
        path=SRC / "adaptive" / "render.py",
        find="    if m.state == O.POTENTIAL_DOMAINS:",
        replace="    if False:",
        target="tests/test_adaptive_guards.py::"
               "test_a_bounded_run_shows_no_empty_decision_or_chain_card",
        expect_failure_contains="assert",
    ),
    Proof(
        label="an investigation chain is drawn as settled causality",
        path=SRC / "adaptive" / "causal.py",
        find="        return _investigation_chain(company=company, "
             "profile=profile,\n"
             "                                    "
             "lens_selection=lens_selection,\n"
             "                                    opportunity=opportunity)\n"
             "\n    built = []",
        replace="        return CausalChain(kind=NO_CHAIN, "
                "reason=\"none\")\n\n    built = []",
        target="tests/test_adaptive_guards.py::"
               "test_an_investigation_chain_never_implies_settled_causality",
        expect_failure_contains="assert",
    ),
    Proof(
        label="the classification source stops distinguishing its four kinds",
        path=SRC / "adaptive" / "profile.py",
        find="    return _MODEL_SOURCE.get(str(profile_source or \"NONE\"),\n"
             "                             MODEL_SOURCE_NONE)",
        replace="    return MODEL_SOURCE_NONE",
        target="tests/test_adaptive_guards.py::"
               "test_the_classification_names_what_kind_of_source_"
               "established_it",
        expect_failure_contains="assert",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_all(
        PROOFS, title="Break proofs — adaptive strategic intelligence\n"))
