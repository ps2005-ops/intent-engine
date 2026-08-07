"""Match arriving evidence to the expectations waiting for it.

WHY THIS EXISTS
---------------
`learning_cycle.run` has always accepted an `observations` mapping and scored
every open expectation against it. Production never passed one. The parameter
defaulted to `{}`, so `reconcile` was asked to score forty-six expectations
with nothing to score them against, correctly returned TOO_EARLY every time,
and the engine recorded — accurately, and for weeks — that no belief had been
tested. `expectation.reconcile` was never the defect. The wire into it was
missing.

Measured at the time this module was written: 27 of 46 open expectations
already had evidence about their own subject sitting in the ledger, ingested
after the expectation was preregistered. The engine was holding the answers
and not looking at them.

HOW A TEST IS FOUND
-------------------
No new taxonomy. `belief_formation._ROUTES` already says which evidence type
proposes which belief family and in which direction, and an expectation's
`metric` IS its family key. So the table that proposed a belief is exactly the
table that tests it: if an UP earnings result proposed `demand_strengthening`,
a later earnings result is the test, and its direction is the verdict.

WHAT IS DELIBERATELY NOT BOUND
------------------------------
**Occurrence-only families.** `capacity_expansion` expects "further capital
commitments"; a capex announcement confirms it and no capex announcement
refutes nothing, because absence is not observation. Binding those would build
a channel that can only ever confirm, and a test that cannot fail is not a
test — it is a ratchet that would drive every posterior to 1.0 and call it
learning. Only families whose evidence type routes BOTH ways are bound, so
each bound expectation can genuinely come back contradicted. That is 23 of the
46 on record; the other 23 stay open and honestly unresolved.

**The evidence that proposed the expectation.** Held out by id, not by date.
A same-day exclusion would be both too weak (a later cycle re-reading the same
document) and too strong (a genuinely different fact reported the same day).

**Anything but the earliest qualifying observation.** Choosing among several
is where a scoring system quietly becomes a flattering one. The first
qualifying evidence to arrive is the test, whichever way it points.
"""
from __future__ import annotations

import collections
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import belief_formation as BF
from . import expectation as EXP
from . import micro_evidence as ME

BINDING_VERSION = "observation_binding.v1"


def falsifiable_families() -> frozenset:
    """Families whose evidence can point either way, so a test can fail.

    Derived from the routing table rather than listed, so a family that gains
    a second direction becomes testable without anyone remembering to add it
    here — and one that loses it stops being bound automatically.
    """
    by_family: Dict[str, set] = collections.defaultdict(set)
    for etype, family, required in BF._ROUTES:
        if required is not None:
            by_family[family].add(required)
    directions_by_type: Dict[str, set] = collections.defaultdict(set)
    for etype, family, required in BF._ROUTES:
        if required is not None:
            directions_by_type[etype].add(required)
    # A family is falsifiable when at least one evidence type that routes to
    # it also routes the opposite way -- that is what makes the contradicting
    # observation reachable rather than merely conceivable.
    out = set()
    for etype, family, required in BF._ROUTES:
        if required is not None and len(directions_by_type[etype]) > 1:
            out.add(family)
    return frozenset(out)


FALSIFIABLE = falsifiable_families()


def types_testing(family: str) -> frozenset:
    """Evidence types that speak to this family, in EITHER direction.

    WHY NOT `routes_for`
    --------------------
    `routes_for` answers "what would this evidence propose", and that is the
    wrong question here. A DOWN earnings result proposes `demand_weakening`,
    so `routes_for` never returns `demand_strengthening` for it — and
    `demand_strengthening` is precisely the belief that result refutes.

    Filtering candidate tests through `routes_for` therefore admits only
    evidence pointing the way the belief already points. Measured on the live
    ledger before this was fixed: 8 expectations bound, 8 CONFIRMED, 0
    CONTRADICTED. Not a strong engine — a channel that had quietly been
    stripped of every disconfirming observation.

    So the type decides relevance and the direction decides the verdict, and
    the two are read independently.
    """
    return frozenset(etype for etype, fam, _ in BF._ROUTES if fam == family)


def _evidence_direction(item: ME.MicroEvidence) -> str:
    return BF.direction_of(item.fact)


def bind(expectations: Sequence[EXP.ExpectedObservation],
         evidence: Sequence[ME.MicroEvidence], *, as_of: str
         ) -> Tuple[Dict[str, dict], Dict[str, int]]:
    """Build the `observations` mapping `learning_cycle.run` already accepts.

    Returns (observations, why-not counts). The refusal counts are returned
    rather than dropped for the same reason belief formation returns them: an
    expectation that stayed open has several possible causes, and an operator
    who cannot tell "no evidence arrived" from "the family is not falsifiable"
    cannot tell patience from a bug.
    """
    refused: Dict[str, int] = collections.Counter()
    by_subject: Dict[str, List[ME.MicroEvidence]] = collections.defaultdict(list)
    for item in evidence:
        subject = (item.subject_company or "").strip().lower()
        if subject:
            by_subject[subject].append(item)
    # Earliest first: the first qualifying observation is the test.
    for subject in by_subject:
        by_subject[subject].sort(key=lambda e: (e.observed_at, e.evidence_id))

    observations: Dict[str, dict] = {}
    for exp in expectations:
        family = exp.metric
        if family not in FALSIFIABLE:
            refused["family_not_falsifiable_by_observation"] += 1
            continue

        subject = (exp.subject or "").strip().lower()
        basis = set(exp.evidence_basis or ())
        relevant_types = types_testing(family)
        found = None
        for item in by_subject.get(subject, ()):
            if item.evidence_id in basis:
                refused["evidence_proposed_this_expectation"] += 1
                continue
            if item.observed_at[:10] < exp.preregistered_at[:10]:
                continue
            if item.evidence_type not in relevant_types:
                continue
            direction = _evidence_direction(item)
            if not direction:
                refused["no_readable_direction"] += 1
                continue
            found = (item, direction)
            break

        if found is None:
            refused["no_qualifying_observation_yet"] += 1
            continue

        item, direction = found
        observations[exp.expectation_id] = {
            "observed_direction": direction,
            "observed_at": item.observed_at[:10],
            "evidence_ids": (item.evidence_id,),
            "binding": BINDING_VERSION,
        }
    return observations, dict(refused)


def summarise(observations: Dict[str, dict], refused: Dict[str, int],
              *, examined: int) -> dict:
    """One row an operator can read without opening the ledger."""
    return {
        "contract": BINDING_VERSION,
        "expectations_examined": examined,
        "observations_bound": len(observations),
        "falsifiable_families": sorted(FALSIFIABLE),
        "refused": dict(sorted(refused.items())),
    }
