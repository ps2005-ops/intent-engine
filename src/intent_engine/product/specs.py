"""Spec drafts (T020) — bounded on purpose.

A spec draft may contain exactly nine sections:

    goals  non_goals  requirements  constraints  acceptance_criteria
    unknowns  dependencies  risks  open_questions

It may not contain implementation, file paths, code, schemas, estimates,
assignees, or dates. That absence is asserted STRUCTURALLY rather than
requested politely: a spec draft carrying an `implementation` or
`estimate` field is rejected, because this subsystem has no execution
authority and a spec that starts making execution promises is how it
would quietly acquire one.

Every acceptance criterion states an observable condition. "Works well",
"is fast", and "is intuitive" are rejected — not because they are wrong,
but because nobody other than their author can check them.

SPEC DEBT is the counterpart of research debt: what this spec still needs
before implementation is reasonable. It is reported, never hidden, and it
travels with the spec into review.
"""
from __future__ import annotations

from intent_engine.product.records import (
    CHECKABLE_MARKERS, FORBIDDEN_SPEC_FIELDS, SPEC_DEBT_KINDS, SPEC_SECTIONS,
    UNFALSIFIABLE_MARKERS, ProductError, assert_no_certainty,
    assert_product_language,
)

SPEC_CONTRACT_VERSION = "spec_draft.v1"

# Deterministic, stated mapping from the wording of an unknown to the kind
# of work that would resolve it. Anything unmatched is research debt,
# which is the honest default: "we do not yet know" is a research state.
_DEBT_KEYWORDS = (
    ("need_ux", ("ux", "user experience", "wireframe", "design", "flow",
                 "copy", "layout", "interface")),
    ("need_architecture", ("architecture", "schema", "data model",
                           "migration", "storage", "scaling", "interface "
                           "contract", "boundary")),
    ("need_experiment", ("experiment", "a/b", "measure whether", "test "
                         "whether", "hypothesis")),
    ("need_customer_validation", ("customer", "interview", "user research",
                                  "willingness to pay", "demand")),
)


def assert_checkable(criterion: str) -> None:
    """An acceptance criterion states a condition somebody other than its
    author can evaluate."""
    text = str(criterion or "").strip()
    if not text:
        raise ProductError("an empty acceptance criterion is rejected")
    lowered = text.lower()
    unfalsifiable = sorted({m for m in UNFALSIFIABLE_MARKERS if m in lowered})
    if unfalsifiable:
        raise ProductError(
            f"acceptance criterion {text!r} states a feeling rather than an "
            f"observation ({unfalsifiable}) — it states an observable "
            "condition instead")
    if not any(marker in lowered for marker in CHECKABLE_MARKERS):
        raise ProductError(
            f"acceptance criterion {text!r} carries no checkable condition — "
            "one of "
            f"{sorted(CHECKABLE_MARKERS)[:6]} ... makes it evaluable by "
            "somebody other than its author")


def build_spec_draft(sections: dict, *, evidence_label: str = "UNKNOWN") -> dict:
    """Only the nine permitted sections survive; anything else is a
    rejection, not a silent drop."""
    if not isinstance(sections, dict):
        raise ProductError("a spec draft is a mapping of its nine sections")

    forbidden = sorted({key for key in sections
                        if key in FORBIDDEN_SPEC_FIELDS})
    if forbidden:
        raise ProductError(
            f"a spec draft carrying {forbidden} is rejected — implementation, "
            "estimates, assignees, and dates are execution concerns, and this "
            "subsystem holds no execution authority")
    unknown_keys = sorted({key for key in sections if key not in SPEC_SECTIONS})
    if unknown_keys:
        raise ProductError(
            f"a spec draft is bounded to {list(SPEC_SECTIONS)}; "
            f"{unknown_keys} is outside that boundary")

    draft = {name: list(sections.get(name) or []) for name in SPEC_SECTIONS}
    if not draft["goals"]:
        raise ProductError("a spec draft states at least one goal")
    if not draft["acceptance_criteria"]:
        raise ProductError(
            "a spec draft states at least one acceptance criterion; a spec "
            "nobody can check is not yet a spec")
    if not draft["unknowns"]:
        raise ProductError(
            "unknowns are mandatory on a spec draft — a spec with none "
            "recorded has hidden them")

    for criterion in draft["acceptance_criteria"]:
        assert_checkable(criterion)

    body = "\n".join(str(v) for values in draft.values() for v in values)
    assert_product_language(body, where="spec draft")
    assert_no_certainty(body, evidence_label, where="spec draft")

    draft["spec_contract_version"] = SPEC_CONTRACT_VERSION
    draft["sections"] = list(SPEC_SECTIONS)
    return draft


def derive_spec_debt(draft: dict) -> list:
    """Deterministic: every unknown becomes a debt item, classified by a
    stated keyword table. Unmatched unknowns are research debt, which is
    the honest default for "we do not yet know"."""
    debt = []
    for unknown in draft.get("unknowns", []):
        lowered = str(unknown).lower()
        kind = "need_research"
        for candidate_kind, keywords in _DEBT_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                kind = candidate_kind
                break
        debt.append({"kind": kind, "detail": str(unknown)})
    for item in debt:
        if item["kind"] not in SPEC_DEBT_KINDS:
            raise ProductError(f"unknown spec-debt kind: {item['kind']!r}")
    seen, unique = set(), []
    for item in debt:
        key = (item["kind"], item["detail"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def spec_debt_report(draft: dict) -> dict:
    debt = derive_spec_debt(draft)
    by_kind = {}
    for item in debt:
        by_kind.setdefault(item["kind"], []).append(item["detail"])
    return {"total": len(debt),
            "by_kind": {k: sorted(v) for k, v in sorted(by_kind.items())},
            "items": debt,
            "note": ("spec debt is what this draft still needs before "
                     "implementation is reasonable; it travels with the spec "
                     "into review rather than being resolved silently")}
