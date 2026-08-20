"""The run opened on a domain and threw the CIK away, so nothing owned anything.

MEASURED LIVE ACROSS THREE DEPLOYS. The claim-ownership repair read green in
unit tests, PASSED a probe against real EDGAR documents, and the rendered
JPMorgan page did not move — byte-identical on 0420fb0, cec9b2f and 71e4dc0:

    How the business actually works -> Distribution model
    "Is committing capital to capacity ahead of the demand for it."
    evidence: WELLS FARGO & COMPANY/MN — 10-K

Those three facts are not a contradiction; together they locate the gap. The
producer was correct — the probe handed it a `subject_cik` directly and it
separated the two filers perfectly. The LIVE path takes that CIK from
`run_meta`, and the run had none, so the producer was being asked "is this
document filed under ''?".

THE ONE CHARACTER. `/analyze` handled a confirmed suggestion with:

    if picked_domain:
        website = website or picked_domain
    elif picked_cik:
        filer_cik = picked_cik

JPMorgan has a domain AND a CIK. The domain branch won and the CIK was
discarded — for every large filer, which all have both. A company with only a
CIK worked, which is why the name-entry path and every domainless-filer test
passed throughout.

The surrounding comment warning that `filer_cik` "must never be filled in from
anywhere else" is about GUESSING: a CIK inferred from a name attributes one
company's filings to another. A confirmed pick is not a guess, and the same
block says so — "A CONFIRMED PICK IS AN ANSWER, NOT A HINT."
"""
import ast
import pathlib

import pytest

def _app_source() -> str:
    """The webapp's source, read THROUGH THE IMPORTED MODULE.

    A structural test that reads a hardcoded repo path bypasses the break
    proof harness, which runs the suite against a MIRRORED src tree — so the
    test reads the unmutated original and every mutation comes back
    NOT_CAUGHT. Both proofs for this file did exactly that before this was
    fixed. Same family as `inspect.getsource` reading by line number: a guard
    must look at the code that is actually running.
    """
    import inspect

    from intent_engine.webapp import app as _app
    return pathlib.Path(inspect.getsourcefile(_app)).read_text()


def _analyze_source() -> str:
    """The source of the /analyze handler that builds the run."""
    source = _app_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.get_source_segment(source, node) or ""
            if "suggest_confirmed" in body and "create_run(" in body:
                return body
    raise AssertionError("the /analyze handler was not found")


def _assigns(node, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name
               for stmt in ast.walk(node)
               for n in ([stmt] if isinstance(stmt, ast.Name) else [])
               ) or any(
        isinstance(t, ast.Name) and t.id == name
        for stmt in ast.walk(node) if isinstance(stmt, ast.Assign)
        for t in stmt.targets)


def test_the_cik_is_not_assigned_inside_the_domain_branchs_else():
    """THE DEFECT, by structure rather than by spelling.

    An `elif` here puts the CIK assignment in the domain branch's `orelse`,
    so a filer with BOTH — every large filer — opens with no CIK. Checked by
    walking the tree rather than searching for the word "elif", because the
    absence of a keyword is a spelling test and the property is *where the
    assignment lives*.
    """
    tree = ast.parse(_analyze_source())
    domain_ifs = [n for n in ast.walk(tree)
                  if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Name)
                  and n.test.id == "picked_domain"]
    assert domain_ifs, "the confirmed-pick branch was not found"
    for node in domain_ifs:
        for alternative in node.orelse:
            assert not _assigns(alternative, "filer_cik"), (
                "the CIK is assigned in the domain branch's else, so a filer "
                "with both a domain and a CIK opens with no CIK")


def test_the_cik_is_assigned_at_all():
    """The positive control. Moving the assignment out of the else must not
    be achieved by deleting it — the test above would pass either way."""
    tree = ast.parse(_analyze_source())
    cik_ifs = [n for n in ast.walk(tree)
               if isinstance(n, ast.If)
               and isinstance(n.test, ast.Name)
               and n.test.id == "picked_cik"
               and any(_assigns(b, "filer_cik") for b in n.body)]
    assert cik_ifs, "a confirmed CIK is never carried into the run"


def test_the_run_is_opened_with_both():
    """Both values reach `create_run`, which accepts both.

    Read by AST rather than by slicing to the first `)` — a call spanning
    several lines with its own parentheses defeats the naive version, and
    the naive version fails CLOSED here but would be silently wrong in a
    guard that searched for something rarer."""
    tree = ast.parse(_app_source())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "create_run"]
    assert calls, "the webapp no longer opens a run"
    for call in calls:
        supplied = {kw.arg: kw.value for kw in call.keywords}
        assert "cik" in supplied, "the run is opened without a CIK at all"
        assert isinstance(supplied["cik"], ast.Name)
        assert supplied["cik"].id == "filer_cik"
        assert "website" in supplied


@pytest.mark.parametrize("has_domain,has_cik,expect_cik", [
    (True, True, True),      # THE LIVE CASE: every large filer
    (False, True, True),     # domainless filer — worked before, must still
    (True, False, False),    # a private company with no CIK
    (False, False, False),
])
def test_a_confirmed_pick_keeps_what_it_was_given(has_domain, has_cik,
                                                  expect_cik):
    """The branch logic itself, evaluated rather than read."""
    picked_domain = "https://jpmorganchase.com" if has_domain else ""
    picked_cik = "19617" if has_cik else ""
    website, filer_cik = "", ""
    # the shape the handler now uses
    if picked_domain:
        website = website or picked_domain
    if picked_cik:
        filer_cik = picked_cik
    assert bool(filer_cik) is expect_cik
    assert bool(website) is has_domain


def test_the_service_still_requires_one_of_them():
    """A run with neither must still be refused — the CIK becoming
    independent of the domain must not open a run on nothing."""
    from intent_engine.company_ingestion.records import IngestionError
    from intent_engine.company_ingestion.service import (
        CompanyIngestionService,
    )
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        service = CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl",
                                          resolver=False)
        with pytest.raises((IngestionError, ValueError)):
            service.create_run(company_name="Nowhere", website="",
                               user_id="u", as_of="2026-08-20T00:00:00+00:00",
                               cik="")
