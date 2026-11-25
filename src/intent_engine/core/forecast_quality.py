"""The forecast-quality gate: is this a forecast that CAN be scored honestly?

Quality is not accuracy. A forecast can be well-formed and wrong, which is
fine; a forecast that was already true when made, that compares a percent
series with a basis-point threshold, or whose claim says "every day" while
its rule reads one day, cannot be scored honestly at all, and the July
programme had all three. This gate decides admission to a REAL evaluation
ledger before the forecast is written. It never edits a forecast: it returns
findings, and the caller refuses (REJECT) or quarantines (QUARANTINE).

One normalised view (`Contract`) is built from each ledger's native record by
an adapter, so the same checks run on the July prediction ledger, the paper
forward ledger and the econ forward ledger.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

CONTRACT = "forecast_quality_gate.v1"
REJECT, QUARANTINE, WARN = "REJECT", "QUARANTINE", "WARN"
ADMIT = "ADMIT"

#: What every genuine forecast must carry (Phase 8 list). The value is the
#: severity when the field is empty.
REQUIRED = {
    "forecast_id": REJECT, "created_at": REJECT, "information_cutoff": REJECT,
    "target": REJECT, "prediction": REJECT, "horizon": REJECT,
    "resolution_rule": REJECT, "outcome_source": REJECT,
    "mechanism": QUARANTINE, "baseline": QUARANTINE,
    "model_version": QUARANTINE, "evidence_provenance": QUARANTINE,
    "invalidation": QUARANTINE,
}

#: Entities that are test fixtures, never companies. `t006-live` is the T006
#: wiring fixture (ROADMAP T006, 2026-07-20: "We're hiring a 4-person outbound
#: sales team before confirming strong product-market fit"). Its three
#: premortem forecasts (32bbf0c5, a4446e76, a5bca63d) are preserved unchanged
#: in the July ledger and excluded from every real-world statistic. No
#: resolution is manufactured for them.
TEST_FIXTURE_ENTITIES = frozenset({"t006-live"})


def classify_entity(entity_id: str) -> str:
    return "TEST_FIXTURE" if entity_id in TEST_FIXTURE_ENTITIES else "GENUINE"


_PERSIST_WORDS = re.compile(r"\b(remains?|stays?|throughout|every day|"
                            r"at all times|continuously|persist\w*)\b", re.I)


@dataclass
class Contract:
    ledger: str
    forecast_id: str
    created_at: str
    information_cutoff: str
    target: str
    prediction: object            # probability, direction or value
    horizon: str                  # human-readable horizon
    resolve_on: str               # the date the outcome is read
    resolution_rule: Optional[dict]
    outcome_source: str
    mechanism: str
    baseline: str
    model_version: str
    evidence_provenance: Sequence[str]
    invalidation: str
    claim_text: str = ""
    evidence_dates: Sequence[str] = ()
    classification: str = "GENUINE"   # or TEST_FIXTURE
    identity: tuple = ()              # duplicate key
    extra: dict = field(default_factory=dict)


@dataclass
class Finding:
    code: str
    severity: str
    detail: str


def verdict(findings: Sequence[Finding]) -> str:
    sev = {f.severity for f in findings}
    if REJECT in sev:
        return REJECT
    if QUARANTINE in sev:
        return QUARANTINE
    return ADMIT


# --- checks -----------------------------------------------------------------

def check(c: Contract, *, existing_identities: Iterable[tuple] = (),
          observe: Optional[Callable[[str, str], Optional[List[float]]]] = None
          ) -> List[Finding]:
    """All findings for one contract.

    `observe(series_id, as_of)` returns the values of a series knowable at
    `as_of` (oldest first), or None. Without it the data-dependent checks
    (already-true, impossible threshold) are reported as NOT_CHECKED, never
    as passed.
    """
    out: List[Finding] = []
    if c.classification != "GENUINE":
        out.append(Finding("NOT_A_REAL_FORECAST", REJECT,
                           f"classified {c.classification}; excluded from "
                           "real-world performance statistics"))
    for name, sev in REQUIRED.items():
        v = getattr(c, name)
        if v in (None, "", [], (), {}):
            out.append(Finding(f"MISSING_{name.upper()}", sev,
                               f"no {name.replace('_', ' ')}"))
    # time consistency
    try:
        created = c.created_at[:10]
        if c.information_cutoff and c.information_cutoff[:10] > created:
            out.append(Finding("CUTOFF_AFTER_CREATION", REJECT,
                               f"cutoff {c.information_cutoff} is after "
                               f"creation {created}"))
        if c.resolve_on and c.resolve_on[:10] <= created:
            out.append(Finding("RESOLVES_BEFORE_CREATION", REJECT,
                               f"outcome read on {c.resolve_on}, created "
                               f"{created}"))
        late = [d for d in c.evidence_dates
                if d and d[:10] > (c.information_cutoff or created)[:10]]
        if late:
            out.append(Finding("EVIDENCE_AFTER_CUTOFF", REJECT,
                               f"{len(late)} evidence item(s) dated after the "
                               f"cutoff, e.g. {late[0]}"))
    except (TypeError, AttributeError):
        out.append(Finding("UNPARSEABLE_DATES", REJECT, "dates not ISO"))
    # duplicates
    if c.identity and c.identity in set(existing_identities):
        out.append(Finding("DUPLICATE_CONTRACT", REJECT,
                           f"same target, rule, horizon and cutoff as an "
                           f"existing forecast: {c.identity}"))
    # the claim and the rule must say the same thing
    rule = c.resolution_rule or {}
    if c.claim_text and _PERSIST_WORDS.search(c.claim_text) and rule.get(
            "type") == "level" and not rule.get("every_observation"):
        out.append(Finding(
            "CLAIM_RULE_MISMATCH", QUARANTINE,
            "the claim asserts persistence ('"
            + _PERSIST_WORDS.search(c.claim_text).group(0)
            + "') but the rule reads a single observation"))
    if c.extra.get("contract_derived_on"):
        out.append(Finding(
            "CONTRACT_DERIVED_FROM_PROSE", WARN,
            f"the machine rule was derived from the original prose rule on "
            f"{c.extra['contract_derived_on']}; the prose is what was "
            "preregistered"))
    # probability sanity
    p = c.prediction
    if isinstance(p, float) and not (0.0 < p < 1.0):
        out.append(Finding("DEGENERATE_PROBABILITY", REJECT,
                           f"probability {p} is not strictly inside (0, 1)"))
    # data-dependent checks for threshold rules
    if rule.get("type") == "level" and rule.get("series"):
        if observe is None:
            out.append(Finding("THRESHOLD_NOT_CHECKED", WARN,
                               "no observer supplied; already-true and "
                               "impossible-threshold checks did not run"))
        else:
            vals = observe(rule["series"], (c.information_cutoff
                                            or c.created_at)[:10])
            out.extend(_threshold_findings(rule, vals))
    return out


def _holds(op: str, x: float, v: float) -> bool:
    return {">=": x >= v, ">": x > v, "<=": x <= v, "<": x < v}[op]


def _threshold_findings(rule: dict, vals: Optional[List[float]]
                        ) -> List[Finding]:
    if not vals:
        return [Finding("TARGET_NOT_OBSERVABLE", REJECT,
                        f"{rule['series']} has no value knowable at the "
                        "cutoff")]
    out = []
    last, v, op = vals[-1], float(rule["value"]), rule["op"]
    if _holds(op, last, v):
        out.append(Finding("ALREADY_TRUE_AT_CREATION", QUARANTINE,
                           f"last known {rule['series']}={last} already "
                           f"satisfies {op} {v}; the forecast is persistence"))
    lo, hi = min(vals), max(vals)
    span = max(hi - lo, abs(last) * 0.05, 1e-9)
    if v > hi + 20 * span or v < lo - 20 * span:
        out.append(Finding(
            "IMPOSSIBLE_OR_UNIT_MISMATCH", REJECT,
            f"threshold {v} is more than 20 ranges outside the series' "
            f"observed {lo}..{hi}; check units (percent vs basis points)"))
    return out


# --- adapters ---------------------------------------------------------------

def from_july(data: dict, *, classification: str = "GENUINE") -> Contract:
    rule = data.get("resolution_rule")
    return Contract(
        ledger="july_prediction_ledger", forecast_id=data.get("id", ""),
        created_at=data.get("created_at", ""),
        information_cutoff=data.get("created_at", "")[:10],
        target=(rule or {}).get("series") or data.get("instrument") or "",
        prediction=data.get("probability"), horizon=data.get("resolve_by", ""),
        resolve_on=(rule or {}).get("by") or data.get("resolve_by", ""),
        resolution_rule=rule, outcome_source=data.get("resolution_source") or "",
        mechanism="", baseline="", model_version="", evidence_provenance=(),
        invalidation="", claim_text=data.get("claim_text", ""),
        classification=classification,
        # Two models forecasting one target is a comparison, not a duplicate:
        # the claim names the model, so it is part of the identity.
        identity=(repr(rule), data.get("resolve_by"), data.get("source"),
                  data.get("claim_text")) if rule else ())


def from_paper(payload: dict) -> Contract:
    inv = payload.get("invalidation_condition") or {}
    return Contract(
        ledger="paper_forward_shadow", forecast_id=payload["forecast_id"],
        created_at=payload.get("decision_ts", ""),
        information_cutoff=payload.get("information_cutoff", ""),
        target=payload.get("target", ""),
        prediction=(payload.get("probability")
                    if payload.get("probability") is not None
                    else payload.get("direction")),
        horizon=f"{payload.get('horizon_sessions')} sessions",
        resolve_on="", resolution_rule={"type": "excess_return_sign",
                                        "entry": payload.get("entry_rule"),
                                        "exit": payload.get("exit_rule")},
        outcome_source=((payload.get("data_vintage") or {}).get("prices") or {})
        .get(payload.get("instrument"), {}).get("source", ""),
        mechanism=payload.get("causal_mechanism", ""),
        # A control or baseline IS the comparison; it needs no other one.
        baseline=(", ".join(payload.get("competing_hypotheses") or [])
                  or (payload.get("provenance") if payload.get("provenance")
                      in ("CONTROL", "BASELINE") else "")),
        model_version=payload.get("model_version", ""),
        evidence_provenance=list(payload.get("evidence_ids") or [])
        or [f"price_cutoff:{payload.get('price_cutoff')}"],
        invalidation=inv.get("forecast_voided_if", ""),
        evidence_dates=[payload.get("price_cutoff", "")],
        identity=(payload.get("policy_id"), payload.get("instrument"),
                  payload.get("decision_date"), payload.get("horizon_sessions")))


def from_econ(rec: dict, history: Sequence[dict] = ()) -> Contract:
    """`rec` is the FIRST record (the immutable registration). `history` is
    every record for the id; a machine contract or a creation date that was
    added later is taken from it and flagged, never silently merged."""
    later = [h for h in history if h.get("resolution_contract")]
    con = rec.get("resolution_contract") or (
        later[0]["resolution_contract"] if later else {})
    derived = "" if rec.get("resolution_contract") or not later else (
        later[0].get("created_at") or "unknown date")
    created = rec.get("created_at") or next(
        (h.get("created_at") for h in history if h.get("created_at")), "")
    return Contract(
        ledger="econ_forward", forecast_id=rec["expectation_id"],
        created_at=created,
        information_cutoff=rec.get("information_cutoff", ""),
        target=rec.get("quantity", ""), prediction=rec.get("confidence"),
        horizon=f"{rec.get('horizon_days')} days",
        resolve_on=rec.get("expires_at", ""),
        resolution_rule=dict(con, type="direction_vs_baseline") if con else None,
        outcome_source=f"ALFRED {con.get('series_id', '')} "
                       f"{con.get('vintage_policy', '')}" if con else "",
        mechanism=rec.get("mechanism", ""),
        baseline=rec.get("model", "") and (
            "BASE" if rec.get("model") == "AUGMENTED" else "persistence"),
        model_version=f"{rec.get('source', '')}:{rec.get('model', '')}",
        evidence_provenance=[rec.get("belief_id", "")] if rec.get(
            "belief_id") else [],
        invalidation=rec.get("falsifier", ""),
        claim_text=rec.get("resolution_rule", "")
        if isinstance(rec.get("resolution_rule"), str) else "",
        identity=(rec.get("quantity"), rec.get("information_cutoff"),
                  rec.get("horizon_days"), rec.get("model")),
        extra={"contract_derived_on": derived} if derived else {})


def admit_batch(contracts: Sequence[Contract], *, existing: Iterable[tuple] = (),
                observe=None) -> Dict[str, List]:
    """Gate a batch. Duplicates WITHIN the batch are caught too."""
    seen = set(existing)
    out = {ADMIT: [], QUARANTINE: [], REJECT: []}
    for c in contracts:
        f = check(c, existing_identities=seen, observe=observe)
        out[verdict(f)].append((c, f))
        if c.identity:
            seen.add(c.identity)
    return out
