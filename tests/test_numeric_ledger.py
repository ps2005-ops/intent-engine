"""Numeric grounding: the ledger, and the gate that runs before the critic.

Measured origin: on five live companies the critic rejected 16 figures and 15
of them appeared in NO retrieved document. The model recalled them.
"""
import pytest

from intent_engine.strategic_intelligence import numeric_ledger as NL
from intent_engine.strategic_intelligence.contract_numeric import (
    validate_numeric_claims,
)


class _Obs:
    def __init__(self, oid, text, title="Filing"):
        self.observation_id, self.text, self.excerpt = oid, text, ""
        self.source_title = title


def facts(text, oid="ev-1"):
    return NL.extract(text, evidence_id=oid, source_title="10-Q")


# --- normalisation ----------------------------------------------------------
def test_currency_scale_and_separators_normalise():
    f = facts("Total revenue was $2.13 billion for FY2025.")[0]
    assert f.value == pytest.approx(2.13e9)
    assert f.currency == "USD" and f.unit == "currency"
    assert f.metric == "revenue" and f.period == "FY2025"


def test_parentheses_mean_negative():
    f = facts("Net income (loss) of $(1,250) thousand")[0]
    assert f.value < 0


def test_percentages_are_not_currency():
    f = facts("Operating margin was 18.4% in Q2 2026.")[0]
    assert f.unit == "percent" and f.currency is None
    assert f.value == pytest.approx(18.4)
    assert f.period == "Q2 2026"


def test_thousands_separator_without_scale_word():
    f = facts("Revenue of $1,006,426 for the period")[0]
    assert f.value == pytest.approx(1006426)


def test_revenue_and_arr_are_not_the_same_metric():
    got = {f.metric for f in facts(
        "Annual recurring revenue reached $500 million. "
        "Total revenue was $610 million.")}
    assert "arr" in got and "revenue" in got


def test_non_gaap_is_recorded_as_a_different_basis():
    f = facts("Non-GAAP operating income was $42 million")[0]
    assert f.basis == "non_gaap"


def test_guidance_and_estimates_are_not_reported_actuals():
    assert facts("We expect revenue of $700 million")[0].kind == "guidance"
    assert facts("Analyst consensus estimates $712 million")[0].kind == \
        "estimate"
    assert facts("Revenue was $690 million")[0].kind == "reported"


def test_quarterly_and_annual_periods_are_distinguished():
    assert facts("Revenue for Q3 2025 was $12 million")[0].period == "Q3 2025"
    assert facts("Revenue for fiscal 2025 was $50 million")[0].period == "FY2025"


def test_an_unlabelled_number_is_never_given_a_metric():
    f = facts("The building houses 4,500 people")[0]
    assert f.metric == "unlabelled"
    assert f.confidence in ("low", "medium")


def test_uncertain_extraction_stays_uncertain():
    """Metric and period both visible is the only 'high' case."""
    assert facts("Total revenue was $2.13 billion for FY2025.")[0].confidence \
        == "high"
    assert facts("It grew to 4,500 last year")[0].confidence == "low"


def test_duplicate_facts_are_resolved():
    got = facts("Revenue was $5 million. Revenue was $5 million.")
    assert len([f for f in got if f.metric == "revenue"]) == 1


def test_every_fact_carries_lineage_back_to_its_evidence():
    f = facts("Revenue was $5 million for FY2024", oid="ev-77")[0]
    assert f.evidence_id == "ev-77" and f.fact_id.startswith("nf-ev-77")
    assert f.excerpt


def test_build_ledger_spans_every_observation():
    led = NL.build_ledger([_Obs("ev-1", "Revenue was $5 million for FY2024"),
                           _Obs("ev-2", "Net income was $1 million for FY2024")])
    assert {f.evidence_id for f in led} == {"ev-1", "ev-2"}


# --- the gate ---------------------------------------------------------------
def test_an_unsupported_number_is_refused_before_the_critic():
    led = NL.build_ledger([_Obs("ev-1", "Revenue was $5 million for FY2024")])
    bad = {"the_insight": {"headline": "Revenue reached $797,198 thousand."}}
    findings = validate_numeric_claims(bad, led)
    assert findings and findings[0].rejects
    assert "797,198" in findings[0].message


