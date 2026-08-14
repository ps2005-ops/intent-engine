"""One FounderDecision, composed from the market dossier with no model call.

WHY THIS IS NOT A PROMPT
------------------------
The tempting build is to hand a model the dossier and ask for a
recommendation. That produces fluent prose whose standing nobody can check,
and it makes the executive read fail when the model is unavailable -- which
is the state this deployment is actually in, and the state the demo must
survive.

So the read is COMPUTED. Every sentence below is assembled from canonical
fields under a controlled vocabulary, and the wording a sentence is allowed
to use is a function of the standing of the evidence under it. That is the
whole design: you cannot get "the evidence shows" out of a BOUNDED reading,
because the word is not reachable from that branch.

WHAT IT MAY NEVER DO
--------------------
Invent a percentage, a revenue delta, a confidence score, a causal effect or
a competitor probability. If a number is not in the canonical inputs it does
not appear. There is no template with a blank in it.

A REFUSAL IS THE INTERESTING CASE
---------------------------------
Every causal block in the live population is PANEL_UNAVAILABLE: the engine
asked a real question and the public record could not answer it. The wrong
product ends there ("no causal answer available"). This one routes it --
what is missing, what would resolve it, what that is worth, and what to do
in the meantime under a guardrail. Uncertainty that names its next move is
the product; uncertainty that ends the page is a dead end.
"""
from __future__ import annotations

from typing import Any, Optional

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD, FounderDecision)

CONTRACT = "founder_decision_synthesis.v1"

# --- standing, and the words each one may use -------------------------------
#
# THE MAPPING IS THE GUARDRAIL. §8 states it as a table and this is that
# table, executable. A surface never picks a verb; it asks for one.
SUPPORTED = "SUPPORTED"
BOUNDED = "BOUNDED"
UNMEASURABLE = "UNMEASURABLE"
REFUSED = "REFUSED"
STANDINGS = (SUPPORTED, BOUNDED, UNMEASURABLE, REFUSED)

_VERB = {
    SUPPORTED: "supports",
    BOUNDED: "is consistent with",
    UNMEASURABLE: "cannot yet determine",
    REFUSED: "should not infer",
}

#: Phrases this product may never emit about risk, at any standing. Kept here
#: as well as in the renderer because a composed sentence is where one would
#: first appear.
FORBIDDEN = ("zero risk", "no risk", "risk free", "risk-free", "guaranteed")


def verb_for(standing: str) -> str:
    """The strongest verb this standing permits. Unknown standing is REFUSED.

    The safe direction: a standing this module has never heard of must not
    reach for the strongest wording in the table.
    """
    return _VERB.get(str(standing), _VERB[REFUSED])


class SynthesisRefused(ValueError):
    """The composed text broke a wall. Never rendered, never softened."""


def _assert_clean(text: str) -> str:
    low = str(text).lower()
    for phrase in FORBIDDEN:
        if phrase in low:
            raise SynthesisRefused(
                f"composed text claimed {phrase!r}: {text[:120]!r}")
    return text


# --- reading the dossier ----------------------------------------------------

def _block(dossier, name: str) -> dict:
    return ((dossier.market_block or {}).get("blocks") or {}).get(name) or {}


def _count(dossier, name: str) -> int:
    value = _block(dossier, name).get("count")
    return value if isinstance(value, int) else 0


def _ran(dossier, name: str) -> bool:
    """Did this subsystem run? AVAILABLE with zero rows still ran."""
    return _block(dossier, name).get("state") == "AVAILABLE"


