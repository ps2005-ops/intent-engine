"""One answer to "does a supported strategic reading exist for this company".

D17. Live on `fbb62ff`, one Cloudflare run said all of this at once:

    X-Ray:  "Supported in direction, not in size · Pricing decision"
    Brief:  "No strategic reading of Cloudflare, Inc. cleared the evidence
             bar, so none is asserted here."
    Slide 1: "not enough to read a strategy from."

Two decision objects, each internally honest, each deciding SEPARATELY whether
there is anything to say. The X-Ray composes from the dossier, which carries
the market engine's published record; the brief, full analysis and deck read
the run's own reasoning decision, which sees only what this run retrieved. On
a company with a market snapshot they diverge; on Bank of America, which has
none, they agree — which is what identified the trigger.

WHAT THIS MODULE IS NOT. It is not "make every surface render the same
object". That was tried in both directions and both directions destroyed
something: pointing the X-Ray at the reasoning decision emptied it (D13), and
running every field through one projection turned a readable claim into a
count of unnameable sources. The brief is entitled to richer prose than the
deck, and the deck to slide structure the X-Ray has no use for.

What none of them is entitled to is its own answer to the questions below.
Those are canonical facts about the company; the rest is presentation.

THE ASYMMETRY IS DELIBERATE. A market reading can rescue a run that retrieved
little, because the market engine genuinely knows something this run did not
look for. A market reading can NEVER manufacture support the run contradicts,
and a stale or unidentified snapshot contributes nothing at all — otherwise
this becomes a machine for inheriting old conclusions, which is the one
failure worse than the contradiction it was written to remove.
"""
from dataclasses import dataclass, field
from typing import Optional

from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD)

CONTRACT = "executive_contract.v1"

#: How the run's own reading and the published market reading combined.
#: Named states rather than a boolean, because "the run found nothing and the
#: market knows something" and "both found something" license DIFFERENT
#: sentences, and collapsing them is how a surface starts overclaiming.
CURRENT_RUN_SUPPORTED = "CURRENT_RUN_SUPPORTED"
MARKET_SUPPORTED = "MARKET_SUPPORTED"
BOTH_SUPPORTED = "BOTH_SUPPORTED"
BOTH_BOUNDED = "BOTH_BOUNDED"
MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
MARKET_STALE = "MARKET_STALE"
MARKET_INVALID = "MARKET_INVALID"
NO_SUPPORTED_READING = "NO_SUPPORTED_READING"

#: Merge states in which a supported reading exists SOMEWHERE. A surface may
#: not say "no strategic reading exists" in any of these.
HAS_READING = frozenset({CURRENT_RUN_SUPPORTED, MARKET_SUPPORTED,
                         BOTH_SUPPORTED})

_SUPPORTED_STANDINGS = frozenset({"SUPPORTED", "BOUNDED"})


@dataclass(frozen=True)
class ExecutiveContract:
    """The canonical facts every executive surface must agree on."""
    contract: str = CONTRACT
    company: str = ""
    merge_state: str = NO_SUPPORTED_READING
    #: The readiness EVERY surface renders. Surfaces keep their own prose;
    #: none of them recomputes this.
    readiness: str = WITHHELD
    #: True when a supported reading exists anywhere. The single question
    #: whose two independent answers were D17.
    reading_exists: bool = False
    #: Set only when the market carries the reading and this run did not.
    #: A surface that would have refused says THIS instead of refusing --
    #: "the run added nothing" and "there is nothing" are different facts and
    #: the product was reporting the first as the second.
    run_contribution: str = ""
    #: Why a market reading was not used, when it was not. Never silent: a
    #: snapshot ignored without a reason is indistinguishable from one that
    #: was never published.
    market_note: str = ""
    sources: tuple = field(default_factory=tuple)


def _standing_of(decision) -> str:
    return str(getattr(decision, "standing", "")
               or (decision or {}).get("standing", "")
               if isinstance(decision, dict)
               else getattr(decision, "standing", "") or "")


def _readiness_of(decision) -> str:
    if decision is None:
        return WITHHELD
    if isinstance(decision, dict):
        return str(decision.get("readiness") or WITHHELD)
    return str(getattr(decision, "readiness", "") or WITHHELD)


def _supported(decision) -> bool:
    """Does this object carry a reading its own producer stands behind?

    Readiness first, standing as the fallback: the two producers populate
    different fields, which is exactly why they disagreed, so this asks both
    rather than assuming either.
    """
    if decision is None:
        return False
    readiness = _readiness_of(decision)
    if readiness in (DECISION_READY, INVESTIGATION_REQUIRED):
        return True
    standing = (decision.get("standing") if isinstance(decision, dict)
                else getattr(decision, "standing", "")) or ""
    return str(standing).upper() in _SUPPORTED_STANDINGS


def decide(*, company: str = "", run_decision=None, market_decision=None,
           market_usable: bool = True,
           market_reason: str = "") -> ExecutiveContract:
    """Combine the run's reading and the published market reading. No I/O.

    `market_usable` is the caller's freshness and identity verdict, passed in
    rather than computed here: whether a snapshot is for the right company and
    recent enough is already decided by the bridge, and a second opinion about
    it would be a second contract.
    """
    run_ok = _supported(run_decision)
    market_ok = _supported(market_decision) and market_usable

    if market_decision is not None and not market_usable:
        note = market_reason or (
            "A market reading exists for this company but was not in a state "
            "this side will read, so it did not inform the reading below.")
        state = MARKET_STALE if market_reason else MARKET_INVALID
        return ExecutiveContract(
            company=company,
            merge_state=(CURRENT_RUN_SUPPORTED if run_ok else state),
            readiness=(_readiness_of(run_decision) if run_ok else WITHHELD),
            reading_exists=run_ok, market_note=note,
            sources=("run",) if run_ok else ())

    if run_ok and market_ok:
        state, readiness = BOTH_SUPPORTED, _readiness_of(run_decision)
    elif run_ok:
        state, readiness = CURRENT_RUN_SUPPORTED, _readiness_of(run_decision)
    elif market_ok:
        # THE CASE THAT WAS D17. This run did not clear its own bar; the
        # market engine has a reading for this company that did. The reading
        # exists, and what the run failed to do is a separate, smaller fact.
        state, readiness = MARKET_SUPPORTED, _readiness_of(market_decision)
    elif market_decision is None:
        state, readiness = MARKET_UNAVAILABLE, WITHHELD
    else:
        state, readiness = NO_SUPPORTED_READING, WITHHELD

    contribution = ""
    if state == MARKET_SUPPORTED:
        contribution = (
            "This run did not add enough independent evidence to strengthen "
            "the existing reading; it neither established nor contradicted "
            "it.")

    return ExecutiveContract(
        company=company, merge_state=state, readiness=readiness,
        reading_exists=state in HAS_READING,
        run_contribution=contribution,
        market_note=("" if market_decision is not None else
                     "No market reading is published for this company, so "
                     "the reading below rests on this run alone."),
        sources=tuple(s for s, ok in (("run", run_ok), ("market", market_ok))
                      if ok))
