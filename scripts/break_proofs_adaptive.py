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
]

if __name__ == "__main__":
    raise SystemExit(run_all(
        PROOFS, title="Break proofs — adaptive strategic intelligence\n"))
