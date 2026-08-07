"""A conclusion a founder cannot check is not intelligence.

THE DEFECT THIS CLOSES. `tool_to_system_of_record` qualified for HubSpot on a
real mechanism — its 10-K says "Our customer platform includes a system of
record for maintaining a unified view of the customer experience" — and the
deployed page showed, as the evidence, "We provide an agentic customer
platform that helps marketing, sales, and customer service teams drive
business growth". The first four hundred characters of the document. The gate
fired correctly; the explanation layer showed the wrong passage.

It was structural, not a typo. An observation is one DOCUMENT and carries
every signal found anywhere in it — HubSpot's filing carried eighteen — while
`excerpt` is chosen once for the whole document. It can therefore be the right
evidence for at most one of those signals, and for a long filing it is the
right evidence for none: the opening of a 10-K is a business description, and
the mechanism sentence is thousands of words further down.

So a signal now records the sentence that produced it (`signal_spans`), the
hypothesis carries the ones that qualified it (`MechanismEvidence`), and one
module turns that into words (`mechanism.py`). This file holds the contract.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.strategic_intelligence import mechanism as MECH
from intent_engine.strategic_intelligence.observations import (
    _NEUTRAL_SIGNAL_KEYWORDS, _SIGNAL_KEYWORDS, derive_observations,
    phrase_span, signal_spans,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import (
    build_strategic_report,
)

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
SRC = pathlib.Path(__file__).resolve().parents[1] / "src/intent_engine"

# The measured case, reduced: a document whose opening says nothing about the
# mechanism, and whose mechanism sentence is further down.
HUBSPOT_SHAPED = (
    "We provide an agentic customer platform that helps marketing, sales, and "
    "customer service teams drive business growth. We deliver seamless "
    "connection for customer-facing teams with a unified platform. "
    "Explore the suite: Marketing, Sales and Service. Developers can use our "
    "REST API and read the developer docs. "
    "Our customer platform includes a system of record for maintaining a "
    "unified view of the customer experience."
)


def _doc(sid, text, title="Acme"):
    return {"source_id": sid, "source_type": "product", "title": title,
            "final_url": f"https://acme.example/{sid}", "meta_description": "",
            "text_content": text, "retrieval_status": "OK",
            "freshness": "CURRENT", "content_hash": sid,
            "retrieved_at": "2026-08-06", "parser_version": "p1"}


@pytest.fixture(scope="module")
def report():
    obs = derive_observations([_doc("s1", HUBSPOT_SHAPED)], company="Acme")
    return build_strategic_report(company_name="Acme", observations=obs)


@pytest.fixture(scope="module")
def sor(report):
    for h in report.hypotheses:
        if h.pattern_id == "tool_to_system_of_record":
            return h
    pytest.fail(f"the fixture no longer produces the reading under test: "
                f"{[h.pattern_id for h in report.hypotheses]}")


# --- a signal knows where it was found ---------------------------------------

def test_a_span_is_the_sentence_that_carried_the_phrase():
    span = phrase_span(HUBSPOT_SHAPED,
                       _NEUTRAL_SIGNAL_KEYWORDS["system_of_record_claim"])
    assert "system of record for maintaining a unified view" in span
    assert "agentic customer platform" not in span, \
        "the span must be the sentence that matched, not the document opening"


def test_each_signal_gets_its_own_span_not_the_documents():
    spans = signal_spans(HUBSPOT_SHAPED)
    assert "system of record" in spans["system_of_record_claim"]
    assert "REST API" in spans["developer_surface"]
    assert spans["system_of_record_claim"] != spans["developer_surface"], \
        "one document, many signals — each needs its own evidence"


def test_a_long_span_is_trimmed_at_word_boundaries():
    """A quotation is only checkable if it reads as language.

    Measured on the deployed Palantir result: the evidence opened "…ong with
    ongoing O&M services", a half-word the reader has to decode before they
    can judge it. Long sentences are common in filings, which is exactly
    where this evidence comes from.
    """
    filler = "The company describes its commercial arrangements at length. "
    text = (filler * 6
            + "Revenue is generated along with ongoing O&M services and the "
              "platform acts as the system of record for the customer estate "
              "under multi-year agreements. " + filler * 4)
    span = phrase_span(text, _NEUTRAL_SIGNAL_KEYWORDS["system_of_record_claim"])
    assert "the system of record for" in span
    core = span.strip("…").strip()
    assert not core.startswith(" ") and not core.endswith(" ")
    for edge in (core.split()[0], core.split()[-1]):
        assert edge in text, f"{edge!r} is a fragment, not a word from the source"


def test_a_span_is_absent_rather_than_empty_when_unresolvable():
    """A caller must be able to tell "nothing to show" from "the empty
    string", or it will render a quotation mark around nothing."""
    assert "system_of_record_claim" not in signal_spans("We sell software.")