def test_a_supported_number_passes():
    led = NL.build_ledger([_Obs("ev-1", "Revenue was $5 million for FY2024")])
    ok = {"the_insight": {"headline": "Revenue was $5 million."}}
    assert validate_numeric_claims(ok, led) == []


def test_a_remembered_famous_company_figure_is_refused():
    """Adversarial: figures the model plausibly knows, absent from the pack.

    These are the exact shapes rejected on the live Datadog and Adobe runs.
    """
    led = NL.build_ledger([_Obs("ev-1", "The platform serves many customers.")])
    for remembered in ("$797,198", "1,561,550", "$6,416", "6,248,585"):
        found = validate_numeric_claims(
            {"business_model": {"note": f"Revenue of {remembered}."}}, led)
        assert found, remembered


def test_years_and_small_counts_are_not_treated_as_claims():
    led = NL.build_ledger([_Obs("ev-1", "No figures here.")])
    benign = {"a": "In 2024 the company named 3 priorities across 2 segments."}
    assert validate_numeric_claims(benign, led) == []


def test_an_empty_ledger_supports_no_numeric_claim_at_all():
    findings = validate_numeric_claims(
        {"x": "Margins improved to 42%."}, [])
    assert findings and findings[0].rejects


def test_the_pack_says_plainly_when_no_figure_is_available():
    text = NL.render_for_pack([])
    assert "NUMERIC_FACTS (0)" in text
    assert "NO numeric claim can be supported" in text


def test_the_pack_labels_period_and_basis_for_every_fact():
    led = NL.build_ledger([_Obs("ev-1", "Total revenue was $2.13 billion "
                                        "for FY2025.")])
    text = NL.render_for_pack(led)
    assert "metric=revenue" in text and "period=FY2025" in text
    assert "fact_id" in text or "[nf-" in text


# --- false positives found on live runs -------------------------------------
def test_a_grouped_number_is_one_token_not_three():
    """LIVE FALSE POSITIVE: "$1,058,226" was reported as the unsupported
    figures '058' and '226' -- claims the analysis never made."""
    from intent_engine.strategic_intelligence.contract_numeric import (
        _candidate_numbers,
    )
    tokens = [raw for raw, _bare, _v in
              _candidate_numbers("Revenue was $1,058,226.")]
    assert tokens == ["$1,058,226"], tokens      # one token, never fragments

    led = NL.build_ledger([_Obs("ev-1", "Revenue was $1,058,226 for FY2025")])
    assert validate_numeric_claims({"x": "Revenue was $1,058,226."}, led) == []

    # and with no ledger it is refused ONCE, as the whole figure
    found = validate_numeric_claims({"x": "Revenue was $1,058,226."}, [])
    assert len(found) == 1 and "$1,058,226" in found[0].message


def test_an_observation_id_is_not_a_numeric_claim():
    """LIVE FALSE POSITIVE: 'obs-src-20260714' produced the figure
    '20260714,'."""
    led = NL.build_ledger([_Obs("ev-1", "No figures here.")])
    cited = {"scope_note": "Per obs-src-20260714 and obs-src-4613 the scope "
                           "covers one entity."}
    assert validate_numeric_claims(cited, led) == []


def test_the_written_and_normalised_forms_both_count_as_supported():
    """"$2.13 billion" in the ledger must support "$2.13 billion" in the
    analysis, and 2130000000 must not be required to match textually."""
    led = NL.build_ledger([_Obs("ev-1", "Total revenue was $2.13 billion "
                                        "for FY2025.")])
    assert validate_numeric_claims({"x": "revenue of $2.13 billion"}, led) == []


def test_the_gate_still_refuses_a_genuinely_absent_figure():
    """The false-positive fix must not blunt the gate."""
    led = NL.build_ledger([_Obs("ev-1", "Total revenue was $2.13 billion "
                                        "for FY2025.")])
    found = validate_numeric_claims({"x": "operating margin of 41.6%"}, led)
    assert found and found[0].rejects
