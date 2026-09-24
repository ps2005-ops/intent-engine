"""How much a CAUSAL CLAIM has earned — which is not how a mechanism scored.

THE DISTINCTION THIS MODULE EXISTS TO HOLD
------------------------------------------
`mechanism_calibration` asks: when this rule fired, did the thing it predicted
happen? That is a question about a PREDICTOR, and a predictor can be excellent
while the causal story behind it is wrong. "Ice cream sales predict drownings"
is a well-calibrated mechanism and a false causal edge.

So a mechanism scoring well is not evidence that its edge is real, and this
module refuses to inherit the other's numbers. The two are computed from the
same episodes and answer different questions:

    mechanism_calibration   did the preregistered direction hold?
    causal_calibration      did it hold ACROSS ENOUGH DIFFERENT SETTINGS
                            that a common cause is no longer the simpler
                            explanation?

WHY SCOPE IS THE WHOLE MEASUREMENT
----------------------------------
Three confirmations at one company under one regime is one company agreeing
with itself three times, and a counter that only totals tests cannot tell that
apart from three independent results. So every family reports company scope,
industry scope and regime scope, and NOTHING is promoted past EMERGING on
company scope alone.

That is why almost everything here reads UNMEASURABLE or EMERGING and will for
a long time. `UNMEASURABLE` is not zero: it says the question has not been put
to the evidence enough times for an answer to exist, which is a different
finding from "the edge failed".

WHAT THIS MODULE WILL NOT SAY
-----------------------------
`ESTABLISHED`. It is not in the vocabulary. `mechanism_calibration` has it and
uses it at five tests, which is defensible for a predictor and is not
defensible for a causal claim. The strongest thing sayable here is
REPEATEDLY_SUPPORTED, and it requires independence the engine does not
currently have for any family.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "causal_calibration.v1"

# --- statuses, weakest first ------------------------------------------------
UNMEASURABLE = "UNMEASURABLE"          # too few tests for any answer
EMERGING = "EMERGING"                  # tested, but not across settings
CONTESTED = "CONTESTED"                # tested enough, both directions seen
SUPPORTED = "SUPPORTED"                # holds across independent companies
REPEATEDLY_SUPPORTED = "REPEATEDLY_SUPPORTED"   # and across industries

STATUSES = (UNMEASURABLE, EMERGING, CONTESTED, SUPPORTED,
            REPEATEDLY_SUPPORTED)

#: The floor at which a result starts to mean anything, matching
#: `mechanism_calibration.MIN_TESTS`. A causal claim must not be easier to
#: establish than the predictor built on top of it, and an earlier draft of
#: this module set the floor at 3 — which made the MINIMUM measurable sample
#: simultaneously sufficient for the STRONGEST status. Three real tests took
#: `demand_strengthening` straight to REPEATEDLY_SUPPORTED, which is the
#: promotion-from-a-tiny-sample this module exists to refuse.
MIN_TESTS = 5

#: SUPPORTED requires the edge to have held at COMPANIES THAT ARE NOT EACH
#: OTHER. This is the constraint that keeps a single well-covered company from
#: promoting a family on its own.
MIN_COMPANIES_FOR_SUPPORTED = 3

#: REPEATEDLY_SUPPORTED additionally requires more than one industry, because
#: an edge that only ever holds inside one sector may be a fact about that
#: sector rather than about the mechanism.
MIN_INDUSTRIES_FOR_REPEATED = 2

#: And materially more evidence than the floor. Every threshold below is
#: strictly greater than the one above it, so no sample size can reach a
#: status that a larger sample could not.
MIN_TESTS_FOR_SUPPORTED = 5
MIN_TESTS_FOR_REPEATED = 8
MIN_COMPANIES_FOR_REPEATED = 5

#: Any contradiction at all, once a family is measurable, makes it CONTESTED.
#: Deliberately strict: a causal claim that has failed once is a claim with a
#: known exception, and "mostly holds" is the phrase this project has had to
#: retract most often.
CONTESTED_ON_ANY_CONTRADICTION = True

_INFORMATIVE = {"CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED"}


@dataclass(frozen=True)
class CausalFamily:
    """One causal claim's standing, and every reason it is not stronger."""
    causal_family: str
    cause: str
    effect: str
    tests: int
    supported: int
    contradicted: int
    ambiguous: int
    unresolved: int
    company_scope: Tuple[str, ...]
    industry_scope: Tuple[str, ...]
    regime_scope: Tuple[str, ...]
    last_tested: str
    status: str
    reason: str
    what_would_promote_it: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "causal_family": self.causal_family,
            "cause": self.cause, "effect": self.effect,
            "tests": self.tests, "supported": self.supported,
            "contradicted": self.contradicted, "ambiguous": self.ambiguous,
            "unresolved": self.unresolved,
            "company_scope": list(self.company_scope),
            "companies": len(self.company_scope),
            "industry_scope": list(self.industry_scope),
            "industries": len(self.industry_scope),
            "regime_scope": list(self.regime_scope),
            "last_tested": self.last_tested, "status": self.status,
            "reason": self.reason,
            "what_would_promote_it": self.what_would_promote_it,
        }


