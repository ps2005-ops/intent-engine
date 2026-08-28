"""§6/§8/§9: the founder engine's consumer of the economic world model.

WHAT THIS CLOSES
----------------
Before this, the two halves of the economic path never met. `econ_context`
read the shared state and handed a founder surface READINGS -- "policy rate is
rising to 4.33 as of 2026-07-31" -- which is a macro dashboard. Separately,
`analysis_selection._transmission` knew how a channel reaches THIS kind of
business, and was fed from a market dossier that is absent on most runs. So the
product either said nothing, or said something true about the economy and
nothing about the company.

This joins them. The shared state supplies the condition and its direction; the
company's own evidence supplies the exposure; the canonical business-model
transmission table supplies the mechanism; and only when all three are present
may a structured decision field move.

    EconomicState evidence -> company exposure -> mechanism -> decision field

Any missing link and the recommendation is left exactly as the company's own
evidence produced it. §6 is explicit about that and it is the whole difference
between informing a decision and decorating one.

WHY THE COMPARATOR IS THE RESEARCH COMPARATOR
---------------------------------------------
`founder_ab.compare` is not re-implemented here. The offline result -- 24
material of 60, 100% attributable, 36 deliberate abstentions -- is only
transferable to the product if the product asks the same question with the same
instrument. A second comparator on the product path would make §20's parity
check a comparison of two implementations rather than a check that the product
preserved the semantics.

WHAT BASELINE A IS ON THIS PATH
--------------------------------
The run's REAL analysis, projected into the structured decision vocabulary:
its recommended action, the channel it is about, its risks, its confidence, its
first information request. Not a stub -- `assert_baseline_is_real` is called on
it, and a run whose analysis produced nothing is reported INSUFFICIENT_EVIDENCE
rather than handed to the comparator as a free win.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

from intent_engine.econ import founder_ab as FA
from intent_engine.econ import founder_contract as FC

CONTRACT = "econ_decision.v1"

#: Which transmission channel each shared-state condition reaches a business
#: through. The channel vocabulary is `company_profile._TRANSMISSION`'s, and
#: this map is the ONLY place the two vocabularies are joined -- a second
#: mapping elsewhere is how one surface came to read a condition through a
#: channel another surface read it through differently.
#:
#: A condition absent from this map has no channel and therefore no mechanism,
#: so it can never move a decision field. That is a coverage gap, reported as
#: an information priority, and deliberately NOT a default channel: a default
#: would give every unmapped condition the same generic mechanism, which is
#: the template collapse this product keeps rediscovering.
CHANNEL_OF = {
    "policy_rate": "POLICY_RATE",
    "sofr": "MARKET_RATE",
    "ois": "MARKET_RATE",
    "treasury_2y": "MARKET_RATE",
    "treasury_5y": "MARKET_RATE",
    "treasury_10y": "MARKET_RATE",
    "treasury_30y": "MARKET_RATE",
    "real_yield": "MARKET_RATE",
    # THE SLOPE AND THE SPREAD ARE NOT THE LEVEL. Folding all three into
    # MARKET_RATE gave a bank three exposures through one channel whose sign
    # is deliberately unestablished, so it could never receive a reading at
    # all -- and a bank is the clearest case there is of an economic condition
    # reaching a business through a named mechanism.
    "curve_slope": "CURVE_SLOPE",
    "credit_spread_ig": "CREDIT_SPREAD",
    "credit_spread_hy": "CREDIT_SPREAD",
    "bank_stress": "CREDIT_SPREAD",
    "financial_conditions": "MARKET_RATE",
    "inflation": "INFLATION",
    "inflation_expectation": "INFLATION",
    "wages": "LABOR",
    # THE UNEMPLOYMENT CHANNEL CARRIES THE UNEMPLOYMENT RATE AND NOTHING ELSE.
    #
    # `consumer_demand` was mapped here too, and the channel's adverse
    # direction is UP -- because a RISING unemployment rate hurts. Real
    # consumption rising is the opposite reading, so the map inverted its
    # sign and a strengthening consumer would have been reported as a risk to
    # a consumer brand. A condition may only sit in a channel whose adverse
    # direction means the same thing for it.
    "labour": "UNEMPLOYMENT",
    "consumer_demand": "INDUSTRIAL_DEMAND",
    "growth": "INDUSTRIAL_DEMAND",
    "industrial_production": "INDUSTRIAL_DEMAND",
    "business_investment": "INDUSTRIAL_DEMAND",
    "housing": "INDUSTRIAL_DEMAND",
    "trade": "INDUSTRIAL_DEMAND",
    "fx_dxy": "CURRENCY",
    "fx_cross": "CURRENCY",
    "currency_basis": "CURRENCY",
    "commodity_oil": "COMMODITY",
    "commodity_gas": "COMMODITY",
    "commodity_copper": "COMMODITY",
    "commodity_gold": "COMMODITY",
    "commodity_ags": "COMMODITY",
    "commodity_curve": "COMMODITY",
}

#: WHICH WAY IS ADVERSE IS A COMPANY FACT, NOT A CHANNEL FACT.
#:
#: There was a table here mapping each channel to one adverse direction, and
#: the 60-case parity harness found it: Walmart was told rising inflation and
#: rising unemployment both hurt it, in four of six regimes, where the research
#: arm had said neither did. Walmart's own mechanism says inflation "widens the
#: everyday-low-price advantage" and its employment exposure is explicitly
#: MIXED. One sign per channel is the generic macro paragraph wearing a
#: mechanism, and it is exactly what §9 forbids.
#:
#: The sign now comes from the profile, keyed on (channel, business model) --
#: the same key as the mechanism, so the two cannot disagree. See
#: `company_profile.adverse_direction_for`, including why a pair with no
#: established sign returns "" and can never move a decision.

#: How far a condition has to move before it can change a decision, as a
#: proportion of its previous level. Declared here, before any live company
#: was scored, and it is the SAME number the research harness declared
#: (`run_decision_value.MATERIAL_MOVE`).
#:
#: WHY THIS IS LOAD-BEARING AND WAS MISSING. The first version of this module
#: treated any adverse-direction move as adverse. Run through the 60-case
#: parity harness it produced 38 material deltas against the research arm's
#: 24 -- nineteen of them on moves the research arm had already judged too
#: small to act on. A product that is LOUDER than the research behind it is
#: the exact failure §20 exists to catch, and it was invisible until the same
#: cases were run through both.
MATERIAL_MOVE = 0.03

#: The smallest previous level a PROPORTIONAL move can be computed from. Below
#: it, a relative change is a divide-by-a-near-zero-base and reports an
#: enormous move for an economically trivial one. It applies ONLY to series a
#: ratio is meaningful for; see `PERCENTAGE_POINT` below for the ones it is
#: not, which is where the real damage was.
MIN_BASE_FOR_RELATIVE = 0.01

#: The unit the producer stamps on a reading measured in PERCENTAGE POINTS.
#:
#: A ratio is the wrong instrument for these and the threshold guard was not
#: enough to save it: the 3-month/10-year slope was -0.02 a year ago and 0.83
#: now, and `MIN_BASE_FOR_RELATIVE` let 0.02 through -- so an 85 basis point
#: steepening was measured as a 4,250% move. Rates, spreads, slopes and
#: unemployment rates cross zero or sit near it routinely, and every one of
#: them takes an arithmetic DIFFERENCE in points.
#:
#: This is the same rule the research arm uses (`experiment.change` ->
#: `release.is_percentage_point`); what differs is only where it is looked up.
#: The producer knows the series and stamps the unit; the consumer knows the
#: condition and reads it. Neither needs the other's vocabulary.
PERCENTAGE_POINT = "percentage_point"

#: The evidence class every shared-state reading carries. A published series
#: read from the canonical core is exactly that and nothing more.
STATE_EVIDENCE_CLASS = "shared_economic_state"


def material_move(value, prior, unit: str = "") -> Optional[float]:
    """How far this condition has moved, in the transform its unit calls for.

    Percentage points take a difference; everything else takes a relative
    change. `None` means the move is not computable, and a move that is not
    computable never counts as material -- an unmeasurable change is not a
    large one.
    """
    if value is None or prior is None:
        return None
    try:
        now, then = float(value), float(prior)
    except (TypeError, ValueError):
        return None
    if str(unit) == PERCENTAGE_POINT:
        return now - then
    if abs(then) < MIN_BASE_FOR_RELATIVE:
        return None
    return (now - then) / abs(then)


#: How a unit is spoken on a customer surface. §41: `percentage_point` is an
#: internal enum and it reached a live page as "rising to 6.66
#: percentage_point", which is neither English nor a unit anyone writes.
_UNIT_WORDS = {PERCENTAGE_POINT: "percentage points", "percent": "percent",
               "index": "", "thousands": "thousand", "": ""}


def unit_words(unit: str) -> str:
    return _UNIT_WORDS.get(str(unit), str(unit).replace("_", " "))


def instrument_of(node_id: str) -> str:
    """The published series a condition was measured BY.

    `financial_conditions` is measured here by MORTGAGE30US, so a reader told
    only that "financial conditions is rising to 6.66" has been given a label
    they cannot check against anything. The series is already in the node id;
    naming it turns the claim into one a reader can look up.
    """
    parts = str(node_id or "").split(":")
    return parts[1] if len(parts) >= 2 else ""


def _today() -> str:
    return _dt.date.today().isoformat()


# =============================================================================
# baseline A, from the run's own analysis
# =============================================================================
def _severity_from(readiness: str, risk_count: int) -> str:
    if risk_count == 0:
        return "NONE"
    return {"DECISION_READY": "MEDIUM",
            "INVESTIGATION_REQUIRED": "MEDIUM"}.get(readiness, "LOW")


def _leading_channel(risks: Sequence[dict]) -> str:
    """The channel the company's own leading risk names."""
    for r in risks or ():
        channel = str((r or {}).get("channel") or "").strip()
        if channel:
            return channel
    return ""


