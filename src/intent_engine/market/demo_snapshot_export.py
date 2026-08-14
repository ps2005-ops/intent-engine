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
from collections.abc import Mapping
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


def _is_evidence_field(key: str) -> bool:
    """Does this field hold evidence ids?

    NOT just `evidence_ids`. That was the first version of this collector, and
    against the real ledger it found nothing: a `StrategicBelief` cites
    `supporting_evidence_ids`, `contradicting_evidence_ids` and
    `applied_evidence_ids`; an expectation cites `evidence_basis`; a thesis
    cites `supporting_evidence` and `contradicting_evidence`. Zero of 76 real
    beliefs carry a field called `evidence_ids`.

    So the rule is the shape, not one name: any field whose name mentions
    evidence and whose value is a list of strings. A narrower rule is a list
    of field names that goes stale silently the next time a producer adds one.
    """
    return "evidence" in key.lower()


def _add_ids(value: Any, into: set) -> bool:
    """Take a list-of-strings as ids. Returns whether it was one -- a nested
    structure under an evidence-ish name still needs descending into."""
    if not isinstance(value, (list, tuple, set)):
        return False
    items = [v for v in value if v]
    if items and all(isinstance(v, str) for v in items):
        into.update(items)
        return True
    return not items


def _collect_evidence_ids(node: Any, into: set, depth: int = 0) -> None:
    """Every evidence id cited anywhere inside one company's own rows.

    Mirrors `strategic_export._collect_ids`, but walks RAW ROWS rather than a
    built payload, so it has to descend through objects as well as mappings.
    Depth is capped because a cycle in a row graph must not hang a publish.
    """
    if depth > 6 or node is None or isinstance(node, str):
        return
    if isinstance(node, Mapping):
        for key, value in node.items():
            if _is_evidence_field(str(key)) and _add_ids(value, into):
                continue
            _collect_evidence_ids(value, into, depth + 1)
        return
    if isinstance(node, (list, tuple, set)):
        for item in node:
            _collect_evidence_ids(item, into, depth + 1)
        return
    # Evidence-bearing attributes are read by NAME rather than only out of
    # `__dict__`: a `__slots__` row has no instance dict at all, and one whose
    # ids live on the class would silently contribute nothing.
    for name in dir(node):
        if name.startswith("_") or not _is_evidence_field(name):
            continue
        try:
            value = getattr(node, name)
        except Exception:  # noqa: BLE001 - a property must not fail a publish
            continue
        if not _add_ids(value, into):
            _collect_evidence_ids(value, into, depth + 1)
    fields = getattr(node, "__dict__", None)
    if isinstance(fields, Mapping):
        for key, value in fields.items():
            if not _is_evidence_field(str(key)):
                _collect_evidence_ids(value, into, depth + 1)


def _posture_of(row: Any) -> str:
    """A hidden state's identity IS its leading posture. Read it whichever
    way the row carries one.

    THE SEAM THIS CROSSES
    ---------------------
    `HiddenStateBelief` exposes `.leading` -- a `(posture, probability)`
    tuple -- and only its `as_dict()` produces `leading_state`. The block was
    wired to `leading_state` alone, so against the real objects production
    passes it named nothing at all, and 22 computed hidden states published
    as a wiring-defect note. The dict form is what the tests used, which is
    why the seam held in test and failed live.
    """
    for name in ("leading_state", "hidden_state_id", "id"):
        value = (row.get(name) if isinstance(row, Mapping)
                 else getattr(row, name, None))
        if value:
            return str(value)
    leading = (row.get("leading") if isinstance(row, Mapping)
               else getattr(row, "leading", None))
    if isinstance(leading, (list, tuple)) and leading:
        return str(leading[0])
    return str(leading) if leading else ""


#: A distribution field is present and this side cannot read it. Distinct
#: from "there is no distribution", because the two have opposite safe
#: defaults: absent means trust the stated posture, unreadable means do not.
UNREADABLE = "UNREADABLE"


