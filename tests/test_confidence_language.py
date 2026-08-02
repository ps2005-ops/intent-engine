"""No founder surface may lead with a grade.

MEASURED on the deployed preview: the brief headline rendered
`headline.confidence` -- the raw analyst grade -- as its own element at the
top of the primary founder surface. "Low" is not a finding. The reason is
the part a founder can act on, because it names the evidence that would
move it.
"""
import re

from intent_engine.founder_brief.render import (
    confidence_sentence, is_bare_grade,
)


def test_bare_grades_are_recognised():
    for g in ("Low", "  medium ", "HIGH", "Limited confidence", "partial",
              "Low.", "uncertain"):
        assert is_bare_grade(g), g
    for s in ("Low, by construction",
              "The acquisition is verified; its effect is not.",
              "Only company-authored material was retrieved"):
        assert not is_bare_grade(s), s


def test_the_reason_leads_and_the_grade_trails():
    out = confidence_sentence(
        "Low", "No independent customer evidence was retrieved")
    assert out.startswith("No independent customer evidence")
    assert not out.lower().startswith("low")


def test_a_grade_with_no_reason_is_withheld_rather_than_shown_bare():
    assert confidence_sentence("Low", "") == ""
    assert confidence_sentence("Medium", None) == ""
    # a genuine sentence in the grade slot survives
    assert confidence_sentence("Low, by construction", "") == \
        "Low, by construction"


def test_the_grade_is_not_repeated_when_the_reason_already_says_it():
    out = confidence_sentence("Low", "Confidence is low because only the "
                                     "company has spoken")
    assert out.count("low") == 1


def test_no_founder_template_renders_a_grade_as_its_own_element():
    """Structural guard against reintroducing `<p>{confidence}</p>`."""
    from pathlib import Path
    import intent_engine.webapp.app as appmod
    src = Path(appmod.__file__).read_text(encoding="utf-8")
    offenders = re.findall(
        r"<(p|h2|h3)[^>]*>\s*(?:Confidence:?\s*&?a?m?p?;?\s*)?"
        r"\{_e\(str\(\w+\[.confidence.\]\)\)\}\s*</\1>", src)
    assert not offenders, offenders
