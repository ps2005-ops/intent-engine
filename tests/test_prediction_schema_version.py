"""The provenance field that never came from where it claimed to.

`executive/snapshots.py::_versions` reported a `prediction_version` by
importing `PREDICTION_SCHEMA_VERSION` from `core.prediction_ledger` — a module
that never defined it. So the import raised on every call, and the handler
supplied the SAME string the import would have returned:

    except ImportError:
        versions["prediction_version"] = "prediction_ledger.v1"

Success and failure were indistinguishable by construction. Nothing in the
snapshot, and no test, could tell that the value had never once come from the
module that owns the schema. Found by the dead-import guard in
`test_architecture_no_dead_imports.py`, which exempts try/except-ImportError
imports because they declare a fallback — this one declared a fallback that was
never not used.

The rule these tests encode: a fallback must be DISTINGUISHABLE from the thing
it stands in for, or it is not a fallback, it is a disguise.
"""
import pytest

from intent_engine.core import prediction_ledger as PL
from intent_engine.executive import snapshots as S


def test_the_module_that_owns_the_schema_publishes_its_version():
    assert PL.PREDICTION_SCHEMA_VERSION
    assert PL.PREDICTION_SCHEMA_VERSION.startswith("prediction_ledger.")


def test_the_snapshot_reports_the_version_the_module_declares():
    """Not a literal that happens to match — the actual imported value."""
    versions = S._versions(_service())
    assert versions["prediction_version"] == PL.PREDICTION_SCHEMA_VERSION


def test_a_failed_import_is_distinguishable_from_a_successful_one(monkeypatch):
    """The regression, stated as behaviour rather than as source text.

    A snapshot is a provenance record. If the module that owns the schema
    cannot be read, the honest entry is that we do not know — and it must not
    be the string a working import produces, or a broken import is invisible
    again and this file stops being able to fail.
    """
    working = S._versions(_service())["prediction_version"]

    import builtins
    real_import = builtins.__import__

    def refuse(name, *a, **kw):
        if name == "intent_engine.core.prediction_ledger":
            raise ImportError("simulated: the ledger module is unreadable")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", refuse)
    broken = S._versions(_service())["prediction_version"]

    assert broken == "unknown"
    assert broken != working, (
        "the ImportError handler restates the version the import provides; "
        "a silent fallback would be undetectable")


def test_the_version_tracks_the_table_not_the_model():
    """`v1` is a claim about `_ensure_schema`, not about `Prediction`.

    Task M5 added five fields for machine-evaluable market predictions and
    every one lives inside the JSON `data` blob; the `predictions` table has
    the same columns it was created with. A reader of the table gets what the
    version promises. This fails if a column is added without a bump.
    """
    import inspect
    schema = inspect.getsource(PL._ensure_schema)
    columns = {"id", "created_at", "source", "entity_id", "resolved_at",
               "outcome", "data"}
    declared = {line.strip().split()[0] for line in schema.splitlines()
                if line.strip() and line.strip().split()[0] in columns}
    assert declared == columns, (
        "the predictions table changed; PREDICTION_SCHEMA_VERSION describes "
        "this table and must be bumped with it")


# --- helpers ----------------------------------------------------------------
def _service():
    """The narrowest thing `_versions` accepts: it reads four attributes."""
    class _Svc:
        product = None
        research = None
        growth = None
        model_version = "test-model"
    return _Svc()