def calibrate(rows: Sequence[dict], *,
              industry_of: Optional[Dict[str, str]] = None,
              regime_of: Optional[Dict[str, str]] = None,
              links: Optional[Dict[str, Tuple[str, str]]] = None
              ) -> Tuple[CausalFamily, ...]:
    """Grade each causal family by the episodes that actually tested it.

    Only families with a stated cause and a SEPARATELY OBSERVABLE effect are
    graded. A family whose "effect" restates its cause has nothing to
    calibrate, and counting it would inflate every total in this report.
    """
    from . import causal_episodes as CE

    pairs = dict(links or CE._LINKS and {
        key: (value[0], value[1]) for key, value in CE._LINKS.items()})
    industries = industry_of or {}
    regimes = regime_of or {}

    expectations = {r.get("expectation_id"): r for r in rows
                    if r.get("record") == "expectation"}

    tests: Dict[str, List[dict]] = collections.defaultdict(list)
    open_by_family: Dict[str, int] = collections.Counter()
    for exp in expectations.values():
        family = str(exp.get("metric") or "")
        if family in pairs:
            open_by_family[family] += 1

    for row in rows:
        if row.get("record") != "reconciliation":
            continue
        exp = expectations.get(row.get("expectation_id")) or {}
        family = str(exp.get("metric") or "")
        if family not in pairs:
            continue
        if row.get("outcome") in _INFORMATIVE:
            tests[family].append(row)

    out: List[CausalFamily] = []
    for family, (cause, effect) in sorted(pairs.items()):
        mine = tests.get(family, [])
        supported = sum(1 for t in mine if t.get("outcome") == "CONFIRMED")
        contradicted = sum(1 for t in mine
                           if t.get("outcome") == "CONTRADICTED")
        ambiguous = sum(1 for t in mine
                        if t.get("outcome") == "PARTIALLY_CONFIRMED")
        subjects = tuple(sorted({str(t.get("subject") or "") for t in mine}
                                - {""}))
        industry = tuple(sorted({industries.get(s, "unknown")
                                 for s in subjects}))
        regime = tuple(sorted({regimes.get(s, "unknown") for s in subjects}))
        last = max((str(t.get("evaluated_at") or "")[:10] for t in mine),
                   default="")
        unresolved = max(open_by_family.get(family, 0) - len(mine), 0)

        status, reason, promote = _grade(
            tests=len(mine), supported=supported, contradicted=contradicted,
            companies=len(subjects), industries=len(industry))
        out.append(CausalFamily(
            causal_family=family, cause=cause, effect=effect,
            tests=len(mine), supported=supported, contradicted=contradicted,
            ambiguous=ambiguous, unresolved=unresolved,
            company_scope=subjects, industry_scope=industry,
            regime_scope=regime, last_tested=last, status=status,
            reason=reason, what_would_promote_it=promote))
    return tuple(out)


