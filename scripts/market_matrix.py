#!/usr/bin/env python3
"""Derive the completion matrix. Counts are computed, never typed.

A hand-written predecessor said "PARTIAL (10)" above a table of twelve
PARTIAL rows. This script is the reason that cannot happen again: the counts
in any report come from here, and `tests/test_market_matrix.py` asserts they
equal the rows.
"""
from __future__ import annotations

import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs" / "execution" / "MARKET_LEARNING_OS_MATRIX.yaml"


def load() -> dict:
    import yaml
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


def tally(matrix: dict) -> dict:
    axes = matrix["axes"]
    capability = collections.Counter(a["capability"] for a in axes)
    empirical = collections.Counter(a["empirical"] for a in axes)
    return {"axes": len(axes),
            "capability": dict(sorted(capability.items())),
            "empirical": dict(sorted(empirical.items()))}


def blocking(matrix: dict) -> list:
    """Axes that block resumption: engineering-executable and not finished.

    BLOCKED_DATA / BLOCKED_EXTERNAL / NOT_APPLICABLE do NOT block — those are
    honest maturity gates. PARTIAL, NOT_BUILT and UNMEASURED do.
    """
    return [a["id"] for a in matrix["axes"]
            if a["capability"] in ("PARTIAL", "NOT_BUILT", "UNMEASURED")]


def render(matrix: dict) -> str:
    counts = tally(matrix)
    out = ["=" * 74,
           f"MARKET LEARNING OS — COMPLETION MATRIX ({counts['axes']} axes)",
           "=" * 74,
           f"  {'axis':<26}{'capability':<16}{'empirical':<18}"]
    for axis in matrix["axes"]:
        out.append(f"  {axis['id']:<26}{axis['capability']:<16}"
                   f"{axis['empirical']:<18}")
    out += ["", "CAPABILITY", "  " + "  ".join(
        f"{k}={v}" for k, v in counts["capability"].items()),
        "EMPIRICAL", "  " + "  ".join(
            f"{k}={v}" for k, v in counts["empirical"].items())]
    total = sum(counts["capability"].values())
    out += ["",
            f"  counts sum to {total}; matrix has {counts['axes']} axes "
            f"({'AGREE' if total == counts['axes'] else 'DISAGREE'})"]
    blockers = blocking(matrix)
    out += ["", f"BLOCKING RESUMPTION ({len(blockers)})",
            "  " + (", ".join(blockers) if blockers else "none"), "=" * 74]
    return "\n".join(out)


if __name__ == "__main__":
    print(render(load()))
    sys.exit(0)
