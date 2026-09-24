#!/usr/bin/env python3
"""Break proofs for D-MDR-001.

    PYTHONPATH=src python3 scripts/break_proofs_minimum_data_request.py

Twelve mutations, each aimed at a guard the node's claim depends on. Every one
runs the hardened harness's five conditions -- source changed, green before,
red after, red FOR THE STATED REASON, restored to the exact bytes -- so a proof
cannot pass on a no-op, an unreachable branch, or a collection error.

The two that matter most, and why:

    MINIMISATION WALKS THE DEMAND SIDE
        `select_minimum` iterates unresolved parameters. Flip it to iterate
        candidates and the ten irrelevant private fields walk straight into the
        request. This is the mutation the v1 implementation could not fail,
        because its output was a constant.

    THE PERMITTED-USE CLAUSE IS A CONSTANT
        Restore the interpolation and an injected sentence reappears inside the
        terms a founder reads as ours. That defect was found by the adversarial
        test in this batch, not by review.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import ROOT, Proof, run_all  # noqa: E402

MDR = ROOT / "src" / "intent_engine" / "external_intel" / "minimum_data_request.py"
II = ROOT / "src" / "intent_engine" / "external_intel" / "internal_impact.py"
VIEW = ROOT / "src" / "intent_engine" / "webapp" / "internal_view.py"

ENGINE = "tests/test_minimum_data_request.py"
SEAM = "tests/test_webapp_minimum_data_request.py"

PROOFS = [
    # -- 1. a bare string bypasses the typed record -------------------------
    Proof(
        label="a flat string field cannot enter a request",
        path=MDR,
        find="""            if not isinstance(got, RequestedField):""",
        replace="""            if False:""",
        target=f"{ENGINE}::test_a_bare_string_can_no_longer_be_constructed_into_a_request",
        # Not "DID NOT RAISE": without this guard the bare string reaches
        # `got.voi_band` and dies as an AttributeError. The guard's job is
        # turning that crash into an auditable refusal, and the AttributeError
        # is the evidence it was doing it.
        expect_failure_contains="AttributeError"),

    # -- 2. minimisation iterates the SUPPLY side ---------------------------
    Proof(
        label="irrelevant candidates cannot widen the request",
        path=MDR,
        find="""    for param in sorted(set(unresolved)):
        band = voi_band_for(param)""",
        replace="""    for param in sorted({p for c in candidates for p in c.resolves}):
        band = voi_band_for(param)""",
        target=f"{ENGINE}::test_ten_irrelevant_private_fields_do_not_widen_the_request",
        expect_failure_contains="assert"),

    # -- 3. privacy ordering ignored ----------------------------------------
    Proof(
        label="the safest sufficient candidate wins",
        path=MDR,
        find="""        ordered = sorted(usable, key=lambda c: (PRIVACY_RANK[c.privacy_class],
                                                GRAIN_RANK[c.grain],
                                                c.field_name))""",
        replace="""        ordered = sorted(usable, key=lambda c: (-PRIVACY_RANK[c.privacy_class],
                                                GRAIN_RANK[c.grain],
                                                c.field_name))""",
        target=f"{ENGINE}::test_a_safer_substitute_wins_when_both_resolve_the_same_uncertainty",
        expect_failure_contains="assert"),

    # -- 4. disproportionate sensitivity still requested --------------------
    Proof(
        label="a restricted low-value field is refused",
        path=MDR,
        find="""        if PRIVACY_RANK[chosen.privacy_class] >= PRIVACY_RANK[
                PRIVACY_RESTRICTED] and _BAND_RANK[band] <= _BAND_RANK[VOI_LOW]:""",
        replace="""        if False:""",
        target=f"{ENGINE}::test_a_highly_sensitive_low_value_field_is_refused_outright",
        expect_failure_contains="assert"),

    # -- 5. the breadth check ------------------------------------------------
    Proof(
        label="a system-access offer is refused as breadth",
        path=MDR,
        find="""            if cand.grain == GRAIN_SYSTEM_ACCESS:""",
        replace="""            if False:""",
        target=f"{ENGINE}::test_a_narrow_metric_is_taken_over_a_broad_export",
        expect_failure_contains="assert"),

    # -- 6. VOI stops being decision-bound -----------------------------------
    Proof(
        label="a valued field must name a boundary it moves",
        path=MDR,
        find="""        if self.voi_band in (VOI_HIGH, VOI_MEDIUM, VOI_LOW) and not self.alters:""",
        replace="""        if False:""",
        target=f"{ENGINE}::test_a_field_claiming_value_must_name_a_boundary_it_moves",
        expect_failure_contains="DID NOT RAISE"),

    # -- 7. a no-value field enters a request --------------------------------
    Proof(
        label="a NO_DECISION_VALUE field is never asked for",
        path=MDR,
        find="""            if got.voi_band == VOI_NONE:""",
        replace="""            if got.voi_band == "___never___":""",
        target=f"{ENGINE}::test_a_no_decision_value_field_can_never_enter_a_request",
        expect_failure_contains="DID NOT RAISE"),

    # -- 8. the request id carries the clock ---------------------------------
    Proof(
        label="the same gap asked twice is one request",
        path=MDR,
        find="""        request_id=_request_id(subject_id, decision,
                               [f.field_name for f in selection.selected],
                               tenant_key),""",
        replace="""        request_id=_request_id(subject_id, decision + when,
                               [f.field_name for f in selection.selected],
                               tenant_key),""",
        target=f"{ENGINE}::test_the_same_gap_asked_twice_is_one_request_not_two",
        expect_failure_contains="assert"),

    # -- 9. an experiment claims it cannot hurt ------------------------------
    Proof(
        label="an experiment may never claim zero risk",
        path=MDR,
        find="""_RISK_DENIALS = ("zero risk", "zero-risk", "no risk", "risk free",""",
        replace="""_RISK_DENIALS = ("__never_matches__", "zero-risk", "no risk", "risk free",""",
        target=f"{ENGINE}::test_an_experiment_may_never_claim_zero_risk",
        expect_failure_contains="DID NOT RAISE"),

    # -- 10. an experiment invents its own numbers ---------------------------
    Proof(
        label="an experiment invents no bounded numeric parameters",
        path=MDR,
        find="""        exposure_scope=EXPOSURE_UNRESOLVED,
        duration=DURATION_UNRESOLVED,""",
        replace="""        exposure_scope="3% of traffic",
        duration="14 days",""",
        target=f"{ENGINE}::test_the_experiment_invents_no_numbers",
        expect_failure_contains="assert"),

    # -- 11. the sufficient-data path still emits a request ------------------
    Proof(
        label="a sufficient-data outcome cannot carry a request",
        path=MDR,
        find="""        if self.state in NO_ASK_STATES and self.request is not None:""",
        replace="""        if False:""",
        target=f"{ENGINE}::test_a_sufficient_data_outcome_carrying_a_request_is_refused",
        expect_failure_contains="DID NOT RAISE"),

    # -- 12. the old persisted shape crashes on reload -----------------------
    Proof(
        label="a v1 row reloads without inventing terms",
        path=MDR,
        find="""                    privacy_class=PRIVACY_RESTRICTED,
                    retention_policy=RETAIN_DISCARD_AFTER_USE,""",
        replace="""                    privacy_class=PRIVACY_INTERNAL,
                    retention_policy=RETAIN_DISCARD_AFTER_USE,""",
        target=f"{ENGINE}::test_a_v1_row_reloads_without_crashing_and_without_inventing_terms",
        expect_failure_contains="assert"),

    # -- 13. the terms clause becomes attacker-writable ----------------------
    Proof(
        label="external text cannot reach the data-use clause",
        path=MDR,
        find="""    return (f"{PERMITTED_USE_CLAUSE} Decision: {decision_id}."
            if decision_id else PERMITTED_USE_CLAUSE)""",
        replace=('    return f"answering: {decision_id}. No other use."'),
        target=f"{SEAM}::test_case_7_an_injected_instruction_does_not_widen_the_request",
        expect_failure_contains="assert"),

    # -- 14. the renderer stops reading the record ---------------------------
    Proof(
        label="the surface renders only what the record holds",
        path=VIEW,
        find="""    heading, lead = _ASK_WORDING[outcome.state]""",
        replace="""    heading, lead = ("Missing information",
                     "We need more data to answer this.")""",
        target=f"{SEAM}::test_the_surface_says_nothing_is_needed_when_nothing_is",
        expect_failure_contains="assert"),

    # -- 15. the tenant boundary on the request store ------------------------
    Proof(
        label="a request partition needs a scope",
        path=MDR,
        find="""        got = read_scope(scope)
        if got is None:
            raise ScopeRefused(""",
        replace="""        got = read_scope(scope)
        if False:
            raise ScopeRefused(""",
        target=f"{ENGINE}::test_a_partition_cannot_be_located_without_a_scope",
        # Not "DID NOT RAISE". `scope_cache_key` refuses a None scope on its
        # own, so removing this guard still raises -- with a message that no
        # longer says WHICH store refused. The assertion on that message is
        # what makes the guard load-bearing, and it is what goes red.
        expect_failure_contains="assert"),

    # -- 16. the LDR link is copied rather than referenced -------------------
    Proof(
        label="the decision record is not revised for an unchanged ask",
        path=VIEW,
        find="""    if (new_gaps, new_reqs, new_mves) == (gaps, reqs, mves):
        return""",
        replace="""    if False:
        return""",
        target=f"{SEAM}::test_asking_twice_does_not_produce_an_empty_revision",
        expect_failure_contains="assert"),

    # -- 17. the internal-impact bridge stops distinguishing answered --------
    Proof(
        label="a measured negative asks for nothing",
        path=II,
        find="""    NO_INTERNAL_IMPACT: (),""",
        replace="""    NO_INTERNAL_IMPACT: (MDR.PARAM_METRIC_EXISTENCE,),""",
        target=f"{ENGINE}::test_a_measured_negative_produces_no_request",
        expect_failure_contains="assert"),
]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title="D-MDR-001 break proofs"))
