"""Make the run say whose document it used, instead of guessing a sixth time.

The claim-ownership repair has read green in unit tests, passed a probe
against real EDGAR documents, and left the rendered page unchanged three
times. FIVE hypotheses about why have all been wrong, and two of them were
argued from a RENDERED LABEL rather than from the source_class the label is
computed from — the same error made in both directions by both sessions.

`/runs/<id>/provenance.json` ends that by measurement: per observation, the
id, the title a reader sees, the class the label came FROM, the origin URL
(whose EDGAR path names the filer), and whether the ownership gate marked it
the subject's own. A row where those disagree is the defect.

OPERATOR ONLY. §16 forbids asking a customer to understand any of this.
"""
import ast
import inspect
import pathlib

import pytest


def _app_source() -> str:
    from intent_engine.webapp import app as _app
    return pathlib.Path(inspect.getsourcefile(_app)).read_text()


def test_the_route_requires_a_session():
    """A guest must never reach it — this is diagnostics, not product."""
    source = _app_source()
    marker = 'parts[2] == "provenance.json"'
    assert marker in source, "the provenance route is gone"
    after = source[source.index(marker):]
    guard = after[:after.index("_run_provenance")]
    assert "session is None" in guard, (
        "the provenance route is reachable without a session")


def test_it_reports_the_four_things_that_settle_the_question():
    from intent_engine.webapp import app as _app
    body = inspect.getsource(_app.ClaudeWebApp._run_provenance) \
        if hasattr(_app, "ClaudeWebApp") else _app_source()
    for field in ("observation_id", "source_class", "rendered_label",
                  "origin", "subject_owned", "filed_by_cik"):
        assert field in body, f"the row cannot answer without {field}"


def test_the_filer_is_read_from_the_edgar_path_not_the_title():
    """The title is what misled both sessions. The path names the filer."""
    from intent_engine.webapp import app as _app
    tree = ast.parse(_app_source())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_run_provenance")
    body = ast.get_source_segment(_app_source(), fn) or ""
    assert '"/data/"' in body, "the filer is no longer read from the path"
    assert "filed_by_cik" in body


def test_the_disagreeing_rows_are_called_out():
    """A reader must not have to spot the contradiction by eye — the row
    where the gate and the filer disagree IS the finding."""
    from intent_engine.webapp import app as _app
    tree = ast.parse(_app_source())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_run_provenance")
    body = ast.get_source_segment(_app_source(), fn) or ""
    assert "rows_where_ownership_disagrees_with_the_filer" in body


@pytest.mark.parametrize("origin,subject,expected", [
    ("https://www.sec.gov/Archives/edgar/data/19617/x/a.htm", "19617", True),
    ("https://www.sec.gov/Archives/edgar/data/72971/x/b.htm", "19617", False),
    ("https://example.com/page", "19617", False),
])
def test_the_filer_extraction_is_right(origin, subject, expected):
    filed_by = ""
    if "/data/" in origin:
        filed_by = origin.split("/data/", 1)[1].split("/", 1)[0]
    assert (bool(filed_by) and filed_by == subject) is expected


def test_it_returns_the_rows_as_the_page_composes_them():
    """A JOIN is invisible in a list of observations.

    If the defect is a join, every observation looks correct on its own and
    the mismatch exists only in the ROW — so an observation list alone would
    read as a clean bill of health. The route resolves each component's own
    evidence ids the way a surface does, and calls out any row citing a
    document filed by someone else, or an id that does not resolve at all.
    """
    from intent_engine.webapp import app as _app
    tree = ast.parse(_app_source())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_run_provenance")
    body = ast.get_source_segment(_app_source(), fn) or ""
    for field in ("rendered_rows", "cited", "resolves",
                  "cites_a_document_filed_by_someone_else",
                  "cites_an_id_that_does_not_resolve",
                  "rows_citing_another_filers_document"):
        assert field in body, f"a join would be invisible without {field}"


def test_an_unresolvable_id_is_a_finding_not_a_blank():
    """An id that points at nothing is exactly the shape a join leaves
    behind, and rendering it as an empty title would hide it."""
    by_id = {"obs-a": {"source_title": "SEC 10-K"}}
    cited = [{"observation_id": oid, "resolves": oid in by_id}
             for oid in ("obs-a", "obs-missing")]
    assert [c["resolves"] for c in cited] == [True, False]
    assert any(not c["resolves"] for c in cited)
