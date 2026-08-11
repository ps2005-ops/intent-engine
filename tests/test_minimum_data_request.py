"""D-MDR-001 -- the ask, its price, its terms, and the experiment behind it.

WHAT THIS SUITE IS ACTUALLY GUARDING
------------------------------------
The v1 request could not fail its own minimisation test, because its output
was a constant: two hard-coded field lists that did not vary with anything.
"Adding ten irrelevant fields did not widen the request" is a true sentence
about a function that ignores its arguments, and it proves nothing.

So the metamorphic tests below are run against a request that DOES vary with
its candidate catalogue -- and the widening test is paired with a test that the
same catalogue, minus a load-bearing field, changes the answer. A property that
holds because nothing is connected is not a property.

THE NEGATIVE CONTROLS ARE THE PRODUCT
-------------------------------------
Six of §11's cases are here, and each one is a DIFFERENT non-ask. A system
that renders "already answered", "would change nothing", "too sensitive for
what it is worth", "refused for breadth" and "nothing can produce it" as a
single "insufficient data" has collapsed the whole ladder, which is the
failure this node was scheduled to remove.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.business_graph import internal as P
from intent_engine.business_graph.model import BusinessGraph, GraphError
from intent_engine.core.tenant import (
    SOURCE_SYNTHETIC_FIXTURE,
    ScopeAuditLog,
    TenantId,
    establish,
)
from intent_engine.external_intel import internal_impact as II
from intent_engine.external_intel import minimum_data_request as M

DECISION = "should we change terms for the segment exposed to this subject?"
SUBJECT = "company:acme"
OBSERVED = "2026-07-01T00:00:00+00:00"


@pytest.fixture
def tenant_scope(tmp_path):
    return establish(tenant=TenantId.mint(),
                     establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                     display_label="Acme",
                     audit=ScopeAuditLog(tmp_path / "audit.jsonl"))


def _offerable(scope, local_id, spec):
    return P.private_node(
        scope=scope, kind=P.INTERNAL_METRIC, local_id=local_id,
        label="offerable", company_id="acme", source="crm",
        observed_at=OBSERVED, known_at=OBSERVED,
        sensitivity=P.SENSITIVITY_INTERNAL,
        attrs={II.OFFERABLE_FIELD_KEY: spec})


# =============================================================================
# Fixtures -- a catalogue that is genuinely varied, not a single shape
# =============================================================================
def _cand(name, resolves, *, privacy=M.PRIVACY_INTERNAL,
          grain=M.GRAIN_AGGREGATE, available=True, window=0, aggregates_to=""):
    return M.CandidateField(
        field_name=name, semantic_definition=f"definition of {name}",
        resolves=tuple(resolves), grain=grain, privacy_class=privacy,
        available=available, time_window_days=window,
        aggregates_to=aggregates_to)


@pytest.fixture
def relevant():
    """Five candidates that between them resolve the two open parameters."""
    return [
        _cand("metric inventory", (M.PARAM_METRIC_EXISTENCE,)),
        _cand("metric linkage", (M.PARAM_METRIC_LINKAGE,)),
        _cand("metric level", (M.PARAM_METRIC_LEVEL,),
              privacy=M.PRIVACY_CONFIDENTIAL),
        _cand("exposure share", (M.PARAM_EXPOSURE_SIZE,)),
        _cand("metric trend", (M.PARAM_TREND,), window=90),
    ]


#: Parameters that are VALUABLE but not currently open. The distinction is the
#: whole test: an earlier version of this fixture used a NO_DECISION_VALUE
#: parameter, and the break proof showed why that was worthless -- the
#: valueless branch discarded them before the loop direction could matter, so
#: a `select_minimum` walking the SUPPLY side passed the widening test too.
_NOT_OPEN_HERE = (M.PARAM_METRIC_EXISTENCE, M.PARAM_EXPOSURE_SIZE,
                  M.PARAM_TREND, M.PARAM_DEMAND_RESPONSE)


@pytest.fixture
def irrelevant():
    """Ten private fields resolving parameters that are not currently open."""
    return [_cand(f"private-{i}", (_NOT_OPEN_HERE[i % len(_NOT_OPEN_HERE)],),
                  privacy=M.PRIVACY_RESTRICTED, grain=M.GRAIN_INDIVIDUAL)
            for i in range(10)]


def _route(unresolved, candidates, **kw):
    return M.route(decision=DECISION, unresolved=unresolved,
                   candidates=candidates, subject_id=SUBJECT, **kw)


# =============================================================================
# 1. VOI IS DERIVED FROM DECISION BOUNDARIES, NEVER ASSERTED
# =============================================================================
def test_voi_band_comes_from_the_boundaries_the_parameter_moves():
    assert M.voi_band_for(M.PARAM_METRIC_EXISTENCE) == M.VOI_HIGH
    assert M.voi_band_for(M.PARAM_METRIC_LEVEL) == M.VOI_MEDIUM
    assert M.voi_band_for(M.PARAM_TREND) == M.VOI_LOW
    assert M.voi_band_for(M.PARAM_OWNER_PREFERENCE) == M.VOI_NONE


def test_an_unobtainable_parameter_is_unmeasurable_however_much_it_matters():
    """`measurable=False` may only ever LOWER the band."""
    assert M.voi_band_for(M.PARAM_METRIC_EXISTENCE, measurable=False) == \
        M.VOI_UNMEASURABLE


def test_a_parameter_outside_the_vocabulary_cannot_be_priced():
    with pytest.raises(GraphError):
        M.voi_band_for("whatever_we_feel_like")


def test_a_field_claiming_value_must_name_a_boundary_it_moves():
    with pytest.raises(GraphError) as exc:
        M.RequestedField(field_name="f", decision_question="q",
                         voi_band=M.VOI_HIGH, alters=(),
                         expected_decision_effect="lots")
    assert "interesting is not" in str(exc.value)


def test_there_is_no_numeric_voi_and_the_refusal_is_recorded(relevant):
    got = _route((M.PARAM_METRIC_LINKAGE,), relevant)
    blob = json.dumps(got.as_dict())
    assert "$" not in blob
    assert "expected information value" not in blob.lower()
    assert "requires action alternatives" in got.request.numeric_voi


# =============================================================================
# 2. BREADTH MINIMISATION -- §7's metamorphic pair
# =============================================================================
def test_ten_irrelevant_private_fields_do_not_widen_the_request(
        relevant, irrelevant):
    base = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL), relevant)
    wide = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL),
                  relevant + irrelevant)
    assert base.request.fields == wide.request.fields
    assert base.request.request_id == wide.request.request_id


def test_the_catalogue_is_actually_connected_so_the_widening_test_can_fail(
        relevant):
    """The pairing that makes the test above mean something.

    Remove the load-bearing candidate and the answer MUST change. Without this
    assertion, a `select_minimum` that returned a constant would pass the
    widening test perfectly -- which is exactly how the v1 request "passed".
    """
    without = [c for c in relevant if c.field_name != "metric linkage"]
    got = _route((M.PARAM_METRIC_LINKAGE,), without)
    assert got.state != M.MDR_ISSUED
    assert M.PARAM_METRIC_LINKAGE in got.selection.unresolvable


def test_a_load_bearing_field_removed_selects_a_valid_substitute(relevant):
    """§7's other half: insufficiency OR a substitute, never a silent skip."""
    swapped = [c for c in relevant if c.field_name != "metric level"]
    swapped.append(_cand("cohort-level metric level", (M.PARAM_METRIC_LEVEL,),
                         privacy=M.PRIVACY_INTERNAL, grain=M.GRAIN_COHORT))
    got = _route((M.PARAM_METRIC_LEVEL,), swapped)
    assert got.request.fields == ("cohort-level metric level",)


