""""Why this matters" must state what follows, not name a topic.

MEASURED on the deployed preview 2026-08-03 (Palantir, commit 2b2e437), the
first grounded run after the reasoning key was added:

    Why this matters
    how much to invest ahead of the transition

That string is not analysis output. `_build_thesis` substituted it verbatim
whenever no tension was observed, and the founder brief renders `tension`
under "Why this matters" -- so a company with no observed tension told its
reader that what mattered was a topic heading.

Two things changed. The fabricated fallback is gone, and the blind spot's
`why_it_may_matter` -- the consequence of the tension, which nothing
downstream had ever read -- is now preferred over the tension itself.
"""
import pytest

from intent_engine.founder_brief.build import _consequence, _is_consequence

REAL = [
    "The complexity that wins enterprise deals can erode the ease that won "
    "the SMB base.",
    "A diffuse value proposition raises acquisition cost and lets focused "
    "competitors win specific segments.",
    "An enterprise push is growing at the same time the brand still promises "
    "small-merchant simplicity.",
]

FRAGMENTS = [
    "how much to invest ahead of the transition",
    "whether to keep investing in depth or in adjacency",
    "Partnership Vanguard",
    "The latest evidence is",
    "product breadth",
    "",
]


@pytest.mark.parametrize("text", REAL)
def test_a_real_consequence_is_accepted(text):
    assert _is_consequence(text), text


@pytest.mark.parametrize("text", FRAGMENTS)
def test_a_fragment_is_rejected(text):
    assert not _is_consequence(text), text


def test_the_measured_preview_string_is_rejected():
    """THE BREAK PROOF, pinned to the exact string that shipped."""
    assert not _is_consequence("how much to invest ahead of the transition")


def test_the_first_real_consequence_wins():
    assert _consequence("how much to invest ahead of the transition",
                        REAL[0]) == REAL[0]


def test_nothing_real_yields_empty_rather_than_a_fragment():
    """Empty is a real outcome -- the renderer drops the block."""
    assert _consequence(*FRAGMENTS) == ""


def test_the_thesis_no_longer_fabricates_a_tension():
    """The rejected string must not be a VALUE the pipeline can emit.

    Checked over string literals rather than raw source, so that the comment
    explaining the defect does not count as the defect.
    """
    import ast
    import inspect

    from intent_engine.strategic_intelligence import reasoning
    tree = ast.parse(inspect.getsource(reasoning))
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)}
    assert "how much to invest ahead of the transition" not in literals, (
        "the fabricated tension fallback is back as a literal")


def test_the_brief_omits_the_heading_when_there_is_no_consequence():
    """A heading over a blank reads as a section the product forgot."""
    import inspect

    from intent_engine.founder_brief import render
    source = inspect.getsource(render.render_brief)
    assert "if k.so_what:" in source, (
        "the 'Why this matters' block renders unconditionally again")