def test_the_observation_carries_its_spans():
    obs = derive_observations([_doc("s1", HUBSPOT_SHAPED)], company="Acme")
    assert obs, "fixture produced no observation"
    spans = obs[0].signal_spans
    assert "system of record" in spans.get("system_of_record_claim", "")


# --- the hypothesis carries the mechanism that qualified it -------------------

def test_the_reading_can_show_what_caused_it(sor):
    evidence = MECH.evidence_of(sor)
    assert evidence, "the reading qualified on a mechanism and cannot show it"
    assert {e["signal"] for e in evidence} <= set(
        PATTERNS["tool_to_system_of_record"].required_any_signals)


def test_the_evidence_is_the_sentence_not_the_excerpt(sor):
    quote = MECH.evidence_of(sor)[0]["quote"]
    assert "system of record for maintaining a unified view" in quote
    assert "agentic customer platform" not in quote, \
        "this is the exact substitution the deployed page made"


def test_the_evidence_is_quoted_rather_than_paraphrased(sor):
    """A paraphrase is the analysis marking its own homework. The founder must
    be able to disagree with the COMPANY's words."""
    line = MECH.because_line(sor)
    assert "“" in line and "”" in line
    assert "system of record" in line


def test_the_excerpt_is_never_substituted_for_the_missing_sentence():
    """THE DEFECT ITSELF, AS A GUARD.

    Found by a break proof: replacing the "no span, skip it" branch with "no
    span, use the excerpt" left the whole suite green. That mutation IS the
    deployed defect — quoting a document's opening as evidence for a specific
    signal — so nothing was protecting against its return.

    The case that catches it has to be the awkward one: an observation with no
    captured spans AND an excerpt that does not contain the phrase. Then the
    only way to produce evidence is to substitute something unrelated, and the
    correct answer is to produce none.
    """
    from intent_engine.strategic_intelligence.records import (
        StrategicObservation,
    )
    from intent_engine.strategic_intelligence.reasoning import (
        _mechanism_evidence,
    )
    observation = StrategicObservation(
        observation_id="obs-x",
        text="Acme shows a signal.",
        observation_type="product_surface",
        source_refs=[{"artifact_id": "x"}],
        signals=("system_of_record_claim", "multi_product"),
        # the shape that produced the live defect: a long document whose
        # opening is a business description and whose mechanism sentence is
        # thousands of words further down and NOT in the excerpt
        excerpt="We provide an agentic customer platform that helps teams "
                "drive business growth.",
        source_title="Acme 10-K", origin="https://acme.example/10k")
    assert not observation.signal_spans, "fixture must have no captured spans"
    evidence = _mechanism_evidence(PATTERNS["tool_to_system_of_record"],
                                   [observation])
    assert evidence == (), (
        "the excerpt was substituted for the sentence that caused the "
        "reading — this is exactly the defect this cycle removed")


