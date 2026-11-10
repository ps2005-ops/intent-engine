"""Same facts, different order: what each role needs first.

THE INVARIANT
-------------
A role lens may change PRIORITY, ORDER, EMPHASIS, FRAMING and WHICH QUESTIONS
ARE OFFERED. It may not change a fact, a number, a citation, a standing label
or a confidence. There is one world model and one set of beliefs about the
company; a CFO and a CEO reading the same run must be able to put the two
screens side by side and find no contradiction.

That is enforced structurally rather than promised: `role_view` receives an
already-composed report and returns an ORDERING over its modules plus a
question set. It is handed no evidence, no profile and no analysis, so there
is nothing for it to rewrite. `break_proofs` mutates the role and asserts the
module BODIES are byte-identical.

WHY NOT A REASONING ENGINE PER ROLE
-----------------------------------
Because then there are nine world models, they disagree, and the disagreements
surface to the customer as the product contradicting itself. The recorded
version of this failure is smaller and the same shape: a primary screen
asserting an industrial capacity mechanism about a software network while the
X-Ray two clicks away read it correctly, because each page composed its own.

CURRENT AND FUTURE ARE LABELLED
-------------------------------
Two roles are live because two roles have surfaces built for them. The rest
are declared, ordered and shown as FUTURE_ROLE_VIEW rather than hidden -- a
reader should be able to see the shape of what is coming without being misled
into thinking it is already connected to their systems.
"""
from __future__ import annotations

import dataclasses
from typing import Tuple

CONTRACT = "role_lens.v1"

LIVE = "LIVE"
FUTURE = "FUTURE_ROLE_VIEW"


@dataclasses.dataclass(frozen=True)
class RoleLens:
    role_id: str
    title: str
    status: str = FUTURE
    #: module ids this role reads first, in order
    priority_modules: Tuple[str, ...] = ()
    #: how the same decision is framed for this reader
    decision_framing: str = ""
    #: what this reader watches between analyses
    monitoring_priorities: Tuple[str, ...] = ()
    #: the follow-up questions offered to this reader
    questions: Tuple[str, ...] = ()
    #: a note on register, never on content
    language: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


ROLES: Tuple[RoleLens, ...] = (
    RoleLens(
        role_id="ceo", title="Chief Executive", status=LIVE,
        priority_modules=("executive_change", "strategic_thesis",
                          "why_this_is_different", "decision_opportunity_map",
                          "decision_delta", "competitive_response",
                          "causal_chain", "what_would_change_our_mind",
                          "contradictions", "evidence", "provenance"),
        decision_framing=("what to change, what it costs to wait, and what "
                          "would make it the wrong call"),
        monitoring_priorities=("what a competitor does first",
                               "the assumption carrying the most weight",
                               "anything that would reverse the decision"),
        questions=("What would make this recommendation wrong?",
                   "What is the largest assumption here?",
                   "What does a competitor do about this first?",
                   "What should I decide this quarter rather than this year?"),
        language="plain, decisive, no hedging that hides a recommendation"),
    RoleLens(
        role_id="cso", title="Strategy", status=LIVE,
        priority_modules=("strategic_lens", "why_this_is_different",
                          "causal_chain", "decision_opportunity_map",
                          "alternative_interpretation", "contradictions",
                          "market_belief", "competitive_response",
                          "scenario_comparison", "information_priority",
                          "evidence", "provenance"),
        decision_framing=("which reading the evidence supports, what the "
                          "strongest case against it is, and what would "
                          "settle it"),
        monitoring_priorities=("the mechanism, not the headline",
                               "evidence that would falsify the reading",
                               "where a rival's position is actually different"),
        questions=("What is the strongest case that this reading is wrong?",
                   "Which link in the causal chain is weakest?",
                   "What alternative interpretation fits the same evidence?",
                   "What evidence would settle this fastest?"),
        language="analytical, comfortable with uncertainty stated as such"),
    RoleLens(
        role_id="cfo", title="Finance",
        priority_modules=("financial_sensitivity", "economic_exposure",
                          "scenario_comparison", "decision_delta",
                          "strategic_thesis", "evidence"),
        decision_framing=("what it costs, what it returns, and what the "
                          "downside case does to the plan"),
        monitoring_priorities=("demand sensitivity", "margin and mix",
                               "working capital", "rates and FX"),
        questions=("What does the downside case do to the plan?",
                   "Which cost moves with volume here?",
                   "What return is being assumed?"),
        language="quantitative where the evidence carries figures, silent "
                 "where it does not"),
    RoleLens(
        role_id="coo", title="Operations",
        priority_modules=("operational_intelligence", "supply_chain_exposure",
                          "causal_chain", "decision_delta", "evidence"),
        decision_framing="what has to change in the operation, and by when",
        monitoring_priorities=("throughput", "service levels",
                               "where delivery binds"),
        questions=("What has to change operationally for this to work?",
                   "Where does delivery bind first?"),
        language="concrete, sequenced"),
    RoleLens(
        role_id="cpo", title="Product",
        priority_modules=("customer_signals", "competitive_response",
                          "data_ai_exposure", "regulatory_exposure",
                          "decision_delta", "evidence"),
        decision_framing="what this means for what gets built and in what order",
        monitoring_priorities=("customer pain", "competitor product moves",
                               "substitutes", "regulation reaching the roadmap"),
        questions=("What does this change about the roadmap?",
                   "Which competitor move would matter most to product?",
                   "What customer pain does this actually address?"),
        language="specific about the user and the job"),
    RoleLens(
        role_id="cro", title="Revenue",
        priority_modules=("customer_signals", "market_belief",
                          "competitive_response", "decision_delta",
                          "scenario_comparison", "evidence"),
        decision_framing="what changes about how revenue is produced",
        monitoring_priorities=("buyer behaviour", "win rate and cycle length",
                               "competitor pricing"),
        questions=("What changes about how a buyer decides?",
                   "Where does the sales motion break first?"),
        language="direct, about the deal"),
    RoleLens(
        role_id="cmo", title="Marketing",
        priority_modules=("market_belief", "customer_signals",
                          "competitive_response", "evidence"),
        decision_framing="what the market believes and where that is wrong",
        monitoring_priorities=("category narrative", "competitor positioning"),
        questions=("What does the market believe that the evidence does not "
                   "support?",),
        language="about the story and who is telling it"),
    RoleLens(
        role_id="risk", title="Risk & Security",
        priority_modules=("regulatory_exposure", "contradictions",
                          "scenario_comparison", "data_ai_exposure",
                          "what_would_change_our_mind", "evidence",
                          "provenance"),
        decision_framing="what the exposure is and what a failure would cost",
        monitoring_priorities=("enforcement", "disclosure obligations",
                               "where the evidence is weakest"),
        questions=("What is the exposure if nothing changes?",
                   "Which claim here rests on the weakest evidence?"),
        language="precise about what is established and what is not"),
    RoleLens(
        role_id="consultant", title="Consultant / Advisor",
        priority_modules=("client_portfolio", "decision_opportunity_map",
                          "why_this_is_different", "competitive_response",
                          "economic_exposure", "evidence", "provenance"),
        decision_framing=("which client exposure is concentrated and which "
                          "engagement to bring this to"),
        monitoring_priorities=("client industry exposure",
                               "decisions clients are about to face",
                               "where evidence can and cannot be reused"),
        questions=("Which client industries carry the most exposure here?",
                   "What decision is a client of this kind about to face?",
                   "Where can this evidence be reused and where can it not?"),
        language="portfolio-first, explicit about engagement boundaries"),
)

