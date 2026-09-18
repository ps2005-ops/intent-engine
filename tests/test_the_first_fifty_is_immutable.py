"""The frozen half of Strategic-100, pinned by hash.

A preregistered cohort is worth exactly as much as the guarantee that nobody
edited it after seeing results. `QUALIFY_50` lives in source control for that
reason, and until now nothing checked it: a reorder, a substitution or a
"small correction" would have passed every test in this suite.

The hash is recorded WITH its algorithm. A hash whose algorithm is not written
down cannot be reproduced by the next reader, which makes it a decoration
rather than a control.

The second 50 is deliberately absent. See
`docs/execution/v5/STRATEGIC100_COHORT_GOVERNANCE.md`: the first 50 was
authored from a prompt rather than sampled from a recorded pool, so no
deterministic rule can reconstruct a matching second half, and inventing one
inside the session that is about to be graded by it is the thing
preregistration exists to prevent.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from perf_progressive_matrix import QUALIFY_50            # noqa: E402

#: sha256(json.dumps(QUALIFY_50, sort_keys=True).encode()).hexdigest()[:16]
FIRST_50_HASH = "716ea020b2fecb35"
FIRST_50_HASH_FULL = (
    "716ea020b2fecb35426df7eba28eec79408c2fd514a092ffbcf1252720dbcd19")


def _hash(cohort) -> str:
    return hashlib.sha256(
        json.dumps(cohort, sort_keys=True).encode()).hexdigest()


def test_the_first_fifty_still_hashes_to_its_frozen_value():
    assert _hash(QUALIFY_50) == FIRST_50_HASH_FULL, (
        "QUALIFY_50 has changed since it was frozen. A cohort edited after "
        "results were seen measures the editor, not the product. If the "
        "change is intended, it is a NEW cohort with a new hash and the "
        "qualification that used the old one does not transfer.")
    assert _hash(QUALIFY_50)[:16] == FIRST_50_HASH


def test_the_cohort_is_fifty_distinct_companies():
    assert len(QUALIFY_50) == 50
    assert len({name for name, _ in QUALIFY_50}) == 50
    assert len({domain for _, domain in QUALIFY_50}) == 50


def test_order_is_part_of_what_is_frozen():
    """NEGATIVE CONTROL. A hash that survives reordering is not pinning the
    cohort, only its membership -- and the ordering is what a resumable
    100-company run indexes into."""
    reordered = list(QUALIFY_50[1:]) + [QUALIFY_50[0]]
    assert _hash(reordered) != FIRST_50_HASH_FULL


def test_a_single_substitution_changes_the_hash():
    """The mutation §11 asks for: alter one member, the hash must move."""
    mutated = list(QUALIFY_50)
    mutated[0] = ("Definitely Not NVIDIA", "example.invalid")
    assert _hash(mutated) != FIRST_50_HASH_FULL


def test_the_second_fifty_is_not_silently_present():
    """A placeholder cohort file would be read as frozen by a later session.
    While the source universe is undecided there must be no such file."""
    docs = pathlib.Path(__file__).resolve().parents[1] / "docs" / "execution" / "v5"
    for name in ("STRATEGIC100_SECOND_50.json",
                 "STRATEGIC100_COHORT_100.json"):
        assert not (docs / name).exists(), (
            f"{name} exists. Either the cohort was frozen and this test must "
            f"be updated with its hash, or a placeholder is masquerading as "
            f"a frozen artifact.")