def test_reordering_the_candidates_produces_the_same_request(relevant):
    a = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL), relevant)
    b = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL),
               list(reversed(relevant)))
    assert a.request.as_dict()["requested_fields"] == \
        b.request.as_dict()["requested_fields"]


def test_the_same_gap_asked_twice_is_one_request_not_two(relevant):
    """§11 CASE F. The id excludes the timestamp deliberately: a content hash
    carrying a read date is a dedupe bug this program has already shipped."""
    a = _route((M.PARAM_METRIC_LINKAGE,), relevant, now="2026-01-01T00:00:00")
    b = _route((M.PARAM_METRIC_LINKAGE,), relevant, now="2026-06-30T00:00:00")
    assert a.request.request_id == b.request.request_id


def test_one_field_answering_two_parameters_is_one_line_of_the_ask():
    both = [_cand("joint field", (M.PARAM_METRIC_LINKAGE,
                                  M.PARAM_METRIC_LEVEL))]
    got = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL), both)
    assert got.request.fields == ("joint field",)
    field = got.request.requested_fields[0]
    assert set(field.alters) >= {M.ALTERS_STANDING, M.ALTERS_KILL_SWITCH}


# =============================================================================
# 3. PRIVACY, SUBSTITUTES AND RETENTION
# =============================================================================
def test_a_safer_substitute_wins_when_both_resolve_the_same_uncertainty():
    """§11 CASE C. Cohort conversion beats a customer-level export."""
    got = _route((M.PARAM_EXPOSURE_SIZE,), [
        _cand("raw customer records", (M.PARAM_EXPOSURE_SIZE,),
              privacy=M.PRIVACY_RESTRICTED, grain=M.GRAIN_INDIVIDUAL),
        _cand("cohort exposure share", (M.PARAM_EXPOSURE_SIZE,),
              privacy=M.PRIVACY_INTERNAL, grain=M.GRAIN_COHORT),
    ])
    assert got.request.fields == ("cohort exposure share",)
    assert "raw customer records" in got.selection.sensitive_avoided
    assert ("raw customer records", "cohort exposure share") in \
        got.selection.substitutions
    assert got.request.requested_fields[0].substitute_for == \
        "raw customer records"


