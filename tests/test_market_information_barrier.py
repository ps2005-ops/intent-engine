"""What the information barrier CAN be verified to do on this branch.

L-BAR-001 and L-ANT-001 are both recorded as inherited obligations for the
internal phase, on the reasoning that a barrier needs private data behind it
and an air-gap needs a second tenant. Both of those are true of the full
pillars and neither is true of the whole branch: `market/internal_state.py`
exists here, it holds company-scoped private facts, and it enforces a
permission wall in code —

    readable(facts, for_company=...)   filters by company_id, refuses an
                                       unnamed reader, and offers no function
                                       that crosses companies
    assert_no_synthetic(...)           refuses a live conclusion built on
                                       demonstration data

So the honest status is not "not applicable". It is: the primitive exists and
is enforced, and NOTHING IN PRODUCTION CALLS IT. `internal_state` is imported
by three test modules and by no module under `src/`. That is the gap this file
measures rather than asserts, and it is the reason the pillar cannot be marked
PASS on the strength of the module existing.

What is verified here is the part that is verifiable now: the wall holds, it
cannot be walked around, and the day a production caller appears it will be
one this guard has seen.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from intent_engine.market import internal_state as IS

SRC = pathlib.Path(__file__).resolve().parents[1] / "src/intent_engine"
MARKET = SRC / "market"


# --- the wall itself --------------------------------------------------------

def test_one_companys_facts_are_not_readable_for_another():
    facts = IS.synthetic_enterprise()
    assert facts
    assert IS.readable(facts, for_company="SOMEBODY_ELSE") == ()


def test_an_unnamed_reader_is_refused_rather_than_served_everything():
    """The dangerous default: an empty company id filtering to nothing would
    be safe, and filtering to everything would be a total leak. It raises."""
    with pytest.raises(IS.PermissionRefused):
        IS.readable(IS.synthetic_enterprise(), for_company="")


def test_there_is_no_function_here_that_crosses_companies():
    """An aggregate is the shape a leak takes: "companies like yours are
    seeing pipeline weakness" is derived from named companies' private data
    and, with a small customer list, is re-identifiable."""
    source = (MARKET / "internal_state.py").read_text()
    tree = ast.parse(source)
    crossing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        args = [a.arg for a in node.args.args + node.args.kwonlyargs]
        # A reader of internal facts either names ONE company or is not a
        # reader. A function taking a plural of companies would be the
        # aggregate this module says it does not have.
        assert "for_companies" not in args, node.name
        assert "companies" not in args, node.name
    assert not crossing


def test_synthetic_facts_cannot_join_a_real_companys_economics():
    with pytest.raises(IS.SyntheticLeak):
        IS.assert_no_synthetic(IS.synthetic_enterprise(),
                               context="a live briefing")


def test_the_demonstration_company_cannot_be_mistaken_for_a_registrant():
    assert "SYNTHETIC" in IS.SYNTHETIC_COMPANY
    assert all(f.synthetic for f in IS.synthetic_enterprise())


# --- the measured gap -------------------------------------------------------

def _imports_internal_state(path: pathlib.Path) -> bool:
    """Tokenised, so the module's own name in a comment does not count."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if "internal_state" in (node.module or "") or \
                    any(a.name == "internal_state" for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any("internal_state" in a.name for a in node.names):
                return True
    return False


def production_callers() -> list:
    return sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*.py")
                  if p.name != "internal_state.py"
                  and _imports_internal_state(p))


def test_the_permission_wall_has_no_production_caller_and_that_is_recorded():
    """MEASURED, NOT ASSERTED, and deliberately allowed to be non-empty.

    The barrier is enforced where it is called and called nowhere, so the
    pillar is a component rather than a system. This test fails the day that
    changes — not because a caller is wrong, but because the pillar's status
    would then be wrong, and a status nobody revisits is how a capability gets
    marked complete on the strength of a class existing.
    """
    callers = production_callers()
    assert callers == [], (
        "internal_state now has production callers; the information-barrier "
        f"pillar must be re-scored rather than left as a component: {callers}")


def test_any_future_reader_must_go_through_the_permission_wall():
    """The guard for the caller that does not exist yet.

    Any production module importing `internal_state` must also reference
    `readable`. Reading `InternalFact.company_id` and filtering by hand is the
    bypass this catches — one that would look completely reasonable in review.
    """
    for name in production_callers():
        tree = ast.parse((SRC / name).read_text())
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "readable" in names, (
            f"{name} reads internal facts without going through readable()")
