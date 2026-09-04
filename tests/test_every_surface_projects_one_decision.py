"""The X-Ray, the full analysis, the deck and the CEO answers agree.

They agree because they PROJECT one `FounderDecision` rather than each
reasoning about the same company. These tests assert that property directly:
if any surface started deriving its own answer, the pages would still render
and only this file would notice.

The presentation may simplify. It may never strengthen -- so it may drop a
caveat's detail but it may not claim a standing the analysis does not hold.
"""
import re

import pytest

from intent_engine.demo_dossier.assembler import assemble
from intent_engine.demo_dossier.contracts import founder_unavailable
from intent_engine.executive import ceo_questions as Q
from intent_engine.executive.decision_synthesis import compose
from intent_engine.founder_brief import deep, plain as P, xray


def _text(html: str) -> str:
    """The words a reader sees. CSS is not content, entities are not text."""
    import html as _html

    body = html.split("</style>")[-1]
    return re.sub(r"\s+", " ",
                  _html.unescape(re.sub(r"<[^>]+>", " ", body)))


def _decision(company_id, aliases, name):
    from intent_engine.demo_dossier.bridge import for_company
    snapshot = for_company(company_id, aliases=aliases)
    if snapshot is None or getattr(snapshot, "snapshot", None) is None:
        pytest.skip(f"no published market snapshot for {company_id}")
    dossier = assemble(snapshot.snapshot,
                       founder_unavailable("no founder run in this test"))
    return compose(dossier), name


COMPANIES = [("cloudflare", ["cloudflare-inc"], "Cloudflare, Inc."),
             ("jpmorgan-chase", ["jpmorgan-chase-co"],
              "JPMorgan Chase & Co.")]


@pytest.fixture(params=COMPANIES, ids=[c[0] for c in COMPANIES])
def surfaces(request):
    decision, name = _decision(*request.param)
    d = decision.as_dict()
    return {
        "decision": decision,
        "dict": d,
        "xray": xray.render(d, company=name),
        "full": deep.full_analysis(d, company=name),
        "deck": deep.presentation(d, company=name),
    }


def test_all_three_screens_state_the_same_decision(surfaces):
    question = surfaces["dict"]["decision_question"]
    assert question
    for name in ("xray", "full", "deck"):
        assert question in _text(surfaces[name]), (
            f"{name} does not state the selected decision question")


def test_all_three_screens_state_the_same_recommendation(surfaces):
    move = surfaces["dict"]["recommended_next_move"]
    assert move
    assert move in _text(surfaces["xray"])
    assert move in _text(surfaces["full"])
    assert move in _text(surfaces["deck"])


def test_the_biggest_risk_is_one_answer_not_four(surfaces):
    """The defect this pins actually shipped in this batch.

    The Q&A read only `guardrails` while the screens fell back through the
    adversarial branch, so a company whose causal question was never asked
    got a rendered risk on the page and "no risk has been recorded" from the
    assistant beside it.
    """
    risk = P.key_risk(surfaces["dict"])
    answer = Q.answer("What is the biggest risk?", surfaces["decision"])
    if risk:
        assert risk in answer.answer or answer.answer in risk
        assert risk in _text(surfaces["xray"])
    else:
        assert not answer.supported


def test_the_presentation_may_simplify_but_never_strengthen(surfaces):
    """A deck cannot claim a standing the analysis does not hold."""
    standing = surfaces["dict"]["standing"]
    deck = _text(surfaces["deck"])
    forbidden = {
        "BOUNDED": ("the evidence shows", "the evidence proves",
                    "we have established that"),
        "UNMEASURABLE": ("the evidence shows", "the evidence proves",
                         "is consistent with"),
        "REFUSED": ("the evidence shows", "we recommend", "is consistent with"),
    }.get(standing, ())
    for phrase in forbidden:
        assert phrase not in deck.lower(), (
            f"the deck used {phrase!r} on a {standing} reading")


def test_the_enum_detector_catches_a_token_inside_brackets():
    """The guard's own hole, pinned.

    `enum_free` stripped only `.,:;"'`, so "(1 PANEL_UNAVAILABLE)" kept its
    closing paren, failed `isalpha` and passed -- and that exact string
    reached a live CEO answer while the test below was green.
    """
    assert not P.enum_free("could not answer (1 PANEL_UNAVAILABLE).")
    assert not P.enum_free("state: MARKET_BRIDGE_MISSING")
    assert not P.enum_free("[CAUSAL_NOT_RUN]")
    assert P.enum_free("no comparable group was observed over the window.")
    assert P.enum_free("Cloudflare, Inc. earns a per-seat subscription.")


def test_no_surface_puts_a_raw_enum_in_front_of_a_reader(surfaces):
    for name in ("xray", "full", "deck"):
        for word in _text(surfaces[name]).split():
            assert P.enum_free(word), f"{name} rendered the raw token {word!r}"
    for question in Q.REQUIRED_QUESTIONS:
        text = Q.answer(question, surfaces["decision"]).answer
        assert P.enum_free(text), f"{question!r} answered with a raw enum"


def test_no_surface_leaks_a_structured_record_as_text(surfaces):
    """Adversary and scenario rows are dicts. Joining them printed reprs."""
    for name in ("xray", "full", "deck"):
        text = _text(surfaces[name])
        assert "{'" not in text and "': '" not in text
    for question in Q.REQUIRED_QUESTIONS:
        text = Q.answer(question, surfaces["decision"]).answer
        assert "{'" not in text, f"{question!r} leaked a dict"


def test_the_first_screen_carries_all_seven_things(surfaces):
    """§13. A first screen missing one of these is not the X-Ray."""
    text = _text(surfaces["xray"])
    for heading in ("Why this decision", "What changed", "Key risk", "Action",
                    "Next test"):
        assert heading in text, f"the X-Ray is missing {heading!r}"
    assert surfaces["dict"]["current_read"] in text


def test_a_section_with_nothing_to_say_is_absent_not_empty(surfaces):
    """§15. An empty heading reads as a broken subsystem."""
    full = _text(surfaces["full"])
    # every rendered h2 in the full analysis is followed by some prose
    for match in re.finditer(r"<h2>([^<]+)</h2>(.{0,40})",
                             surfaces["full"].split("</style>")[-1]):
        assert match.group(2).strip(), (
            f"section {match.group(1)!r} rendered as an empty heading")
    assert full.strip()


def test_no_screen_claims_an_independence_count_it_did_not_measure(surfaces):
    """Zero independent sources is a claim; not measuring is not."""
    if surfaces["dict"].get("independent_origins"):
        return
    for name in ("xray", "full", "deck"):
        text = _text(surfaces[name]).lower()
        assert "0 independent" not in text
        assert "no independent sources" not in text
