"""Problem statements, deduplication, and problem evolution (T020).

A problem is recorded BEFORE any solution exists. It carries what is
wrong, the evidence for believing it, who it affects, what makes it
current, and what it costs to do nothing. A statement missing any of
those is rejected rather than softened.

Problems are first-class and separate from opportunities because one
problem routinely carries several competing opportunities:

    Problem: onboarding loses people between signup and first value
        Opportunity A: an interactive first-run walkthrough
        Opportunity B: a lifecycle email sequence
        Opportunity C: a pricing-page change that resets expectations

Collapsing those into one record destroys the fan-out the founder needs
in order to choose. Problems also EVOLVE — they split, merge, retire, and
get superseded — so they are not modelled as static rows.
"""
from __future__ import annotations

import hashlib
import re

from intent_engine.product.records import (
    REFERENCE_KINDS, ProductError, assert_product_language,
)

PROBLEM_DEDUP_VERSION = "problem_dedup.v1"

REQUIRED_PROBLEM_PARTS = ("statement", "evidence_references", "why_now",
                          "what_changes_if_ignored")


def normalize_problem(text: str) -> str:
    """Deterministic normalization — the key that lets two recordings of
    the same problem be recognized as one."""
    lowered = " ".join((text or "").lower().split())
    lowered = re.sub(r"[^\w\s%.-]", "", lowered)
    return lowered.strip()


def problem_dedup_key(statement: str, scope: str = "") -> str:
    """EXACT-match dedup, deliberately. Near-duplicate merging silently
    folds two different problems into one, and the founder loses the
    distinction that made them different."""
    payload = "|".join([normalize_problem(statement), normalize_problem(scope)])
    return "problem-" + hashlib.sha256(payload.encode()).hexdigest()[:32]


def validate_reference(ref) -> dict:
    """An evidence reference points INTO another subsystem. It is never a
    copy of what that subsystem holds."""
    if not isinstance(ref, dict):
        raise ProductError(
            "an evidence reference is a mapping of kind + ref_id, so it can "
            "be resolved back to the subsystem that owns the fact")
    kind, ref_id = ref.get("kind"), ref.get("ref_id")
    if kind not in REFERENCE_KINDS:
        raise ProductError(
            f"unknown evidence reference kind: {kind!r} — one of "
            f"{sorted(REFERENCE_KINDS)}")
    if not isinstance(ref_id, str) or not ref_id.strip():
        raise ProductError("an evidence reference requires a non-empty ref_id")
    out = {"kind": kind, "ref_id": ref_id}
    for optional in ("request_id", "experiment_id", "crm_entity_id",
                     "metric_name", "detail", "label", "stance"):
        if ref.get(optional) is not None:
            out[optional] = ref[optional]
    return out


def build_problem_statement(*, statement: str, evidence_references,
                            why_now: str, what_changes_if_ignored: str,
                            affected_customers=None, scope: str = "",
                            first_observed_at: str) -> dict:
    """The structural bars, applied before anything is written."""
    if not str(statement or "").strip():
        raise ProductError("a problem statement states what is wrong")
    refs = [validate_reference(r) for r in (evidence_references or [])]
    if not refs:
        raise ProductError(
            "a problem statement with zero evidence references is rejected — "
            "evidence comes before problem, and problem before solution")
    for part, value in (("why_now", why_now),
                        ("what_changes_if_ignored", what_changes_if_ignored)):
        if not str(value or "").strip():
            raise ProductError(
                f"{part} is a required part of a problem statement: a problem "
                "with no stated currency and no stated cost of inaction is "
                "not yet a problem this subsystem can carry")
    customers = sorted({c for c in (affected_customers or []) if c})
    for text, where in ((statement, "problem statement"),
                        (why_now, "why_now"),
                        (what_changes_if_ignored, "what_changes_if_ignored")):
        assert_product_language(text, where=where)
    return {
        "statement": statement.strip(),
        "normalized": normalize_problem(statement),
        "dedup_key": problem_dedup_key(statement, scope),
        "dedup_version": PROBLEM_DEDUP_VERSION,
        "scope": scope,
        "evidence_references": refs,
        "affected_customers": customers,
        "why_now": why_now.strip(),
        "what_changes_if_ignored": what_changes_if_ignored.strip(),
        "first_observed_at": first_observed_at,
    }


def assert_solution_free(text: str, *, where: str = "problem statement") -> None:
    """A problem stated as its solution is not a problem statement. This is
    the structural defence against a feature factory, applied at the point
    where the distortion enters."""
    lowered = " ".join((text or "").lower().split())
    tells = ("we should build", "we need to build", "add a button",
             "implement a", "ship a", "build a feature", "we will build")
    hits = sorted({t for t in tells if t in lowered})
    if hits:
        raise ProductError(
            f"{where} is phrased as a solution ({hits}) — record what is "
            "wrong first; candidate solutions belong on a proposal")
