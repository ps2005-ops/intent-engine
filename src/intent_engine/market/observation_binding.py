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


def _fingerprint(text: str) -> str:
    """A fact's identity, independent of which outlet carried it.

    Punctuation, case and the trailing "- Publisher Name" attribution are
    stripped, because the same wire story reaching the ledger twice with
    two ids is the exact case this exists to catch. Deliberately blunt: a
    fuzzy similarity threshold would need tuning against a corpus nobody
    has labelled, and the failure it prevents -- a belief scoring itself
    -- is worth over-rejecting a little to avoid.
    """
    import re
    body = re.split(r"\s+[-–—]\s+[A-Z]", " ".join((text or "").split()))[0]
    return re.sub(r"[^a-z0-9 ]", "", body.lower()).strip()[:120]


def _evidence_direction(item: ME.MicroEvidence) -> str:
    return BF.direction_of(item.fact)


def bind(expectations: Sequence[EXP.ExpectedObservation],
         evidence: Sequence[ME.MicroEvidence], *, as_of: str,
         event_index: Optional[Dict[str, str]] = None
         ) -> Tuple[Dict[str, dict], Dict[str, int]]:
    """Build the `observations` mapping `learning_cycle.run` already accepts.

    Returns (observations, why-not counts). The refusal counts are returned
    rather than dropped for the same reason belief formation returns them: an
    expectation that stayed open has several possible causes, and an operator
    who cannot tell "no evidence arrived" from "the family is not falsifiable"
    cannot tell patience from a bug.
    """
    from . import event_identity as EI

    refused: Dict[str, int] = collections.Counter()
    # One occurrence, many accounts. An expectation opened by one report of
    # an event must not be tested by another report of the SAME event, and
    # the fact fingerprint cannot see that: two outlets write it differently.
    # Grouping 249 rows costs ~5ms and does not change between calls in a
    # cycle, so a caller that binds more than once computes it once. The
    # fallback keeps every existing call site working unchanged.
    event_of = (event_index if event_index is not None
                else EI.index(EI.group(evidence)))
    corroboration: Dict[str, int] = collections.Counter()
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
        basis_text = {_fingerprint(e.fact) for e in evidence
                      if e.evidence_id in basis}
        relevant_types = types_testing(family)
        found = None
        for item in by_subject.get(subject, ()):
            if item.evidence_id in basis:
                refused["evidence_proposed_this_expectation"] += 1
                continue
            # SAME FACT, DIFFERENT ID. Holding out the basis by id is not
            # enough: the same story arrives twice, from two outlets or on two
            # sweeps, with two ids and near-identical text. Measured on the
            # real ledger before this guard -- 3 of 10 informative results
            # scored a belief against the very sentence that opened it,
            # including one where opener and test were byte-identical.
            #
            # Those are self-tests, and every one of them came back CONFIRMED,
            # which is exactly how a channel that cannot fail looks from the
            # outside.
            if _fingerprint(item.fact) in basis_text:
                refused["restates_the_evidence_that_opened_it"] += 1
                continue
            # Different wording, different outlet, SAME occurrence. This is
            # corroboration of the opener and is counted as such rather than
            # discarded — throwing it away would cost the source diversity
            # that makes the opener worth anything.
            opener_events = [event_of.get(i) for i in basis]
            if EI.role_of(event_of.get(item.evidence_id),
                          [e for e in opener_events if e]) == EI.CORROBORATES:
                refused["corroborates_the_opening_event"] += 1
                corroboration[exp.expectation_id] += 1
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
        # NOTE: this dict is `expectation.reconcile`'s argument list. A key
        # added here becomes a keyword argument there, so corroboration
        # counts live in the refusal telemetry instead — where the health
        # layer reads them and where they cannot break a contract.
        observations[exp.expectation_id] = {
            "observed_direction": direction,
            "observed_at": item.observed_at[:10],
            "evidence_ids": (item.evidence_id,),
            "binding": BINDING_VERSION,
        }
    out = dict(refused)
    if corroboration:
        out["corroborating_accounts"] = sum(corroboration.values())
    return observations, out


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


# ---------------------------------------------------------------------------
# why a candidate was a self-test — the decomposition
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS AS A CAPABILITY RATHER THAN A ONE-OFF PROBE
# -----------------------------------------------------------
# "self_test_rate is 0.8" is a number nobody can act on. "28 of 31 are the
# same page re-read on a later sweep" names a producer, and the producer was
# `evidence_id_for` hashing the date the sweep ran into the identity of the
# fact it read. One measurement found it; the class breakdown is what made
# the measurement possible, so it stays.
#
# The classes are ordered from most mechanical to least, and the first match
# wins. AMBIGUOUS is real and is reported rather than absorbed.
EXACT_FACT_RESTATEMENT = "EXACT_FACT_RESTATEMENT"
SEMANTIC_RESTATEMENT = "SEMANTIC_RESTATEMENT"
SAME_SOURCE_REPACKAGING = "SAME_SOURCE_REPACKAGING"
WIRE_DUPLICATE = "WIRE_DUPLICATE"
SAME_EVENT_DIFFERENT_HEADLINE = "SAME_EVENT_DIFFERENT_HEADLINE"
SAME_DOCUMENT_DIFFERENT_EXCERPT = "SAME_DOCUMENT_DIFFERENT_EXCERPT"
LEGITIMATE_LATER_OBSERVATION = "LEGITIMATE_LATER_OBSERVATION"
AMBIGUOUS = "AMBIGUOUS"

