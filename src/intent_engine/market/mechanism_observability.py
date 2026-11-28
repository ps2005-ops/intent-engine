"""Which of the 16 belief mechanisms can reality actually test, and how.

WHY THIS EXISTS
---------------
`mechanism_calibration` reports 12 of 16 families UNFALSIFIABLE_BY_OBSERVATION
and stops there. That is true and not actionable: it does not say whether a
family is untestable in principle, testable with an adapter nobody has
written, or testable but starved of evidence. Those need different work, and
calling all three "unfalsifiable" hides which work is worth doing.

This registry is the observation contract for each mechanism. It is checked
against the code that forms and binds beliefs (tests pin it), so it cannot
claim a channel that `observation_binding` does not implement.

CLASSES
-------
DIRECT              Bound today. The evidence type that proposes the belief
                    also arrives pointing the other way, so a test can fail.
PROXY               A falsifier is reachable through a DIFFERENT, already
                    classified evidence type (a layoff refutes "adding people
                    ahead of the work"). Defined, not yet bound.
PARTIAL             Confirmation is observable ("further X"); contradiction
                    needs a reversal reader (capex cut, dividend cut, deal
                    abandoned) that does not exist, AND a base rate, because
                    "further acquisitions" from an acquisitive company is
                    near-certain and confirms nothing.
UNOBSERVABLE        The current sources do not carry the observation.
RESEARCH_ONLY       The falsifier is an interpretation, not an observation.

Only DIRECT may be represented as a calibrated predictive claim. Everything
else is an explicitly exploratory hypothesis until it earns a channel.

MEASURED 2026-11-26 on the live ledger (206 expectations): later evidence
about the same subject existed for most PARTIAL families, and genuine reversal
wording appeared in it essentially never (one case, about a takeover TARGET,
not the subject). So reversal readers would today produce ~0 contradictions.
That is why PARTIAL is not bound: a channel that can only confirm is a ratchet.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional, Tuple

DIRECT = "DIRECT"
PROXY = "PROXY"
PARTIAL = "PARTIAL"
UNOBSERVABLE = "UNOBSERVABLE"
RESEARCH_ONLY = "RESEARCH_ONLY"
CLASSES = (DIRECT, PROXY, PARTIAL, UNOBSERVABLE, RESEARCH_ONLY)

REGISTRY_VERSION = "mechanism_observability.v1"


@dataclass(frozen=True)
class ObservationContract:
    family: str
    observability: str
    variable: str                 # what is measured about the subject
    confirm: str
    contradict: str
    inconclusive: str
    sources: Tuple[str, ...]      # evidence types eligible as the observation
    contradicting_sources: Tuple[str, ...]
    confounders: Tuple[str, ...]
    needs: str                    # the next piece of work, "" if bound
    calibrated_claim_allowed: bool

    def as_dict(self) -> dict:
        return asdict(self)


_ABSENCE = "no qualifying observation by the window end: OPEN/EXPIRED, never contradicted"
_REVERSAL = ("a reversal reader for this type (subject-anchored, held-out "
             "development set) and a per-subject base rate of the confirming "
             "event, so a confirmation is scored as lift over that rate")


def _c(family, cls, variable, confirm, contradict, sources, contra=(),
       confounders=(), needs="", inconclusive=_ABSENCE):
    return ObservationContract(
        family=family, observability=cls, variable=variable, confirm=confirm,
        contradict=contradict, inconclusive=inconclusive,
        sources=tuple(sources), contradicting_sources=tuple(contra),
        confounders=tuple(confounders), needs=needs,
        calibrated_claim_allowed=(cls == DIRECT))


REGISTRY: Dict[str, ObservationContract] = {c.family: c for c in (
    _c("demand_strengthening", DIRECT, "next reported revenue or guidance figure",
       "next figure higher than the one that opened the belief",
       "next figure flat or lower",
       ("EARNINGS_RESULT", "EARNINGS_SURPRISE", "GUIDANCE_REVISION",
        "INVENTORY_CHANGE", "COMMITTED_DEMAND"),
       ("EARNINGS_RESULT", "EARNINGS_SURPRISE", "GUIDANCE_REVISION"),
       ("price or FX effects in reported revenue", "acquired revenue",
        "same-quarter recaps (refused by same_reporting_event)")),
    _c("demand_weakening", DIRECT, "next reported revenue or guidance figure",
       "next figure flat or lower", "next figure higher",
       ("EARNINGS_RESULT", "EARNINGS_SURPRISE", "GUIDANCE_REVISION",
        "INVENTORY_CHANGE", "COMMITTED_DEMAND"),
       ("EARNINGS_RESULT", "EARNINGS_SURPRISE", "GUIDANCE_REVISION"),
       ("divestitures shrinking reported revenue", "FX translation")),
    _c("pricing_power", DIRECT, "the subject's own list or contract prices",
       "a further increase, or margin holding as volume softens",
       "a subsequent price cut or discounting programme",
       ("PRICING_SIGNAL", "PRICE_CHANGE"), ("PRICING_SIGNAL", "PRICE_CHANGE"),
       ("cost pass-through mistaken for pricing power",
        "analyst price targets (refused by event_patterns)")),
    _c("market_share_seeking", DIRECT, "the subject's own prices",
       "further price reductions or bundling",
       "prices raised again or margin stated as priority",
       ("PRICING_SIGNAL", "PRICE_CHANGE"), ("PRICING_SIGNAL", "PRICE_CHANGE"),
       ("input-cost deflation passed through",)),
    _c("capacity_hiring", PROXY, "the subject's headcount direction",
       "further hiring, or revenue per employee falling",
       "a LAYOFF of the subject within the window (hiring reversed)",
       ("HIRING",), ("LAYOFF",),
       ("hiring in one unit while cutting another", "acquired headcount"),
       needs="bind LAYOFF as the contradicting type; HIRING evidence is thin "
             "(10 rows in the ledger), so expect few tests"),
    _c("margin_protection", PROXY, "the subject's cost base and headcount",
       "further cost reductions, or margin holding on flat revenue",
       "HIRING by the subject (headcount resuming growth) before margin improves",
       ("LAYOFF", "COST_SHOCK"), ("HIRING",),
       ("restructuring charges depressing reported margin",
        "fund holding notices (refused by event_patterns since 2026-11-26)"),
       needs="bind HIRING as the contradicting type; 7 margin_protection "
             "beliefs opened by holding notices must be withdrawn first "
             "(PROPOSED_belief_invalidations_2026-11-26.jsonl)"),
    _c("capacity_expansion", PARTIAL, "the subject's committed capital",
       "further capital commitments or capacity coming online",
       "the programme paused, cancelled, or capex cut",
       ("CAPEX_SIGNAL",), (), ("capex re-phasing reported as a cut",),
       needs=_REVERSAL),
    _c("capital_return_posture", PARTIAL, "dividends and buybacks",
       "further dividend increases or buyback authorisations",
       "dividend held or cut, buyback suspended",
       ("CAPITAL_RETURN",), (),
       ("routine annual dividend increases (high base rate)",
        "capex alongside buybacks is NOT redirection"),
       needs=_REVERSAL),
    _c("consolidation_posture", PARTIAL, "the subject's own deals",
       "further acquisitions or divestitures",
       "an acquisition abandoned by the subject, or a build-first statement",
       ("MA_ACTIVITY",), (),
       ("the subject as a TARGET (Stripe abandoning a PayPal bid is not "
        "PayPal's posture)",), needs=_REVERSAL),
    _c("partner_led_distribution", PARTIAL, "the subject's distribution channel",
       "further partnership or joint-venture announcements",
       "a partnership ended or distribution brought in-house",
       ("PARTNERSHIP",), (), ("marketing 'partnerships' with no distribution",),
       needs=_REVERSAL),
    _c("procurement_momentum", PARTIAL, "awards in the subject's category",
       "further contract awards or task orders",
       "a competitive loss or an award to a rival in the same programme",
       ("CONTRACT_AWARD", "PROCUREMENT_SIGNAL"), (),
       ("awards re-announced at each funding increment",),
       needs=_REVERSAL + "; award-to-rival needs programme identity"),
    _c("productization", PARTIAL, "the subject's product catalogue",
       "further launches or GA announcements",
       "the offering withdrawn, or delivery moving back to bespoke work",
       ("PRODUCT_LAUNCH",), (), ("feature releases counted as products",),
       needs=_REVERSAL),
    _c("regulatory_pressure", PARTIAL, "proceedings against the subject",
       "further actions, filings or disclosed proceedings",
       "the matter closed, dismissed or settled without obligations",
       ("REGULATORY_ACTION",), (),
       ("class-action solicitation adverts", "risk-factor boilerplate"),
       needs=_REVERSAL + "; matter identity to tie a dismissal to its action"),
    _c("supply_constraint", UNOBSERVABLE, "supplier lead times for the subject",
       "further commentary on lead times or shortages",
       "lead times normalise, or shortfalls attributed to demand",
       ("SUPPLIER_COMMENT",), (), ("industry-wide shortages vs the subject's",),
       needs="a source that carries supplier commentary (4 rows ledger-wide)"),
    _c("competitor_aggression", UNOBSERVABLE, "a rival's moves in the segment",
       "further competitor moves in the same segment",
       "the rival withdraws, raises prices, or exits",
       ("COMPETITOR_ACTION",), (),
       ("the observation is about another actor, so identity must resolve "
        "the RIVAL, not the subject",),
       needs="rival-resolved evidence (4 rows ledger-wide)"),
    _c("leadership_transition", RESEARCH_ONLY, "the subject's stated priorities",
       "a named successor, or a stated change of priorities",
       "an internal continuity appointment with no stated change",
       ("EXECUTIVE_CHANGE",), (),
       ("'continuity' and 'change of priorities' are both interpretations",),
       needs="an operational definition of a priority change that two "
             "annotators agree on; until then, not a predictive claim"),
)}


def contract_for(family: str) -> Optional[ObservationContract]:
    return REGISTRY.get(family)


def claim_standing(family: str) -> str:
    """How a belief in this family may be presented."""
    c = REGISTRY.get(family)
    if c is None:
        return "UNREGISTERED"
    return "CALIBRATED_PREDICTIVE" if c.calibrated_claim_allowed else "EXPLORATORY"


def matrix() -> dict:
    by = {k: sorted(f for f, c in REGISTRY.items() if c.observability == k)
          for k in CLASSES}
    return {"version": REGISTRY_VERSION, "families": len(REGISTRY),
            "by_class": by,
            "contracts": {f: c.as_dict() for f, c in sorted(REGISTRY.items())}}