def _standing_of(dossier) -> str:
    """The standing of the whole reading.

    Deliberately conservative and deliberately simple: it is a function of
    what the market engine actually published, not a score. Evidence with no
    belief over it is a pile of documents, so beliefs are what lift a reading
    above BOUNDED -- and nothing here can reach SUPPORTED while the causal
    question is refused, because that is precisely what "supported" would be
    claiming.
    """
    if (dossier.market_block or {}).get("availability") not in ("AVAILABLE",
                                                                "STALE"):
        return REFUSED
    beliefs, evidence = _count(dossier, "beliefs"), _count(dossier, "evidence")
    if not evidence:
        return UNMEASURABLE
    if not beliefs:
        # Documents without a belief over them: the engine holds no position,
        # so there is nothing for a recommendation to rest on.
        return BOUNDED
    causal = _block(dossier, "causal_results")
    if causal.get("is_refusal") or not _ran(dossier, "causal_results"):
        return BOUNDED
    return SUPPORTED if causal.get("count") else BOUNDED


def _causal_status(dossier):
    """(status, note). A refusal keeps its own name; it is never 'no effect'."""
    block = _block(dossier, "causal_results")
    if block.get("state") != "AVAILABLE":
        return "CAUSAL_NOT_RUN", ("No causal question was asked for this "
                                  "company in this cycle.")
    states = block.get("states") or {}
    if not states:
        return "CAUSAL_NO_QUESTION", ("The causal router ran and raised no "
                                      "question for this company.")
    if block.get("is_refusal"):
        named = ", ".join(f"{n} {s}" for s, n in sorted(states.items()))
        return "CAUSAL_UNMEASURABLE", (
            f"The causal router asked {block.get('count', 0)} question(s) and "
            f"could not answer any of them from the public record ({named}). "
            f"That is a limit of the available data, not a finding that the "
            f"effect is absent.")
    return "CAUSAL_ESTIMATED", (
        f"The causal router resolved {block.get('count', 0)} question(s): "
        f"{', '.join(f'{n} {s}' for s, n in sorted(states.items()))}.")


ECONOMIC_AVAILABLE = "ECONOMIC_STATE_AVAILABLE"
ECONOMIC_NO_EXPOSURE = "ECONOMIC_STATE_NO_RELEVANT_EXPOSURE"
ECONOMIC_UNMEASURABLE = "ECONOMIC_STATE_UNMEASURABLE"
ECONOMIC_NOT_RUN = "ECONOMIC_STATE_NOT_RUN"


def _economic(dossier):
    """(state, conditions). Four answers that are not interchangeable.

    The one a generic macro dashboard cannot give is NO_RELEVANT_EXPOSURE:
    the economy IS measured, and none of it reaches this company, because
    nothing in this company's own evidence establishes an exposure that
    transmits a measured condition. That is the live answer for 22 of 26
    companies, and it is a finding -- not a gap in the macro layer.

    UNMEASURABLE is its opposite: rows arrived that this side could not read.
    Reporting either as NOT_RUN would send someone to fix the scheduler when
    the actual repair is retrieval on this company's documents.
    """
    block = _block(dossier, "economic_state")
    if block.get("state") != "AVAILABLE":
        return ECONOMIC_NOT_RUN, ()
    ids = tuple(block.get("ids") or ())
    if ids:
        return ECONOMIC_AVAILABLE, ids
    note = str(block.get("note") or "")
    if "wiring defect" in note:
        return ECONOMIC_UNMEASURABLE, ()
    return ECONOMIC_NO_EXPOSURE, ()


def _hidden_state(dossier) -> str:
    block = _block(dossier, "hidden_states")
    if block.get("state") != "AVAILABLE":
        return "HIDDEN_STATE_NOT_RUN"
    ids = block.get("ids") or []
    if ids:
        return str(ids[0])
    if block.get("unidentified"):
        # The live case for 22 of 26 companies. Naming it is the product:
        # "we track this and cannot yet call it" is a real answer.
        return "TRACKED_NO_IDENTIFIED_STATE"
    return "HIDDEN_STATE_NONE_TRACKED"


# --- §9: a refusal becomes a next move --------------------------------------

