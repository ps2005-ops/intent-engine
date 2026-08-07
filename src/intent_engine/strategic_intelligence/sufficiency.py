"""Why a gated reading did not qualify — and whether that is a finding.

THE CASE THIS EXISTS FOR. `product_to_platform` was gated on evidence that
third parties depend on the company. Stripe stopped qualifying. Stripe is, in
the world, infrastructure that thousands of businesses depend on — but the
run's retrieved sources never said so, and the engine was right not to assert
it.

Refusing was correct. Reporting it as though the evidence argued against it
would not be. Those are different states and the product could not tell them
apart:

    MECHANISM_CONTRADICTED   the run retrieved evidence that weakens this
    REASONING_NOT_SUPPORTED  the right kind of sources were read and none of
                             them establishes the mechanism
    RETRIEVAL_MISSING        the sources that would carry the mechanism were
                             never retrieved, so this run cannot speak to it
    RETRIEVAL_BLOCKED        those sources were attempted and refused
    SUPPORTED                the mechanism is evidenced

Absence of evidence is not evidence of absence. It is also not permission to
assert. The distinction changes what a founder should DO — chase a source, or
stop believing the thesis — which is why it is worth carrying.

These labels are internal. `explain()` is what a reader sees.
"""
from __future__ import annotations

SUPPORTED = "SUPPORTED"
MECHANISM_CONTRADICTED = "MECHANISM_CONTRADICTED"
REASONING_NOT_SUPPORTED = "REASONING_NOT_SUPPORTED"
RETRIEVAL_MISSING = "RETRIEVAL_MISSING_MECHANISM_EVIDENCE"
RETRIEVAL_BLOCKED = "RETRIEVAL_BLOCKED"

#: Which kind of source usually carries a given mechanism. Used to decide
#: whether a run was ever in a position to observe it — NOT to go looking for
#: a conclusion. See `mechanism_request`.
_CARRIED_BY = {
    "third_party_builds_on": ("developer documentation, a marketplace or app "
                              "directory, or partner case studies"),
    "external_operations_depend": ("customer architecture stories, partner "
                                   "case studies, or a filing describing "
                                   "ecosystem reliance"),
    "system_of_record_claim": ("product documentation or a filing describing "
                               "what the platform holds"),
    "shared_data_model": ("architecture or platform documentation"),
    "replaces_incumbent_systems": ("migration guides or customer case "
                                   "studies"),
    "cross_product_coupling": ("pricing, packaging or administration "
                               "documentation"),
    "content_and_channel": ("a segment disclosure or an investor "
                            "presentation"),
    "services_motion": ("a professional-services or implementation page"),
    "productization": ("a product page describing what was productised"),
    "segment_split": ("a customers page or a segment disclosure"),
}


def _mechanisms(pattern) -> tuple:
    return tuple(pattern.required_signals) + tuple(pattern.required_any_signals)


def classify(pattern, observations, *, blocked_families=()) -> dict:
    """Why this pattern did or did not qualify, as a diagnosis.

    `blocked_families` are source kinds the run tried and could not read; a
    run that was refused is in a different position from one that never
    looked.
    """
    mechanisms = _mechanisms(pattern)
    if not mechanisms:
        # Ungated pattern: it claims no mechanism, so there is nothing to be
        # insufficient about. Recorded debt, not a diagnosis.
        return {"state": None, "mechanisms": (), "missing": (),
                "would_be_carried_by": ()}

    present = set()
    for observation in observations or ():
        present.update(observation.signals or ())

    have = tuple(m for m in mechanisms if m in present)
    missing = tuple(m for m in mechanisms if m not in present)
    disconfirmed = tuple(s for s in pattern.disconfirming_signals
                         if s in present)

    if have:
        return {"state": SUPPORTED, "mechanisms": have, "missing": (),
                "would_be_carried_by": ()}

    carriers = tuple(_CARRIED_BY[m] for m in missing if m in _CARRIED_BY)

    if blocked_families:
        state = RETRIEVAL_BLOCKED
    elif disconfirmed:
        # The run read something that argues the other way. That IS a finding.
        state = MECHANISM_CONTRADICTED
    elif _looked_in_the_right_place(pattern, observations):
        state = REASONING_NOT_SUPPORTED
    else:
        state = RETRIEVAL_MISSING
    return {"state": state, "mechanisms": (), "missing": missing,
            "would_be_carried_by": carriers,
            "disconfirmed_by": disconfirmed}


def _looked_in_the_right_place(pattern, observations) -> bool:
    """Whether this run read the kind of source that carries the mechanism.

    Deliberately coarse: a run holding a filing and product documentation has
    looked where the mechanism would be, and its silence is informative. A run
    holding only a homepage has not, and its silence is not.

    Coarse is the honest setting. A precise mapping from mechanism to URL is
    the beginning of retrieving until the answer comes out the way you wanted.
    """
    kinds = {(o.source_class or "") for o in (observations or ())}
    depth = sum(1 for o in (observations or ())
                if len(o.excerpt or "") > 400)
    return len(kinds) >= 2 and depth >= 1


def mechanism_request(pattern) -> tuple:
    """What facts would settle this, phrased as facts.

    THE CONFIRMATION-BIAS BOUNDARY. This returns "evidence that third parties
    build on the company", never "evidence for product_to_platform". A
    retrieval layer told which CONCLUSION to support will find support for it;
    one told which FACT is missing can come back empty, and coming back empty
    has to remain possible or the gate is theatre.

    `test_retrieval_is_never_asked_to_prove_a_named_hypothesis` enforces that
    no pattern id appears in anything this returns.
    """
    out = []
    for signal in _mechanisms(pattern):
        carrier = _CARRIED_BY.get(signal)
        if carrier:
            out.append(f"evidence of {signal.replace('_', ' ')}, usually "
                       f"found in {carrier}")
    return tuple(out)


def explain(company: str, pattern, diagnosis: dict) -> str:
    """What a founder is told. Never the raw label."""
    state = diagnosis.get("state")
    if state in (None, SUPPORTED):
        return ""
    subject = pattern.name.lower()
    if state == MECHANISM_CONTRADICTED:
        return (f"The public record argues against reading {company} as "
                f"{subject}: what was retrieved points the other way.")
    if state == RETRIEVAL_BLOCKED:
        return (f"We could not establish whether {company} fits "
                f"{subject}: the sources that would show it were unavailable "
                f"to this run.")
    if state == RETRIEVAL_MISSING:
        carriers = diagnosis.get("would_be_carried_by") or ()
        where = f" It would usually appear in {carriers[0]}." if carriers else ""
        return (f"We did not find public evidence establishing that {company} "
                f"fits {subject}. That does not mean it is untrue — this run "
                f"did not read a source that would show it.{where}")
    return (f"The sources this run read do not establish that {company} fits "
            f"{subject}. They are the kind of sources that would show it, so "
            f"treat the absence as informative rather than incidental.")
