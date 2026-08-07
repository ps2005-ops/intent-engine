"""An AI feature is a capability. A workflow changing hands is the transition.

And: a reading this run nearly reached must say so, and say what was missing.

HUMAN_TO_AGENT_WORKFLOW was the highest-frequency ungated reading in the
library — live it fired for Amazon, HubSpot, Shopify and Stripe with the
identical sentence. Reproduced from one line: the bare word "agentic" plus
"marketplace". `when_it_applies` names three clauses and the first is "ships
agent/AI-commerce ENDPOINTS"; nothing measured it.

NEAR MISSES close the gap the previous cycle left open. `sufficiency.classify`
could already tell a retrieval hole from a contradiction, and nothing showed
it to anyone: a founder saw a reading silently absent and could not tell
whether the analysis had looked and found nothing, or never looked.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence import sufficiency as S
from intent_engine.strategic_intelligence.observations import (
    _SIGNAL_KEYWORDS, derive_observations,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import (
    _hypothesis_for, build_strategic_report,
)

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
H2A = PATTERNS["human_to_agent_workflow"]
SCAFFOLD = HYPOTHESIS_SCAFFOLDS["human_to_agent_workflow"]
MECHANISMS = ("agent_executes_actions", "agent_callable_endpoint",
              "human_intervention_reduced")

CTX = "Acme sells commerce software to merchants and their storefronts. "


def _obs(text, company="Acme"):
    return derive_observations([{
        "source_id": "s1", "source_type": "product", "title": company,
        "final_url": "https://acme.example/", "meta_description": "",
        "text_content": text, "retrieval_status": "OK", "freshness": "CURRENT",
        "content_hash": "s1", "retrieved_at": "2026-08-07",
        "parser_version": "p1"}], company=company)


def _fires(text, company="Acme"):
    return _hypothesis_for(H2A, SCAFFOLD, _obs(CTX + text, company), company)


# --- the contract ------------------------------------------------------------

def test_the_gate_is_the_endpoint_clause_the_pattern_already_named():
    assert set(H2A.required_any_signals) == set(MECHANISMS)
    assert "endpoints" in H2A.when_it_applies
    assert "no agent endpoints" in H2A.when_it_does_not_apply


def test_the_stated_counter_case_is_declared():
    """`when_it_does_not_apply` says buying stays human-driven; if a person
    approves every step the workflow has not changed hands."""
    assert "human_in_the_loop" in H2A.disconfirming_signals


# --- marketing vocabulary is not a transition --------------------------------

NEGATIVES = [
    ("bare agentic + marketplace",
     "Our agentic platform helps teams. Browse the marketplace of apps."),
    ("chatbot", "Our chatbot answers shopper questions. Sales channels "
                "include retail."),
    ("copilot drafts", "An AI copilot drafts product descriptions. "
                       "Omnichannel selling."),
    ("ai search", "AI shopping search helps buyers find products across "
                  "sales channels."),
    ("recommendations", "Our recommendation engine suggests products. "
                        "Marketplace listings supported."),
    ("deterministic rules", "Automated workflow templates run on rules you "
                            "configure. Marketplace apps."),
    ("approval every step",
     "Our ai agent drafts orders but requires your approval before anything "
     "is sent. Marketplace."),
    ("analytics", "Predictive analytics forecast demand across sales "
                  "channels and the marketplace."),
    ("competitor's agents",
     "Our competitors ship an agent api and their agents complete purchases. "
     "Marketplace."),
]

POSITIVES = [
    ("agent executes orders",
     "Our ai agent places orders and completes the purchase without human "
     "intervention."),
    ("agent endpoint",
     "We ship an agent api and agentic checkout so ai agents can transact "
     "directly."),
    ("acts on behalf",
     "The assistant acts on your behalf to reconcile invoices end-to-end "
     "autonomously."),
    ("mcp endpoint",
     "Our mcp server is agent-ready, letting agents complete multi-step "
     "buying."),
    ("agents execute workflow",
     "Agents execute the workflow across your tools with no human "
     "intervention."),
]


@pytest.mark.parametrize("label,text", NEGATIVES, ids=[n for n, _ in NEGATIVES])
def test_ai_vocabulary_alone_does_not_move_a_workflow(label, text):
    assert _fires(text) is None, label


@pytest.mark.parametrize("label,text", POSITIVES, ids=[n for n, _ in POSITIVES])
def test_delegated_execution_still_qualifies(label, text):
    """The gate must not be a mute button."""
    assert _fires(text) is not None, label


def test_precision_and_recall_on_shaped_companies():
    """Before this gate, "agentic" + "marketplace" was sufficient."""
    fp = sum(1 for _, t in NEGATIVES if _fires(t) is not None)
    fn = sum(1 for _, t in POSITIVES if _fires(t) is None)
    assert fp == 0, f"{fp} false positive(s)"
    assert fn == 0, f"{fn} genuine agent compan(ies) missed"


def test_the_reading_quotes_the_action_that_earned_it():
    from intent_engine.strategic_intelligence import mechanism as MECH
    fired = _fires("Our ai agent places orders and completes the purchase "
                   "without human intervention.")
    assert MECH.is_explained(fired)
    assert "places orders" in MECH.because_line(fired).lower()


def test_a_supervised_assistant_argues_against_the_reading():
    """Present as counter-evidence, not as a veto: a company can ship both a
    supervised assistant and an autonomous endpoint."""
    fired = _fires("We ship an agent api and agentic checkout so ai agents "
                   "transact directly and complete the purchase. Our copilot "
                   "always keeps a human in the loop for approvals.")
    assert fired is not None, "a real endpoint still qualifies"
    assert fired.counter_observation_ids or fired.confidence in (
        "low", "speculative")


# --- a refusal that speaks ---------------------------------------------------

@pytest.fixture(scope="module")
def near_miss_report():
    text = ("Acme is payments infrastructure and commerce rails. Merchants "
            "use our checkout api and one-click checkout. One platform for "
            "payments and payouts. We own the full stack with first-party "
            "payments.")
    return build_strategic_report(company_name="Acme",
                                  observations=_obs(text))


def test_a_near_miss_is_named_rather_than_silently_absent(near_miss_report):
    ids = {m["pattern_id"] for m in near_miss_report.near_misses}
    assert "product_to_platform" in ids, near_miss_report.near_misses


def test_the_near_miss_says_what_was_verified_and_what_was_not(near_miss_report):
    miss = next(m for m in near_miss_report.near_misses
                if m["pattern_id"] == "product_to_platform")
    assert miss["verified_evidence"], "must say what it DID establish"
    assert "third_party_builds_on" in miss["missing_mechanism"]
    assert miss["source_family_needed"], "must say what would resolve it"


def test_the_founder_sentence_names_a_fact_not_a_pattern(near_miss_report):
    """THE DEFECT THIS CAUGHT ON FIRST RUN.

    The first version said "…establishing that Acme fits product → platform /
    tool → infrastructure" — `pattern.name`, the library's own taxonomy, on
    the page. Every other surface filters exactly that. A founder cannot check
    whether a company "fits product → platform"; they can check whether
    outside businesses depend on it.
    """
    for miss in near_miss_report.near_misses:
        said = miss["safe_explanation"]
        assert said
        assert "→" not in said
        for pattern in PATTERNS.values():
            assert pattern.name.lower() not in said.lower()
            assert pattern.pattern_id not in said


def test_a_retrieval_gap_does_not_read_as_a_contradiction(near_miss_report):
    miss = near_miss_report.near_misses[0]
    said = miss["safe_explanation"]
    assert "not the same as finding it untrue" in said
    assert "argues against" not in said


def test_the_explanation_reaches_a_surface(near_miss_report):
    """Internal sufficiency with no founder-facing output is incomplete —
    `evidence_gaps` is rendered by the deck, the brief and the dossier."""
    assert any("did not verify" in g for g in near_miss_report.evidence_gaps)


def test_it_survives_serialisation(near_miss_report):
    d = near_miss_report.as_dict()
    assert d["near_misses"], "a field that stops here is one no reader sees"
    assert d["near_misses"][0]["safe_explanation"]


def test_not_every_refusal_is_reported():
    """Only decision-relevant near misses. A company with nothing supporting a
    pattern is simply not that kind of company, and listing every rejected
    reading would bury the one that matters."""
    report = build_strategic_report(
        company_name="Acme", observations=_obs("Acme sells a note-taking app."))
    assert len(report.near_misses) <= 2
    for miss in report.near_misses:
        assert len(miss["verified_evidence"]) >= 2


def test_the_near_miss_survives_every_surface_truncation(near_miss_report):
    """MEASURED LIVE AT c472e1f: the text existed, was serialised, and reached
    no page.

    Every surface truncates `evidence_gaps` — the founder view takes two, the
    deck's gaps screen three — and the near miss was appended after the
    scaffold's generic unknowns, so on a real company with several gaps it
    fell off the end. Position is part of being founder-visible.
    """
    gaps = near_miss_report.evidence_gaps
    where = [i for i, g in enumerate(gaps) if "did not verify" in g]
    assert where, "no near miss in the gaps at all"
    assert min(where) <= 2, (
        f"near miss sits at index {min(where)}; surfaces truncate before "
        f"that: {[g[:60] for g in gaps]}")


def test_the_near_miss_reaches_the_rendered_deck(near_miss_report):
    from intent_engine.strategic_intelligence.slides import build_slides
    text = " ".join(b["text"] for s in build_slides(near_miss_report)
                    for b in s["bullets"])
    assert "did not verify" in text