def _route_refusal(dossier, causal_status: str):
    """CAUSAL_UNMEASURABLE -> what is missing -> what would resolve it.

    Returns (information_gaps, minimum_data_requests, value_of_information,
    guardrails). Every element names the prerequisite the engine itself
    reported; none of it is invented, and where the dossier carries no
    prerequisite this returns empty rather than a plausible-sounding one.
    """
    if causal_status != "CAUSAL_UNMEASURABLE":
        return (), (), (), ()
    block = _block(dossier, "causal_results")
    states = block.get("states") or {}
    gaps, mdrs, vois = [], [], []
    for state, n in sorted(states.items()):
        if state == "PANEL_UNAVAILABLE":
            gaps.append(
                f"No comparable control panel exists for {n} causal "
                f"question(s): the public record carries no set of similar "
                f"companies observed over the same window.")
            mdrs.append(
                "A panel of comparable companies over the same window, or "
                "the outcome series for this company before and after the "
                "change, would move this from unmeasurable to bounded.")
            vois.append(
                "High for a decision that turns on the size of the effect; "
                "low for one that turns only on its direction, which the "
                "beliefs above already speak to.")
        else:
            gaps.append(f"{n} causal question(s) ended in {state}.")
    # THE GUARDRAIL NAMES THIS COMPANY'S OWN UNRESOLVED QUESTION.
    #
    # It used to be one fixed sentence, and across eight companies it
    # produced two distinct answers to "what is the biggest risk" -- six of
    # them word-for-word identical. A risk that reads the same for a bank and
    # a mining company is not a risk assessment, and adding the company's
    # name to it would be worse: the same generic claim wearing a label.
    #
    # So it is built from what is actually different here: how many questions
    # went unanswered, on how much evidence, and what the company is exposed
    # to. Where those are genuinely the same, the sentence is genuinely the
    # same -- the fix is not to manufacture variety the evidence lacks.
    guardrails = ()
    if gaps:
        unanswered = sum(states.values())
        evidence = _count(dossier, "evidence")
        beliefs = _count(dossier, "beliefs")
        exposure = tuple(_block(dossier, "economic_state").get("ids") or ())
        where = (f" while it stays exposed to {', '.join(exposure[:3])}"
                 if exposure else "")
        guardrails = (
            f"Size any commitment to survive the effect being smaller than "
            f"expected{where}: {unanswered} causal question(s) are open and "
            f"the reading rests on {evidence} evidence row(s) under "
            f"{beliefs} belief(s), so the direction is better supported than "
            f"the magnitude.",
        )
    return tuple(gaps), tuple(mdrs), tuple(vois), guardrails


# --- the read ---------------------------------------------------------------

def _economic_sentence(state: str, conditions) -> str:
    """The economy, only where it reaches this company.

    A generic macro line is worse than none: it reads as specific, applies to
    everyone, and so carries the least information of anything on the page.
    """
    if state == ECONOMIC_AVAILABLE and conditions:
        named = ", ".join(str(c) for c in conditions[:4])
        return (f" Measured economic conditions reach it through its own "
                f"established exposures: {named}.")
    if state == ECONOMIC_NO_EXPOSURE:
        return (" The economy is measured, and none of it reaches this "
                "company through an exposure its own evidence establishes.")
    if state == ECONOMIC_UNMEASURABLE:
        return (" Economic conditions were published for this company and "
                "could not be read.")
    return ""


def _current_read(company: str, standing: str, dossier, hidden: str,
                  economic_state: str = "", economic_context=()) -> str:
    """One sentence, in the wording this standing permits."""
    verb = verb_for(standing)
    evidence, beliefs = _count(dossier, "evidence"), _count(dossier, "beliefs")
    if standing == REFUSED:
        return (f"No market reading is put forward for {company}: the "
                f"published snapshot was not in a state this side will read.")
    if standing == UNMEASURABLE:
        return (f"The market record for {company} {verb} a position: no "
                f"evidence this company's blocks cite has been published.")
    subject = (f"{evidence} evidence row(s) and {beliefs} belief(s)"
               if beliefs else f"{evidence} evidence row(s) and no belief")
    tail = ""
    if hidden == "TRACKED_NO_IDENTIFIED_STATE":
        tail = (" Its operating posture is tracked and not yet "
                "distinguishable from the prior.")
    elif hidden not in ("HIDDEN_STATE_NOT_RUN", "HIDDEN_STATE_NONE_TRACKED"):
        tail = f" Its leading operating posture reads {hidden}."
    return _assert_clean(
        f"The published market record for {company} — {subject} — {verb} the "
        f"reading below.{tail}"
        f"{_economic_sentence(economic_state, economic_context)}")


