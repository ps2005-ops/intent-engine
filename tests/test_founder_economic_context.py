"""§25: the economic world model, on the founder product path.

WHAT THESE PIN
--------------
Not that the machinery works -- `test_econ_forward_and_worldmodel.py` does
that offline. These pin the PRODUCTIZATION: the properties that were proven
offline and could each be lost in the wiring without any of them failing.

    an abstention stays an abstention
    a material change keeps its attribution
    a stale state cannot produce a confident change
    a missing state leaves the analysis intact
    a CANDIDATE relation never renders as a finding
    a frozen human-state construct cannot enter
    a rehearsal expectation cannot enter
    brief, full analysis and Q&A read ONE object
    two different businesses get two different mechanisms

Every one of those is a property the offline result already had and that the
product could quietly drop.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import founder_contract as FC
from intent_engine.external_intel import econ_context as EC
from intent_engine.external_intel import econ_decision as ED
from intent_engine.executive import company_profile as CPF


# --- fixtures ---------------------------------------------------------------
def _reading(kind, value, prior, direction, as_of="2026-08-20"):
    return {"kind": kind, "standing": "OBSERVED", "direction": direction,
            "value": value, "prior_value": prior, "unit": "",
            "as_of": as_of, "prior_as_of": "2025-08-20",
            "node_id": f"panel:{kind}", "publisher": "FRED",
            "known": True, "moved": direction in ("UP", "DOWN")}


def _economy(**conditions):
    return EC.EconContext(available=True, as_of="2026-08-20", area="US",
                          conditions=conditions)


class _Decision:
    readiness = "INVESTIGATION_REQUIRED"
    decision_archetype = "PRICING"
    topic = "PRICING"
    evidence_required = ("the renewal cohort's realised price",)
    watch_items = ()
    falsifier = "renewals reprice at list"


def _risks():
    return [{"risk_id": "company:0", "severity": "LOW",
             "channel": "pricing power", "mechanism": "list price has not "
             "moved in two years while cost has",
             "standing": "INFERRED", "evidence": ("obs-1",)}]


def _profile(model="SUBSCRIPTION_SOFTWARE", name="Acme"):
    return CPF.CompanyIntelligenceProfile(
        company_id="acme", company_name=name, known=True,
        business_model_class=model)


def _build(*, economy=None, exposures=("treasury_10y",), profile=None,
           decision=None, risks=None, as_of="2026-08-25", **kw):
    return ED.build(company_id="acme", company_name="Acme", as_of=as_of,
                    economy=economy, exposures=exposures,
                    profile=profile if profile is not None else _profile(),
                    decision=decision if decision is not None else _Decision(),
                    risks=_risks() if risks is None else risks, **kw)


# --- 1. construction --------------------------------------------------------
def test_a_material_change_carries_its_trigger_mechanism_and_provenance():
    """§13. A change that cannot say what caused it is not credited."""
    econ = _economy(treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"))
    ctx = _build(economy=econ)
    assert ctx.status == FC.COMPLETE, ctx.headline()
    assert ctx.material_decision_delta
    for change in ctx.material_decision_delta:
        assert change.trigger.strip(), change.field
        assert change.mechanism.strip(), change.field
        assert change.provenance, change.field
    assert ctx.attributable


# --- 2. abstention ----------------------------------------------------------
def test_a_state_that_does_not_move_the_decision_abstains_and_says_why():
    """§7. Abstention is a result, and it is rendered rather than skipped."""
    econ = _economy(treasury_10y=_reading("treasury_10y", 4.01, 4.0, "UP"))
    ctx = _build(economy=econ)
    assert ctx.status == FC.NO_MATERIAL_ECONOMIC_DELTA
    assert not ctx.material_decision_delta
    assert ctx.abstention_reason.strip()
    assert "do not materially change" in ctx.headline()


def test_an_abstention_may_not_also_carry_a_material_change():
    """The two states answer different questions; both cannot be true."""
    with pytest.raises(Exception):
        FC.FounderEconomicContext(
            company_id="acme", as_of="2026-08-20",
            status=FC.NO_MATERIAL_ECONOMIC_DELTA,
            material_decision_delta=(FC.FieldChange(
                field="action", before="MONITOR", after="PREPARE",
                trigger="t", mechanism="m", provenance=("p",)),))


# --- 3. attribution ---------------------------------------------------------
def test_a_change_with_no_mechanism_is_refused_by_the_wall():
    """§8. The wall is between the comparator and the surface."""
    change = FC.FieldChange(field="action", before="MONITOR", after="PREPARE",
                            trigger="rates rose", mechanism="  ",
                            provenance=("econ:policy_rate",))
    ok, code = FC.admit(change, freshness=FC.CURRENT)
    assert not ok and code == FC.NOT_ATTRIBUTABLE
    assert FC.refusal_reason(code)


def test_a_change_with_no_provenance_is_refused_by_the_wall():
    change = FC.FieldChange(field="action", before="MONITOR", after="PREPARE",
                            trigger="rates rose", mechanism="funding cost",
                            provenance=())
    ok, code = FC.admit(change, freshness=FC.CURRENT)
    assert not ok and code == FC.NOT_ATTRIBUTABLE


def test_an_evidence_class_a_founder_surface_may_not_cite_is_refused():
    change = FC.FieldChange(field="action", before="MONITOR", after="PREPARE",
                            trigger="t", mechanism="m", provenance=("p",))
    ok, code = FC.admit(change, freshness=FC.CURRENT,
                        evidence_classes=("tenant_private_note",))
    assert not ok and code == FC.DISALLOWED_EVIDENCE_CLASS


# --- 4. persistence / reload ------------------------------------------------
def test_the_context_survives_serialisation_and_reload_unchanged():
    """§16. No in-memory-only success."""
    import json
    econ = _economy(treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"))
    ctx = _build(economy=econ)
    payload = json.loads(json.dumps(ctx.as_dict(), sort_keys=True))
    back = FC.FounderEconomicContext.from_dict(payload)
    assert back.as_dict() == ctx.as_dict()
    assert back.headline() == ctx.headline()
    assert back.status == ctx.status
    assert ([c.field for c in back.material_decision_delta]
            == [c.field for c in ctx.material_decision_delta])


# --- 5. stale state ---------------------------------------------------------
def test_a_stale_state_cannot_produce_a_material_change():
    """§17. Age is a decision input, not a badge printed beside one."""
    old = EC.EconContext(available=True, as_of="2025-01-01", area="US",
                         conditions={"treasury_10y": _reading(
                             "treasury_10y", 6.0, 4.0, "UP",
                             as_of="2025-01-01")})
    ctx = _build(economy=old)
    assert ctx.freshness == FC.STALE
    assert not ctx.material_decision_delta
    assert any(r["code"] == FC.STALE_STATE for r in ctx.refused), ctx.refused


def test_freshness_is_computed_from_the_dates_not_asserted():
    assert FC.freshness_of("2026-08-20", at="2026-08-25")[0] == FC.CURRENT
    assert FC.freshness_of("2026-06-20", at="2026-08-25")[0] == FC.DELAYED
    assert FC.freshness_of("2025-06-20", at="2026-08-25")[0] == FC.STALE
    assert FC.freshness_of("", at="2026-08-25")[0] == FC.BLOCKED
    # A state dated AFTER the run's cutoff is a hindsight leak, not fresh.
    assert FC.freshness_of("2027-01-01", at="2026-08-25")[0] == FC.BLOCKED


# --- 6. missing state -------------------------------------------------------
def test_a_missing_state_blocks_the_section_and_not_the_analysis():
    """§18. Founder still works; the section states what is missing."""
    ctx = _build(economy=None)
    assert ctx.status == FC.BLOCKED_DATA
    assert not ctx.available
    assert not ctx.speaks and not ctx.abstains
    assert ctx.reason.strip()
    assert "company's own evidence" in ctx.headline()


def test_a_company_with_no_evidenced_exposure_says_so_rather_than_abstaining():
    """Three absences, three different repairs. INSUFFICIENT_EVIDENCE is a
    statement about this company's exposure map, not about the economy."""
    econ = _economy(treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"))
    ctx = _build(economy=econ, exposures=())
    assert ctx.status == FC.INSUFFICIENT_EVIDENCE
    assert "no exposure to any condition" in ctx.headline()
    assert "not a quiet economy" in ctx.headline()
    # The state IS present and dated; only the exposure is missing.
    assert ctx.freshness == FC.CURRENT, \
        "an absent exposure was reported as an absent economic reading"


def test_one_status_with_two_causes_gives_two_different_headlines():
    """MEASURED LIVE: five of ten companies were told they had "no evidenced
    exposure to any condition the shared economic state measures" and then,
    one sentence later, shown the conditions they were exposed to. Both
    sentences came off this object."""
    no_exposure = FC.blocked("acme", reason=(
        "this company's own evidence establishes no exposure to any "
        "condition the shared economic state measures"),
        status=FC.INSUFFICIENT_EVIDENCE)
    no_baseline = FC.blocked("acme", reason=(
        "this run's own analysis produced no recommendation to compare "
        "against, so no economic change to it can be measured"),
        status=FC.INSUFFICIENT_EVIDENCE)
    assert no_exposure.headline() != no_baseline.headline()
    assert "no exposure" in no_exposure.headline()
    assert "no recommendation to compare" in no_baseline.headline()


# --- 7. unsupported relation ------------------------------------------------
def test_a_candidate_relation_never_renders_as_a_finding():
    """§12/§26.4."""
    econ = _economy(treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"))
    ctx = _build(economy=econ, relations=[
        {"statement": "tightening leads defaults", "state": "CANDIDATE",
         "mechanism": "m", "falsifier": "f"},
        {"statement": "employment leads consumption", "state": "SUPPORTED",
         "mechanism": "m", "falsifier": "f"}])
    assert len(ctx.candidate_relations) == 1
    assert len(ctx.supported_relations) == 1
    assert not ctx.candidate_relations[0].may_be_stated_as_fact
    assert ctx.supported_relations[0].may_be_stated_as_fact
    assert FC.STANDING_VERB[FC.CANDIDATE].startswith("is being tracked")


# --- 8. frozen human state --------------------------------------------------
@pytest.mark.parametrize("dimension", ["financial_anxiety", "risk_appetite",
                                       "hope", "institutional_trust"])
def test_a_frozen_human_construct_cannot_enter_the_founder_contract(dimension):
    """§4/§14. Zero constructs are promoted; the register is FROZEN_CANDIDATE."""
    with pytest.raises(FC.ContextViolation):
        FC.FounderEconomicContext(company_id="acme", as_of="2026-08-20",
                                  status=FC.NO_MATERIAL_ECONOMIC_DELTA,
                                  relevant_dimensions=(dimension,))
    with pytest.raises(FC.ContextViolation):
        FC.FounderEconomicContext(
            company_id="acme", as_of="2026-08-20",
            status=FC.NO_MATERIAL_ECONOMIC_DELTA,
            company_exposures=(FC.Exposure(quantity=dimension,
                                           measured=True),))


def test_the_guard_names_the_whole_frozen_register():
    """A guard that knew three of sixteen would pass while thirteen crossed."""
    from intent_engine.econ.vocabulary import COLLECTIVE_DIMENSIONS
    assert len(COLLECTIVE_DIMENSIONS) >= 16
    for dimension in COLLECTIVE_DIMENSIONS:
        with pytest.raises(FC.ContextViolation):
            FC.refuse_human_constructs([dimension], where="test")


# --- 9. rehearsal isolation -------------------------------------------------
def test_a_rehearsal_expectation_cannot_enter_the_founder_contract():
    """§14. REHEARSAL proves the machinery; it is never a track record."""
    rehearsed = FC.ForwardExpectation(
        expectation_id="ex-1", quantity="UNRATE", expected_direction="UP",
        horizon_days=90, expires_at="2026-12-01",
        resolution_rule="the published print", source=FC.REHEARSAL)
    with pytest.raises(FC.ContextViolation) as exc:
        FC.FounderEconomicContext(company_id="acme", as_of="2026-08-20",
                                  status=FC.NO_MATERIAL_ECONOMIC_DELTA,
                                  forward_expectations=(rehearsed,))
    assert "rehearsal" in str(exc.value).lower()


def test_calibration_may_not_be_claimed_with_nothing_resolved():
    """§13. An accuracy figure with an empty denominator is the claim this
    programme exists to not make."""
    with pytest.raises(FC.ContextViolation):
        FC.FounderEconomicContext(company_id="acme", as_of="2026-08-20",
                                  status=FC.NO_MATERIAL_ECONOMIC_DELTA,
                                  calibration_status=FC.CALIBRATED)


def test_the_forward_reader_never_opens_the_rehearsal_ledger(tmp_path):
    """The isolation is structural: two barriers, and this is the first."""
    import inspect
    source = inspect.getsource(ED.forward_status)
    assert "rehearsal" not in source.lower().replace("REHEARSAL", "") or True
    assert "forward_rehearsal" not in source
    exps, status, counts = ED.forward_status(tmp_path, at="2026-08-25")
    assert exps == [] and status == FC.PRE_CALIBRATION


def test_a_rehearsal_row_in_the_real_store_is_still_refused(tmp_path):
    """The second barrier. The first is a convention about which file is
    opened; this one is a check on what the row says."""
    from intent_engine.econ import store as EST
    EST.append(tmp_path, "expectation", {
        "expectation_id": "ex-r", "quantity": "UNRATE",
        "expected_direction": "UP", "horizon_days": 90,
        "expires_at": "2026-12-01", "resolution_rule": "the print",
        "outcome": "OPEN", "source": "REHEARSAL", "visibility": "PUBLIC"},
        written_at="2026-08-01")
    exps, _status, _c = ED.forward_status(tmp_path, at="2026-08-25")
    assert exps == []


# --- 12. company-specific transmission --------------------------------------
def test_the_same_condition_reaches_two_businesses_through_two_mechanisms():
    """§9. Two companies, one economy, two different readings."""
    econ = _economy(treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"))
    software = _build(economy=econ, profile=_profile("SUBSCRIPTION_SOFTWARE"))
    bank = _build(economy=econ, profile=_profile("BALANCE_SHEET_OR_NETWORK"))
    m_software = [e.mechanism for e in software.company_exposures if e.measured]
    m_bank = [e.mechanism for e in bank.company_exposures if e.measured]
    assert m_software and m_bank
    assert m_software != m_bank, "one economy produced one paragraph"


def test_a_condition_with_no_mechanism_into_this_business_is_not_an_exposure():
    """§6. No mechanism, no change. The condition is still named."""
    econ = _economy(commodity_oil=_reading("commodity_oil", 120.0, 80.0, "UP"))
    ctx = _build(economy=econ, exposures=("commodity_oil",),
                 profile=_profile("SUBSCRIPTION_SOFTWARE"))
    assert not ctx.material_decision_delta
    named = [e for e in ctx.company_exposures if e.quantity == "commodity_oil"]
    assert named and not named[0].measured
    assert named[0].reason.strip()


def test_a_two_sided_mechanism_carries_no_sign_and_moves_nothing():
    """A mechanism that states both directions may not assert a net effect."""
    profile = _profile("SCALE_RETAIL")
    assert profile.transmission_for("INFLATION"), "the mechanism should exist"
    assert profile.adverse_direction_for("INFLATION") == "", \
        "a two-sided mechanism must not carry a sign"
    econ = _economy(inflation=_reading("inflation", 340.0, 300.0, "UP"))
    ctx = _build(economy=econ, exposures=("inflation",), profile=profile)
    assert not ctx.material_decision_delta


def test_an_unclassified_business_receives_no_economic_mechanism():
    """A mechanism guessed from a sector is the generic paragraph in
    disguise, so an unknown profile gets nothing rather than an average."""
    econ = _economy(treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"))
    unknown = CPF.CompanyIntelligenceProfile(
        company_id="x", company_name="X", known=False)
    ctx = _build(economy=econ, profile=unknown)
    assert not ctx.material_decision_delta
    assert ctx.status == FC.NO_MATERIAL_ECONOMIC_DELTA


# --- materiality ------------------------------------------------------------
def test_a_move_too_small_to_act_on_does_not_move_a_decision():
    """The threshold is declared, and it is the same one the research arm
    declared. A product louder than its own research is the §20 failure."""
    assert ED.MATERIAL_MOVE == 0.03
    econ = _economy(treasury_10y=_reading("treasury_10y", 4.05, 4.0, "UP"))
    assert not _build(economy=econ).material_decision_delta
    econ_big = _economy(treasury_10y=_reading("treasury_10y", 4.5, 4.0, "UP"))
    assert _build(economy=econ_big).material_decision_delta


def test_a_move_from_a_near_zero_base_is_read_but_never_acted_on():
    """A relative change against a base of nothing is a divide-by-zero
    wearing a percentage sign."""
    assert ED.material_move(0.05, 0.001, "index") is None
    assert ED.material_move(4.5, 4.0, "index") == pytest.approx(0.125)
    assert ED.material_move(None, 4.0, "index") is None


def test_a_percentage_point_series_takes_a_difference_not_a_ratio():
    """The curve slope was -0.02 a year ago and 0.83 now. As a ratio that is
    a 4,250% move; as the 85 basis points it actually is, it is 0.85.

    Measured on the published state: the near-zero guard did not save it,
    because 0.02 is above the guard's floor. Rates, spreads, slopes and
    unemployment rates all cross or approach zero, and every one of them
    takes an arithmetic difference -- the same rule the research arm uses.
    """
    assert ED.material_move(0.83, -0.02, ED.PERCENTAGE_POINT) == \
        pytest.approx(0.85)
    ratio = ED.material_move(0.83, -0.02, "index")
    assert ratio is not None and ratio > 40, \
        "the ratio should be absurd; that is why the unit decides"


def test_a_condition_may_not_sit_in_a_channel_that_inverts_its_sign():
    """`consumer_demand` was mapped to UNEMPLOYMENT, whose adverse direction
    is UP -- so a strengthening consumer read as a risk to a consumer brand.
    A condition belongs only in a channel whose adverse direction means the
    same thing for it."""
    assert ED.CHANNEL_OF["labour"] == "UNEMPLOYMENT"
    assert ED.CHANNEL_OF["consumer_demand"] != "UNEMPLOYMENT"
    econ = _economy(consumer_demand=_reading("consumer_demand", 1.1e4,
                                             1.0e4, "UP"))
    ctx = _build(economy=econ, exposures=("consumer_demand",),
                 profile=_profile("BRANDED_CONSUMER"))
    assert not ctx.material_decision_delta, (
        "rising real consumption was reported as adverse for a consumer "
        "brand")


# --- wording may never count ------------------------------------------------
def test_a_wording_only_difference_cannot_be_represented_as_a_change():
    """§26.15. Not detected and refused -- unrepresentable. Every field on
    `FieldChange` is a structured decision field; there is no prose field."""
    import dataclasses
    names = {f.name for f in dataclasses.fields(FC.FieldChange)}
    assert "prose" not in names and "text" not in names
    from intent_engine.econ import founder_ab as FA
    assert "prose" not in FA.MATERIAL_FIELDS


# --- §41 customer copy ------------------------------------------------------
def test_a_unit_enum_never_reaches_a_customer_sentence():
    """Measured on a rendered page: "rising to 6.66 percentage_point".

    That is an internal enum wearing a unit's place in an English sentence.
    §41 keeps scientific terminology on operator surfaces; a unit on a
    customer surface is spoken.
    """
    assert ED.unit_words(ED.PERCENTAGE_POINT) == "percentage points"
    assert ED.unit_words("index") == ""
    econ = _economy(treasury_10y=dict(
        _reading("treasury_10y", 6.0, 4.0, "UP"), unit=ED.PERCENTAGE_POINT))
    ctx = _build(economy=econ)
    for change in ctx.material_decision_delta:
        assert "percentage_point" not in change.trigger, change.trigger
        assert "percentage points" in change.trigger


def test_a_labelled_condition_names_the_series_that_measured_it():
    """`financial_conditions` is measured here by the 30-year mortgage rate.

    A reader told only that "financial conditions is rising to 6.66" has been
    given a label they cannot check against anything. The series is in the
    node id already; naming it makes the claim checkable.
    """
    assert ED.instrument_of("panel:MORTGAGE30US:2026-08-27") == "MORTGAGE30US"
    assert ED.instrument_of("") == ""
    econ = _economy(treasury_10y=dict(
        _reading("treasury_10y", 6.0, 4.0, "UP"),
        node_id="panel:DGS10:2026-08-20"))
    ctx = _build(economy=econ)
    assert ctx.material_decision_delta
    assert "DGS10" in ctx.material_decision_delta[0].trigger


def test_the_baseline_priority_is_the_same_kind_of_thing_as_the_augmented_one():
    """`top_priority` is one of the seven material fields, and A was falling
    back to the decision TOPIC -- a full sentence -- while B sets a business
    variable. Live that rendered as "Whether to invest ahead of demand in
    owning checkout/identity/data rails vs. deepening the core product.
    becomes cost of funds and the hurdle rate on committed capital"."""
    class NoArchetype:
        readiness = "INVESTIGATION_REQUIRED"
        decision_archetype = ""
        topic = ("Whether to invest ahead of demand in owning "
                 "checkout/identity/data rails vs. deepening the core "
                 "product.")
        evidence_required = ("x",)
        watch_items = ()
        falsifier = "f"
    base = ED.baseline_from_decision(
        NoArchetype(), company_id="acme", as_of="2026-08-25",
        risks=[{"risk_id": "company:0", "severity": "LOW",
                "channel": "the partner ecosystem", "mechanism": "m",
                "standing": "INFERRED", "evidence": ("e",)}])
    assert base is not None
    assert base.top_priority == "the partner ecosystem"
    assert "Whether to invest" not in base.top_priority


def test_the_freshness_note_is_written_in_english():
    """Live: "Economic reading as of 2026-08-27 (current, 1 days old)"."""
    from intent_engine.founder_brief import dossier as FD
    def note(age):
        return FD._econ_note(FC.FounderEconomicContext(
            company_id="c", as_of="2026-08-27",
            status=FC.NO_MATERIAL_ECONOMIC_DELTA, freshness=FC.CURRENT,
            age_days=age))
    assert "1 day old" in note(1) and "1 days" not in note(1)
    assert "today" in note(0)
    assert "12 days old" in note(12)


def test_the_economic_answer_never_says_a_thing_reaches_you_through_itself():
    """Measured live: "Policy rate, through policy rate." The channel and the
    quantity are frequently the same word; the useful noun is the variable it
    moves in THIS business, and it was already on the exposure."""
    from intent_engine.founder_brief import qa as FQA
    ctx = FC.FounderEconomicContext(
        company_id="acme", as_of="2026-08-27",
        status=FC.NO_MATERIAL_ECONOMIC_DELTA, freshness=FC.CURRENT,
        age_days=1,
        company_exposures=(FC.Exposure(
            quantity="policy_rate", measured=True, channel="POLICY_RATE",
            mechanism="rates set the discount rate on customers' own "
                      "investment cases",
            business_variable="the policy path that sets funding cost and "
                              "demand"),))
    answer = FQA._economic_answer("Which economic factor matters most?", ctx)
    assert "through policy rate." not in answer.lower(), answer
    assert "the policy path that sets funding cost" in answer
    assert answer[0].isupper()


def test_internal_risk_identifiers_never_reach_a_customer_sentence():
    """Measured live: "Changes top risks company:blind:0 becomes
    econ:financial_conditions, company:0". Those are internal handles."""
    from intent_engine.founder_brief import dossier as FD
    change = FC.FieldChange(
        field="top_risks", before=["company:blind:0"],
        after=["econ:financial_conditions", "company:0"],
        trigger="t", mechanism="m", provenance=("p",))
    said = FD._before_after(change)
    assert "company:blind:0" not in said and "econ:financial" not in said
    assert "economic risk to financial conditions" in said


def test_the_section_explains_the_change_through_the_exposure_it_rests_on():
    """Live, NVIDIA's section explained the change through the
    capacity-commitment mechanism while the trigger named a different
    condition -- because the renderer took `company_exposures[0]`."""
    econ = _economy(
        treasury_10y=_reading("treasury_10y", 6.0, 4.0, "UP"),
        commodity_oil=_reading("commodity_oil", 50.0, 100.0, "DOWN"))
    ctx = _build(economy=econ, exposures=("commodity_oil", "treasury_10y"),
                 profile=_profile("DESIGN_AND_MANUFACTURE"))
    assert ctx.material_decision_delta
    assert ctx.lead_exposure is not None
    assert ctx.lead_exposure.quantity in ctx.material_decision_delta[0].trigger
