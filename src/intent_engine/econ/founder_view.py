"""What a CEO is shown about collective state, and what is withheld.

SECTION 50'S RULE, AS A FUNCTION
--------------------------------
Instead of:

    "consumer confidence declined"

say:

    "Household financial insecurity is rising despite stable headline
     employment. Large-ticket intent is weakening first. For this company
     that matters because ..."

The difference is not tone. The first sentence is true of every company and
therefore informs no decision; the second names a CHANNEL, and a channel is
what a management team can actually act on. So this module refuses to produce
a reading for a company with no declared exposure -- returning an explicit
"this construct does not reach you through any channel we have declared"
rather than the population average.

TWO GATES, BOTH OF WHICH MUST PASS
----------------------------------
    1. the construct must be PROMOTED (Section 42): it has beaten the base
       economic model out of sample, in two regimes, after FDR correction
    2. the company must have a declared exposure (Section 13): a named
       channel and a named company observable it would show up in

Failing gate 1 is a research state. Failing gate 2 is a coverage state. They
are reported separately, because conflating them would make an untested
construct look like a company that simply is not exposed.

WHY THE WITHHELD LIST IS RETURNED
---------------------------------
A surface that silently showed nothing would be indistinguishable from one
where the engine had nothing to say. `withheld` names every construct that
was measured and not shown, with the gate that stopped it -- so the absence
is legible as a decision rather than as a blank.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from .collective import CollectiveStateEstimate, narrate
from .construct import Construct
from .transmission import Exposure, TransmissionRegistry
from .vocabulary import PROMOTED, PUBLIC, PrivacyViolation, require

CONTRACT = "econ_founder_view.v1"

NOT_PROMOTED = "NOT_PROMOTED"
NO_CHANNEL = "NO_CHANNEL"
NOT_USABLE = "NOT_USABLE"
GATES = (NOT_PROMOTED, NO_CHANNEL, NOT_USABLE)

_GATE_REASON = {
    NOT_PROMOTED: ("has not beaten the base economic model out of sample, so "
                   "it may not inform a decision yet"),
    NO_CHANNEL: ("has no declared channel into this company; showing it here "
                 "would be the generic psychology dump that makes every "
                 "company's report identical"),
    NOT_USABLE: ("is measured but its uncertainty is wide enough to be "
                 "consistent with the opposite reading"),
}


def for_company(*, company_id: str, state: CollectiveStateEstimate,
                registry: TransmissionRegistry,
                register: Sequence[Construct],
                economy_note: str = "") -> dict:
    """The collective-state section of one company's brief.

    `economy_note` is the conventional economic reading this is being set
    AGAINST -- Section 50's example works because "despite stable headline
    employment" is in the sentence. Passing it empty is allowed and produces
    a weaker sentence, which is the honest outcome when nobody supplied the
    contrast.
    """
    require(bool(company_id), "a company view names its company")
    if state.visibility != PUBLIC:
        raise PrivacyViolation(
            f"{company_id}: a tenant-private collective estimate reached the "
            "shared founder view. Section 33: private evidence never trains "
            "or informs the public model.")

    promoted = {c.dimension for c in register if c.state == PROMOTED}
    exposures: Dict[str, List[Exposure]] = {}
    for e in registry.exposures(company_id, enforce=False):
        exposures.setdefault(e.construct, []).append(e)

    shown, withheld = [], []
    for name in sorted(state.dimensions):
        est = state.dimensions[name]
        if est.posterior_mean is None:
            continue
        if not est.usable:
            withheld.append({"construct": name, "gate": NOT_USABLE,
                             "reason": _GATE_REASON[NOT_USABLE]})
            continue
        if name not in promoted:
            withheld.append({"construct": name, "gate": NOT_PROMOTED,
                             "reason": _GATE_REASON[NOT_PROMOTED],
                             "state": next((c.state for c in register
                                            if c.dimension == name),
                                           "NOT_IN_REGISTER")})
            continue
        if name not in exposures:
            withheld.append({"construct": name, "gate": NO_CHANNEL,
                             "reason": _GATE_REASON[NO_CHANNEL]})
            continue
        for exp in exposures[name]:
            shown.append({
                "construct": name,
                "sentence": _sentence(est, state, exp, economy_note),
                "channel": exp.channel,
                "observable": exp.observable,
                "direction": exp.sign,
                "moved": est.moved,
                "uncertainty": est.uncertainty,
                "lag_days": est.lag_model.typical_days,
                "falsifier": (
                    f"{exp.observable} does not move {exp.sign} for this "
                    f"company within {est.lag_model.upper_days} days while "
                    f"{name.replace('_', ' ')} continues in this direction"),
            })

    return {"contract": CONTRACT, "company_id": company_id,
            "as_of": state.as_of,
            "population": state.population.as_dict(),
            "shown": shown, "withheld": withheld,
            "shown_count": len(shown), "withheld_count": len(withheld),
            "has_anything_to_say": bool(shown),
            # The line a surface prints when `shown` is empty. Computed, so
            # it cannot drift from the gates above it.
            "empty_reason": _empty_reason(shown, withheld, company_id)}


def _sentence(est, state, exp: Exposure, economy_note: str) -> str:
    """Section 50's shape: the reading, the contrast, then WHY IT MATTERS HERE."""
    base = narrate(est, state.population)
    contrast = f" {economy_note.strip()}" if economy_note.strip() else ""
    return (f"{base}{contrast} For this company that matters because it "
            f"reaches you through {exp.channel}, where it would show up as "
            f"{exp.observable} moving {exp.sign}.")


def _empty_reason(shown, withheld, company_id: str) -> str:
    if shown:
        return ""
    if not withheld:
        return (f"No collective construct is currently measured, so there is "
                f"nothing to report for {company_id} either way.")
    # THE DOMINANT GATE, not the first one found. An earlier version tested
    # `NOT_PROMOTED in gates` before counting, so a company blocked by two
    # missing channels and one untested construct was told its problem was
    # research when its problem was coverage. Those call for opposite
    # actions -- run an experiment, or map the company's exposures -- so
    # naming the minority gate sends the reader the wrong way.
    counts: Dict[str, int] = {}
    for w in withheld:
        counts[w["gate"]] = counts.get(w["gate"], 0) + 1
    dominant = max(counts, key=lambda g: (counts[g], g))
    others = sorted(g for g in counts if g != dominant)

    if dominant == NO_CHANNEL:
        head = (f"{counts[NO_CHANNEL]} construct(s) are measured and none has "
                f"a declared channel into {company_id}. That is a gap in this "
                f"company's exposure map, not a quiet economy.")
    elif dominant == NOT_PROMOTED:
        head = (f"{counts[NOT_PROMOTED]} construct(s) are being measured for "
                f"this population and have not beaten the base economic "
                f"model out of sample. Nothing from them may inform a "
                f"decision about {company_id} yet.")
    else:
        head = (f"{counts[NOT_USABLE]} construct(s) are measured too "
                f"imprecisely to support a reading for {company_id}.")
    if others:
        tail = ", ".join(f"{counts[g]} by {g}" for g in others)
        return f"{head} Also withheld: {tail}."
    return head
