"""Are the V4 economic guards load-bearing? Break them and find out.

Each proof mutates the real source, requires the bytes to change, requires the
named test to turn RED for the stated reason, and requires an exact restore. A
mutation that changes bytes and nothing that runs is reported NOT_CAUGHT — a
finding about the guard, not a failure of the harness.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
MS = S / "macro_state.py"
CX = S / "company_exposure.py"
TX = S / "transmission.py"
ECH = S / "economic_chain.py"

M = "tests/test_market_macro_state.py"
E = "tests/test_market_company_exposure.py"
X = "tests/test_market_transmission.py"

PROOFS = [
    # 1. a statistic is allowed to say what it means for a company
    ("v4-1. a macro state answers what it means for a company",
     MS,
     "    raise CausalOverreach(",
     "    return 'demand will fall'\n    raise CausalOverreach(",
     f"{M}::test_a_macro_state_refuses_to_say_what_it_means_for_a_company"),

    # 2. the reference period becomes the publication date
    ("v4-2. availability is decided by the period rather than the release",
     MS,
     "        return self.published_at[:10] <= str(when)[:10]",
     "        return self.reference_period[:10] <= str(when)[:10]",
     f"{M}::test_availability_is_decided_by_publication_not_by_reference_period"),

    # 3. a later revision is applied to an earlier decision
    ("v4-3. a newer vintage leaks backward into an older decision",
     MS,
     "        if not obs.known_at(when):\n            continue",
     "        if False:\n            continue",
     f"{M}::test_a_decision_is_scored_against_the_vintage_it_could_have_seen"),

    # 4. an opinion about the economy anchors a chain
    ("v4-4. a hypothesised economy anchors a chain",
     MS,
     "ANCHORING = frozenset({OBSERVED, INFERRED})",
     "ANCHORING = frozenset({OBSERVED, INFERRED, HYPOTHESIZED})",
     f"{M}::test_a_hypothesized_state_does_not_anchor_a_chain"),

    # 5. an unmeasured condition reads as flat rather than unknown
    ("v4-5. an unmeasured condition stops being UNKNOWN",
     MS,
     # Anchor updated when `state_of` gained an area; the guard is unchanged
     # and the mutation is the same one — an unmeasured condition reporting
     # itself as a measured, flat one.
     "    if not mine:\n        return unknown(state_kind, area=area)",
     "    if not mine:\n        return EconomicState(state_kind=state_kind, "
     "standing=OBSERVED, area=area, reason='flat')",
     f"{M}::test_an_unmeasured_condition_is_unknown_and_never_flat"),

    # 6. the sector prior comes back
    ("v4-6. an exposure may be inferred from a sector",
     CX,
     "    raise ExposureRejected(\n        \"an exposure may not be inferred",
     "    return True\n    raise ExposureRejected(\n        \"an exposure "
     "may not be inferred",
     f"{E}::test_an_exposure_may_not_be_inferred_from_a_sector"),

    # 7. a share-price headline establishes a cost structure
    ("v4-7. third-party reporting establishes the company's own exposure",
     CX,
     "    if role in _THIRD_PARTY:\n        return INFERRED",
     "    if role in _THIRD_PARTY:\n        return OBSERVED",
     f"{E}::test_a_share_price_headline_does_not_establish_a_cost_structure"),

    # 8. a rated exposure no longer needs the evidence behind it
    ("v4-8. a rated exposure without evidence is accepted",
     CX,
     "        if self.standing in CONDITIONING and not self.evidence_ids:",
     "        if False:",
     f"{E}::test_a_rated_exposure_without_evidence_is_refused"),

    # 9. a transmission is proposed from an unestablished exposure
    ("v4-9. a sector prior becomes a transmission",
     TX,
     "    if not CX.conditions_transmission(exposure, state):\n        return None",
     "    if False:\n        return None",
     f"{X}::test_an_unestablished_exposure_proposes_nothing"),

    # 10. a transmission may be built with nothing that could disprove it
    ("v4-10. a transmission without a falsifier is accepted",
     TX,
     "        if not self.falsifier.strip():",
     "        if False:",
     f"{X}::test_a_transmission_without_a_falsifier_is_refused"),

    # 11. the join becomes an observation rather than a hypothesis
    ("v4-11. a proposed transmission is born already supported",
     TX,
     "        alternative_explanation=alternative, standing=HYPOTHESIZED,",
     "        alternative_explanation=alternative, standing=SUPPORTED,",
     f"{X}::test_a_transmission_is_born_hypothesized_and_untested"),

    # 12. anchoring the chain silently promotes the link below it
    ("v4-12. the macro anchor promotes a link with one end missing",
     ECH,
     "    if macro is not None and getattr(macro, \"anchors\", False):",
     "    if macro is not None:",
     f"{M}::test_an_opinion_about_the_economy_does_not_anchor_the_chain"),
]

#: Proofs whose guard RAISES. Removing it makes pytest report DID NOT RAISE,
#: never an assertion — expecting "assert" for these reported four genuinely
#: load-bearing guards as INVALID.
_RAISING = {"v4-1", "v4-6", "v4-8", "v4-10"}


def _expected(label: str) -> str:
    return ("DID NOT RAISE" if label.split(".")[0] in _RAISING else "assert")


PROOFS = [Proof(label=p[0], path=p[1], find=p[2], replace=p[3], target=p[4],
                expect_failure_contains=_expected(p[0]))
          for p in PROOFS]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS))