def baseline_from_decision(decision, *, company_id: str, as_of: str,
                           risks: Sequence[dict] = (),
                           channel: str = "") -> Optional[FA.Analysis]:
    """The run's real recommendation, in the structured decision vocabulary.

    Returns None when the run produced nothing to compare -- no priority, no
    risk and no information request. That is INSUFFICIENT_EVIDENCE, not a
    baseline; handing the comparator an empty A is how a crippled control
    manufactures product value, and §3 forbids it.
    """
    # A'S PRIORITY MUST BE THE SAME KIND OF THING AS B'S.
    #
    # `top_priority` is one of the seven material fields, and it was falling
    # back to the decision TOPIC -- a full sentence -- while B sets it to a
    # business variable. Live that produced: "Whether to invest ahead of
    # demand in owning checkout/identity/data rails vs. deepening the core
    # product. becomes cost of funds and the hurdle rate on committed
    # capital", which reads as a non-sequitur because the two sides are a
    # question and a variable. The company's own leading risk names a
    # CHANNEL, which is the comparable thing.
    priority = (channel or str(getattr(decision, "decision_archetype", ""))
                or _leading_channel(risks)
                or str(getattr(decision, "topic", "")))
    readiness = str(getattr(decision, "readiness", "")) or "UNKNOWN"
    action = {"DECISION_READY": FA.PREPARE,
              "INVESTIGATION_REQUIRED": FA.INVESTIGATE}.get(readiness,
                                                            FA.MONITOR)
    built: List[FA.Risk] = []
    for r in risks:
        rid = str(r.get("risk_id") or r.get("id") or "")
        if not rid:
            continue
        built.append(FA.Risk(
            risk_id=rid,
            severity=str(r.get("severity") or "MEDIUM"),
            channel=str(r.get("channel") or priority),
            mechanism=str(r.get("mechanism") or ""),
            standing=str(r.get("standing") or FA.INFERRED),
            evidence=tuple(r.get("evidence") or ())))
    requests = tuple(str(x) for x in
                     (getattr(decision, "evidence_required", ()) or ())
                     if str(x).strip())[:3]
    watch = tuple(str(x) for x in (getattr(decision, "watch_items", ()) or ())
                  if str(x).strip())[:3]
    falsifier = str(getattr(decision, "falsifier", "") or "")
    if not priority or not built:
        return None
    return FA.Analysis(
        company_id=company_id, as_of=as_of, variant=FA.A,
        top_priority=priority, action=action, risks=tuple(built),
        scenario="POSSIBLE",
        confidence=("MEDIUM" if readiness == "DECISION_READY" else "LOW"),
        information_requests=requests or watch,
        falsifiers=((falsifier,) if falsifier else ()),
        evidence=tuple(dict.fromkeys(
            e for r in built for e in r.evidence)),
        unknowns=("the current economic environment",),
        prose="")


