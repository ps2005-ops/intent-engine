"""The dossier carries what its evidence ids are WORTH, not just how many.

`evidence_trust` had existed since wave 8 with exactly one importer: its own
test. The export shipped `evidence_ids` — a list of ROWS — and the founder
side, having nothing else, could only count them. That is how "three sources
confirm" gets said about one press release.

These pin the seam: the producer normalizes, the number that crosses is the
normalized one, and the production call site actually supplies the rows.
"""
from __future__ import annotations

import inspect

from intent_engine.market import evidence_trust as ET
from intent_engine.market import steps as STEPS
from intent_engine.market import strategic_export as SE
from intent_engine.market import strategic_publish as SEP


class Row:
    def __init__(self, eid, source, role, fact, when="2026-08-01",
                 subject="shopify"):
        self.evidence_id = eid
        self.source = source
        self.source_role = role
        self.fact = fact
        self.observed_at = when
        self.subject = subject
        self.evidence_type = "ANNOUNCEMENT"


class Belief:
    def __init__(self, ids, subject="shopify"):
        self.proposition = "Shopify is moving upmarket"
        self.subject = subject
        self.posterior_probability = 0.586
        self.history = []
        self.last_updated = "2026-08-01"
        self.confidence_basis = "opened by one evidence item"
        self.limitations = []
        self.supporting_evidence_ids = list(ids)
        self.contradicting_evidence_ids = []


#: Three outlets, one announcement, identical figure.
ONE_RELEASE = [
    Row("e1", "techcrunch.com", "news", "Plus tier priced at 2000 per month"),
    Row("e2", "verge.com", "news", "Plus tier priced at 2000 per month"),
    Row("e3", "zdnet.com", "news", "Plus tier priced at 2000 per month"),
]

#: A filing and somebody who read the company separately.
TWO_WITNESSES = [
    Row("f1", "sec.gov", "regulatory_filing", "Revenue grew 21 percent"),
    Row("f2", "analystco.com", "news", "Revenue grew 21 percent"),
]


def _export(rows, ids):
    return SE.build_export(
        company_id="shopify", as_of="2026-08-01", display_name="Shopify",
        beliefs=[Belief(ids)], evidence_rows=rows)


def _trust(rows, ids):
    return _export(rows, ids)["strategic_beliefs"][0]["evidence_trust"]


# --- the count that crosses is the normalized one -------------------------

def test_three_reports_of_one_release_cross_as_one_occurrence():
    trust = _trust(ONE_RELEASE, ["e1", "e2", "e3"])
    assert trust["raw_accounts"] == 3
    assert trust["distinct_events"] == 1
    assert trust["standing"] == ET.DEPENDENT_REREPORTING


def test_the_raw_ids_still_cross_beside_the_normalized_count():
    """Normalization must not DELETE provenance. The founder side has to be
    able to walk back to the rows; it just may not count them."""
    belief = _export(ONE_RELEASE, ["e1", "e2", "e3"])["strategic_beliefs"][0]
    assert belief["evidence_ids"] == ["e1", "e2", "e3"]
    assert belief["evidence_trust"]["distinct_events"] == 1


def test_dependent_rereporting_does_not_outweigh_a_single_report():
    """The whole point, in one assertion."""
    three = _trust(ONE_RELEASE, ["e1", "e2", "e3"])
    one = _trust(ONE_RELEASE[:1], ["e1"])
    assert three["weight"] == one["weight"] == 1.0


def test_independent_corroboration_is_not_flattened_to_one_report():
    """The fix must discriminate, not merely deflate everything."""
    dependent = _trust(ONE_RELEASE, ["e1", "e2", "e3"])
    independent = _trust(TWO_WITNESSES, ["f1", "f2"])
    assert independent["standing"] == ET.INDEPENDENTLY_CORROBORATED
    assert independent["weight"] > dependent["weight"]


def test_a_claim_inherits_the_weakest_standing_beneath_it():
    """Averaging would let a filing launder a rumour the claim also needs."""
    trust = _trust(ONE_RELEASE + TWO_WITNESSES,
                   ["e1", "e2", "e3", "f1", "f2"])
    assert trust["distinct_events"] == 2
    assert trust["standing"] == ET.DEPENDENT_REREPORTING


def test_the_sentence_is_derived_from_the_standing():
    """Prose and weight come from one place, so they cannot disagree."""
    trust = _trust(ONE_RELEASE, ["e1", "e2", "e3"])
    assert trust["sentence"]
    assert "independent confirmation" in trust["sentence"]


# --- absence is a distinct state from "one observation" -------------------

def test_no_rows_supplied_means_no_trust_block_rather_than_a_zero():
    """A consumer must tell 'we normalized this' from 'nobody looked'."""
    belief = SE.build_export(
        company_id="shopify", as_of="2026-08-01", display_name="Shopify",
        beliefs=[Belief(["e1"])])["strategic_beliefs"][0]
    assert "evidence_trust" not in belief


def test_the_dossier_states_its_own_standing_too():
    payload = _export(ONE_RELEASE, ["e1", "e2", "e3"])
    assert payload["evidence_trust"]["distinct_events"] == 1


# --- the allowlist still governs ------------------------------------------

def test_the_trust_block_survives_the_outbound_allowlist():
    """It crosses because it is declared, not because nothing checked."""
    payload = _export(ONE_RELEASE, ["e1", "e2", "e3"])
    SE.assert_sanitized(payload)


def test_an_undeclared_field_inside_the_trust_block_is_still_refused():
    payload = _export(ONE_RELEASE, ["e1", "e2", "e3"])
    payload["strategic_beliefs"][0]["evidence_trust"]["sharpe"] = 1.4
    try:
        SE.assert_sanitized(payload)
    except SE.ExportLeak:
        return
    raise AssertionError("the allowlist did not walk into the trust block")


# --- the call site, which is where the last six of these died -------------

def test_publish_forwards_evidence_rows_to_the_export():
    assert "evidence_rows" in inspect.signature(SEP.publish).parameters


def test_the_production_cycle_supplies_the_rows():
    """A parameter nobody passes is a module with no callers wearing a
    signature. Grepping the call site is the assertion that would have caught
    every previous instance of this."""
    source = inspect.getsource(STEPS.learning_step)
    assert "evidence_rows=store.evidence()" in source