SELF_TEST_CLASSES = (
    EXACT_FACT_RESTATEMENT, SEMANTIC_RESTATEMENT, SAME_SOURCE_REPACKAGING,
    WIRE_DUPLICATE, SAME_EVENT_DIFFERENT_HEADLINE,
    SAME_DOCUMENT_DIFFERENT_EXCERPT, LEGITIMATE_LATER_OBSERVATION, AMBIGUOUS)

#: Which producer each class blames. A class with no named producer is a
#: class nobody can fix, and that is worth saying out loud.
PRODUCER_OF = {
    SAME_SOURCE_REPACKAGING: (
        "ingestion: the same source re-read on a later sweep. Fixed at "
        "`micro_evidence.occurrence_key`, which no longer hashes the sweep "
        "date into a fact's identity"),
    EXACT_FACT_RESTATEMENT: (
        "ingestion: byte-identical text from a different source. Two "
        "outlets genuinely are two items, so this is correlated evidence "
        "rather than a duplicate row"),
    WIRE_DUPLICATE: (
        "the wire: one story, several outlets. Correlated, handled by the "
        "design-effect penalty in `beliefs`, never by pretending it is one "
        "observation"),
    SAME_EVENT_DIFFERENT_HEADLINE: (
        "the aggregator: one event, two headlines. Caught by the fact "
        "fingerprint rather than by identity"),
    SAME_DOCUMENT_DIFFERENT_EXCERPT: (
        "extraction: one document, two spans of it, both routed to the "
        "same belief"),
    SEMANTIC_RESTATEMENT: (
        "no mechanical producer — the two sentences say the same thing in "
        "different words, which no fingerprint catches"),
    LEGITIMATE_LATER_OBSERVATION: "not a self-test; admitted",
    AMBIGUOUS: "unclassified; inspect before acting on the count",
}


def classify_self_test(opener, candidate) -> str:
    """Which kind of self-test this pair is. First match wins."""
    same_text = (opener.fact or "").strip() == (candidate.fact or "").strip()
    same_source = (opener.source == candidate.source
                   and opener.source_role == candidate.source_role)
    if same_text and same_source:
        if opener.observed_at[:10] == candidate.observed_at[:10]:
            return SAME_DOCUMENT_DIFFERENT_EXCERPT
        return SAME_SOURCE_REPACKAGING
    if same_text and opener.source_role != candidate.source_role:
        return WIRE_DUPLICATE
    if same_text:
        return EXACT_FACT_RESTATEMENT
    if _fingerprint(opener.fact) == _fingerprint(candidate.fact):
        return SAME_EVENT_DIFFERENT_HEADLINE
    return SEMANTIC_RESTATEMENT


def diagnose(expectations: Sequence[EXP.ExpectedObservation],
             evidence: Sequence[ME.MicroEvidence]) -> dict:
    """Decompose the self-test population, and name a producer for each class.

    Reports the classes as counts and the producers as sentences, because a
    rate without a producer is a dashboard and a producer without a count is
    an opinion.
    """
    by_id = {e.evidence_id: e for e in evidence}
    by_subject: Dict[str, List[ME.MicroEvidence]] = collections.defaultdict(list)
    for item in evidence:
        subject = (item.subject_company or "").strip().lower()
        if subject:
            by_subject[subject].append(item)

    counts: Dict[str, int] = collections.Counter()
    samples: Dict[str, dict] = {}
    for exp in expectations:
        basis = set(exp.evidence_basis or ())
        openers = {_fingerprint(by_id[i].fact): by_id[i]
                   for i in basis if i in by_id}
        for candidate in by_subject.get((exp.subject or "").strip().lower(),
                                        ()):
            if candidate.evidence_id in basis:
                continue
            opener = openers.get(_fingerprint(candidate.fact))
            if opener is None:
                continue
            kind = classify_self_test(opener, candidate)
            counts[kind] += 1
            samples.setdefault(kind, {
                "subject": exp.subject,
                "opener": opener.evidence_id,
                "candidate": candidate.evidence_id,
                "opener_seen": opener.observed_at[:10],
                "candidate_seen": candidate.observed_at[:10],
                "identical_text": (opener.fact or "").strip()
                == (candidate.fact or "").strip()})
    total = sum(counts.values())
    return {
        "contract": BINDING_VERSION,
        "self_tests": total,
        "by_class": {k: counts.get(k, 0) for k in SELF_TEST_CLASSES
                     if counts.get(k)},
        "producers": {k: PRODUCER_OF.get(k, "") for k in counts},
        "samples": samples,
        "dominant_class": (counts.most_common(1)[0][0] if counts else ""),
        "note": ("a self-test rate without a class breakdown names no "
                 "producer, and every producer named here is upstream of "
                 "this module"),
    }