# =============================================================================
# the join: state x exposure x mechanism
# =============================================================================
def transmissions(*, readings: Sequence[dict], profile,
                  ) -> Tuple[List[dict], List[str]]:
    """(admitted channels, conditions with no mechanism into this business).

    `readings` are the company's evidenced exposures joined to the shared
    state (`econ_context.relevant_to`). `profile` is the canonical company
    profile; a business whose model class is unknown gets NOTHING, because a
    mechanism guessed from a sector is the generic paragraph in disguise.
    """
    out, unmapped = [], []
    if profile is None or not getattr(profile, "known", False):
        return out, [str(r.get("quantity", "")) for r in readings]
    for row in readings:
        quantity = str(row.get("quantity", ""))
        if not row.get("measured"):
            unmapped.append(quantity)
            continue
        channel = CHANNEL_OF.get(quantity, "")
        if not channel:
            unmapped.append(quantity)
            continue
        mechanism = profile.transmission_for(channel)
        if not mechanism and channel == "POLICY_RATE":
            mechanism = profile.transmission_for("MARKET_RATE")
        if not mechanism:
            unmapped.append(quantity)
            continue
        direction = str(row.get("direction", "")).upper()
        adverse_when = profile.adverse_direction_for(channel)
        move = material_move(row.get("value"), row.get("prior_value"),
                             row.get("unit") or "")
        # THREE CONDITIONS, AND THE MAGNITUDE IS THE ONE THAT WAS MISSING.
        # A move in the adverse direction that is smaller than the declared
        # threshold is a reading, not a reason; and a move whose size cannot
        # be computed is not treated as though it were large.
        adverse = (bool(adverse_when) and direction == adverse_when
                   and bool(row.get("moved", direction in ("UP", "DOWN")))
                   and move is not None and abs(move) >= MATERIAL_MOVE)
        out.append({"quantity": quantity, "channel": channel,
                    "mechanism": mechanism, "direction": direction,
                    "adverse": adverse, "move": move,
                    "adverse_when": adverse_when,
                    "value": row.get("value"),
                    "unit": row.get("unit") or "",
                    "as_of": row.get("as_of") or "",
                    "prior_value": row.get("prior_value"),
                    "prior_as_of": row.get("prior_as_of") or "",
                    "publisher": row.get("publisher") or "",
                    "node_id": row.get("node_id") or ""})
    return out, unmapped


