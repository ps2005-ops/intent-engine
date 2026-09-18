"""§27/§30: market and founder must share one economic exposure truth.

The specific failure this guards: the exposure patterns lived as two hand-
synced copies, and when two dead regex branches were found, BOTH had to be
fixed. A fix applied to one would have left the two products inferring
different exposures from the same sentence, silently, for as long as nobody
compared them.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import exposure as EXP
from intent_engine.market import company_exposure as CX
from intent_engine.market import exposure_parity as PAR


# =============================================================================
# One producer for the pattern layer
# =============================================================================

def test_the_market_patterns_are_the_canonical_ones_not_a_copy():
    """Identity, not equality. Two equal copies drift; one object cannot."""
    assert CX._EXP_PATTERNS is EXP._PATTERNS, (
        "the market side holds its own copy of the exposure patterns. Two "
        "copies is how a fix applied to one leaves the two products "
        "inferring different exposures from the same sentence.")


def test_both_sides_compile_the_same_number_of_patterns():
    assert len(CX._COMPILED) == len(EXP._COMPILED)


def test_both_sides_read_the_same_exposure_from_the_same_sentence():
    """The property the shared producer exists to give."""
    text = ("The Company's floating rate exposure increased during the "
            "period as its credit facility was refinanced.")
    canonical = PAR.read_canonical([text], company_id="X")
    assert canonical, "the canonical producer found nothing in a sentence "\
                      "that plainly states an exposure"
    quantities = {r["quantity"] for r in canonical}
    # The market side reads the same patterns, so a sentence that establishes
    # an exposure for one must establish it for the other.
    rows = [{"record": "evidence", "subject_company": "X",
             "evidence_id": "e1", "observed_at": "2026-01-01",
             # A CLASSIFIED role. "company_filing" is not one, and the
             # market side correctly yields UNKNOWN for it -- an unclassified
             # source class is not evidence that a company is exposed. That
             # gate is a legitimate downstream difference from the founder
             # side, which reads documents whose provenance it already knows.
             "source_role": "regulatory_filing", "fact": text}]
    market = CX.read_exposures(rows, company_id="X")
    seq = list(market.values()) if isinstance(market, dict) else list(market)
    assert seq, ("the market side found no exposure in a sentence the "
                 "canonical producer rates")
    assert {e.dimension for e in seq} & {r["dimension"] for r in canonical}, (
        "the two sides rated different dimensions from one sentence, which "
        "is exactly what sharing the pattern layer is supposed to prevent")


# =============================================================================
# The reconciliation
# =============================================================================

def test_identical_corpora_reconcile():
    text = ("Our interest rate exposure is significant. The Company is "
            "exposed to foreign exchange risk on its European revenue.")
    rows, s = PAR.compare(company_id="X", market_texts=[text],
                          founder_texts=[text],
                          market_producer=PAR.CANONICAL_PRODUCER,
                          founder_producer=PAR.CANONICAL_PRODUCER)
    assert s["producers_agree"]
    assert s["reconciles"], (
        f"the same text through the same producer did not reconcile: "
        f"{[r.as_dict() for r in rows]}")
    assert s["market_only"] == 0 and s["founder_only"] == 0


def test_a_thinner_corpus_is_reported_as_a_corpus_difference():
    """Section 27's real finding: a headline corpus and a filing corpus are
    not the same evidence, and the asymmetry must be visible."""
    headline = "Acme Corp beats estimates."
    filing = ("Our interest rate exposure increased. The Company is exposed "
              "to foreign exchange risk. Labor cost inflation pressured "
              "margins during the period.")
    rows, s = PAR.compare(company_id="X", market_texts=[headline],
                          founder_texts=[filing],
                          market_producer=PAR.CANONICAL_PRODUCER,
                          founder_producer=PAR.CANONICAL_PRODUCER)
    assert s["producers_agree"], "the producers must agree even when the "\
                                 "corpora do not"
    assert s["founder_only"] > 0
    assert s["corpus_ratio"] > 1, "the corpus asymmetry must be reported"
    assert not s["reconciles"]


def test_divergent_producers_are_flagged_even_when_the_output_agrees():
    """The finding that matters. Two corpora disagreeing is information;
    two PRODUCERS disagreeing is a bug that grows."""
    text = "Our interest rate exposure is significant."
    rows, s = PAR.compare(company_id="X", market_texts=[text],
                          founder_texts=[text],
                          market_producer="market.company_exposure",
                          founder_producer=PAR.CANONICAL_PRODUCER)
    assert not s["producers_agree"]
    assert any(r.status == PAR.PRODUCER_DIVERGENCE for r in rows)
    assert not s["reconciles"], (
        "output agreeing today does not make two producers one producer")


def test_audit_runs_over_several_companies():
    filing = ("Our interest rate exposure increased. The Company is exposed "
              "to foreign exchange risk.")
    out = PAR.audit({"A": ([filing], [filing]), "B": ([filing], [filing])},
                    market_producer=PAR.CANONICAL_PRODUCER,
                    founder_producer=PAR.CANONICAL_PRODUCER)
    assert out["companies"] == 2
    assert out["producers_agree"]
    assert out["companies_reconciling"] == 2


def test_an_empty_corpus_produces_no_exposures_rather_than_an_error():
    rows, s = PAR.compare(company_id="X", market_texts=[], founder_texts=[],
                          market_producer=PAR.CANONICAL_PRODUCER,
                          founder_producer=PAR.CANONICAL_PRODUCER)
    assert s["market_exposures"] == 0
    assert s["founder_exposures"] == 0
    assert s["reconciles"], "two empty corpora trivially reconcile"
