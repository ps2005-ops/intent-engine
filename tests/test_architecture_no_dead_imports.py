"""Structural guards on the failure that broke this branch's baseline.

`founder_brief/market.py` was a second market consumer, parallel to
`external_intel`. It was deleted in f2b7a18 -- a commit whose message states
the module was "left in place", which its own diff contradicts -- and three
test modules went on importing it. The suite could not even be COLLECTED, and
the commit reported a passing run that the delivered tree could not produce.

Two properties are asserted here, because the ordinary suite catches neither:

1. A deleted module cannot remain imported. Collection catches this for
   top-level test imports and nothing else -- `webapp/app.py` imports the
   presenter INSIDE a method, so an equivalent deletion there would raise for
   the first time in front of a founder, on the live page, inside a bare
   `except` that would report it as "market context unavailable".

2. A duplicate market consumer cannot come back. The deleted module's real
   defect was not that it was stale, it was that it existed at all: two
   independently-written readers of the same upstream artefact, drifting
   apart, with only one of them routed.
"""
import ast
import importlib
import importlib.util
import pathlib

import pytest

import intent_engine

PKG = pathlib.Path(intent_engine.__file__).resolve().parent
REPO = PKG.parents[1]
TESTS = REPO / "tests"


def _python_files():
    yield from sorted(PKG.rglob("*.py"))
    yield from sorted(TESTS.rglob("*.py"))


def _optional_imports(tree):
    """Import nodes inside a `try` that handles ImportError.

    Exempt on purpose, and the exemption is narrow: such an import DECLARES a
    fallback, so a missing target is a designed state rather than a break.
    `executive/snapshots.py` reads a prediction schema version this way and
    names the version to use when it is absent. An unguarded import makes no
    such statement -- it simply asserts the module is there, which is what
    f2b7a18 turned into a false claim.
    """
    exempt = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handled = any(
            h.type is None
            or (isinstance(h.type, ast.Name)
                and h.type.id in {"ImportError", "ModuleNotFoundError",
                                  "Exception"})
            for h in node.handlers)
        if not handled:
            continue
        for stmt in node.body:
            for inner in ast.walk(stmt):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    exempt.add(id(inner))
    return exempt


def _imported_targets(tree):
    """Every `intent_engine.*` name a module claims to import.

    Yields `(module, name)` where `name` may be a submodule or an attribute --
    `from intent_engine.founder_brief import market` cannot be told apart from
    an attribute import without resolving it, which is the point.
    """
    exempt = _optional_imports(tree)
    for node in ast.walk(tree):
        if id(node) in exempt:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("intent_engine"):
                    yield alias.name, ""
        elif isinstance(node, ast.ImportFrom):
            if node.level or not (node.module or "").startswith(
                    "intent_engine"):
                continue
            for alias in node.names:
                yield node.module, alias.name


def _resolves(module, name):
    if not name:
        return importlib.util.find_spec(module) is not None
    try:
        if importlib.util.find_spec(f"{module}.{name}") is not None:
            return True
    except (ImportError, AttributeError, ValueError):
        pass
    return hasattr(importlib.import_module(module), name)


def test_no_module_imports_something_that_no_longer_exists():
    """The guard the baseline needed: an import edge to a deleted module.

    Every `intent_engine` import in `src/` and `tests/`, including the lazy
    ones inside functions that no import-time check would ever reach.
    """
    dead = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as exc:  # a broken file is a different failure
            pytest.fail(f"{path}: {exc}")
        for module, name in _imported_targets(tree):
            try:
                ok = _resolves(module, name)
            except ModuleNotFoundError:
                ok = False
            if not ok:
                target = f"{module}.{name}" if name else module
                dead.append(f"{path.relative_to(REPO)}: {target}")
    assert not dead, "imports of modules that do not exist:\n" + "\n".join(dead)


def test_the_founder_brief_holds_no_second_market_consumer():
    """One reader of the market export, not two.

    `founder_brief` receives market context as an already-validated dict from
    `external_intel.presenter`. It must not know the export's schema name,
    because knowing it is how a module starts parsing the export itself.
    """
    offenders = [
        f"{py.relative_to(REPO)}"
        for py in sorted((PKG / "founder_brief").rglob("*.py"))
        if "market_intel_export" in py.read_text()
    ]
    assert not offenders, (
        "founder_brief names the market export schema, which is the shape a "
        "duplicate consumer takes: " + ", ".join(offenders))


def test_the_market_export_is_validated_in_exactly_one_place():
    """The allowlist is the whole safety argument for what reaches a founder.

    A second validator would be a second allowlist, and the one that was
    weaker would be the one that let a trading internal through.
    """
    validators = {
        py.relative_to(PKG).as_posix()
        for py in sorted(PKG.rglob("*.py"))
        if "ExportViolation" in py.read_text()
        and "raise ExportViolation" in py.read_text()
    }
    assert validators == {"external_intel/market_contract.py"}, validators