def _what_changed(dossier, previous) -> tuple:
    """Only real movement. An identical snapshot changed nothing, and saying
    otherwise is the failure mode this whole programme keeps finding."""
    if previous is None:
        return ("This is the first published reading for this company; there "
                "is no earlier one to compare it against.",)
    changes = []
    for name, label in (("evidence", "evidence rows"),
                        ("beliefs", "beliefs"),
                        ("expectations", "preregistered expectations"),
                        ("causal_results", "causal resolutions")):
        now, before = _count(dossier, name), _count(previous, name)
        if now != before:
            changes.append(f"{label}: {before} -> {now}")
    if not changes:
        return ("Nothing in the published market record changed since the "
                "previous reading.",)
    return tuple(changes)


def compose(dossier, *, previous: Optional[Any] = None,
            prior_decision: Optional[Any] = None) -> FounderDecision:
    """Build one FounderDecision from one company demo dossier.

    ZERO MODEL CALLS. Verified by a break proof, not by intent.
    """
    company = dossier.canonical_name or dossier.company_id
    standing = _standing_of(dossier)
    hidden = _hidden_state(dossier)
    causal_status, causal_note = _causal_status(dossier)
    economic_state, economic_context = _economic(dossier)
    gaps, mdrs, vois, guardrails = _route_refusal(dossier, causal_status)

    evidence_block = _block(dossier, "evidence")
    monitoring = []
    if _ran(dossier, "expectations") and _count(dossier, "expectations"):
        monitoring.append(
            f"{_count(dossier, 'expectations')} preregistered expectation(s) "
            f"are open for this company; each carries its own falsifier and "
            f"evaluation window.")
    if hidden == "TRACKED_NO_IDENTIFIED_STATE":
        monitoring.append(
            "The operating-posture distribution is uniform. The first "
            "observation that moves it is the cheapest signal available here.")

    # READINESS. A reading with no belief under it is not a decision, and a
    # refused snapshot is not an investigation -- it is nothing at all.
    readiness = (WITHHELD if standing == REFUSED
                 else DECISION_READY if standing == SUPPORTED
                 else INVESTIGATION_REQUIRED)

    decision = FounderDecision(
        company=company,
        decision_question=(
            f"What should be concluded about {company} from the published "
            f"market record, and what would change it?"),
        current_read=_current_read(company, standing, dossier, hidden,
                                   economic_state, economic_context),
        standing=standing,
        readiness=readiness,
        supporting_evidence_ids=tuple(evidence_block.get("ids") or ()),
        independent_origins=0,   # not measured by the market snapshot; §16
        hidden_state=hidden,
        causal_status=causal_status,
        causal_note=causal_note,
        information_gaps=gaps,
        minimum_data_requests=mdrs,
        value_of_information=vois,
        guardrails=guardrails,
        monitoring=tuple(monitoring),
        what_changed=_what_changed(dossier, previous),
        economic_state=economic_state,
        economic_context=economic_context,
        provenance=(f"market snapshot {dossier.market_snapshot_id}",
                    f"market runtime {dossier.market_runtime_sha[:12]}",
                    f"evidence cutoff {dossier.effective_evidence_cutoff}"),
        derived_from="market_dossier",
        limitation=causal_note if causal_status == "CAUSAL_UNMEASURABLE"
        else "",
    )
    _assert_clean(decision.current_read)
    for text in decision.guardrails + decision.information_gaps:
        _assert_clean(text)
    return decision