def _business_variable(channel: str, profile) -> str:
    from intent_engine.executive.analysis_selection import (
        _CHANNEL_VARIABLE, _CHANNEL_VARIABLE_BY_MODEL,
    )
    model = str(getattr(profile, "business_model_class", "") or "")
    return (_CHANNEL_VARIABLE_BY_MODEL.get((channel, model))
            or _CHANNEL_VARIABLE.get(channel, ""))


def lead_row(rows: Sequence[dict]) -> Optional[dict]:
    """The adverse condition the delta rests on. One definition, one place."""
    adverse = [r for r in rows if r["adverse"]]
    if not adverse:
        return None
    return max(adverse, key=lambda r: (r["channel"] == "MARKET_RATE",
                                       r["quantity"]))


def augmented(base: FA.Analysis, *, rows: Sequence[dict], profile,
              company_name: str = "") -> Tuple[FA.Analysis, Dict[str, tuple]]:
    """B: everything A has, plus the economic state, and nothing else.

    Returns (B, triggers). `triggers` maps each decision field to the
    (trigger, mechanism, provenance) that moved it -- §13's attribution, built
    at the moment the field is set rather than reconstructed afterwards.
    """
    adverse = [r for r in rows if r["adverse"]]
    inputs = tuple(f"econ:{r['quantity']}@{r['as_of']}" for r in rows)
    risks = list(base.risks)
    for r in adverse:
        variable = _business_variable(r["channel"], profile)
        risks.append(FA.Risk(
            risk_id=f"econ:{r['quantity']}",
            severity="HIGH" if len(adverse) > 2 else "MEDIUM",
            channel=variable or r["channel"].replace("_", " ").lower(),
            mechanism=r["mechanism"], standing=FA.OBSERVED,
            evidence=(f"econ:{r['quantity']}@{r['as_of']}",)))
    if not adverse:
        # §7/§15 ABSTENTION. The state was read and does not bear on this
        # decision. B is A plus the record of having looked -- the economic
        # inputs are carried so the surface can say WHAT was read and still
        # changed nothing, which is the difference between abstaining and
        # having nothing.
        b = FA.Analysis(
            company_id=base.company_id, as_of=base.as_of, variant=FA.B,
            top_priority=base.top_priority, action=base.action,
            risks=tuple(risks), scenario=base.scenario,
            confidence=base.confidence,
            information_requests=base.information_requests,
            falsifiers=base.falsifiers,
            evidence=tuple(dict.fromkeys(base.evidence + inputs)),
            unknowns=base.unknowns, economic_inputs=inputs, prose="")
        return b, {}

    lead = lead_row(rows)
    variable = _business_variable(lead["channel"], profile)
    action = FA.PREPARE if len(adverse) > 1 else FA.INVESTIGATE
    if FA.ACTION_RANK[base.action] > FA.ACTION_RANK[action]:
        # NEVER DOWNGRADE. The company's own evidence already justified a
        # stronger posture; an economic reading is context and may not talk a
        # founder out of something their own record supports.
        action = base.action
    band = "LIKELY" if len(adverse) > 1 else base.scenario
    confidence = "MEDIUM" if base.confidence == "LOW" else base.confidence
    requests = tuple([f"how much of {variable or lead['channel']} is already "
                      f"contracted or hedged"]
                     + list(base.information_requests))[:3]
    name = company_name or base.company_id
    falsifiers = tuple([f"{name} reports {variable or lead['channel']} holding "
                        f"while {lead['quantity'].replace('_', ' ')} continues "
                        f"{lead['direction'].lower()}"]
                       + list(base.falsifiers))[:3]
    words = unit_words(lead.get("unit", ""))
    value = ("" if lead.get("value") is None
             else f"{lead['value']:g}{(' ' + words) if words else ''}")
    prior = ("" if lead.get("prior_value") is None
             else f" from {lead['prior_value']:g} a year earlier "
                  f"({lead.get('prior_as_of', '')})")
    instrument = instrument_of(lead.get("node_id", ""))
    source = ", ".join(x for x in (instrument, lead.get("publisher", "")) if x)
    trigger = (f"{lead['quantity'].replace('_', ' ')} is "
               f"{'rising' if lead['direction'] == 'UP' else 'falling'} to "
               f"{value}{prior} (as of {lead['as_of']}"
               f"{', ' + source if source else ''})")
    provenance = (f"econ:{lead['quantity']}@{lead['as_of']}",)
    triggers = {f: (trigger, lead["mechanism"], provenance)
                for f in FA.MATERIAL_FIELDS}
    b = FA.Analysis(
        company_id=base.company_id, as_of=base.as_of, variant=FA.B,
        top_priority=variable or lead["channel"], action=action,
        risks=tuple(risks), scenario=band, confidence=confidence,
        information_requests=requests, falsifiers=falsifiers,
        evidence=tuple(dict.fromkeys(base.evidence + inputs)),
        unknowns=base.unknowns + ("what is already contracted",),
        economic_inputs=inputs, prose="")
    return b, triggers