def test_a_late_resolution_still_quotes_only_the_matching_sentence():
    """The companion to the test above.

    Spans are captured during detection, and observations built elsewhere
    (fixtures, caches, the stored path) have none. Those may still be
    resolved — but by SEARCHING the excerpt for the phrase, never by assuming
    the excerpt is about it.
    """
    from intent_engine.strategic_intelligence.records import (
        StrategicObservation,
    )
    from intent_engine.strategic_intelligence.reasoning import (
        _mechanism_evidence,
    )
    observation = StrategicObservation(
        observation_id="obs-y",
        text="Acme shows a signal.",
        observation_type="product_surface",
        source_refs=[{"artifact_id": "y"}],
        signals=("system_of_record_claim",),
        excerpt="We sell software to teams. Acme is the system of record for "
                "your customer data. Pricing starts low.",
        source_title="Acme", origin="https://acme.example/")
    evidence = _mechanism_evidence(PATTERNS["tool_to_system_of_record"],
                                   [observation])
    assert evidence, "a resolvable phrase in the excerpt must still be quoted"
    quote = evidence[0].quote
    assert "system of record for your customer data" in quote
    assert "Pricing starts low" not in quote, \
        "the quote must be the matching sentence, not the whole excerpt"


def test_the_mechanism_names_its_source(sor):
    assert MECH.citations(sor), "evidence with no observation id cannot be traced"
    assert all(e.get("observation_id") for e in MECH.evidence_of(sor))


def test_the_evidence_survives_serialisation(report):
    """Every surface downstream reads dicts, and this is where a field is
    silently dropped."""
    d = report.as_dict()
    hyp = [h for h in d["hypotheses"]
           if h["pattern_id"] == "tool_to_system_of_record"][0]
    assert hyp["mechanism_evidence"], "lost in as_dict()"
    assert MECH.evidence_of(hyp), "the dict form must answer the same question"
    assert MECH.because_line(hyp) == MECH.because_line(
        [h for h in report.hypotheses
         if h.pattern_id == "tool_to_system_of_record"][0]), \
        "object and dict must produce the SAME sentence, or surfaces disagree"


# --- every gated pattern must be ABLE to show its mechanism -------------------

GATED = sorted(pid for pid, p in PATTERNS.items()
               if p.required_signals or p.required_any_signals)


@pytest.mark.parametrize("pid", GATED)
def test_every_gated_pattern_can_resolve_a_span_for_its_mechanism(pid):
    """A gate whose signal has no phrases could never quote itself, so the
    reading it produces would be permanently unexplainable. Filing-derived
    propositions are exempt: they are matched by sentence-scoped rules in
    `filing_detectors` rather than by a keyword table here.
    """
    from intent_engine.strategic_intelligence import filing_detectors as FD
    pattern = PATTERNS[pid]
    for signal in (tuple(pattern.required_signals)
                   + tuple(pattern.required_any_signals)):
        if signal in FD.PROPOSITIONS:
            continue
        assert (signal in _NEUTRAL_SIGNAL_KEYWORDS
                or signal in _SIGNAL_KEYWORDS), (
            f"{pid} gates on {signal!r}, which has no phrase table — the "
            "reading could never show what caused it")


# --- the explanation contract, per pattern ------------------------------------

@pytest.mark.parametrize("pid", sorted(PATTERNS))
def test_every_pattern_declares_the_full_explanation_contract(pid):
    """Seven things a reading owes a founder.

    MONITORING AND FALSIFIER ARE ONE FIELD HERE, DELIBERATELY. What a founder
    should watch for IS the observation that would make the reading wrong —
    the deck's watch screen is built from `falsification` for exactly that
    reason. Two fields holding one idea drift apart and then two surfaces
    disagree, which is the failure this whole cycle is about.
    """
    pattern = PATTERNS[pid]
    scaffold = HYPOTHESIS_SCAFFOLDS.get(pid) or {}
    assert pattern.mechanism.strip(), f"{pid}: no mechanism"
    assert pattern.when_it_applies.strip(), f"{pid}: no applicability"
    assert pattern.when_it_does_not_apply.strip(), f"{pid}: no inapplicability"
    assert pattern.qualifying_signals, f"{pid}: no evidence vocabulary"
    assert pattern.limitations.strip(), f"{pid}: no uncertainty"
    assert (pattern.disconfirming_signals
            or scaffold.get("alternatives")), f"{pid}: no counter-evidence"
    assert scaffold.get("falsification"), f"{pid}: no falsifier / watch item"
    assert scaffold.get("gaps"), f"{pid}: no stated unknown"