_BY_ID = {r.role_id: r for r in ROLES}

DEFAULT_ROLE = "ceo"


def role(role_id: str) -> RoleLens:
    return _BY_ID.get(str(role_id or "").lower().strip(),
                      _BY_ID[DEFAULT_ROLE])


def live_roles() -> Tuple[RoleLens, ...]:
    return tuple(r for r in ROLES if r.status == LIVE)


@dataclasses.dataclass(frozen=True)
class RoleView:
    """An ORDERING over an already-composed report, and a question set.

    It holds no module bodies. There is nothing here that could disagree with
    another role's screen, because there is nothing here that says anything
    about the company.
    """
    role_id: str
    title: str
    status: str
    #: module ids, in the order this role should meet them
    order: Tuple[str, ...] = ()
    #: module ids this role's lens raised above their composed position
    promoted: Tuple[str, ...] = ()
    questions: Tuple[str, ...] = ()
    decision_framing: str = ""
    monitoring_priorities: Tuple[str, ...] = ()
    why: str = ""
    contract: str = CONTRACT

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def role_view(*, role_id: str, module_ids, lens_selection=None) -> RoleView:
    """Reorder a composed report for one reader. Facts are not an input.

    `module_ids` is the composer's own order. Modules this role prioritises
    move to the front IN THE ROLE'S ORDER; everything else keeps the
    composer's relative order behind them. Nothing is added and nothing is
    dropped -- a role that hid a module would be a role that changed what the
    reader is told, which is the line this object does not cross.
    """
    lens_role = role_id
    if not lens_role and lens_selection is not None:
        priorities = getattr(getattr(lens_selection, "lens", None),
                             "role_priority", ()) or ()
        lens_role = priorities[0] if priorities else DEFAULT_ROLE
    r = role(lens_role)
    present = [m for m in module_ids]
    front = [m for m in r.priority_modules if m in present]
    rest = [m for m in present if m not in front]
    promoted = tuple(m for i, m in enumerate(front)
                     if present.index(m) > i)
    return RoleView(
        role_id=r.role_id, title=r.title, status=r.status,
        order=tuple(front + rest), promoted=promoted,
        questions=r.questions, decision_framing=r.decision_framing,
        monitoring_priorities=r.monitoring_priorities,
        why=(f"{r.title} reads "
             f"{', '.join(m.replace('_', ' ') for m in front[:3])} first "
             f"because the decision in front of that reader is "
             f"{r.decision_framing}. Nothing below is removed or reworded; "
             f"the order changes and the facts do not."
             if front else
             f"{r.title} has no module in this report to raise, so the order "
             f"is the composer's own."))
