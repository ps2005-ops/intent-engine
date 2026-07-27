"""Versioned golden quality baselines.

The golden tests prove a report is useful TODAY. These prove it has not
regressed BELOW a recorded bar — and that the bar itself cannot drift silently:
the baseline file is data under review, and nothing here rewrites it.
"""
import json
import pathlib

import pytest

from test_golden_demo_companies import GOLDEN, _run
from intent_engine.company_ingestion.quality import (
    QUALITY_RULES_VERSION, assess,
)

BASELINE_PATH = pathlib.Path(__file__).with_name("golden_baselines.json")
BASELINES = json.loads(BASELINE_PATH.read_text())


def _measure(company, tmp_path):
    ci, run_id, result = _run(company, tmp_path)
    documents = ci.store.retrieved(run_id)
    quality = result.get("quality") or assess(result, documents)
    metrics = quality["metrics"]
    return {
        "successful_sources": metrics["successful_sources"],
        "source_families": metrics["source_families"],
        "product": metrics["has_product_evidence"],
        "customer": metrics["has_customer_evidence"],
        "strategy": metrics["has_strategy_evidence"],
        "populated_share": metrics["populated_share"],
        "placeholder_share": metrics["placeholder_share"],
        "legal_contamination": len(metrics["legal_as_insight"]),
        "opaque_ids": 1 if metrics["opaque_ids"] else 0,
        "internal_leaks": len(metrics["internal_leak"]),
        "outcome": quality["outcome"],
    }


def test_baseline_file_is_versioned_and_matches_the_rules_version():
    assert BASELINES["baseline_version"] >= 1
    assert BASELINES["rules_version"] == QUALITY_RULES_VERSION, (
        "the quality rules changed; baselines must be reviewed and the "
        "rules_version updated deliberately")
    assert set(BASELINES["companies"]) == {c.domain for c in GOLDEN}


@pytest.mark.parametrize("company", GOLDEN, ids=lambda c: c.domain)
def test_golden_company_meets_its_versioned_baseline(company, tmp_path):
    baseline = BASELINES["companies"][company.domain]
    actual = _measure(company, tmp_path)

    assert actual["successful_sources"] >= baseline["min_successful_sources"], \
        f"{company.name}: sources {actual['successful_sources']} < baseline"
    assert actual["source_families"] >= baseline["min_source_families"], \
        f"{company.name}: families {actual['source_families']} < baseline"
    if baseline["requires_product_evidence"]:
        assert actual["product"], f"{company.name}: lost product evidence"
    if baseline["requires_customer_evidence"]:
        assert actual["customer"], f"{company.name}: lost customer evidence"
    if baseline["requires_strategy_evidence"]:
        assert actual["strategy"], f"{company.name}: lost strategy evidence"
    assert actual["populated_share"] >= baseline["min_populated_share"], \
        f"{company.name}: populated {actual['populated_share']} < baseline"
    assert actual["placeholder_share"] <= baseline["max_placeholder_share"]
    assert actual["legal_contamination"] <= baseline["max_legal_contamination"]
    assert actual["opaque_ids"] <= baseline["max_opaque_ids"]
    assert actual["internal_leaks"] <= baseline["max_internal_leaks"]
    assert actual["outcome"] in baseline["allowed_outcomes"], \
        f"{company.name}: outcome {actual['outcome']} not allowed by baseline"


def test_a_degraded_report_fails_its_baseline():
    """The baseline must actually be able to FAIL — a check that can only pass
    protects nothing."""
    baseline = BASELINES["companies"]["palantir.com"]
    degraded = {
        "successful_sources": 1, "source_families": 1, "product": False,
        "customer": False, "strategy": False, "populated_share": 0.1,
        "placeholder_share": 0.9, "legal_contamination": 3, "opaque_ids": 1,
        "internal_leaks": 2, "outcome": "REPORT_QUALITY_FAIL",
    }
    violations = []
    if degraded["successful_sources"] < baseline["min_successful_sources"]:
        violations.append("sources")
    if degraded["source_families"] < baseline["min_source_families"]:
        violations.append("families")
    if baseline["requires_product_evidence"] and not degraded["product"]:
        violations.append("product")
    if degraded["legal_contamination"] > baseline["max_legal_contamination"]:
        violations.append("legal")
    if degraded["outcome"] not in baseline["allowed_outcomes"]:
        violations.append("outcome")
    assert len(violations) >= 5, violations


def test_baselines_are_not_rewritten_by_running_the_golden_suite(tmp_path):
    """No test may rewrite the baseline file: a regression must surface, not
    be absorbed. Behavioural check — measure a golden company, then prove the
    baseline file is byte-identical."""
    import hashlib
    before = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    _measure(GOLDEN[0], tmp_path)
    after = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    assert before == after, "the suite must never rewrite golden baselines"
