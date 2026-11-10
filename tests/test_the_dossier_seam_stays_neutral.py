"""The neutral package must stay neutral, and its restated vocabulary must
not drift from the canonical one.

WHY THIS PARSES RATHER THAN GREPS
----------------------------------
A grep for "intent_engine.market" matches the ADR paragraph explaining why
that import is forbidden, and matches this module's own docstring. A guard
that passes because it found its own comment is worse than no guard: it
reports GREEN for the exact condition it exists to detect. So the source is
parsed and only real import statements are inspected.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from intent_engine.demo_dossier import contracts, vocabulary as V

PACKAGE = pathlib.Path(
    __import__("intent_engine.demo_dossier", fromlist=["x"]).__file__).parent

#: Packages the neutral join may never import. `market` is the structural
#: guarantee; the founder intelligence packages are the other half of it,
#: because a join that could read founder internals directly would stop
#: needing the snapshot contract and the seam would rot from the other side.
FORBIDDEN_PREFIXES = (
    "intent_engine.market",
    "intent_engine.external_intel",
    "intent_engine.business_graph",
    "intent_engine.executive",
    "intent_engine.webapp",
    "intent_engine.company_ingestion",
    "intent_engine.founder_brief",
    "intent_engine.research",
    "intent_engine.strategic_intelligence",
)


def _modules():
    return sorted(PACKAGE.glob("*.py"))


def _imported_names(path: pathlib.Path):
    """Every module name this file actually imports, from the AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import; resolve against the package
                names.append(f"intent_engine.demo_dossier.{node.module or ''}")
            elif node.module:
                names.append(node.module)
    return names


def test_the_neutral_package_imports_neither_side():
    offenders = []
    for path in _modules():
        for name in _imported_names(path):
            if any(name.startswith(p) for p in FORBIDDEN_PREFIXES):
                offenders.append(f"{path.name} imports {name}")
    assert offenders == [], (
        "the neutral dossier package imported an intelligence package; the "
        "Market/Founder boundary is structural and this is how it stops "
        f"being structural: {offenders}")


def test_the_guard_can_actually_fail():
    """A guard that cannot fail is not a guard.

    Recorded in this program as "a test that cannot fail": 8 bound, 8
    confirmed, 0 contradicted was a bug report about the filter. So the
    detector is run against a source that genuinely violates the rule.
    """
    bad = ast.parse("from intent_engine.market import beliefs\n"
                    "import intent_engine.external_intel.pack\n")
    names = []
    for node in ast.walk(bad):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    hits = [n for n in names if any(n.startswith(p)
                                    for p in FORBIDDEN_PREFIXES)]
    assert len(hits) == 2, hits


def test_a_comment_naming_the_forbidden_package_does_not_trip_the_guard():
    """The complement: the guard must not fire on prose.

    Without this, the cheapest way to make the guard pass is to stop writing
    down why the rule exists — which would delete the documentation that
    keeps the rule alive.
    """
    prose = ast.parse('"""This may never import intent_engine.market."""\n'
                      "# nor intent_engine.external_intel\n"
                      "X = 'intent_engine.market'\n")
    names = []
    for node in ast.walk(prose):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    assert names == []


def test_the_assembler_never_reaches_a_visual_verdict():
    """`VISUAL_PASS` is not a name this package defines, so a backend cannot
    set it even by accident (§27)."""
    assert not hasattr(V, "VISUAL_PASS")
    assert V.DEMO_VERIFIED not in V.ASSEMBLER_REACHABLE
    assert V.UNMEASURED in V.SURFACE_STATES


# --- drift pins: the restated vocabulary against the canonical one ---------
# These tests import the founder side ON PURPOSE. A test may look at both
# sides of a seam; the package under test may not.

def test_the_population_vocabulary_has_not_drifted():
    from intent_engine.external_intel import internal_impact as II
    assert V.POPULATIONS == II.POPULATIONS
    assert V.SYNTHETIC_ENTERPRISE == II.SYNTHETIC_ENTERPRISE
    assert V.REAL_ENTERPRISE == II.REAL_ENTERPRISE


def test_the_banned_trading_terms_have_not_drifted():
    """If the two lists disagree, the stricter side must win — so this side
    must be a superset of nothing it has dropped."""
    from intent_engine.external_intel import strategic_contract as SC
    missing = set(SC._BANNED_SUBSTRINGS) - set(contracts._BANNED_SUBSTRINGS)
    assert missing == set(), (
        f"the dossier contract dropped trading terms the strategic contract "
        f"still refuses: {sorted(missing)}")


def test_the_window_tolerance_matches_the_strategic_contract():
    from intent_engine.external_intel import strategic_contract as SC
    assert V.BOUNDED_WINDOW_DAYS == SC.MAX_AGE_DAYS


def test_every_coverage_state_the_founder_can_send_is_one_this_side_knows():
    """The neutral side passes coverage through rather than interpreting it,
    but HYDRATING is read by `_readiness`, so that one name must be real."""
    from intent_engine.external_intel import coverage_state as CS
    assert V.HYDRATING in CS.COVERAGE_STATES


@pytest.mark.parametrize("name", ["tenant_id", "tenant_scope", "auth_token",
                                  "data_population", "owner_id",
                                  "private_notes", "acl_entries"])
def test_authority_shaped_field_names_fail_closed(name):
    assert contracts.is_security_sensitive(name)


@pytest.mark.parametrize("name", ["belief_refs", "canonical_name",
                                  "coverage_state", "learning_summary"])
def test_descriptive_field_names_do_not_fail_closed(name):
    assert not contracts.is_security_sensitive(name)
