"""Turn one learning session into per-company sanitized exports.

WHY THIS MODULE EXISTS
----------------------
`strategic_export` defines the contract and the allowlist that guards it, and
it is correct. But until now nothing in the operating cycle CALLED it: the
only caller in the whole repository was a test. A contract with no producer is
not a boundary, it is a document — the founder side had nothing to read
however carefully the schema was specified.

WHAT A COMPANY IS HERE
----------------------
The learning session is global; the export is per company. Everything the
session produced carries a subject — a belief's `subject`, a hidden state's
`subject`, a reconciliation's `subject`, an interaction's two actors — and
this module inverts that into one bundle per company.

An actor is not automatically a company. `focal_actor` may be a regulator or a
buyer group, and publishing a strategic dossier keyed on "EU Commission"
would invent a company that the engine never evaluated. So interactions are
attached to companies that ALREADY have material of their own, and never
create a company on their own.

SILENCE IS THE DEFAULT
----------------------
A company with no beliefs, no posture movement, no mismatch and no priority
gets no file. An empty dossier published daily is how a product teaches its
reader to stop opening it — and worse, an empty export is indistinguishable
from a fresh one that happens to say nothing, which is exactly the confusion
`freshness` exists to prevent.

A LEAK FAILS THAT COMPANY, NOT THE CYCLE
----------------------------------------
`build_export` raises `ExportLeak` when a field is not allowlisted. That is a
safety stop and it is honoured: the file is NOT written and the company is
reported as refused, with the reason. It does not take the session down —
learning already happened and is already recorded — and it is never swallowed
into a success count, because a silent leak-refusal would look identical to
having nothing to say.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any, Dict, List, Sequence, Tuple

from . import strategic_export as SE

EXPORT_DIR = "reports/market/strategic"


def company_key(subject: str) -> str:
    """A stable filename for a company subject.

    Lowercase, non-alphanumerics collapsed to a single dash. Two subjects that
    differ only by punctuation or case are the same company, and must not
    produce two dossiers that each hold half the evidence.
    """
    key = re.sub(r"[^a-z0-9]+", "-", (subject or "").strip().lower())
    return key.strip("-")


def _by_subject(items: Sequence[Any], attr: str = "subject",
                ) -> Dict[str, List[Any]]:
    out: Dict[str, List[Any]] = {}
    for item in items:
        subject = getattr(item, attr, "") or ""
        key = company_key(subject)
        if key:
            out.setdefault(key, []).append(item)
    return out


def _display_name(items: Sequence[Any], attr: str = "subject") -> str:
    for item in items:
        name = getattr(item, attr, "") or ""
        if name:
            return name
    return ""


def bundles(result, *, market_structures: Sequence[Any] = (),
            pricing_actions: Sequence[Any] = (),
            causal_pathways: Sequence[Any] = ()) -> Dict[str, dict]:
    """Group one session's material into per-company bundles.

    Market structure, pricing analysis and causal pathways describe a MARKET
    rather than a company, so they are attached to every company that already
    has material — they qualify a reading, they never constitute one.
    """
    beliefs = _by_subject(getattr(result, "beliefs_after", ()))
    hidden = _by_subject(getattr(result, "hidden_states_after", ()))
    mismatches = _by_subject(getattr(result, "reconciliations_seen", ()))
    priorities = _by_subject(getattr(result, "priorities_seen", ()))

    # Only companies that spoke for themselves get a dossier.
    keys = set(beliefs) | set(hidden) | set(mismatches) | set(priorities)

    interactions: Dict[str, List[Any]] = {}
    for item in getattr(result, "interactions_seen", ()):
        for attr in ("focal_actor", "responding_actor"):
            key = company_key(getattr(item, attr, "") or "")
            if key in keys:
                interactions.setdefault(key, []).append(item)

    out: Dict[str, dict] = {}
    for key in sorted(keys):
        out[key] = {
            "company_id": key,
            "display_name": (_display_name(beliefs.get(key, ()))
                             or _display_name(hidden.get(key, ()))
                             or _display_name(mismatches.get(key, ()))
                             or key),
            "beliefs": beliefs.get(key, []),
            "hidden_states": hidden.get(key, []),
            "interactions": interactions.get(key, []),
            "reconciliations": mismatches.get(key, []),
            "information_priorities": priorities.get(key, []),
            "market_structure": (market_structures[0]
                                 if market_structures else None),
            "pricing_actions": list(pricing_actions),
            "causal_pathways": list(causal_pathways),
        }
    return out


def publish(result, *, root=".", market_structures: Sequence[Any] = (),
            pricing_actions: Sequence[Any] = (),
            causal_pathways: Sequence[Any] = (),
            limitations: Sequence[str] = ()) -> dict:
    """Write one sanitized export per company with something to say.

    Returns a report the cycle can print: what was published, what was
    skipped for having no material, and what was REFUSED because the
    allowlist caught a field on its way out.
    """
    grouped = bundles(result, market_structures=market_structures,
                      pricing_actions=pricing_actions,
                      causal_pathways=causal_pathways)
    published: List[str] = []
    refused: List[dict] = []
    for key, bundle in grouped.items():
        try:
            payload = SE.build_export(
                company_id=key, as_of=result.as_of,
                beliefs=bundle["beliefs"],
                hidden_states=bundle["hidden_states"],
                interactions=bundle["interactions"],
                market_structure=bundle["market_structure"],
                pricing_actions=bundle["pricing_actions"],
                causal_pathways=bundle["causal_pathways"],
                reconciliations=bundle["reconciliations"],
                information_priorities=bundle["information_priorities"],
                limitations=list(limitations))
            SE.write_export(payload, root=root)
        except SE.ExportLeak as exc:
            # Fail closed, loudly, and per company. Never counted as a
            # publish, never counted as "nothing to say".
            refused.append({"company_id": key, "reason": str(exc)})
            continue
        published.append(key)
    return {
        "contract": SE.EXPORT_VERSION,
        "as_of": result.as_of,
        "companies_with_material": len(grouped),
        "published": sorted(published),
        "refused": refused,
        "directory": str(pathlib.Path(root) / EXPORT_DIR),
        "note": ("a company with no belief, posture move, mismatch or "
                 "information priority is not given an empty dossier"),
    }
