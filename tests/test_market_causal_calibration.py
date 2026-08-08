"""A well-calibrated mechanism is not a proven edge.

The load-bearing test is `test_the_ladder_is_monotone_in_sample_size`. An
earlier draft set the floor at three tests and required three companies for
the strongest status, which made the MINIMUM measurable sample sufficient for
the MAXIMUM claim — and three real Honda/Shopify/Cloudflare confirmations
duly promoted `demand_strengthening` to REPEATEDLY_SUPPORTED on the first
live run. That is the promotion-from-a-tiny-sample this module exists to
refuse, and it was caught by running on the real ledger rather than by any
test written first.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import causal_calibration as CC

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def rows():
    return [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]


def synthetic(family, results, *, industries=None):
    """`results` is [(subject, outcome), ...]."""
    out = []
    for i, (subject, outcome) in enumerate(results):
        out.append({"record": "expectation", "expectation_id": f"e{i}",
                    "hypothesis_id": f"b{i}", "subject": subject,
                    "metric": family})
        out.append({"record": "reconciliation", "expectation_id": f"e{i}",
                    "hypothesis_id": f"b{i}", "subject": subject,
                    "outcome": outcome, "evaluated_at": "2026-08-01"})
    return out


def only(families, key):
    return next(f for f in families if f.causal_family == key)


# --- the ladder ----------------------------------------------------------

def test_never_tested_is_unmeasurable_and_says_so():
    got = only(CC.calibrate([]), "pricing_power")
    assert got.status == CC.UNMEASURABLE
    assert "never tested" in got.reason
    assert got.tests == 0


def test_tested_below_the_floor_is_emerging_not_unmeasurable():
    """Two results is an answer that cannot be told from a coincidence."""
    ledger = synthetic("demand_strengthening",
                       [("a", "CONFIRMED"), ("b", "CONFIRMED")])
    got = only(CC.calibrate(ledger), "demand_strengthening")
    assert got.status == CC.EMERGING
    assert f"floor of {CC.MIN_TESTS}" in got.reason


def test_the_ladder_is_monotone_in_sample_size():
    """No sample can reach a status a larger sample could not."""
    assert CC.MIN_TESTS <= CC.MIN_TESTS_FOR_SUPPORTED
    assert CC.MIN_TESTS_FOR_SUPPORTED < CC.MIN_TESTS_FOR_REPEATED
    assert CC.MIN_COMPANIES_FOR_SUPPORTED < CC.MIN_COMPANIES_FOR_REPEATED

    industries = {c: f"ind_{c}" for c in "abcdefgh"}
    seen = []
    for n in range(1, 9):
        ledger = synthetic("demand_strengthening",
                           [(chr(97 + i), "CONFIRMED") for i in range(n)])
        seen.append(only(CC.calibrate(ledger, industry_of=industries),
                         "demand_strengthening").status)
    rank = {s: i for i, s in enumerate(
        (CC.UNMEASURABLE, CC.EMERGING, CC.SUPPORTED,
         CC.REPEATEDLY_SUPPORTED))}
    assert [rank[s] for s in seen] == sorted(rank[s] for s in seen)


def test_the_minimum_measurable_sample_is_not_the_strongest_status():
    """The exact regression the real ledger caught."""
    industries = {c: f"ind_{c}" for c in "abc"}
    ledger = synthetic("demand_strengthening",
                       [("a", "CONFIRMED"), ("b", "CONFIRMED"),
                        ("c", "CONFIRMED")])
    got = only(CC.calibrate(ledger, industry_of=industries),
               "demand_strengthening")
    assert got.status == CC.EMERGING
    assert got.status != CC.REPEATEDLY_SUPPORTED


def test_one_company_agreeing_with_itself_never_reaches_supported():
    ledger = synthetic("demand_strengthening",
                       [("a", "CONFIRMED")] * 9)
    got = only(CC.calibrate(ledger), "demand_strengthening")
    assert got.status == CC.EMERGING
    assert len(got.company_scope) == 1
    assert "agreeing with itself" in got.reason


def test_any_contradiction_above_the_floor_makes_it_contested():
    ledger = synthetic("demand_strengthening",
                       [("a", "CONFIRMED"), ("b", "CONFIRMED"),
                        ("c", "CONFIRMED"), ("d", "CONFIRMED"),
                        ("e", "CONTRADICTED")])
    got = only(CC.calibrate(ledger), "demand_strengthening")
    assert got.status == CC.CONTESTED
    assert "known exception" in got.reason


def test_one_industry_caps_the_family_at_supported():
    ledger = synthetic("demand_strengthening",
                       [(c, "CONFIRMED") for c in "abcdefgh"])
    industries = {c: "one_sector" for c in "abcdefgh"}
    got = only(CC.calibrate(ledger, industry_of=industries),
               "demand_strengthening")
    assert got.status == CC.SUPPORTED
    assert len(got.industry_scope) == 1


def test_the_strongest_status_needs_scope_and_volume_together():
    ledger = synthetic("demand_strengthening",
                       [(c, "CONFIRMED") for c in "abcdefgh"])
    industries = {c: f"ind_{i % 3}" for i, c in enumerate("abcdefgh")}
    got = only(CC.calibrate(ledger, industry_of=industries),
               "demand_strengthening")
    assert got.status == CC.REPEATEDLY_SUPPORTED


def test_an_uninformative_reconciliation_is_not_a_test():
    """A row that discriminated nothing is not evidence about the edge."""
    ledger = synthetic("demand_strengthening",
                       [("a", "CONFIRMED"), ("b", "UNINFORMATIVE"),
                        ("c", "TOO_EARLY"), ("d", "UNMEASURABLE")])
    got = only(CC.calibrate(ledger), "demand_strengthening")
    assert got.tests == 1
    assert got.company_scope == ("a",)
    assert got.unresolved == 3


# --- what the vocabulary refuses to say ----------------------------------

def test_established_is_not_in_the_vocabulary():
    assert "ESTABLISHED" not in CC.STATUSES
    assert not any(s == "ESTABLISHED" for s in CC.STATUSES)


def test_a_causal_claim_is_never_easier_than_its_own_predictor():
    from intent_engine.market import mechanism_calibration as MC
    assert CC.MIN_TESTS >= MC.MIN_TESTS


# --- the real ledger ------------------------------------------------------

def test_the_real_ledger_reads_two_unmeasurable_and_two_emerging():
    from intent_engine.universe.companies import default_universe
    industries = {c.company_id: getattr(c, "industry", "")
                  or getattr(c, "sector", "")
                  for c in default_universe().prediction_companies()}
    got = CC.summarise(CC.calibrate(rows(), industry_of=industries))
    assert got["by_status"][CC.UNMEASURABLE] == 2
    assert got["by_status"][CC.EMERGING] == 2
    assert got["by_status"][CC.SUPPORTED] == 0
    assert got["by_status"][CC.REPEATEDLY_SUPPORTED] == 0
    assert got["total_tests"] == 5
    assert got["total_contradictions"] == 2


def test_unresolved_expectations_are_reported_separately_from_failures():
    """An open window is not a failed test, and the counts must not merge."""
    from intent_engine.universe.companies import default_universe
    industries = {c.company_id: getattr(c, "sector", "")
                  for c in default_universe().prediction_companies()}
    families = CC.calibrate(rows(), industry_of=industries)
    strengthening = only(families, "demand_strengthening")
    assert strengthening.unresolved > strengthening.tests
    assert strengthening.contradicted == 0
