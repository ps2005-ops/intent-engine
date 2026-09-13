"""Q&A may not print a Python object at a board.

MEASURED LIVE on 8397d67, the first deployment where all ten board questions
actually reached the Q&A router. Meta and Cloudflare, both on "what does the
market believe?" and "what's the weakest assumption?":

    marketbelief(belief_id='mb_f3a52cac10', subject_id='Meta Platforms, Inc.',
    proposition="that ... resumes.", belief_type='market_expectation', ...)

    link(frm="Meta's filed results", to='attention sold by auction ...',
    standing='observed', because='...', evidence='', settled_by='')

The renderer recognised dicts and strings. These producers return DATACLASS
INSTANCES, so every isinstance check missed them and `str()` fell through to
`repr()`. The defect could not exist before the router repair: these are among
the eight intents that used to fall to a catch-all.

TWO PROPERTIES, AND THE SECOND IS THE ONE THAT LASTS. Normalising the three
known types stops today's leak. Refusing anything that LOOKS like a repr stops
the fourth type somebody adds next month. A test for only the first would pass
for exactly as long as the type list stayed complete.
"""
import dataclasses

import pytest

from intent_engine.founder_brief import qa as Q


@dataclasses.dataclass
class MarketBelief:
    belief_id: str = "mb_f3a52cac10"
    subject_id: str = "Meta Platforms, Inc."
    proposition: str = ("that Meta's current weakness is a cyclical trough "
                        "rather than a structural reset.")
    belief_type: str = "market_expectation"
    source_basis: str = "inferred"
    basis_detail: str = "Meta's own filed results show growth decelerating."


@dataclasses.dataclass
class Link:
    frm: str = "Meta's filed results"
    to: str = "attention sold by auction is what the economics rest on"
    standing: str = "observed"
    because: str = "the filed series is what this reading is computed from."
    evidence: str = ""


class Plain:
    """Not a dataclass. The shape nobody has added yet."""

    def __init__(self):
        self.statement = "Ad load taken today is paid for tomorrow."
        self._internal = "never rendered"


def _is_repr(text):
    return bool(Q._LOOKS_LIKE_A_REPR.match((text or "").strip()))


# --- the leak itself --------------------------------------------------------

def test_a_dataclass_never_reaches_the_reader_as_a_repr():
    for row in (MarketBelief(), Link()):
        rendered = Q._render_row(row)
        assert not _is_repr(rendered), rendered
        assert "belief_id=" not in rendered
        assert "standing=" not in rendered


def test_the_belief_is_actually_said_not_merely_suppressed():
    """SUPPRESSION IS NOT A FIX.

    The first version of this repair normalised the object and then rendered
    nothing, because none of the row key names appear on these producers. That
    turns a leak into an absence on a question whose answer is sitting in the
    object -- the §24 dead end arriving through the door just opened.
    """
    rendered = Q._render_row(MarketBelief())
    assert "cyclical trough" in rendered, rendered
    assert "filed results show growth decelerating" in rendered, rendered

    linked = Q._render_rows([Link()])
    assert "attention sold by auction" in linked, linked


def test_a_list_of_dataclasses_is_structured_not_string_joined():
    """The branch that produced the leak decided shape from raw members.

    ASSERTED THROUGH `_route_answer`, NOT `_render_rows`. The first version
    of this test called the renderer directly and so never executed the
    branch that actually leaked -- a break proof that removed the
    normalisation ran GREEN. `_render_rows` normalises per row on its own, so
    testing it proves the wrong half.
    """
    answer, name = Q._route_answer(
        "What does the market believe?",
        {"expectations": [MarketBelief(), Link()]})
    assert not _is_repr(answer), answer
    assert "belief_id=" not in answer, answer
    assert "cyclical trough" in answer, answer


def test_nested_dataclasses_are_flattened_not_left_as_reprs():
    """WHY THE DATACLASS BRANCH IS NOT REDUNDANT WITH `vars()`.

    A break proof that disabled `dataclasses.asdict` ran green, because a
    dataclass also has `__dict__` and the generic object branch caught it.
    For a FLAT object those two agree. They stop agreeing the moment a
    producer nests one dataclass inside another: `vars()` leaves the inner
    one as an object, and it reaches the reader as a repr.
    """

    @dataclasses.dataclass
    class Inner:
        because: str = "the filed series is what this is computed from."

    @dataclasses.dataclass
    class Outer:
        proposition: str = "that the trough is cyclical."
        basis_detail: str = ""
        detail: "Inner" = dataclasses.field(default_factory=Inner)

    rendered = Q._render_row(Outer())
    assert not _is_repr(rendered), rendered
    assert "Inner(" not in rendered and "inner(" not in rendered.lower(), \
        rendered
    assert "that the trough is cyclical." in rendered, rendered