# =============================================================================
# forward status (§13/§14)
# =============================================================================
def forward_status(runtime_root, *, at: str = "", limit: int = 3
                   ) -> Tuple[List[FC.ForwardExpectation], str, dict]:
    """(open expectations, calibration status, counts).

    §14 IS ENFORCED BY WHERE THIS READS. The rehearsal ledger is a separate
    file that this function does not open. A rehearsal record could still
    reach the contract only by being written into the real store, and
    `FounderEconomicContext.__post_init__` refuses one by `source` -- two
    independent barriers, because the first is a convention and the second is
    a check.
    """
    from intent_engine.econ import store as EST
    at = at or _today()
    try:
        rows = EST.load(runtime_root, "expectation", upto=at)
    except Exception:                                       # noqa: BLE001
        return [], FC.PRE_CALIBRATION, {"open": 0, "resolved": 0,
                                        "error": "unreadable"}
    current: Dict[str, dict] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("expectation_id"):
            current[str(r["expectation_id"])] = r
    live = [r for r in current.values()
            if str(r.get("visibility", "PUBLIC")) == "PUBLIC"
            and str(r.get("source", "")).upper() != FC.REHEARSAL]
    resolved = [r for r in live if str(r.get("outcome", "OPEN")) != "OPEN"]
    openish = sorted((r for r in live
                      if str(r.get("outcome", "OPEN")) == "OPEN"),
                     key=lambda r: str(r.get("expires_at", "")))
    out = [FC.ForwardExpectation(
        expectation_id=str(r.get("expectation_id", "")),
        quantity=str(r.get("quantity", "")),
        expected_direction=str(r.get("expected_direction", "")),
        horizon_days=int(r.get("horizon_days") or 0),
        expires_at=str(r.get("expires_at", "")),
        resolution_rule=str(r.get("resolution_rule", "")),
        outcome=str(r.get("outcome", "OPEN")),
        source=str(r.get("source", "")),
        mechanism=str(r.get("mechanism", "")),
        falsifier=str(r.get("falsifier", ""))) for r in openish[:limit]]
    # PRE_CALIBRATION UNTIL SOMETHING HAS ACTUALLY RESOLVED. Not until enough
    # have -- until ANY have. Nothing has, and saying so is the claim.
    status = FC.PRE_CALIBRATION if not resolved else FC.CALIBRATING
    return out, status, {"open": len(openish), "resolved": len(resolved),
                         "next_resolution": (openish[0].get("expires_at", "")
                                             if openish else "")}


