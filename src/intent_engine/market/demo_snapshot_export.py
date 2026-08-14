"""Emit `market_demo_snapshot.v1` — bounded references, never bodies.

WHAT THIS IS NOT
-----------------
Not a second `strategic_export`. That one carries the market's *reasoning* to
a founder surface for rendering, and pays for it with a large allowlist and a
text scan. This carries only IDS and STATES, so a neutral read model can say
what exists, how much of it there is, and when it was true, without any of it
being rendered as an assertion.

The narrower payload is the safety property. There is very little here that
could leak, because there is very little here at all.

WHY `None` AND `()` MEAN DIFFERENT THINGS
------------------------------------------
Every block argument defaults to `None`, meaning THE CALLER DID NOT PASS THIS,
which serializes as `UNAVAILABLE` with a reason. An explicitly passed empty
sequence means THE CALLER LOOKED AND FOUND NOTHING, which serializes as
`AVAILABLE` with `count: 0`.

Collapsing those two is the defect the consuming contract is built to refuse,
and a producer that emitted `[]` for both would defeat it before the bytes
ever left this process. The distinction has to be made HERE, by the only code
that knows which subsystems actually ran.

WHAT THIS SIDE MAY NEVER SAY
-----------------------------
`tenant_id`, `data_population`, a scope, a private reference. Market
intelligence is derived from public evidence and has no standing to name a
tenant. The founder-side contract refuses these outright rather than treating
them as an unrecognised producer, and `assert_sanitized` refuses them here so
the failure lands on the side that caused it.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import date
from typing import Any, Dict, Optional, Sequence

SNAPSHOT_VERSION = "market_demo_snapshot.v1"
EXPORT_DIR = "reports/market/demo_snapshots"

#: Bounded so a 100-company sweep does not copy the ledger. `count` carries
#: the true size, so bounding never understates a population.
MAX_REFS = 64


class SnapshotLeak(RuntimeError):
    """The snapshot carried a field this side may not publish."""


#: Restated rather than imported from `strategic_export`, for the same reason
#: that module restates them from the founder side: if the two lists ever
#: disagree, the stricter one must win, and shared mutable state between the
#: gates would let one relaxation open both.
_BANNED_SUBSTRINGS = (
    "win rate", "win_rate", "sharpe", "alpha", "profit factor",
    "profit_factor", "expectancy", "net return", "net_return",
    "paper book", "paper_book", "shadow portfolio", "shadow_portfolio",
    "position size", "position_size", "signal fired", "signal_fired",
    "strategy key", "strategy_key", "buy signal", "sell signal",
    "long position", "short position", "price target", "target price",
)

#: Names this side may never emit at any depth. Mirrors the founder-side
#: `_MARKET_FORBIDDEN`; a match is a refusal, not an unknown field.
_FORBIDDEN_NAMES = frozenset({
    "tenant_id", "tenant_state", "scope", "tenant_scope", "private_refs",
    "internal_refs", "data_population", "authorization", "credential",
})

REAL_MARKET = "REAL_MARKET"
SYNTHETIC_MARKET = "SYNTHETIC_MARKET"

REF_AVAILABLE = "AVAILABLE"
REF_UNAVAILABLE = "UNAVAILABLE"
REF_NOT_ATTEMPTED = "NOT_ATTEMPTED"


def _scan(node: Any, path: str = "") -> None:
    if isinstance(node, str):
        low = node.lower()
        for banned in _BANNED_SUBSTRINGS:
            if banned in low:
                raise SnapshotLeak(
                    f"{path or 'root'}: text contains {banned!r}, a trading "
                    f"internal that may not cross to a founder surface")
    elif isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in _FORBIDDEN_NAMES:
                raise SnapshotLeak(
                    f"{path or 'root'}: field {key!r} may not be published "
                    f"by the market side; it claims authority this side "
                    f"does not have")
            _scan(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _scan(item, f"{path}[{i}]")


def assert_sanitized(payload: dict) -> None:
    """Both gates on the way out. Raises `SnapshotLeak` on any refusal."""
    _scan(payload)


def _id_of(row: Any, *names: str) -> str:
    for name in names:
        value = (row.get(name) if isinstance(row, dict)
                 else getattr(row, name, None))
        if value:
            return str(value)
    return ""


def _block(rows: Optional[Sequence[Any]], *names: str,
           missing_note: str = "") -> dict:
    """Serialize one reference block, honouring the None/() distinction."""
    if rows is None:
        return {"state": REF_UNAVAILABLE, "ids": [], "count": 0,
                "note": missing_note or ("this subsystem did not run for "
                                         "this snapshot")}
    ids = [i for i in (_id_of(r, *names) for r in rows) if i]
    rows = list(rows)
    if rows and not ids:
        # ROWS EXIST AND NONE COULD BE NAMED. Returning count 0 here would be
        # indistinguishable from "the subsystem ran and found nothing" -- the
        # same missing-vs-zero confusion this block's None branch exists to
        # avoid, arriving through the other door. Say so instead.
        return {"state": REF_AVAILABLE, "ids": [], "count": 0,
                "note": f"{len(rows)} row(s) present but none carried any of "
                        f"the identifying fields {names}; this is a wiring "
                        f"defect, not an absence of findings"}
    return {"state": REF_AVAILABLE, "ids": ids[:MAX_REFS], "count": len(ids),
            "note": ""}


def _causal_block(rows: Optional[Sequence[Any]]) -> dict:
    """The causal block, with the resolution STATES stated on the block.

    Publishing only ids would leave a surface unable to tell an estimate from
    a refusal without dereferencing every one, and the refusal is the case a
    CEO surface most needs to render honestly: the engine asked, and the data
    could not answer. That is not "this subsystem did not run".
    """
    block = _block(rows, "resolution_id", "result_id", "id")
    if rows is None or not rows:
        return block
    states: Dict[str, int] = {}
    for row in rows:
        state = (row.get("state") if isinstance(row, dict)
                 else getattr(row, "state", "")) or "UNKNOWN"
        states[str(state)] = states.get(str(state), 0) + 1
    block["states"] = states
    block["note"] = ("the causal router ran; " + ", ".join(
        f"{n} {s}" for s, n in sorted(states.items())))
    return block


def _not_attempted(note: str) -> dict:
    return {"state": REF_NOT_ATTEMPTED, "ids": [], "count": 0, "note": note}


def _snapshot_id(company_id: str, as_of: str, run_id: str) -> str:
    blob = f"{company_id}|{as_of}|{run_id}".encode("utf-8")
    return f"ms-{hashlib.sha256(blob).hexdigest()[:20]}"


def build_snapshot(*, company_id: str, as_of: str, canonical_name: str = "",
                   subject_names: Sequence[str] = (), market_run_id: str = "",
                   runtime_sha: str = "", coverage_state: str = "",
                   market_population: str = REAL_MARKET,
                   known_at: str = "", evidence_cutoff: str = "",
                   source_health: Optional[dict] = None,
                   evidence_summary: Optional[dict] = None,
                   learning_summary: Optional[dict] = None,
                   evidence_rows: Optional[Sequence[Any]] = None,
                   economic_states: Optional[Sequence[Any]] = None,
                   demand_states: Optional[Sequence[Any]] = None,
                   beliefs: Optional[Sequence[Any]] = None,
                   # Produced for 22 of 26 companies and already carried by
                   # the strategic export, but this contract had no field for
                   # it, so the founder product could not show a hidden state
                   # the engine had already inferred.
                   hidden_states: Optional[Sequence[Any]] = None,
                   theses: Optional[Sequence[Any]] = None,
                   thesis_revisions: Optional[Sequence[Any]] = None,
                   expectations: Optional[Sequence[Any]] = None,
                   reconciliations: Optional[Sequence[Any]] = None,
                   contradictions: Optional[Sequence[Any]] = None,
                   causal_questions: Optional[Sequence[Any]] = None,
                   causal_results: Optional[Sequence[Any]] = None,
                   replay_episodes: Optional[Sequence[Any]] = None,
                   adversary_cases: Optional[Sequence[Any]] = None,
                   ) -> dict:
    """Build one company's demo snapshot. Returns a plain serializable dict."""
    known_at = known_at or as_of
    payload: Dict[str, Any] = {
        "contract_version": SNAPSHOT_VERSION,
        "snapshot_id": _snapshot_id(company_id, as_of, market_run_id),
        "company_id": company_id,
        "canonical_name": canonical_name or company_id,
        "subject_names": [str(n) for n in subject_names],
        "market_run_id": market_run_id,
        "analysis_id": market_run_id,
        "runtime_sha": runtime_sha,
        "generated_at": date.today().isoformat(),
        "known_at": known_at,
        "evidence_cutoff": evidence_cutoff or as_of,
        "availability": "AVAILABLE",
        "unavailable_reason": "",
        "market_population": (market_population
                              if market_population in (REAL_MARKET,
                                                       SYNTHETIC_MARKET)
                              else SYNTHETIC_MARKET),
        "coverage_state": coverage_state or "FIELD_UNAVAILABLE",
        "source_health_summary": source_health or {
            "state": "UNAVAILABLE",
            "note": "source health was not summarised for this snapshot"},
        "evidence_summary": evidence_summary or {
            "state": "UNAVAILABLE",
            "note": "evidence was not summarised for this snapshot"},
        # NOT MEASURED HERE, and never faked from `len(evidence_rows)`. A row
        # count is not an independence count: three sites carrying one press
        # release are one account, and the founder-side contract pins this.
        "evidence_independence_state": "UNAVAILABLE",
        "evidence_reference_ids": _block(evidence_rows, "evidence_id", "id"),
        "economic_state_refs": _block(economic_states, "state_id", "id",
                                      "area"),
        "demand_state_refs": _block(demand_states, "id", "state_id"),
        "belief_refs": _block(beliefs, "belief_id", "id", "proposition"),
        # A hidden state carries no id; its identity IS the posture,
        # which is also the only part a CEO surface can use.
        "hidden_state_refs": _block(hidden_states, "leading_state",
                                    "hidden_state_id", "id"),
        "thesis_refs": _block(theses, "thesis_id", "id"),
        "thesis_revision_refs": _block(thesis_revisions, "revision_id", "id"),
        "expectation_refs": _block(expectations, "expectation_id", "id"),
        "reconciliation_refs": _block(reconciliations, "reconciliation_id",
                                      "id"),
        "contradiction_refs": _block(contradictions, "contradiction_id", "id"),
        "causal_question_refs": _block(causal_questions, "causal_question_id",
                                      "question_id", "id"),
        # `resolution_id` is what the resolver actually writes. A refusal
        # carries one exactly like an estimate does, because the engine ran
        # either way -- which is the whole point of publishing these.
        "causal_result_refs": _causal_block(causal_results),
        "replay_refs": _block(replay_episodes, "episode_id", "id"),
        "adversary_refs": _block(adversary_cases, "case_id", "id"),
        "learning_summary": learning_summary or {
            "state": "UNAVAILABLE",
            "note": "learning health was not summarised for this snapshot"},
        "provenance_summary": {"state": "AVAILABLE", "value": runtime_sha,
                               "as_of": known_at,
                               "note": "market runtime provenance"},
    }
    assert_sanitized(payload)
    return payload


def unavailable(company_id: str, reason: str, *, as_of: str = "") -> dict:
    """A stated absence. Published so the founder side can tell "the engine
    looked and published nothing" from "no engine has ever run here" — the
    distinction whose absence hid 22 refused dossiers."""
    return {
        "contract_version": SNAPSHOT_VERSION,
        "snapshot_id": _snapshot_id(company_id, as_of or "", ""),
        "company_id": company_id, "canonical_name": company_id,
        "availability": "UNAVAILABLE", "unavailable_reason": reason,
        "generated_at": date.today().isoformat(),
        "known_at": as_of or date.today().isoformat(),
    }


def write_snapshot(payload: dict, *, root=".") -> pathlib.Path:
    """One file per company. A transport, not the contract — the same bytes
    go over HTTP through `dossier_transport` unchanged."""
    assert_sanitized(payload)
    directory = pathlib.Path(root) / EXPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload['company_id']}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path