def test_a_plain_object_is_handled_too():
    rendered = Q._render_row(Plain())
    assert rendered == "Ad load taken today is paid for tomorrow.", rendered
    assert "never rendered" not in rendered


# --- the guard that outlives the type list ---------------------------------

def test_anything_repr_shaped_is_refused():
    for shape in ("marketbelief(belief_id='x', a=1)",
                  "BeliefChallenge(belief_id='y')",
                  "Link(frm='a', to='b')",
                  "SomethingNobodyHasWrittenYet(field=1)",
                  "Thing()"):
        assert Q._printable(shape) == "", shape


def test_ordinary_prose_with_brackets_survives():
    """THE POSITIVE CONTROL. A refusal that also ate real sentences would be
    a worse defect than the one it replaced."""
    for sentence in ("Revenue (net) rose 12% on price, not volume.",
                     "Meta sells attention to advertisers.",
                     "Hold this decision open for now.",
                     "EBITDA (adjusted) is the wrong measure here."):
        assert Q._printable(sentence) == sentence, sentence


def test_a_scalar_object_field_is_rendered_not_reprd():
    """key_risk and falsifier are strings today. Nothing guarantees the next
    producer returns one."""
    answer, name = Q._route_answer(
        "What's the biggest risk?",
        {"key_risk": MarketBelief()})
    assert name == "biggest_risk"
    assert not _is_repr(answer), answer
    assert "cyclical trough" in answer, answer


def test_an_empty_row_still_falls_through_to_the_absent_copy():
    """Refusing must not invent. Nothing renderable is still an honest gap."""
    answer, name = Q._route_answer(
        "What's the biggest risk?", {"key_risk": ""})
    assert name == "biggest_risk"
    assert answer, "an empty field must still say something"
    assert not _is_repr(answer)


# --- the OTHER producer, which the first repair missed entirely -------------

class _Read:
    """The canonical read, carrying the shapes production carries.

    `_route_answer` reads the RUN'S DECISION. These three questions are
    answered from the read instead whenever the decision is silent -- which
    is the normal case live. The first repair fixed only the decision branch
    and the leak did not move: 3 of 3 answers still leaked on the deployed
    build, identical to the build before it.
    """

    puts_a_strategy_forward = True
    reading_exists = True

    def __init__(self):
        self.market_beliefs = (MarketBelief(),)
        self.belief_challenges = (MarketBelief(),)
        self.assumption_chain = _Chain()


class _Chain:
    def __init__(self):
        self.links = (Link(),)


def test_the_read_branch_renders_objects_too():
    """THE REGRESSION THAT SHIPPED. Straight at `_from_read`."""
    for holder in ("market_belief", "weakest_assumption"):
        out = Q._from_read(holder, _Read())
        assert not _is_repr(out), (holder, out)
        assert "belief_id=" not in out and "standing=" not in out, (holder, out)


def test_the_read_branch_still_says_something():
    """Suppression is not a fix here either."""
    said = Q._from_read("market_belief", _Read())
    assert "cyclical trough" in said, said
    assert "filed results show growth decelerating" in said, said
    weak = Q._from_read("weakest_assumption", _Read())
    assert "attention sold by auction" in weak, weak


def test_answer_end_to_end_never_leaks_from_either_producer():
    """Both producers, through the function the webapp actually calls.

    A test that exercised only one branch is what let an inert repair look
    green and ship.
    """
    class _Brief:
        """Permissive: `answer` reads a dozen brief fields and none of them
        are what this test is about. Naming them one by one would make the
        test fail for reasons unrelated to the leak."""

        def __getattr__(self, name):
            return ""

    for decision in ({}, {"expectations": [MarketBelief()]}):
        for question in ("What does the market believe?",
                         "What's the weakest assumption?"):
            out = Q.answer(question, _Brief(), decision=decision,
                           read=_Read())
            assert not _is_repr(out.direct_answer), (question, decision,
                                                     out.direct_answer)
            assert "belief_id=" not in out.direct_answer
