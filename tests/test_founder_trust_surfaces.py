"""Normalized trust on the surfaces BESIDE the analysis: Q&A and slides.

WHY THIS FILE EXISTS
--------------------
The analysis page was taught to reason from occurrences rather than rows. The
surfaces around it were not, and a founder does not experience "the analysis
path" — they experience whichever screen they happened to open. Q&A was the
worst case, because it is the surface a founder uses to ASK how strong the
evidence is:

    "Probably — 3 independent source(s) support this. Removing the strongest
     one still leaves independent corroboration."

Every number in that sentence was a row count. `independent` meant "the
publisher is not the company", which is a statement about who printed it, not
about whether the accounts are separate. Three outlets rewriting one press
release satisfied it three times. The sentence also leaked `corroboration` —
a banned founder-facing term — because it was assembled after `_plain` had
already run over the answer.

So this pins three things:

    the standing DECIDES the answer, and the row count does not;
    the same rows under different standings give different answers;
    a dossier newer than the analysis is not silently applied to it.
"""
from __future__ import annotations

import inspect

import pytest

from intent_engine.external_intel import evidence_trust as ET
from intent_engine.founder_brief import qa as FQA
from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY
from tests.test_founder_brief_v3 import _rich

#: Three rows whose publisher is not the company. Under the old rule this was
#: "3 independent sources" on its own, whatever the rows actually were.
THREE_ROWS = [{"source_class": "press", "text": "a", "date": "2026-07-01"},
              {"source_class": "press", "text": "b", "date": "2026-07-01"},
              {"source_class": "press", "text": "c", "date": "2026-07-02"}]

ABLATION = "What is this based on — would it hold without that source?"


def _trust(standing, *, raw=3, distinct=1, independent=0, weight=1.0):
    return ET.read({"standing": standing, "raw_accounts": raw,
                    "distinct_events": distinct,
                    "independent_support": independent, "weight": weight,
                    "sentence": ""})


DEPENDENT = _trust(ET.DEPENDENT_REREPORTING)
INDEPENDENT = _trust(ET.INDEPENDENTLY_CORROBORATED, distinct=3, independent=3,
                     weight=2.0)
CONFLICTED = _trust(ET.CONFLICTED, distinct=2)
SINGLE = _trust(ET.SINGLE_SOURCE, raw=1, distinct=1)


def _answer(trust):
    return FQA.answer(ABLATION, _rich(), engine_answer="",
                      observations=THREE_ROWS, trust=trust)


def _code_only(module) -> str:
    """A module's EXECUTABLE source, with comments and docstrings removed.

    A structural guard that greps raw source cannot tell code from the comment
    explaining why the code is not there. Both guards below first failed that
    way — one matched the note recording that a source count was removed, the
    other matched this file's own description of the rule it enforces. A
    prose-matching guard reports the defect as present forever after it is
    fixed, and reports it absent the moment someone deletes the comment.
    """
    import io
    import tokenize

    src = inspect.getsource(module)
    kept, prev = [], tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        # A STRING in statement position is a docstring; one following an
        # operator or name is a real value the code depends on.
        if tok.type == tokenize.STRING and prev in (
                tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE,
                tokenize.NL, None):
            continue
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT):
            prev = tok.type
        kept.append(tok.string)
    return " ".join(kept)


# --- Q&A answers from the standing, not from the rows ----------------------

def test_a_dependent_cluster_is_not_reported_as_independent_support():
    """THE DEFECT. Three re-reports of one announcement answered "3
    independent source(s) support this"."""
    a = _answer(DEPENDENT)
    assert "independent source" not in a.direct_answer.lower()
    assert "3" not in a.direct_answer
    assert a.direct_answer.startswith("No")


def test_independent_corroboration_still_survives_ablation():
    """The fix must not flatten every multi-source claim into one source."""
    a = _answer(INDEPENDENT)
    assert a.direct_answer.startswith("Probably")
    assert "still leaves" in a.direct_answer


def test_dependent_and_independent_differ_on_identical_rows():
    """The control. Same three rows, same question, same brief — only the
    canonical standing differs, so only the standing can be deciding it."""
    assert _answer(DEPENDENT).direct_answer != _answer(
        INDEPENDENT).direct_answer