def _distribution_of(row: Any):
    """The posterior as {posture: probability}, or None if there is none.

    BOTH SHAPES. `HiddenStateBelief.distribution` is a TUPLE OF PAIRS, and
    only its `as_dict()` form is a mapping. Reading the mapping alone made
    every real posterior unreadable, and an unreadable posterior is precisely
    the case that must not fall through to "identified".
    """
    value = (row.get("distribution") if isinstance(row, Mapping)
             else getattr(row, "distribution", None))
    if value is None:
        return None
    if isinstance(value, Mapping):
        try:
            return {str(k): float(v) for k, v in value.items()}
        except (TypeError, ValueError):
            return UNREADABLE
    if isinstance(value, (list, tuple)):
        out = {}
        for pair in value:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return UNREADABLE
            try:
                out[str(pair[0])] = float(pair[1])
            except (TypeError, ValueError):
                return UNREADABLE
        return out
    return UNREADABLE


def _posture_identified(row: Any) -> bool:
    """Has a posture actually been inferred, or is this the prior?

    THE DEFECT THIS EXISTS TO STOP
    ------------------------------
    All 22 hidden states in the live ledger are UNIFORM: twelve postures at
    0.0833 each, entropy 3.585, which is exactly log2(12) -- the maximum. The
    engine had observed nothing that moved any of them.

    `leading` still returns a posture, because something has to sort first,
    and 22 of 26 companies published `GROWING`. A CEO reading that is told
    the system infers the company is growing. The system inferred nothing;
    `GROWING` was the first key of a twelve-way tie. That is not a display
    bug, it is a fabricated finding, and it is worse than showing nothing.

    So a posture counts as identified only when it is strictly ahead of the
    runner-up AND ahead of the uniform baseline. A distribution nobody can
    read is not evidence of a posture -- it is evidence of no observation.
    """
    dist = _distribution_of(row)
    if dist is None:
        # No distribution to judge. A row that names a posture without one is
        # taken at its word: this guard exists to catch uniform posteriors,
        # not to refuse producers that publish a settled posture directly.
        return True
    if dist is UNREADABLE or not dist:
        # A posterior this side cannot read is not a posture it may publish.
        # The permissive default here is what let a tuple-shaped distribution
        # ship 22 fabricated postures.
        return False
    values = sorted(dist.values(), reverse=True)
    if len(values) < 2:
        return True
    leading, runner_up = values[0], values[1]
    uniform = 1.0 / len(values)
    return leading > runner_up + 1e-9 and leading > uniform + 1e-9


def _hidden_state_block(rows: Optional[Sequence[Any]]) -> dict:
    """The hidden-state block, named by posture across both representations.

    Three outcomes, kept apart: the subsystem did not run; it ran and could
    not identify a posture; it ran and identified one.
    """
    if rows is None:
        return {"state": REF_UNAVAILABLE, "ids": [], "count": 0,
                "note": "this subsystem did not run for this snapshot"}
    rows = list(rows)
    identified = [r for r in rows if _posture_identified(r)]
    ids = [p for p in (_posture_of(r) for r in identified) if p]
    if rows and not identified:
        # RAN, AND IDENTIFIED NOTHING. A real measured zero with a reason --
        # not an absence, and emphatically not a posture.
        return {"state": REF_AVAILABLE, "ids": [], "count": 0,
                "unidentified": len(rows),
                "note": (f"{len(rows)} hidden state(s) were tracked and none "
                         f"is identified: the posterior is uniform, so no "
                         f"posture is distinguishable from the prior. The "
                         f"subsystem ran and observed nothing that moved it")}
    if rows and not ids:
        return {"state": REF_AVAILABLE, "ids": [], "count": 0,
                "note": f"{len(rows)} hidden state(s) present and none "
                        f"carried a leading posture; this is a wiring "
                        f"defect, not an absence of findings"}
    block = {"state": REF_AVAILABLE, "ids": ids[:MAX_REFS], "count": len(ids),
             "note": ""}
    dropped = len(rows) - len(identified)
    if dropped:
        block["unidentified"] = dropped
        block["note"] = (f"{dropped} further hidden state(s) are tracked and "
                         f"not identified; their posteriors are uniform")
    return block


