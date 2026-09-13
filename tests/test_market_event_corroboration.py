"""Several accounts of one event are not several tests of a belief.

Wave 7 counted 5 events with independent accounts by counting distinct
source ROLES. Two rows can carry different roles and still be one wire
story, so that number was an upper bound presented as a count.
"""
from __future__ import annotations

import types

import pytest

from intent_engine.market import event_corroboration as EC
from intent_engine.market import event_identity as EI
from intent_engine.market import normalized_learning_health as NH


def row(fact, source, role, self_authored=False, evidence_id="e1",
        subject="shopify", evidence_type="EARNINGS_RESULT"):
    return types.SimpleNamespace(
        evidence_id=evidence_id, fact=fact, source=source, source_role=role,
        self_authored=self_authored, subject_company=subject,
        evidence_type=evidence_type, observed_at="2026-08-01",
        available_at="2026-08-01")


# --- the distinction that must never collapse -----------------------------

def test_corroboration_never_resolves_an_expectation():
    """The permanent one. Three rewrites of a release are not three
    confirmations of the belief that release opened."""
    entry = EC.assess(types.SimpleNamespace(event_id="ev1", subject="s"),
                      [row("Revenue rose 36% - Reuters", "u1",
                           "independent_reporting"),
                       row("Revenue rose 36% - CNBC", "u2",
                           "analyst_coverage")])
    resolved, why = EC.resolves_expectation(entry)
    assert resolved is False
    assert "LATER" in why


def test_the_corroboration_record_carries_no_outcome_field():
    """Structural: there is no field a reconciliation could read as one."""
    fields = set(EC.EventCorroboration.__dataclass_fields__)
    for forbidden in ("outcome", "informative", "confirmed", "contradicted",
                      "resolution", "expectation_id"):
        assert forbidden not in fields


# --- wire syndication is not independence ---------------------------------

def test_the_same_publisher_twice_is_one_account():
    kind, why = EC.classify(
        row("Shopify revenue rose 36% - Yahoo Finance", "u1",
            "independent_reporting"),
        row("Shopify beats estimates again - Yahoo Finance", "u2",
            "analyst_coverage"))
    assert kind == EC.SAME_ORIGIN
    assert "yahoo finance" in why


def test_two_aggregators_are_partially_independent_not_independent():
    kind, _why = EC.classify(
        row("Shopify revenue rose 36% - MarketBeat", "u1",
            "independent_reporting"),
        row("Shopify revenue rose 36% - TradingView", "u2",
            "independent_reporting"))
    assert kind == EC.PARTIALLY_INDEPENDENT


def test_a_filing_and_a_reporter_are_independent():
    kind, _why = EC.classify(
        row("Shopify reported revenue of $2.1B", "sec.gov/x",
            "regulatory_filing", self_authored=True),
        row("Shopify tops estimates on cloud strength - Reuters", "u2",
            "independent_reporting"))
    assert kind == EC.INDEPENDENT


def test_a_rewrite_of_the_companys_own_release_is_derived():
    text = ("Shopify announced record quarterly revenue of 2100 million "
            "dollars driven by merchant solutions growth")
    kind, why = EC.classify(
        row(text, "shopify.com/news", "company_owned", self_authored=True),
        row(text + " - Stock Titan", "u2", "independent_reporting"))
    assert kind == EC.DERIVED
    assert "second witness" in why


def test_syndication_does_not_raise_the_effective_account_count():
    """Six copies of one story stay one account."""
    rows = [row(f"Shopify revenue rose 36% - Yahoo Finance", f"u{i}",
                "independent_reporting") for i in range(6)]
    entry = EC.assess(types.SimpleNamespace(event_id="ev1", subject="s"),
                      rows)
    assert entry.accounts == 6
    assert entry.effective_accounts == pytest.approx(1.0)
    assert entry.standing == EC.DEPENDENT_ACCOUNTS


def test_genuinely_separate_witnesses_do_raise_it():
    entry = EC.assess(
        types.SimpleNamespace(event_id="ev1", subject="s"),
        [row("Shopify reported revenue of $2.1B", "sec.gov/x",
             "regulatory_filing", self_authored=True),
         row("Shopify tops estimates - Reuters", "u2",
             "independent_reporting")])
    assert entry.effective_accounts == pytest.approx(2.0)
    assert entry.standing == EC.CORROBORATED
    assert entry.source_diversity == "INDEPENDENT_ROLES"


def test_a_single_account_is_not_corroboration():
    entry = EC.assess(types.SimpleNamespace(event_id="ev1", subject="s"),
                      [row("Shopify revenue rose - Reuters", "u1",
                           "independent_reporting")])
    assert entry.standing == EC.SINGLE_ACCOUNT
    assert entry.effective_accounts == pytest.approx(1.0)


# --- the publisher is not the host ----------------------------------------

def test_the_publisher_is_read_from_the_attribution_not_the_aggregator():
    """135 of 249 live rows carry news.google.com as their host. Scoring
    independence on the host makes all of them one outlet."""
    entry = row("Shopify beats estimates - Reuters",
                "https://news.google.com/rss/articles/CBMi", "x")
    assert EC.publisher_of(entry) == "reuters"


def test_a_trailing_clause_is_not_an_attribution():
    """The live corpus contains headlines whose last dash introduces prose,
    not a publisher: "powering their evolution into a house of"."""
    entry = row("Brand X is powering their evolution into a house of",
                "https://example.test/a", "x")
    assert EC.publisher_of(entry) == "example.test"


# --- normalized health ----------------------------------------------------