# =============================================================================
# §4/§6 the product contract, assembled once
# =============================================================================
def build(*, company_id: str, company_name: str, as_of: str, economy,
          exposures: Sequence[str], profile, decision,
          risks: Sequence[dict] = (), runtime_root=None,
          relations: Sequence[dict] = ()) -> FC.FounderEconomicContext:
    """One company's economic decision context. Never raises on missing data.

    The order of the early returns is the order a reader needs them in: no
    state at all is a DEPLOYMENT fact, no exposure is a COMPANY fact, and no
    baseline is a RUN fact. Collapsing them into one "unavailable" would tell
    an operator to fix the wrong thing.
    """
    from .econ_context import relevant_to

    if economy is None or not getattr(economy, "available", False):
        return FC.blocked(
            company_id,
            reason=(getattr(economy, "reason", "") or
                    "no shared economic state is available"),
            as_of=as_of, status=FC.BLOCKED_DATA)

    state_as_of = str(getattr(economy, "as_of", ""))
    freshness, age = FC.freshness_of(state_as_of, at=as_of or _today())
    readings = relevant_to(economy, exposures=list(exposures))
    if not readings:
        return FC.blocked(
            company_id,
            reason=("this company's own evidence establishes no exposure to "
                    "any condition the shared economic state measures, so no "
                    "economic reading is asserted for it. That is a gap in "
                    "this company's exposure map, not a quiet economy."),
            as_of=state_as_of, status=FC.INSUFFICIENT_EVIDENCE,
            # THE STATE IS PRESENT AND DATED. Only the exposure is missing, so
            # reporting the reading itself as "unavailable" describes the wrong
            # absence.
            freshness=freshness, age_days=age,
            computed_at=(as_of or _today()))

    rows, unmapped = transmissions(readings=readings, profile=profile)
    exposures_out = tuple(
        FC.Exposure(quantity=r["quantity"], measured=True,
                    channel=r["channel"],
                    mechanism=r["mechanism"],
                    business_variable=_business_variable(r["channel"], profile),
                    direction=r["direction"], value=r.get("value"),
                    unit=r.get("unit", ""), as_of=r.get("as_of", ""),
                    prior_value=r.get("prior_value"),
                    prior_as_of=r.get("prior_as_of", ""),
                    publisher=r.get("publisher", ""),
                    node_id=r.get("node_id", "")) for r in rows) + tuple(
        FC.Exposure(quantity=q, measured=False,
                    reason=("no mechanism connects this condition to this "
                            "business model, so it is not read as an "
                            "exposure here"))
        for q in dict.fromkeys(unmapped))

    # A'S PRIORITY IS THE RUN'S OWN, NOT AN ECONOMIC CHANNEL. Seeding the
    # baseline with a channel the economic state named would put the treatment
    # inside the control, and `top_priority` is one of the seven material
    # fields.
    base = baseline_from_decision(decision, company_id=company_id,
                                  as_of=as_of, risks=risks)
    if base is None:
        return FC.FounderEconomicContext(
            company_id=company_id, as_of=state_as_of,
            status=FC.INSUFFICIENT_EVIDENCE,
            economic_state_summary=_summary(rows, state_as_of),
            relevant_dimensions=tuple(r["quantity"] for r in rows),
            company_exposures=exposures_out, freshness=freshness,
            age_days=age, computed_at=(as_of or _today()),
            reason=("this run's own analysis produced no recommendation to "
                    "compare against, so no economic change to it can be "
                    "measured. The economic reading is shown; the decision "
                    "delta is not claimed."),
            provenance=_provenance(rows),
            information_priorities=_priorities(rows, unmapped, profile),
            **_forward_kwargs(runtime_root, as_of))
    FA.assert_baseline_is_real(base)
    b, triggers = augmented(base, rows=rows, profile=profile,
                            company_name=company_name)
    delta = FA.compare(base, b, regime="live", triggers=triggers)

    changes, refused, seen_triggers = [], [], []
    for f in delta.fields:
        if not f.material:
            continue
        change = FC.FieldChange(
            field=f.field, before=f.before, after=f.after,
            trigger=f.trigger, mechanism=f.mechanism,
            provenance=tuple(f.provenance), why_material=f.why_material)
        ok, code = FC.admit(change, freshness=freshness,
                            evidence_classes=(STATE_EVIDENCE_CLASS,),
                            already_triggered_by=seen_triggers)
        if ok:
            changes.append(change)
        else:
            refused.append({"field": f.field, "code": code,
                            "reason": FC.refusal_reason(code)})
    # §14 DAMAGE, on the product path and with the same detector.
    damage = FA.detect_damage(base, b, regime="live",
                              stale_days=(age if age >= 0 else None))
    for d in damage:
        refused.append({"field": "*", "code": d.kind, "reason": d.detail})
    if damage:
        # A change that made the analysis worse is not shipped, whatever it
        # moved. Offline this is a counted row; here it is a sentence a
        # founder would act on, so it is dropped rather than annotated.
        changes = []

    supported, candidate = _relations(relations)
    fwd = _forward_kwargs(runtime_root, as_of)
    speaking = bool(changes)
    return FC.FounderEconomicContext(
        company_id=company_id, as_of=state_as_of,
        status=FC.COMPLETE if speaking else FC.NO_MATERIAL_ECONOMIC_DELTA,
        economic_state_summary=_summary(rows, state_as_of),
        relevant_dimensions=tuple(r["quantity"] for r in rows),
        company_exposures=exposures_out,
        supported_relations=supported, candidate_relations=candidate,
        material_decision_delta=tuple(changes),
        abstention_status=("" if speaking else FC.NO_MATERIAL_ECONOMIC_DELTA),
        abstention_reason=("" if speaking else _abstention_reason(rows,
                                                                  refused)),
        uncertainty=dict(getattr(economy, "uncertainty", {}) or {}),
        falsifiers=tuple(b.falsifiers) if speaking else (),
        information_priorities=_priorities(rows, unmapped, profile),
        provenance=_provenance(rows),
        freshness=freshness, age_days=age,
        computed_at=(as_of or _today()),
        # THE EXPOSURE THE CHANGE RESTS ON, not the first one measured. Live,
        # NVIDIA's section explained the change through the
        # capacity-commitment mechanism while the trigger named a different
        # condition entirely.
        lead_exposure=_lead_exposure(exposures_out, lead_row(rows)),
        refused=tuple(refused), **fwd)


