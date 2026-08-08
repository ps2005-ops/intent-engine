"""Three strings a founder actually saw, and must not see again.

From live customer feedback on the deployed Palantir result:

    "Palantir Partnership Vanguard."
    "The most recent evidence is About Palantir."
    "Whether to keep investing in depth or in adjacency."

Each is a different failure wearing the same clothes -- something the system
knows about ITSELF, printed where a founder expects something about their
business:

    a source TITLE used as an insight,
    PROVENANCE used as a reason,
    an internal pattern LABEL used as a decision.

This gate pins the exact strings, because they are evidence of what reached a
real user, and also the shapes behind them, because pinning only the literals
would let the same defect return under a different noun.
"""
import pytest

from intent_engine.strategic_intelligence.slides import (
    _why_now_in_plain_words,
)

REPORTED = [
    "Palantir Partnership Vanguard.",
    "The most recent evidence is About Palantir.",
    "Whether to keep investing in depth or in adjacency.",
]


@pytest.mark.parametrize("text", REPORTED)
def test_the_reported_strings_are_not_valid_founder_conclusions(text):
    """They must fail the consequence test the founder brief already applies."""
    from intent_engine.founder_brief.build import _is_consequence
    assert not _is_consequence(text), (
        f"{text!r} would render as a founder-facing conclusion")


def test_provenance_is_never_rendered_as_why_now():
    """A publication date is not a reason the situation is urgent."""
    out = _why_now_in_plain_words(
        "Recent public signal (2026-07-20, About Palantir) keeps this timely")
    assert out == "", f"provenance rendered as a reason: {out!r}"
    assert "most recent evidence is" not in out


def test_a_real_reason_still_passes_through():
    """The guard withholds non-answers; it must not swallow real ones."""
    reason = ("Two of the three largest customers renewed on shorter terms "
              "this quarter, which changes the revenue base.")
    assert _why_now_in_plain_words(reason) == reason


def test_the_pipelines_own_vocabulary_never_reaches_the_founder():
    assert _why_now_in_plain_words("Recent public signal keeps this timely") == ""


def test_no_module_reintroduces_the_metadata_sentence():
    """Source-level: the phrase itself must not exist as a literal again."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        # Skip docstrings: the comment EXPLAINING this defect is not the
        # defect. An earlier AST guard flagged its own explanation, which is
        # how a gate teaches people to delete the reasoning behind it.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "most recent evidence is" in node.value
                    and node.value not in docstrings):
                offenders.append(str(path))
    assert not offenders, f"metadata-as-insight string is back in: {offenders}"
