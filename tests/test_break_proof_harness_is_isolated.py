"""A trust harness may not make the working tree wrong, even briefly.

THE DEFECT THIS PINS. `verify()` used to write each mutation into `src/` and
restore it in a `finally`. While that window is open every other reader of the
repository -- the rest of the suite, an editor, a concurrent agent session on
the same checkout -- sees deliberately broken source. A full-suite run failed
intermittently on a proof that passed 20/20 in isolation, which is what that
hazard looks like from outside.

Mutations now happen in a private hard-linked copy of `src/`, so the shared
tree is never written at all. These tests are the negative controls for that:
under the OLD harness the first one fails by construction, because the old
code bumped the mutated file's mtime on purpose.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from break_proof_harness import HELD, NO_OP, Proof, ROOT, verify  # noqa: E402

TARGET = ROOT / "src/intent_engine/company_ingestion/relevance.py"
PAIRED = ("tests/test_relevance_wall.py"
          "::test_the_real_eventiko_sentence_is_irrelevant")
BIOGRAPHY = ("tests/test_discovery_coverage_is_measured.py"
             "::test_an_executive_biography_is_not_evidence_about_the_company")


def _stat(path: pathlib.Path):
    info = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(),
            info.st_mtime_ns, info.st_size)


def test_a_proof_never_writes_the_shared_source():
    """NEGATIVE CONTROL. mtime is the tell: the old harness bumped it
    deliberately on every proof, so this assertion could not have passed
    before the isolation change."""
    before = _stat(TARGET)
    result = verify(Proof(
        label="relevance stops demoting executive biographies",
        path=TARGET,
        find="        if _BIOGRAPHICAL.search(sentence):",
        replace="        if False and _BIOGRAPHICAL.search(sentence):",
        target=BIOGRAPHY,
        expect_failure_contains="assert"))
    after = _stat(TARGET)

    assert result.verdict == HELD, result.detail
    assert before == after, (
        "the shared source was written during an isolated proof: "
        f"{before} -> {after}")


def test_the_harness_still_refuses_a_no_op_mutation():
    """Isolation must not cost the hardening. A mutation that changes no bytes
    is still INVALID, not a pass -- that is the defect the harness exists for.
    """
    result = verify(Proof(
        label="no-op",
        path=TARGET,
        find="        if listed and author_voice:",
        replace="        if listed and author_voice:",
        target=PAIRED))
    assert result.verdict == NO_OP


def test_the_mutation_actually_reaches_the_subprocess():
    """THE FAILURE THIS ALMOST SHIPPED.

    pytest.ini pins `pythonpath = src` and inserts it at the FRONT of
    sys.path, ahead of the environment. The first isolated implementation was
    therefore shadowed by the real tree, every mutation was inert, and all
    twenty proofs reported NOT_CAUGHT at once -- a harness that cannot fail
    dressed as a harness that passes. HELD here means the private copy really
    is the code under test.
    """
    result = verify(Proof(
        label="biographical demotion removed",
        path=TARGET,
        find="        if _BIOGRAPHICAL.search(sentence):",
        replace="        if False and _BIOGRAPHICAL.search(sentence):",
        target=BIOGRAPHY,
        expect_failure_contains="assert"))
    assert result.verdict == HELD, result.detail