def test_health_reports_raw_and_normalized_side_by_side():
    evidence = [row("Shopify revenue rose 36% - Reuters", "u1",
                    "independent_reporting", evidence_id="e1"),
                row("Shopify revenue rose 36% - CNBC", "u2",
                    "analyst_coverage", evidence_id="e2")]
    got = NH.report(evidence=evidence)
    assert got["raw_evidence_rows"] == 2
    assert got["normalized_events"] == 1
    assert got["redundancy"] == pytest.approx(0.5)
    metrics = {p["metric"] for p in got["pairs"]}
    assert "evidence_identity" in metrics
    assert "self_test_contamination" in metrics


def test_a_reconciliation_on_the_opening_event_is_counted_as_a_self_test():
    evidence = [row("Shopify revenue rose 36% - Reuters", "u1",
                    "independent_reporting", evidence_id="e1"),
                row("Shopify revenue rose 36% - CNBC", "u2",
                    "analyst_coverage", evidence_id="e2")]
    expectations = [{"expectation_id": "x1", "evidence_basis": ["e1"]}]
    reconciliations = [{"expectation_id": "x1", "informative": True,
                        "outcome": "CONFIRMED", "evidence_ids": ["e2"]}]
    got = NH.report(evidence=evidence, expectations=expectations,
                    reconciliations=reconciliations)
    # e1 and e2 are the SAME event, so this "test" restates its own opener.
    assert got["self_tests_on_the_opening_event"] == 1
    assert got["informative_reconciliations"] == 1


def test_a_reconciliation_on_a_later_event_is_not_a_self_test():
    evidence = [row("Shopify revenue rose 36% - Reuters", "u1",
                    "independent_reporting", evidence_id="e1"),
                row("Shopify guided revenue down 4% - Reuters", "u2",
                    "independent_reporting", evidence_id="e2",
                    evidence_type="GUIDANCE_REVISION")]
    expectations = [{"expectation_id": "x1", "evidence_basis": ["e1"]}]
    reconciliations = [{"expectation_id": "x1", "informative": True,
                        "outcome": "CONTRADICTED", "evidence_ids": ["e2"]}]
    got = NH.report(evidence=evidence, expectations=expectations,
                    reconciliations=reconciliations)
    assert got["self_tests_on_the_opening_event"] == 0


def test_the_index_may_be_supplied_rather_than_recomputed():
    evidence = [row("Shopify revenue rose 36% - Reuters", "u1",
                    "independent_reporting", evidence_id="e1")]
    events = EI.group(evidence)
    index = EI.index(events)
    got = NH.report(evidence=evidence, event_index=index)
    assert got["normalized_events"] == 1


# --- health changes the research mix (§23) --------------------------------

def test_a_syndicated_corpus_asks_originating_sources_first():
    """Measured live: 133 of 148 paired accounts are SAME_ORIGIN. A corpus
    that redundant does not need more accounts, it needs another KIND."""
    from intent_engine.market import research_planning as RP

    live = {"SAME_ORIGIN": 133, "PARTIALLY_INDEPENDENT": 9, "INDEPENDENT": 6}
    before = RP.plan(RP.NEEDS_FRESH_OBSERVATION)
    after = RP.plan(RP.NEEDS_FRESH_OBSERVATION, dependency_classes=live)

    assert before.families != after.families
    assert after.families.index("customer_case_study") < \
        after.families.index("comparison_page")
    assert "SAME_ORIGIN" in after.health_adjustment


def test_the_dependency_adjustment_never_suppresses_baseline_coverage():
    """Reordering is the intervention. Dropping a family would make the
    engine unable to discover that the family recovered."""
    from intent_engine.market import research_planning as RP

    live = {"SAME_ORIGIN": 133, "INDEPENDENT": 6}
    before = RP.plan(RP.NEEDS_FRESH_OBSERVATION)
    after = RP.plan(RP.NEEDS_FRESH_OBSERVATION, dependency_classes=live)
    assert set(before.families) == set(after.families)


def test_a_balanced_corpus_leaves_the_plan_alone():
    from intent_engine.market import research_planning as RP

    balanced = {"SAME_ORIGIN": 5, "INDEPENDENT": 40}
    before = RP.plan(RP.NEEDS_FRESH_OBSERVATION)
    after = RP.plan(RP.NEEDS_FRESH_OBSERVATION, dependency_classes=balanced)
    assert before.families == after.families
    assert after.health_adjustment == ""


def test_corroboration_reads_a_mapping_row_the_same_as_an_object():
    """The sibling of the event_identity fix, and the reason it matters here.

    These two modules consume the SAME rows. If grouping reads mappings and
    corroboration does not, a dict-fed ledger groups correctly and then
    reports every event as a single account with no publisher — a
    corroboration pass that finds nothing wrong because it read nothing.
    """
    class Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    fields = [
        dict(evidence_id="ev_1", subject_company="cloudflare",
             evidence_type="EARNINGS_RESULT", fact="revenue rises 36%",
             observed_at="2026-08-01", source="https://reuters.com/a",
             source_role="news_report"),
        dict(evidence_id="ev_2", subject_company="cloudflare",
             evidence_type="EARNINGS_RESULT",
             fact="revenue rises 36%, filing shows",
             observed_at="2026-08-02", source="https://sec.gov/b",
             source_role="regulatory_filing"),
    ]
    event = EI.group(fields)[0]
    as_dicts = EC.assess(event, fields)
    as_objects = EC.assess(EI.group([Row(**f) for f in fields])[0],
                            [Row(**f) for f in fields])
    assert as_dicts.standing == as_objects.standing
    assert as_dicts.accounts == as_objects.accounts == 2
    assert as_dicts.effective_accounts == as_objects.effective_accounts
    assert as_dicts.publishers == as_objects.publishers
    # And it actually READ them: an empty read would report no publishers.
    assert as_dicts.publishers and all(as_dicts.publishers)
