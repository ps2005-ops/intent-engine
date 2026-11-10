"""Three layers grade the same evidence. They must not contradict each other.

THE STATE THIS EXISTS TO CATCH
------------------------------
    mechanism_calibration   demand_strengthening is CONTESTED
    belief_maturity         "shopify is seeing demand strengthen" is
                            REPEATEDLY_SUPPORTED

Both are computed correctly from their own inputs and together they are
incoherent. Maturity counts confirmations of ONE belief; mechanism
calibration counts how the RULE behind it has fared everywhere. A belief
cannot be better established than the mechanism it is an instance of, and
counting alone will happily say otherwise.

PRECEDENCE, AND WHY IT RUNS THIS WAY
------------------------------------
    causal calibration   CAPS   mechanism calibration
    mechanism            CAPS   belief maturity

Each layer is a claim about a strictly larger population than the one below
it, so it can only ever bound its instances, never raise them. A single
belief with four confirmations does not promote the rule; the rule bounds
the belief.

WHAT THIS DOES NOT DO
---------------------
It does not rewrite anything. Maturity is a view and stays a view; this
reports INCOHERENT PAIRS with the cap that should apply, and the report is
what a reader acts on. A checker that silently downgraded stored state would
make the two layers agree by destroying the evidence that they disagreed.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import belief_maturity as BM
from . import causal_calibration as CC
from . import mechanism_calibration as MC

CONTRACT = "calibration_consistency.v1"

#: How strong each maturity is, so "stronger than" is a comparison rather
#: than a judgement.
_MATURITY_RANK = {
    BM.CANDIDATE: 0, BM.STALE: 0, BM.WEAKENING: 1, BM.CONTESTED: 1,
    BM.SUPPORTED: 2, BM.REPEATEDLY_SUPPORTED: 3, BM.RETIRED: 0,
}

#: The strongest belief maturity each mechanism maturity permits.
_MECHANISM_CAP = {
    MC.FAILING: BM.WEAKENING,
    MC.CONTESTED: BM.SUPPORTED,
    MC.UNFALSIFIABLE_BY_OBSERVATION: BM.CANDIDATE,
    MC.UNTESTED: BM.SUPPORTED,
    MC.EMERGING: BM.SUPPORTED,
    MC.ESTABLISHED: BM.REPEATEDLY_SUPPORTED,
    MC.UNMEASURABLE: BM.REPEATEDLY_SUPPORTED,
}

#: The strongest mechanism maturity each causal standing permits. A causal
#: family that is CONTESTED cannot sit under an ESTABLISHED predictor: the
#: predictor may still work, but nobody may read it as a mechanism.
_CAUSAL_CAP = {
    CC.CONTESTED: MC.CONTESTED,
    CC.UNMEASURABLE: MC.ESTABLISHED,
    CC.EMERGING: MC.ESTABLISHED,
    CC.SUPPORTED: MC.ESTABLISHED,
    CC.REPEATEDLY_SUPPORTED: MC.ESTABLISHED,
}

_MECHANISM_RANK = {MC.UNFALSIFIABLE_BY_OBSERVATION: 0, MC.FAILING: 0,
                   MC.UNTESTED: 1, MC.UNMEASURABLE: 1, MC.EMERGING: 2,
                   MC.CONTESTED: 2, MC.ESTABLISHED: 3}


@dataclass(frozen=True)
class Incoherence:
    """One pair of layers that cannot both be right."""
    kind: str
    family: str
    subject: str
    upper_layer: str
    upper_state: str
    lower_layer: str
    lower_state: str
    permitted: str
    why: str

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "family": self.family, "subject": self.subject,
            "upper_layer": self.upper_layer, "upper_state": self.upper_state,
            "lower_layer": self.lower_layer, "lower_state": self.lower_state,
            "permitted": self.permitted, "why": self.why,
        }


def check(*, maturities: Sequence = (), mechanisms: Sequence = (),
          causal_families: Sequence = (),
          family_of: Optional[Dict[str, str]] = None
          ) -> Tuple[Incoherence, ...]:
    """Every pair where a lower layer claims more than its ceiling allows."""
    families = family_of or {}
    mechanism_state = {getattr(m, "key", ""): getattr(m, "maturity", "")
                       for m in mechanisms}
    causal_state = {getattr(c, "causal_family", ""): getattr(c, "status", "")
                    for c in causal_families}

    out: List[Incoherence] = []

    for key, causal in causal_state.items():
        mech = mechanism_state.get(key)
        if mech is None:
            continue
        cap = _CAUSAL_CAP.get(causal, MC.ESTABLISHED)
        if _MECHANISM_RANK.get(mech, 0) > _MECHANISM_RANK.get(cap, 3):
            out.append(Incoherence(
                kind="MECHANISM_ABOVE_ITS_CAUSAL_CEILING", family=key,
                subject="", upper_layer="causal_calibration",
                upper_state=causal, lower_layer="mechanism_calibration",
                lower_state=mech, permitted=cap,
                why=(f"the causal family is {causal}, so the rule may still "
                     f"predict but must not be read as a mechanism above "
                     f"{cap}")))

    for maturity in maturities:
        belief_id = getattr(maturity, "belief_id", "")
        key = families.get(belief_id, "")
        mech = mechanism_state.get(key)
        if not key or mech is None:
            continue
        cap = _MECHANISM_CAP.get(mech, BM.REPEATEDLY_SUPPORTED)
        state = getattr(maturity, "state", "")
        if _MATURITY_RANK.get(state, 0) > _MATURITY_RANK.get(cap, 3):
            out.append(Incoherence(
                kind="BELIEF_ABOVE_ITS_MECHANISM_CEILING", family=key,
                subject=getattr(maturity, "subject", ""),
                upper_layer="mechanism_calibration", upper_state=mech,
                lower_layer="belief_maturity", lower_state=state,
                permitted=cap,
                why=(f"the mechanism is {mech} across every subject, so one "
                     f"belief's confirmation count cannot carry it past "
                     f"{cap}; counting confirmations of a single instance "
                     f"does not promote the rule")))
    return tuple(out)


def summarise(incoherences: Sequence[Incoherence]) -> dict:
    return {
        "contract": CONTRACT,
        "incoherent_pairs": len(incoherences),
        "by_kind": dict(collections.Counter(i.kind for i in incoherences)),
        "detail": [i.as_dict() for i in incoherences],
        "precedence": ("causal_calibration caps mechanism_calibration caps "
                       "belief_maturity; each layer claims about a strictly "
                       "larger population than the one below and can only "
                       "bound it"),
        "note": ("nothing is rewritten. A checker that silently downgraded "
                 "stored state would make the layers agree by destroying "
                 "the evidence that they disagreed"),
    }
