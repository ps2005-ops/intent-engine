"""Event vocabulary — the precision repair and the two measured gaps.

Every sentence in this file is REAL text from a real SEC filing pulled during
the corpus audit, not invented. That matters: the classifier's failures were
not the ones anyone would have guessed, and inventing test sentences would
have reproduced the guess rather than the failure.

What the audit found, over five 10-Q/10-K filings and 2112 candidates:

  - 3.9% of everything ACCEPTED was accounting-standards prose, accepted as
    economically meaningful events. An audit cross-reference classified as
    LAYOFF; a FASB rulemaking as GUIDANCE_REVISION.
  - only 2.6% of everything REJECTED carried a quantified economic fact.

So the funnel's ~92% loss is mostly correct rejection, and the real defect was
precision, not recall. Both directions are pinned here.

After the change, on the same corpus: accounting prose accepted 14 -> 0, and
about 27 genuinely new economic events captured.
"""
import pytest

from intent_engine.market import belief_formation as BF
from intent_engine.market import event_patterns as EP
from intent_engine.market import micro_evidence as ME
from intent_engine.market import observation_binding as OB


# ===========================================================================
# PRECISION — accounting prose is not a commercial event
# ===========================================================================
@pytest.mark.parametrize("sentence", [
    # classified LAYOFF before this fix
    "The December 31, 2025 financial position data included herein is derived "
    "from the audited consolidated financial statements included in the 2025 "
    "Form 10-K.",
    # classified GUIDANCE_REVISION before this fix
    "B. Accounting standards issued but not yet adopted Disaggregation of "
    "income statement expenses (ASU 2024-03) — In November 2024, the "
    "Financial Accounting Standards Board issued guidance.",
    "We are in the process of evaluating the effect of this new guidance on "
    "the related disclosures.",
    "Internal-use software costs (ASU 2025-06) — In September 2025, the FASB "
    "issued accounting guidance to modernize the accounting for "
    "internal-use software.",
    "This guidance is effective January 1, 2028, with early adoption "
    "permitted.",
    "Interim results are not necessarily indicative of results for a full "
    "year.",
    "The financial statements have been prepared in conformity with generally "
    "accepted accounting principles in the United States of America.",
    "Certain amounts for prior periods have been reclassified to conform to "
    "the current period financial statement presentation.",
])
def test_accounting_prose_is_not_an_event(sentence):
    """A rule a standards board wrote is not something the company did.

    The failure mode this prevents is not a wasted row. A LAYOFF that never
    happened routes to `margin_protection` and proposes a belief about cost
    discipline built out of an audit cross-reference — a fabricated economic
    signal carrying a real citation, which is the kind nobody catches.
    """
    assert EP.classify_sentence(sentence) is None


def test_a_real_layoff_still_classifies():
    """The precision fix must not have bought silence."""
    assert EP.classify_sentence(
        "The company said it would cut 1,200 jobs across its manufacturing "
        "operations.") == ME.LAYOFF


def test_a_real_guidance_revision_still_classifies():
    assert EP.classify_sentence(
        "The company raised its full-year revenue guidance to $4.2 billion."
    ) == ME.GUIDANCE_REVISION


# ===========================================================================
# RECALL — committed demand
# ===========================================================================
@pytest.mark.parametrize("sentence", [
    "The dollar amount of unsatisfied performance obligations for contracts "
    "with an original duration greater than one year is $ 44.1 billion.",
    "Contract liabilities were $ 7,280 million, $ 4,678 million and $ 2,745 "
    "million as of June 30, 2026, December 31, 2025 and December 31, 2024, "
    "respectively.",
])
def test_committed_demand_is_now_representable(sentence):
    """Forward demand a filing has already contracted for.

    `INVENTORY_CHANGE` matched the word "backlog", which no filing uses — they
    say "unsatisfied performance obligations". Caterpillar's $44.1bn order
    book and its contract liabilities rising 165% were both discarded.
    """
    assert EP.classify_sentence(sentence) == ME.COMMITTED_DEMAND


def test_committed_demand_is_separate_from_inventory():
    """Opposite economics, so they must not share a type.

    Rising inventory is goods nobody has bought. Rising committed demand is
    revenue customers have signed for. Collapsing them would route the two to
    the same belief family in the same direction.
    """
    assert ME.COMMITTED_DEMAND != ME.INVENTORY_CHANGE
    routes = {(f, d) for e, f, d in BF._ROUTES if e == ME.COMMITTED_DEMAND}
    inventory = {(f, d) for e, f, d in BF._ROUTES
                 if e == ME.INVENTORY_CHANGE}
    assert routes != inventory


def test_committed_demand_lands_in_a_falsifiable_family():
    """It must be testable, not merely proposable.

    Routed in both directions so `observation_binding` will bind it and a
    belief it supports can genuinely come back contradicted.
    """
    families = {f for e, f, d in BF._ROUTES if e == ME.COMMITTED_DEMAND}
    assert families & OB.FALSIFIABLE


def test_an_accounting_policy_statement_is_not_committed_demand():
    """"We recognize X as a contract liability" is a policy, not a change.

    Caught by this file's own first draft, which listed it as a recovery
    case. It names the right concept and reports no movement in it — the same
    class as the accounting prose rejected above, and admitting it would have
    re-imported the precision defect through the recall fix.
    """
    assert EP.classify_sentence(
        "We recognize advanced customer payments as a contract liability in "
        "Customer advances and Other liabilities.") is None


# ===========================================================================
# RECALL — externally imposed cost
# ===========================================================================
@pytest.mark.parametrize("sentence", [
    "During 2025 and until CBP ceased collecting IEEPA tariffs in 2026, the "
    "company's total IEEPA tariff costs were approximately $ 1.0 billion.",
    "For both the three and six months ended June 30, 2026, the company "
    "recorded $ 392 million of expected IEEPA tariff recoveries.",
])
def test_cost_shock_is_now_representable(sentence):
    assert EP.classify_sentence(sentence) == ME.COST_SHOCK


def test_cost_shock_is_occurrence_only_and_stays_unfalsifiable():
    """A tariff that was not disclosed refutes nothing.

    Kept out of the falsifiable set deliberately: binding an occurrence-only
    family builds a channel that can only confirm.
    """
    families = {f for e, f, d in BF._ROUTES if e == ME.COST_SHOCK}
    assert families
    assert not (families & OB.FALSIFIABLE)


def test_a_tariff_is_not_a_company_pricing_decision():
    """Distinct from PRICING_SIGNAL because the strategy differs.

    A company chooses its prices. It does not choose a tariff — it absorbs it,
    passes it through, or relocates, and which one it does is the question
    worth asking.
    """
    assert ME.COST_SHOCK != ME.PRICING_SIGNAL