def _evidence_block(rows: Optional[Sequence[Any]], cited: set) -> dict:
    """THIS COMPANY'S evidence, not the ledger.

    THE DEFECT THIS REPLACES
    ------------------------
    This block was `_block(evidence_rows, ...)` over the WHOLE market ledger,
    and the ledger is shared by every subject. So all 26 published snapshots
    carried the same 474-row count and the same first 64 ids: Johnson &
    Johnson's dossier cited Cloudflare's sources. A founder clicking "show me
    the source" was shown another company's evidence, which is false
    intelligence rather than a display bug.

    The strategic export never had this problem because it collects the ids
    its own payload cites (`_collect_ids`). This does the same thing one step
    earlier, over the rows themselves.

    The three outcomes are kept apart on purpose:

    - rows is None      -> the ledger was not supplied; nothing was measured.
    - nothing cited     -> a real zero. This company's blocks cite no evidence.
    - cited, none found -> a WIRING DEFECT, named as one. Citing ids the
      ledger cannot resolve is not the same as citing nothing, and reporting
      it as count 0 is exactly the silent zero the other guards exist to stop.
    """
    if rows is None:
        return {"state": REF_UNAVAILABLE, "ids": [], "count": 0,
                "note": "this subsystem did not run for this snapshot"}
    by_id: Dict[str, Any] = {}
    for row in rows:
        key = _id_of(row, "evidence_id", "id")
        if key:
            by_id.setdefault(key, row)
    if not cited:
        return {"state": REF_AVAILABLE, "ids": [], "count": 0,
                "note": ("no block published for this company cites an "
                         "evidence row; this is a measured zero, not an "
                         "absent ledger")}
    matched = sorted(i for i in cited if i in by_id)
    if not matched:
        return {"state": REF_AVAILABLE, "ids": [], "count": 0,
                "note": (f"{len(cited)} evidence id(s) are cited by this "
                         f"company's blocks and none resolves against the "
                         f"{len(by_id)} identified ledger row(s); this is a "
                         f"wiring defect, not an absence of evidence")}
    note = ""
    unresolved = len(cited) - len(matched)
    if unresolved:
        note = (f"{unresolved} cited evidence id(s) do not resolve against "
                f"the supplied ledger and are not counted")
    return {"state": REF_AVAILABLE, "ids": matched[:MAX_REFS],
            "count": len(matched), "note": note}


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
    # WHICH EVIDENCE IS THIS COMPANY'S. Collected from the company-scoped rows
    # only -- every group below is already filtered to this subject by the
    # caller, which is what makes the result a per-company set.
    _cited: set = set()
    for _group in (beliefs, hidden_states, theses, thesis_revisions,
                   expectations, reconciliations, contradictions,
                   causal_questions, causal_results, replay_episodes,
                   adversary_cases, economic_states, demand_states):
        _collect_evidence_ids(_group, _cited)
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
        # FILTERED TO WHAT THIS COMPANY'S OWN BLOCKS CITE. Passing the shared
        # ledger straight through made every company's evidence identical.
        "evidence_reference_ids": _evidence_block(evidence_rows, _cited),
        "economic_state_refs": _block(economic_states, "state_id", "id",
                                      "area"),
        "demand_state_refs": _block(demand_states, "id", "state_id"),
        "belief_refs": _block(beliefs, "belief_id", "id", "proposition"),
        # A hidden state carries no id; its identity IS the posture,
        # which is also the only part a CEO surface can use.
        "hidden_state_refs": _hidden_state_block(hidden_states),
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