def test_a_narrow_metric_is_taken_over_a_broad_export():
    """§11 CASE E: one narrow metric is enough, so no broad export."""
    got = _route((M.PARAM_METRIC_LEVEL,), [
        _cand("full CRM export", (M.PARAM_METRIC_LEVEL,),
              privacy=M.PRIVACY_RESTRICTED, grain=M.GRAIN_SYSTEM_ACCESS),
        _cand("that one metric", (M.PARAM_METRIC_LEVEL,)),
    ])
    assert got.request.fields == ("that one metric",)
    assert "full CRM export" in got.selection.system_access_refused


def test_a_highly_sensitive_low_value_field_is_refused_outright():
    """§11 CASE D. Nothing safer exists, and it is still not asked for."""
    got = _route((M.PARAM_TREND,), [
        _cand("restricted trend detail", (M.PARAM_TREND,),
              privacy=M.PRIVACY_RESTRICTED, grain=M.GRAIN_INDIVIDUAL),
    ])
    assert got.request is None
    assert "restricted trend detail" in got.selection.sensitive_avoided
    assert got.selection.declined == (
        ("restricted trend detail", M.DECLINE_DISPROPORTIONATE),)


def test_a_high_value_restricted_field_is_still_asked_for():
    """The counterpart, so the rule above is proportionality and not a ban."""
    got = _route((M.PARAM_METRIC_EXISTENCE,), [
        _cand("restricted inventory", (M.PARAM_METRIC_EXISTENCE,),
              privacy=M.PRIVACY_RESTRICTED),
    ])
    assert got.request.fields == ("restricted inventory",)


def test_retention_is_the_least_that_answers_the_question(relevant):
    got = _route((M.PARAM_METRIC_LEVEL,), relevant)
    field = got.request.requested_fields[0]
    assert field.retention_policy == M.RETAIN_DISCARD_AFTER_USE
    windowed = _route((M.PARAM_TREND,), relevant)
    assert windowed.request.requested_fields[0].retention_policy == \
        M.RETAIN_WINDOW


def test_every_requested_field_carries_a_privacy_class_and_a_purpose(relevant):
    got = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL), relevant)
    for field in got.request.requested_fields:
        assert field.privacy_class in M.PRIVACY_CLASSES
        assert field.retention_policy in M.RETENTION_POLICIES
        assert field.permitted_use.startswith(M.PERMITTED_USE_CLAUSE)


def test_an_unclassified_field_cannot_be_constructed():
    with pytest.raises(GraphError):
        M.RequestedField(field_name="f", decision_question="q",
                         privacy_class="whatever")


def test_a_field_that_names_a_system_cannot_be_requested():
    with pytest.raises(GraphError) as exc:
        M.RequestedField(field_name="your CRM", decision_question="q",
                         required_grain=M.GRAIN_SYSTEM_ACCESS)
    assert "system rather than" in str(exc.value)


# =============================================================================
# 4. THE NEGATIVE CONTROLS -- five different non-asks
# =============================================================================
def test_case_a_sufficient_data_asks_for_nothing(relevant):
    got = _route((), relevant)
    assert got.state == M.NO_REQUEST_DATA_SUFFICIENT
    assert got.request is None and got.experiment is None