def test_conflicted_evidence_stays_bounded():
    a = _answer(CONFLICTED)
    assert a.direct_answer.startswith("No")
    assert "disagree" in a.direct_answer


def test_an_unrated_dossier_does_not_claim_independence():
    """Nobody established independence, so the surface may report the accounts
    and must not characterise them."""
    a = _answer(ET.UNRATED)
    assert "independent" not in a.direct_answer.lower()
    assert "not established" in a.direct_answer.lower()


def test_no_dossier_at_all_behaves_as_unrated():
    """The call site passes None when no dossier exists; that must not be an
    upgrade to 'independent' and must not raise."""
    a = FQA.answer(ABLATION, _rich(), engine_answer="",
                   observations=THREE_ROWS)
    assert "independent source" not in a.direct_answer.lower()


def test_a_reading_resting_only_on_the_company_still_says_so():
    a = FQA.answer(ABLATION, _rich(), engine_answer="",
                   observations=[{"source_class": "company_owned"}],
                   trust=ET.UNRATED)
    assert "company describing itself" in a.direct_answer


# --- the vocabulary regression that shipped with it ------------------------

@pytest.mark.parametrize("trust", [DEPENDENT, INDEPENDENT, CONFLICTED, SINGLE,
                                   ET.UNRATED])
def test_no_answer_leaks_internal_vocabulary(trust):
    """`corroboration` is banned founder-facing vocabulary and the old answer
    said it out loud on the dependent branch."""
    a = _answer(trust)
    text = " ".join([a.direct_answer, a.so_what, a.decision_affected,
                     a.what_could_change, " ".join(a.limitations)])
    assert not FQA.leaked_terms(a), FQA.leaked_terms(a)
    assert not ET.contains_internal_vocabulary(text)
    assert "corroboration" not in text.lower()


@pytest.mark.parametrize("trust,expected", [
    (DEPENDENT, True), (CONFLICTED, True), (ET.UNRATED, True),
    (INDEPENDENT, False), (SINGLE, False)])
def test_the_standing_earns_its_limitation_on_the_evidence_surface(trust,
                                                                   expected):
    """A standing that has to bound the reading says so where the founder
    asked about evidence — and one that does not stays silent, because a
    caution on every answer is a caution nobody reads."""
    a = _answer(trust)
    carried = any(ET.limitation(trust) == lim for lim in a.limitations)
    assert carried is expected


def test_the_limitation_is_not_added_twice():
    a = _answer(DEPENDENT)
    assert len(a.limitations) == len(set(a.limitations))


# --- Q&A does not carry its own classifier ---------------------------------

def test_qa_does_not_reimplement_trust_classification():
    """§17: no separate source-count logic. The module may READ a standing; it
    may not decide one, so the standing names must only ever be compared
    against, never assigned."""
    src = _code_only(FQA)
    for banned in ("_classify", "_standing", "SAME_ORIGIN",
                   "dependency_class"):
        assert banned not in src, banned
    # The old rule, in the form it actually took: a verdict computed from how
    # many rows survived a publisher-class filter.
    assert "len ( independent ) >= 2" not in src


# --- §18 an old analysis is not re-rated by a newer dossier ----------------

class _Intel:
    """The two fields `as_read_by` reads, in the shape the contract yields."""

    def __init__(self, as_of, trust):
        self.as_of = as_of
        self.evidence_trust = trust


TRUST_BLOCK = {"standing": ET.INDEPENDENTLY_CORROBORATED, "raw_accounts": 3,
               "distinct_events": 3, "independent_support": 3, "weight": 2.0,
               "sentence": ""}


def test_a_dossier_from_after_the_analysis_is_not_applied_to_it():
    """The market side republishes as evidence arrives. A founder re-opening
    last week's analysis must not be answered from a standing that analysis
    never saw."""
    intel = _Intel("2026-08-08", TRUST_BLOCK)
    assert ET.as_read_by(intel, "2026-08-01") is ET.UNRATED


def test_the_dossier_the_analysis_actually_read_still_applies():
    """The pin must not withhold every standing — only the ones from the
    future."""
    intel = _Intel("2026-08-01", TRUST_BLOCK)
    assert ET.as_read_by(intel, "2026-08-01").standing == (
        ET.INDEPENDENTLY_CORROBORATED)
    assert ET.as_read_by(intel, "2026-08-08").standing == (
        ET.INDEPENDENTLY_CORROBORATED)