def _lead_exposure(exposures, lead):
    if lead is None:
        return None
    return next((e for e in exposures
                 if e.measured and e.quantity == lead["quantity"]), None)


def _forward_kwargs(runtime_root, as_of: str) -> dict:
    if runtime_root is None:
        return {"forward_expectations": (),
                "calibration_status": FC.PRE_CALIBRATION}
    exps, status, _counts = forward_status(runtime_root, at=as_of)
    return {"forward_expectations": tuple(exps), "calibration_status": status}


def _summary(rows: Sequence[dict], as_of: str) -> str:
    if not rows:
        return ""
    parts = []
    for r in rows[:3]:
        moving = {"UP": "rising", "DOWN": "falling",
                  "FLAT": "unchanged"}.get(r["direction"], "at a level with "
                                           "no earlier reading to compare")
        parts.append(f"{r['quantity'].replace('_', ' ')} {moving}")
    return (f"As of {as_of} the shared economic state reads "
            + "; ".join(parts) + ".")


def _abstention_reason(rows: Sequence[dict], refused: Sequence[dict]) -> str:
    """WHY nothing changed. §7 -- concise, and never a missing section."""
    blocked = [r for r in refused if r.get("code") in FC.REFUSALS
               and r.get("code") != FC.NOT_MATERIAL]
    if blocked:
        first = blocked[0]
        return (f"The economic state moved this company's channels, but the "
                f"change was not admitted: {first.get('reason', '')}")
    if not rows:
        return ("No condition the shared state measures reaches this business "
                "through an established mechanism.")
    names = ", ".join(r["quantity"].replace("_", " ") for r in rows[:3])
    return (f"{names} were read against this company's own exposures and "
            f"none of them moves adversely through a channel that reaches "
            f"this business, so the recommendation is unchanged.")