def test_case_b_a_parameter_that_moves_no_decision_is_not_requested(relevant):
    got = _route((M.PARAM_OWNER_PREFERENCE,),
                 relevant + [_cand("seating chart",
                                   (M.PARAM_OWNER_PREFERENCE,))])
    assert got.state == M.NO_REQUEST_NO_DECISION_VALUE
    assert got.request is None
    assert M.PARAM_OWNER_PREFERENCE in got.selection.no_decision_value


def test_a_no_decision_value_field_can_never_enter_a_request():
    with pytest.raises(GraphError) as exc:
        M.MinimumDataRequest(
            decision=DECISION, reason=M.MDR_PARAMETER_UNRESOLVED,
            requested_fields=(M.RequestedField(
                field_name="seating chart", decision_question="q",
                voi_band=M.VOI_NONE),))
    assert "never asked for" in str(exc.value)


def test_the_four_non_asks_are_four_different_states(relevant):
    states = {
        _route((), relevant).state,
        _route((M.PARAM_OWNER_PREFERENCE,), relevant).state,
        _route((M.PARAM_METRIC_LINKAGE,), []).state,
        _route((M.PARAM_METRIC_LEVEL,), [
            _cand("only a system", (M.PARAM_METRIC_LEVEL,),
                  grain=M.GRAIN_SYSTEM_ACCESS)]).state,
    }
    assert states == {M.NO_REQUEST_DATA_SUFFICIENT,
                      M.NO_REQUEST_NO_DECISION_VALUE, M.UNRESOLVABLE,
                      M.BREADTH_REFUSED}


def test_a_sufficient_data_outcome_carrying_a_request_is_refused(relevant):
    got = _route((M.PARAM_METRIC_LINKAGE,), relevant)
    with pytest.raises(GraphError) as exc:
        M.RequestOutcome(state=M.NO_REQUEST_DATA_SUFFICIENT,
                         request=got.request)
    assert "unbounded-collection" in str(exc.value)


# =============================================================================
# 5. THE EXPERIMENT BRIDGE
# =============================================================================
def test_an_unobtainable_parameter_routes_to_a_bounded_experiment():
    got = _route((M.PARAM_DEMAND_RESPONSE,), [])
    assert got.state == M.MVE_PROPOSED
    mve = got.experiment
    assert mve.guardrail_metrics and mve.kill_switch and mve.falsifier
    assert mve.unresolved_parameter == M.PARAM_DEMAND_RESPONSE


def test_an_experiment_is_not_offered_merely_to_avoid_saying_we_dont_know():
    """§14's named failure. A parameter no field can produce is NOT
    automatically experimentable -- an observation about the past cannot be
    manufactured by an intervention."""
    got = _route((M.PARAM_EXPOSURE_SIZE,), [])
    assert got.state == M.UNRESOLVABLE
    assert got.experiment is None


def test_the_experiment_invents_no_numbers():
    mve = _route((M.PARAM_DEMAND_RESPONSE,), []).experiment
    assert mve.duration == M.DURATION_UNRESOLVED
    assert mve.exposure_scope == M.EXPOSURE_UNRESOLVED
    assert mve.kill_threshold == M.KILL_THRESHOLD_UNRESOLVED
    assert mve.downside_budget_status == M.BUDGET_UNRESOLVED
    assert not mve.is_fully_parameterized
    assert mve.parameterization


def test_an_experiment_may_never_claim_zero_risk():
    with pytest.raises(GraphError) as exc:
        M.MinimumViableExperiment(
            decision=DECISION, hypothesis="a zero risk trial",
            guardrail_metrics=("g",), kill_switch="stop", falsifier="f")
    assert "zero risk" in str(exc.value)


@pytest.mark.parametrize("phrase", ["no downside", "risk-free", "cannot fail"])
def test_every_risk_denial_phrasing_is_refused(phrase):
    with pytest.raises(GraphError):
        M.refuse_risk_denial(f"this is {phrase} for the tenant")


def test_a_proposed_experiment_without_a_guardrail_is_refused():
    with pytest.raises(GraphError) as exc:
        M.MinimumViableExperiment(decision=DECISION, hypothesis="h",
                                  kill_switch="stop", falsifier="f")
    assert "guardrail" in str(exc.value)


def test_a_proposed_experiment_without_a_falsifier_is_refused():
    with pytest.raises(GraphError) as exc:
        M.MinimumViableExperiment(decision=DECISION, hypothesis="h",
                                  guardrail_metrics=("g",), kill_switch="s")
    assert "refute" in str(exc.value)