def test_a_live_analysis_with_no_recorded_date_gets_the_standing():
    """There is no history to protect on the path that has not stored one."""
    assert ET.as_read_by(_Intel("2026-08-08", TRUST_BLOCK), "").standing == (
        ET.INDEPENDENTLY_CORROBORATED)


def test_the_pin_survives_a_timestamped_revision():
    """`as_of` is a date on one side and can carry a time on the other."""
    intel = _Intel("2026-08-08T04:00:00Z", TRUST_BLOCK)
    assert ET.as_read_by(intel, "2026-08-01") is ET.UNRATED


def test_a_withheld_standing_reads_as_unrated_rather_than_as_dependent():
    """Withholding must not accidentally assert that the sources were found to
    repeat each other — that is a claim, and nobody made it."""
    withheld = ET.as_read_by(_Intel("2026-08-08", TRUST_BLOCK), "2026-08-01")
    assert withheld.standing == ET.UNKNOWN
    assert ET.sentence(withheld) == ""


# --- §20 the grouping is not rebuilt per belief ----------------------------

def test_the_projection_normalizes_each_belief_once():
    """Reading a standing rebuilds the whole event grouping — every `Event`
    and its evidence ids. The projection needs that standing twice: once for
    the node's rendered attributes and once for its confidence word. It read
    it twice, so every dossier paid for the grouping of every belief twice on
    the one path that runs for all of them.

    Counted rather than timed: a duration threshold on a laptop measures the
    laptop.
    """
    from intent_engine.business_graph import projections as PROJ
    from intent_engine.business_graph.model import BusinessGraph

    beliefs = [{"proposition": f"Claim {i}.", "subject": "Acme",
                "confidence": "medium", "update_method": "evidence",
                "direction_of_last_change": "strengthened",
                "last_updated": "2026-08-01",
                "evidence_ids": [f"e{i}a", f"e{i}b", f"e{i}c"],
                "evidence_trust": dict(TRUST_BLOCK)} for i in range(7)]

    calls = []
    real = ET.read

    def counting(block):
        calls.append(block)
        return real(block)

    ET.read = counting
    try:
        PROJ.from_strategic_dossier(company_id="acme", company_label="Acme",
                                    beliefs=beliefs, graph=BusinessGraph())
    finally:
        ET.read = real

    assert len(calls) == len(beliefs), (
        f"{len(calls)} normalizations for {len(beliefs)} beliefs")


def test_the_standing_still_decides_the_confidence_word():
    """The cache must not become a bypass: passing the trust in has to give
    the same answer as letting it read its own."""
    from intent_engine.business_graph import projections as PROJ

    belief = {"proposition": "Claim.", "update_method": "evidence",
              "direction_of_last_change": "strengthened",
              "evidence_trust": {"standing": ET.DEPENDENT_REREPORTING,
                                 "raw_accounts": 3, "distinct_events": 1,
                                 "independent_support": 0, "weight": 1.0,
                                 "sentence": ""}}
    assert PROJ.belief_standing(belief) == PROJ.belief_standing(
        belief, ET.of_belief(belief))


# --- §16 slides -------------------------------------------------------------

def test_slides_never_assert_corroboration_from_a_count():
    """A slide must not say several sources confirm something. The deck has no
    trust standing of its own and must not manufacture one from how many
    citations a bullet happens to carry."""
    from intent_engine.strategic_intelligence import slides as SL

    src = _code_only(SL).lower()
    for claim in ("sources confirm", "independent source(s) support",
                  "sources agree", "independently confirm",
                  "multiple sources"):
        assert claim not in src, claim


def test_slides_do_not_count_sources_into_founder_prose():
    """A prior wave removed "Built from 5 company owned source(s)." from the
    deck. This keeps it removed: a count of rows is not intelligence, and
    under normalization it is not even a count of things that happened."""
    from intent_engine.strategic_intelligence import slides as SL

    src = _code_only(SL)
    assert "source(s)." not in src
    assert "Built from" not in src