# --- one phrasing, not one per surface ----------------------------------------

def test_only_the_mechanism_module_phrases_the_evidence_line():
    """THE ARCHITECTURAL RULE.

    Every surface used to decide for itself which evidence to show, and they
    all decided wrong in the same way. If a second module starts formatting
    the quoted-evidence sentence, the deck and the brief will eventually
    disagree about why the same company got the same reading — which is the
    defect wearing different clothes.
    """
    marker = "The company's own words:"
    owners = sorted(p.relative_to(SRC).as_posix()
                    for p in SRC.rglob("*.py") if marker in p.read_text())
    assert owners == ["founder_brief/narrative.py",
                      "strategic_intelligence/slides.py"], owners
    # ...and both get the QUOTE itself from the one module that builds it.
    for path in owners:
        text = (SRC / path).read_text()
        assert "mechanism" in text and "because_line" in text, (
            f"{path} writes the evidence lead-in without calling "
            "mechanism.because_line — it is regenerating the explanation")


def test_a_gated_reading_without_its_mechanism_stays_quiet():
    """The rule that makes the contract enforceable rather than aspirational.

    A hypothesis whose pattern claims a mechanism, but which cannot produce
    the sentence that established it, must not be handed to a founder as a
    consequence. Saying less is the correct behaviour; asserting a structural
    force with nothing behind it is what this cycle removes.
    """
    silent = {"pattern_id": "tool_to_system_of_record",
              "statement": "Acme appears to be broadening from a focused tool.",
              "mechanism_evidence": []}
    assert MECH.needs_mechanism(silent)
    assert not MECH.is_explained(silent)
    assert MECH.because_line(silent) == ""


def test_the_three_states_are_distinguishable_to_a_reader():
    """SILENCE IS NOT TRANSPARENCY, and this is the test that says so.

    The first attempt dropped a gated claim that could not quote itself.
    Measured, that was worse than saying it: `services_to_product` lost an
    entire company-specific section, and its page moved CLOSER to an unrelated
    company's — `test_break_two_unrelated_companies_receive_the_same_narrative`
    went red, because what had been removed was the specific half and what
    remained was the shared scaffolding.

    So a reading is never silently withheld. It arrives in one of three
    states, and a founder can tell which.
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_scrollable_narrative import _synthetic, _text

    # gated, nothing quotable in the fixture -> claim kept, status stated
    gated = " ".join(_text(_synthetic("services_to_product")[2]).split())
    assert "the engagement teaches the workflow" in gated, \
        "the claim was silently dropped instead of labelled"
    assert "No retrieved source states this in its own words" in gated

    # ungated -> untouched, no status line invented for it
    ungated = " ".join(_text(_synthetic("smb_wedge_to_enterprise")[2]).split())
    assert "smaller-customer base toward larger enterprise buyers" in ungated
    assert "No retrieved source states this" not in ungated


def test_the_evidenced_state_quotes_instead_of_disclaiming(sor):
    """And when the evidence IS there, the reader gets the words, not a note
    about their absence."""
    line = MECH.because_line(sor)
    assert "system of record" in line
    assert "No retrieved source" not in line


def test_an_ungated_pattern_is_not_silenced_by_this_rule():
    """The recorded debt keeps the analysis it always had. Suppressing it here
    would delete working readings to punish a gap tracked in
    `test_every_pattern_earns_its_mechanism`."""
    ungated = {"pattern_id": "portfolio_run_as_one", "mechanism_evidence": []}
    assert not MECH.needs_mechanism(ungated)
