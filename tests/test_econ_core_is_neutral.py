"""The canonical core must import neither product, forever.

WHY THIS PARSES RATHER THAN GREPS
----------------------------------
A grep for "intent_engine.market" matches this module's own docstring and
every ADR paragraph explaining why the import is forbidden. A guard that
passes because it found its own comment reports GREEN for exactly the
condition it exists to detect. So the source is parsed and only real import
statements are inspected -- the same shape as the guard already protecting
`demo_dossier`.

WHAT THE WALL IS FOR AFTER UNIFICATION
---------------------------------------
Both products now live in one tree, so the old guarantee -- "the market
package is not even present on this branch" -- is gone, and it was doing real
work. `econ` replaces it with a stronger one: the shared substrate is
STRUCTURALLY incapable of reaching either product's internals, so a leak
would require someone to add an import to a file this test reads.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import intent_engine.econ as ECON

PACKAGE = pathlib.Path(ECON.__file__).parent

#: Everything the neutral core may not import. Both sides, deliberately: a
#: substrate that could read founder internals would stop needing the
#: contracts, and the seam would rot from that end instead.
FORBIDDEN_PREFIXES = (
    "intent_engine.market",
    "intent_engine.external_intel",
    "intent_engine.founder_brief",
    "intent_engine.founder_intelligence",
    "intent_engine.business_graph",
    "intent_engine.executive",
    "intent_engine.webapp",
    "intent_engine.company_ingestion",
    "intent_engine.strategic_intelligence",
    "intent_engine.paper",
    "intent_engine.predictions",
    "intent_engine.learning",
    "intent_engine.demo_dossier",
    "intent_engine.research",
)


def _modules():
    mods = sorted(PACKAGE.glob("*.py"))
    assert mods, "the econ package has no modules; this guard is vacuous"
    return mods


def _imported_names(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names.append(f"intent_engine.econ.{node.module or ''}")
            elif node.module:
                names.append(node.module)
    return names


def test_the_core_imports_neither_product():
    offenders = []
    for path in _modules():
        for name in _imported_names(path):
            if any(name.startswith(p) for p in FORBIDDEN_PREFIXES):
                offenders.append(f"{path.name} imports {name}")
    assert offenders == [], (
        "the canonical economic core imported a product package. The whole "
        "value of a shared substrate is that neither side's internals can "
        "reach it, and this is how that stops being structural: "
        f"{offenders}")


def test_the_guard_can_actually_fail():
    """A negative control, because a guard that cannot fail is not a guard."""
    bad = ast.parse("from intent_engine.market import beliefs\n"
                    "import intent_engine.founder_brief.build\n")
    names = []
    for node in ast.walk(bad):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    caught = [n for n in names
              if any(n.startswith(p) for p in FORBIDDEN_PREFIXES)]
    assert len(caught) == 2, caught


def test_prose_naming_the_boundary_is_not_an_import():
    """The docstring above names both packages and must not trip the guard."""
    prose = ast.parse('"""This may never import intent_engine.market."""\n'
                      "# intent_engine.founder_brief is also forbidden\n"
                      "X = 'intent_engine.market'\n")
    names = []
    for node in ast.walk(prose):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    assert names == []


def test_the_founder_side_still_cannot_import_the_market_engine():
    """The pre-existing wall, re-asserted after unification.

    `test_market_intel_contract.py` owns this assertion. It is repeated here
    because unification is exactly the change that would break it, and a
    reader looking at the new package should be able to see that the old
    guarantee survived rather than having to go and find out.
    """
    root = PACKAGE.parent
    offenders = []
    for area in ("external_intel", "founder_brief", "founder_intelligence"):
        for py in (root / area).rglob("*.py"):
            for name in _imported_names(py):
                if name.startswith("intent_engine.market"):
                    offenders.append(f"{area}/{py.name} imports {name}")
    assert offenders == [], offenders


def test_the_founder_side_does_import_the_shared_core():
    """The other half: the seam exists and is USED.

    A wall with nothing crossing it legitimately is not a boundary, it is a
    partition -- and that was the state this work set out to end.
    """
    root = PACKAGE.parent
    users = []
    for area in ("external_intel",):
        for py in (root / area).rglob("*.py"):
            for name in _imported_names(py):
                if name.startswith("intent_engine.econ"):
                    users.append(f"{area}/{py.name}")
    assert users, (
        "no founder-side module imports the shared economic core; the two "
        "products are still not consuming one substrate")


def test_the_market_side_does_import_the_shared_core():
    root = PACKAGE.parent
    users = []
    for py in (root / "market").rglob("*.py"):
        for name in _imported_names(py):
            if name.startswith("intent_engine.econ"):
                users.append(f"market/{py.name}")
    assert users, (
        "no market-side module imports the shared economic core")