def _priorities(rows: Sequence[dict], unmapped: Sequence[str],
                profile) -> Tuple[str, ...]:
    """§23. The highest-value next unknown, named. Never 'more research'."""
    out: List[str] = []
    for r in sorted(rows, key=lambda x: (not x["adverse"], x["quantity"]))[:2]:
        variable = _business_variable(r["channel"], profile)
        if variable:
            out.append(f"How much of {variable} is already contracted, hedged "
                       f"or repriced")
    for q in list(dict.fromkeys(unmapped))[:1]:
        out.append(f"Whether {q.replace('_', ' ')} reaches this business "
                   f"through a mechanism we have not established")
    return tuple(dict.fromkeys(out))[:3]


def _provenance(rows: Sequence[dict]) -> Tuple[FC.Provenance, ...]:
    return tuple(FC.Provenance(
        claim=f"{r['quantity'].replace('_', ' ')} is {r['direction'].lower()}",
        source=r.get("publisher", "") or "shared economic state",
        observation=r.get("node_id", "") or f"econ:{r['quantity']}",
        as_of=r.get("as_of", ""),
        evidence_type=STATE_EVIDENCE_CLASS,
        derived_from=(f"econ:{r['quantity']}",)) for r in rows)


def _relations(relations: Sequence[dict]
               ) -> Tuple[Tuple[FC.Relation, ...], Tuple[FC.Relation, ...]]:
    """§12/§26.4. A CANDIDATE never crosses into the supported list.

    The split is made HERE, once, from the relation's own recorded state --
    not by a renderer deciding which list to put a row in.
    """
    supported, candidate = [], []
    for r in relations or ():
        if not isinstance(r, dict):
            continue
        state = str(r.get("state") or r.get("standing") or "").upper()
        rel = FC.Relation(
            statement=str(r.get("statement") or r.get("proposition") or ""),
            standing=(FC.SUPPORTED if state.startswith("SUPPORTED")
                      else FC.CANDIDATE),
            mechanism=str(r.get("mechanism", "")),
            falsifier=str(r.get("falsifier", "")),
            evidence=tuple(r.get("evidence") or ()))
        (supported if rel.standing == FC.SUPPORTED else candidate).append(rel)
    return tuple(supported), tuple(candidate)