def _grade(*, tests: int, supported: int, contradicted: int,
           companies: int, industries: int) -> Tuple[str, str, str]:
    """The status, why, and what is missing. Order encodes what outranks what."""
    if tests == 0:
        return UNMEASURABLE, (
            "never tested: no expectation of this family has resolved "
            "informatively. This is not a finding about the edge — the "
            "question has not been put to the evidence at all"
        ), "one informative reconciliation of this family, at any company"

    if tests < MIN_TESTS:
        direction = ("all of them contradicting" if contradicted == tests
                     else f"{supported} confirming, {contradicted} "
                          f"contradicting")
        return EMERGING, (
            f"{tests} informative test(s) ({direction}) against a floor of "
            f"{MIN_TESTS}; below that floor a result cannot be told from a "
            f"coincidence, whichever way it went"
        ), (f"{MIN_TESTS - tests} more informative reconciliation(s) of this "
            f"family, at companies that are not each other")

    if contradicted and CONTESTED_ON_ANY_CONTRADICTION:
        return CONTESTED, (
            f"{supported} confirmation(s) and {contradicted} "
            f"contradiction(s) across {companies} compan(y/ies); a causal "
            f"claim with a known exception is contested, not 'mostly holding'"
        ), ("an account of WHEN the edge operates that the contradicting "
            "case fails, tested prospectively")

    if companies < MIN_COMPANIES_FOR_SUPPORTED or \
            tests < MIN_TESTS_FOR_SUPPORTED:
        return EMERGING, (
            f"{tests} test(s) across only {companies} compan(y/ies); a "
            f"company agreeing with itself repeatedly is one observation "
            f"repeated, and cannot separate the mechanism from something "
            f"true of that company"
        ), (f"the same result at "
            f"{max(MIN_COMPANIES_FOR_SUPPORTED - companies, 0)} more "
            f"independent compan(y/ies), over at least "
            f"{MIN_TESTS_FOR_SUPPORTED} tests in total")

    if industries < MIN_INDUSTRIES_FOR_REPEATED or \
            tests < MIN_TESTS_FOR_REPEATED or \
            companies < MIN_COMPANIES_FOR_REPEATED:
        return SUPPORTED, (
            f"{supported} confirmation(s) across {companies} independent "
            f"companies with no contradiction, all within {industries} "
            f"industr(y/ies) over {tests} test(s) — short of the "
            f"{MIN_TESTS_FOR_REPEATED} tests, {MIN_COMPANIES_FOR_REPEATED} "
            f"companies and {MIN_INDUSTRIES_FOR_REPEATED} industries the "
            f"strongest status requires"
        ), (f"the same result in "
            f"{max(MIN_INDUSTRIES_FOR_REPEATED - industries, 0)} further "
            f"industr(y/ies), across "
            f"{max(MIN_COMPANIES_FOR_REPEATED - companies, 0)} more "
            f"companies and {max(MIN_TESTS_FOR_REPEATED - tests, 0)} more "
            f"tests")

    return REPEATEDLY_SUPPORTED, (
        f"{supported} confirmation(s) across {companies} companies and "
        f"{industries} industries with no contradiction"
    ), ("nothing further is required for this status; it is the strongest "
        "this module can say, and it is still not ESTABLISHED")


def summarise(families: Sequence[CausalFamily]) -> dict:
    counts = collections.Counter(f.status for f in families)
    measurable = [f for f in families if f.status != UNMEASURABLE]
    return {
        "contract": CONTRACT,
        "families": len(families),
        "by_status": {s: counts.get(s, 0) for s in STATUSES},
        "measurable": len(measurable),
        "unmeasurable": counts.get(UNMEASURABLE, 0),
        "total_tests": sum(f.tests for f in families),
        "total_contradictions": sum(f.contradicted for f in families),
        "widest_company_scope": max((len(f.company_scope) for f in families),
                                    default=0),
        "families_detail": [f.as_dict() for f in families],
        "note": ("a well-calibrated mechanism is not a proven edge: a "
                 "predictor can be accurate while its causal story is "
                 "wrong. UNMEASURABLE means the question has not been put "
                 "enough times, which is not the same as the edge failing. "
                 "ESTABLISHED is deliberately absent from this vocabulary"),
    }
