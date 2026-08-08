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

    # A WEAK DISCONFIRMER IS NOT A CONTRADICTION.
    #
    # This treated any disconfirming signal as "the public record argues
    # against it", and measured live on Cloudflare that produced exactly that
    # sentence because the company publishes a price list. `pricing_published`
    # is `tool_to_system_of_record`'s disconfirmer, and that pattern's own note
    # says why it is a weak one: "a company can publish prices and still hold
    # the record."
    #
    # The library already separates the two. `blocking_signals` are the
    # disconfirmers strong enough to displace a reading; the rest argue with it
    # and are shown as counter-evidence. Only the strong ones may be reported
    # to a founder as the record pointing the other way.
    # Requiring a BLOCKING signal alone was tried and is too strict: only
    # `services_to_product` declares one, so the contradiction state became
    # unreachable for the rest of the library and a real "the record points
    # the other way" case would have gone unreported. Either a blocking
    # signal, or more than one ordinary disconfirmer — one weak signal is
    # noise, a second is a direction.
    strong = tuple(s for s in getattr(pattern, "blocking_signals", ())
                   if s in present) or (
        disconfirmed if len(disconfirmed) >= 2 else ())
    if blocked_families:
        state = RETRIEVAL_BLOCKED
    elif strong:
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


#: How much supporting evidence a refused reading needs before it is worth
#: naming. Below this the company simply is not that kind of company and
#: saying so is noise; the point of a near miss is that the run got close.
_NEAR_MISS_SUPPORT = 2


def near_misses(company, patterns, observations, *, fired_ids=(),
                limit: int = 2) -> list:
    """Readings this run ALMOST reached, as founder-facing objects.

    THE GAP THIS CLOSES. `classify` could already tell a retrieval hole from a
    contradiction, and nothing showed it to anyone. A founder saw a reading
    silently absent and could not tell whether the analysis had looked and
    found nothing, or never looked.

    Deliberately not every refusal. A reading is worth naming only when the
    run has real supporting evidence for the pattern AND exactly the
    mechanism is unverified — that is a decision-relevant gap. Everything
    else is the ordinary condition of not being that kind of company, and
    listing it would bury the one that matters.
    """
    present = set()
    for observation in observations or ():
        present.update(observation.signals or ())

    out = []
    for pattern in patterns:
        if pattern.pattern_id in set(fired_ids):
            continue
        if not _mechanisms(pattern):
            continue
        supporting = [s for s in pattern.qualifying_signals
                      if s in present and s not in _mechanisms(pattern)]
        if len(supporting) < _NEAR_MISS_SUPPORT:
            continue
        diagnosis = classify(pattern, observations)
        if diagnosis["state"] in (None, SUPPORTED):
            continue
        out.append({
            "pattern_id": pattern.pattern_id,
            "status": diagnosis["state"],
            "verified_evidence": supporting,
            "missing_mechanism": list(diagnosis.get("missing") or ()),
            "contradicting_evidence": list(diagnosis.get("disconfirmed_by")
                                           or ()),
            "source_family_needed": list(
                diagnosis.get("would_be_carried_by") or ()),
            "why_it_matters": pattern.mechanism,
            "falsifier": pattern.when_it_does_not_apply,
            "safe_explanation": explain(company, pattern, diagnosis),
        })
    return out[:limit]


#: What each mechanism would ESTABLISH, in a reader's words. The sentence
#: names the missing fact, never the pattern.
#:
#: The first version said "…establishing that Acme fits product → platform /
#: tool → infrastructure", which is `pattern.name` — the library's own
#: taxonomy, on the page, to a reader who has never met it. Every other
#: surface in this system filters exactly that (`reads_as_taxonomy`), and a
#: new surface reintroduced it. A founder cannot go and check whether a
#: company "fits product → platform"; they can check whether outside
#: businesses depend on it.
_WOULD_ESTABLISH = {
    "third_party_builds_on": "outside organisations build on this company",
    "external_operations_depend":
        "other businesses run their own operations on it",
    "system_of_record_claim": "it holds the authoritative record rather than "
                              "a copy of it",
    "shared_data_model": "its products run on one model of the customer's data",
    "replaces_incumbent_systems": "customers retire a system they already had",
    "cross_product_coupling": "its products share identity, billing or "
                              "contracts",
    "content_and_channel": "it owns both what is sold and the channel that "
                           "distributes it",
    "agent_executes_actions": "software acts on the customer's behalf rather "
                              "than suggesting",
    "agent_callable_endpoint": "it ships a surface an agent can transact "
                               "through",
    "human_intervention_reduced": "the workflow runs without a person",
    "services_motion": "it delivers work alongside customers",
    "productization": "it sells what those engagements taught it",
    "segment_split": "it names two clearly different buyer groups",
    "gov_dedicated_delivery": "it runs a separate estate for public-sector "
                              "buyers",
    "accreditation_gate": "it holds accreditations those buyers require",
    "public_procurement_vehicle": "it is bought through public procurement",
    "disclosed_public_sector_exposure": "it has disclosed what those buyers "
                                        "contribute",
}


def _in_readers_words(diagnosis) -> str:
    claims = [_WOULD_ESTABLISH[m] for m in (diagnosis.get("missing") or ())
              if m in _WOULD_ESTABLISH]
    if not claims:
        return ""
    if len(claims) == 1:
        return claims[0]
    return " or ".join([", ".join(claims[:-1]), claims[-1]])


def explain(company: str, pattern, diagnosis: dict) -> str:
    """What a founder is told. Never the raw label, and never the pattern."""
    state = diagnosis.get("state")
    if state in (None, SUPPORTED):
        return ""
    claim = _in_readers_words(diagnosis)
    if not claim:
        return ""
    subject = claim
    if state == MECHANISM_CONTRADICTED:
        return (f"The public record argues against the reading that "
                f"{subject}: what was retrieved points the other way.")
    if state == RETRIEVAL_BLOCKED:
        return (f"We could not establish whether {subject}: the sources that "
                f"would show it were unavailable to this run.")
    if state == RETRIEVAL_MISSING:
        carriers = diagnosis.get("would_be_carried_by") or ()
        where = f" It would usually appear in {carriers[0]}." if carriers else ""
        return (f"We found signs of this shape for {company}, but did not "
                f"verify that {subject}. That distinction matters: this run "
                f"did not read a source that would show it, which is not "
                f"the same as finding it untrue.{where}")
    return (f"The sources this run read do not establish that {subject}. "
            f"They are the kind of sources that would show it, so treat the "
            f"absence as informative rather than incidental.")