def test_a_partially_resolvable_gap_returns_both_the_ask_and_the_experiment():
    got = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_DEMAND_RESPONSE),
                 [_cand("metric linkage", (M.PARAM_METRIC_LINKAGE,))])
    assert got.state == M.MDR_ISSUED
    assert got.request.fields == ("metric linkage",)
    assert got.experiment is not None


# =============================================================================
# 6. PERSISTENCE, RELOAD AND THE OLD SCHEMA
# =============================================================================
def test_a_request_survives_a_round_trip(tmp_path, tenant_scope, relevant):
    store = M.DataRequestStore(tmp_path)
    got = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL), relevant)
    store.append(got.request, scope=tenant_scope)
    back = store.requests(scope=tenant_scope)
    assert len(back) == 1
    assert back[0].as_dict() == got.request.as_dict()
    assert back[0].requested_fields[0].privacy_class in M.PRIVACY_CLASSES


def test_the_same_request_written_twice_reloads_as_one(tmp_path, tenant_scope,
                                                       relevant):
    store = M.DataRequestStore(tmp_path)
    got = _route((M.PARAM_METRIC_LINKAGE,), relevant)
    store.append(got.request, scope=tenant_scope)
    store.append(got.request, scope=tenant_scope)
    assert len(store.requests(scope=tenant_scope)) == 1


def test_an_experiment_survives_a_round_trip(tmp_path, tenant_scope):
    store = M.DataRequestStore(tmp_path)
    mve = _route((M.PARAM_DEMAND_RESPONSE,), []).experiment
    store.append(mve, scope=tenant_scope)
    back = store.experiments(scope=tenant_scope)
    assert back and back[0].as_dict() == mve.as_dict()
    assert not back[0].is_fully_parameterized


def test_a_v1_row_reloads_without_crashing_and_without_inventing_terms():
    """§4. The old shape stored bare strings. It is LIFTED, and the lift says
    so -- a reload that guessed MEDIUM/INTERNAL would manufacture terms the
    tenant never agreed to, and those terms are what gets audited."""
    legacy = {"contract": M.LEGACY_CONTRACT, "request_id": "mdr-old",
              "decision": DECISION, "missing": "a metric",
              "fields": ["metric name", "current value"],
              "window_days": 90, "reason": M.MDR_NO_INTERNAL_WORLD,
              "subject_id": SUBJECT}
    back = M.MinimumDataRequest.from_dict(legacy)
    assert back.fields == ("metric name", "current value")
    assert back.schema_version == M.LEGACY_CONTRACT
    for field in back.requested_fields:
        assert field.voi_band == M.VOI_UNMEASURABLE
        assert field.privacy_class == M.PRIVACY_RESTRICTED
        assert "never recorded" in field.reason


def test_a_v1_row_with_a_missing_optional_field_reloads():
    back = M.MinimumDataRequest.from_dict(
        {"decision": DECISION, "fields": ["x"],
         "reason": M.MDR_METRIC_NOT_WIRED})
    assert back.fields == ("x",)


def test_an_explicit_null_reloads_as_absent():
    back = M.MinimumDataRequest.from_dict(
        {"decision": DECISION, "fields": ["x"], "missing": None,
         "subject_id": None, "declined": None, "window_days": None,
         "reason": M.MDR_METRIC_NOT_WIRED})
    assert back.missing == "" and back.window_days == 0


def test_a_v2_row_round_trips_its_typed_fields(relevant):
    got = _route((M.PARAM_METRIC_LEVEL,), relevant)
    back = M.MinimumDataRequest.from_dict(got.request.as_dict())
    assert back.as_dict() == got.request.as_dict()


def test_a_bare_string_can_no_longer_be_constructed_into_a_request():
    """The v1 constructor is the defect: a string carries no privacy class,
    no retention and no decision link."""
    with pytest.raises(GraphError) as exc:
        M.MinimumDataRequest(decision=DECISION, requested_fields=("a field",),
                             reason=M.MDR_NO_INTERNAL_WORLD)
    assert "bare string" in str(exc.value)


def test_a_partition_cannot_be_located_without_a_scope(tmp_path):
    from intent_engine.core.tenant import ScopeRefused

    with pytest.raises(ScopeRefused) as exc:
        M.DataRequestStore(tmp_path).path_for(None)
    # `scope_cache_key` refuses a None scope too, so asserting only the
    # exception CLASS proves nothing about this store -- the break proof
    # caught exactly that. What this guard adds is the message naming which
    # partition could not be located.
    assert "data-request partition" in str(exc.value)


# =============================================================================
# 7. THE INTERNAL-IMPACT BRIDGE
# =============================================================================
def _impact(state, **kw):
    return II.InternalImpact(state=state, subject_id=SUBJECT, **kw)


def test_both_answered_states_leave_nothing_unresolved():
    assert II.unresolved_parameters(
        _impact(II.INTERNAL_IMPACT_IDENTIFIED)) == ()
    assert II.unresolved_parameters(_impact(II.NO_INTERNAL_IMPACT)) == ()


def test_a_measured_negative_produces_no_request():
    got = II.request_outcome(_impact(II.NO_INTERNAL_IMPACT), decision=DECISION)
    assert got.state == M.NO_REQUEST_DATA_SUFFICIENT
    assert got.request is None


def test_a_gap_produces_a_narrow_request_from_the_baseline():
    got = II.request_outcome(
        _impact(II.INTERNAL_LINK_WITHOUT_METRIC, declared_links=("i-1",)),
        decision=DECISION)
    assert got.state == M.MDR_ISSUED
    assert got.request.fields == ("metric-to-initiative linkage",
                                  "current metric value")
    assert got.request.reason == II.MDR_METRIC_NOT_WIRED


def test_the_baseline_catalogue_names_no_system():
    for cand in II.BASELINE_CANDIDATES:
        assert cand.grain != M.GRAIN_SYSTEM_ACCESS
        assert "CRM" not in cand.field_name


def test_a_tenant_declared_candidate_joins_the_catalogue(tenant_scope):
    """The ONLY way a candidate beyond the baseline enters. It comes off a
    private node read through the scoped reader, so another tenant's
    declaration is never seen -- not filtered, never seen."""
    graph = BusinessGraph()
    graph.add_private_node(_offerable(tenant_scope, "off", {
        "field_name": "cohort conversion",
        "resolves": [M.PARAM_EXPOSURE_SIZE],
        "grain": M.GRAIN_COHORT,
        "privacy_class": M.PRIVACY_INTERNAL}), scope=tenant_scope)
    names = [c.field_name
             for c in II.candidate_fields(graph, scope=tenant_scope)]
    assert "cohort conversion" in names


def test_a_malformed_declaration_is_skipped_not_raised(tenant_scope):
    graph = BusinessGraph()
    graph.add_private_node(
        _offerable(tenant_scope, "bad",
                   {"field_name": "x", "resolves": ["not_a_parameter"]}),
        scope=tenant_scope)
    assert [c.field_name for c in II.candidate_fields(graph,
                                                      scope=tenant_scope)] == \
        [c.field_name for c in II.BASELINE_CANDIDATES]


def test_a_scopeless_catalogue_is_the_baseline_only():
    assert II.candidate_fields(None, scope=None) == II.BASELINE_CANDIDATES


# =============================================================================
# 8. TELEMETRY -- bounded, and SYSTEM rather than economic
# =============================================================================
def test_telemetry_counts_the_restraint_as_well_as_the_ask(relevant,
                                                           irrelevant):
    got = _route((M.PARAM_METRIC_LINKAGE, M.PARAM_METRIC_LEVEL),
                 relevant + irrelevant)
    tel = M.MDRTelemetry.of(got)
    assert tel.requests_generated == 1
    assert tel.fields_requested == 2
    assert tel.fields_declined_unnecessary >= 10
    assert tel.learning_class == "SYSTEM"


def test_telemetry_records_an_avoided_request(relevant):
    tel = M.MDRTelemetry.of(_route((), relevant))
    assert tel.requests_avoided_data_sufficient == 1
    assert tel.requests_generated == 0


def test_telemetry_names_no_private_column(relevant):
    tel = M.MDRTelemetry.of(_route((M.PARAM_METRIC_LEVEL,), relevant))
    assert "metric level" not in json.dumps(tel.as_dict())


def test_telemetry_merges_without_losing_a_counter(relevant):
    a = M.MDRTelemetry.of(_route((M.PARAM_METRIC_LEVEL,), relevant))
    b = M.MDRTelemetry.of(_route((), relevant))
    merged = a.merged(b)
    assert merged.requests_generated == 1
    assert merged.requests_avoided_data_sufficient == 1
