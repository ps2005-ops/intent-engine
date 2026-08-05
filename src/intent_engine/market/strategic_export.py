"""The ONLY channel from strategic market learning to Founder Intelligence.

WHY AN ALLOWLIST AND NOT A DENYLIST
-----------------------------------
`intelligence_export` uses `FORBIDDEN_KEYS`, and that was the right call for a
payload whose shape was fixed. This payload is not: it carries beliefs,
interactions, hidden states and causal pathways, and every one of those grows
new fields as the engine grows. A denylist protects against the leaks somebody
already thought of. The leak that matters is the one added six months from now
by someone who has never read this file.

So the rule is inverted. A field reaches a founder only if it is named here.
Everything else fails closed, at any depth, including inside lists — and the
test suite drives an unknown field through to prove it.

WHAT MAY NEVER CROSS
--------------------
Strategy names, signal names, trade direction, position details, book names,
win rate, alpha, Sharpe, profit factor, internal calibration, shadow-policy
performance, and raw regret tied to trading policy. None of these are
allowlisted, so none of them can appear — but `_BANNED_SUBSTRINGS` also
catches them inside otherwise-permitted free text, because a leak dressed as
prose is still a leak.

WHAT MAY CROSS, AND WHY IT IS SAFE
----------------------------------
Strategic knowledge about the WORLD: that a competitor cut prices, that the
posture evidence has shifted, that a preregistered expectation was
contradicted, that an upcoming filing would resolve an open question. None of
it describes the engine's positions or performance, and all of it is
independently useful to somebody who will never trade.

FRESHNESS IS PART OF THE CONTRACT
---------------------------------
A strategic reading with no date is indistinguishable from a current one. Every
export carries `as_of` and per-item freshness, and a consumer can tell stale
from fresh without asking.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

EXPORT_VERSION = "strategic_market_intel.v1"


class ExportLeak(RuntimeError):
    """The export tried to emit a field that is not allowlisted."""


# --------------------------------------------------------------------------
# THE ALLOWLIST. A field absent from this tree cannot be exported.
# `"*"` means "any key at this level", used only for genuinely open maps
# whose VALUES are themselves scalars (never nested objects).
# --------------------------------------------------------------------------
ALLOWED: Dict[str, Any] = {
    "export_version": None,
    "generated_at": None,
    "company_id": None,
    # THE SUBJECT, NAMED OUT LOUD. `company_id` is derived from this engine's
    # internal universe id, which the founder side has never seen and cannot
    # guess; it asked for the dossier under the name a founder typed and got
    # nothing, on every real company, without either side reporting a fault.
    # A key is not an identity unless both sides derive it from the same
    # string, so the export now states its subject instead of encoding it.
    "company_display_name": None,
    "subject_names": None,
    "as_of": None,
    "freshness": {"status": None, "as_of": None, "age_days": None,
                  "stale": None, "note": None},
    "strategic_beliefs": [{
        "proposition": None, "subject": None, "confidence": None,
        "direction_of_last_change": None, "last_updated": None,
        "basis": None, "update_method": None, "evidence_ids": None,
        "limitations": None,
    }],
    "hidden_states": [{
        "subject": None, "leading_state": None, "leading_probability": None,
        "alternatives": [{"state": None, "probability": None}],
        "moved": [{"state": None, "from": None, "to": None}],
        "as_of": None, "evidence_ids": None,
        "certainty_note": None,
    }],
    "interactions": [{
        "focal_actor": None, "responding_actor": None,
        "initial_action": None, "response": None, "at": None,
        "response_lag_days": None, "payoff_change": None,
        "payoff_note": None, "inferred_objective": None,
        "alternative_explanations": None, "evidence_ids": None,
        "status": None,
    }],
    "market_structure": {
        "market_definition": None, "strategic_job": None,
        "buyer_groups": None, "concentration": None,
        "concentration_note": None,
        "facts": [{"dimension": None, "finding": None, "status": None,
                   "evidence_ids": None, "limitation": None}],
        "unassessed_dimensions": None,
    },
    "pricing_actions": [{
        "kind": None, "applies": None, "applies_because": None,
        "mechanism": None, "findings": None, "risks": None,
        "evidence_ids": None, "limitations": None,
    }],
    "causal_pathways": [{
        "name": None, "narrative": None, "nodes": None, "status": None,
        "total_lag_days": None, "weakest_link": None,
        "edges": [{"cause": None, "effect": None, "direction": None,
                   "mechanism": None, "lag_days": None, "status": None,
                   "competing_explanations": None, "evidence_ids": None}],
    }],
    "expectation_mismatches": [{
        "subject": None, "expected_event": None,
        "expected_direction": None, "observed_direction": None,
        "outcome": None, "rationale": None, "evaluated_at": None,
        "preregistered_at": None, "falsifier": None, "evidence_ids": None,
    }],
    "competitor_reactions": [{
        "responder": None, "response": None, "confidence": None,
        "payoff_effect": None, "rationale": None, "precedents": None,
        "second_order": None, "evidence_ids": None, "is_prediction": None,
    }],
    "information_priorities": [{
        "subject": None, "candidate_observation": None,
        "observation_kind": None, "expected_date": None,
        "priority": None, "falsifies": None, "limitation": None,
    }],
    "limitations": None,
    "evidence_ids": None,
    "disclaimer": None,
    "interpretation_allowed": None,
    "interpretation_forbidden": None,
}

# Caught inside free text too — a leak dressed as prose is still a leak.
_BANNED_SUBSTRINGS = (
    "win rate", "win_rate", "sharpe", "alpha", "profit factor",
    "profit_factor", "expectancy", "net return", "net_return",
    "paper book", "paper_book", "shadow portfolio", "shadow_portfolio",
    "position size", "position_size", "signal fired", "signal_fired",
    "strategy key", "strategy_key", "buy signal", "sell signal",
    "long position", "short position", "price target", "target price",
)

DISCLAIMER = (
    "Descriptive strategic context derived from public evidence. Not a "
    "recommendation, not a forecast, and not a statement about any "
    "investment position.")

INTERPRETATION_ALLOWED = (
    "A named actor took a stated action on a stated date.",
    "The evidence has shifted the weight across possible postures.",
    "A preregistered expectation was contradicted by what was observed.",
    "A stated mechanism connects one factor to another, with its lag.",
    "This upcoming observation would most reduce a stated uncertainty.",
)

INTERPRETATION_FORBIDDEN = (
    "any buy/sell/hold implication, however hedged",
    "any claim about the engine's trading performance",
    "any assertion that a competitor's motive is known",
    "any forecast of a price or a financial result",
    "any presentation of a posture probability as a certainty",
)


def _walk_allowlist(node: Any, spec: Any, path: str) -> None:
    """Recursively verify every emitted field is named in the allowlist."""
    if spec is None:
        # Leaf: scalars and flat lists of scalars are fine. A nested object
        # under a leaf spec is an un-declared structure and fails closed.
        if isinstance(node, dict):
            raise ExportLeak(
                f"{path or 'root'}: nested object where the allowlist "
                f"declares a leaf; declare its fields explicitly")
        if isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                if isinstance(item, (dict, list, tuple)):
                    raise ExportLeak(
                        f"{path}[{i}]: nested structure inside a leaf list")
        return

    if isinstance(spec, list):
        if not isinstance(node, (list, tuple)):
            raise ExportLeak(f"{path}: expected a list")
        inner = spec[0] if spec else None
        for i, item in enumerate(node):
            _walk_allowlist(item, inner, f"{path}[{i}]")
        return

    if isinstance(spec, dict):
        if not isinstance(node, dict):
            raise ExportLeak(f"{path}: expected an object")
        for key, value in node.items():
            if key in spec:
                _walk_allowlist(value, spec[key],
                                f"{path}.{key}" if path else str(key))
            elif "*" in spec:
                _walk_allowlist(value, spec["*"],
                                f"{path}.{key}" if path else str(key))
            else:
                raise ExportLeak(
                    f"unknown field {key!r} at {path or 'root'} is not in "
                    f"the allowlist; the export fails closed rather than "
                    f"letting an upstream addition ride along")
        return

    raise ExportLeak(f"{path}: malformed allowlist spec")  # pragma: no cover


def _scan_text(node: Any, path: str = "") -> None:
    """Catch internals leaking inside otherwise-permitted free text."""
    if isinstance(node, str):
        low = node.lower()
        for banned in _BANNED_SUBSTRINGS:
            if banned in low:
                raise ExportLeak(
                    f"{path}: text contains {banned!r}, which is a trading "
                    f"internal and may not reach a founder surface")
    elif isinstance(node, dict):
        for key, value in node.items():
            _scan_text(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _scan_text(item, f"{path}[{i}]")


def assert_sanitized(payload: dict) -> None:
    """Both gates. Called on the way out, never trusted at the call site."""
    _walk_allowlist(payload, ALLOWED, "")
    _scan_text(payload)


def _displayer(subject_id: str, display_name: str):
    """Render the engine's internal subject in the founder's vocabulary.

    The learning store keys a belief on `subject_company`, which is the market
    universe's company id — stable, which is exactly why it is used, and a
    slug, which is why it must not be the word a founder reads. The first real
    dossiers said "microsoft is seeing demand strengthen rather than plateau":
    a correct claim about a key.

    The substitution is EXACT and positional, never a search-and-replace. Every
    family template is `"{subject} ..."`, so the subject is a known prefix and
    nothing else in the sentence is touched. A proposition that does not begin
    with the subject is left exactly as written rather than guessed at.
    """
    src = (subject_id or "").strip()
    dst = (display_name or "").strip()

    def show(value: str) -> str:
        return dst if (dst and src and (value or "").strip() == src) else value

    def sentence(text: str) -> str:
        if dst and src and (text or "").startswith(src + " "):
            return dst + text[len(src):]
        return text

    return show, sentence


def build_export(*, company_id: str, as_of: str,
                 subject_id: str = "", display_name: str = "",
                 subject_names: Sequence[str] = (),
                 beliefs: Sequence[Any] = (),
                 hidden_states: Sequence[Any] = (),
                 interactions: Sequence[Any] = (),
                 market_structure: Optional[Any] = None,
                 pricing_actions: Sequence[Any] = (),
                 causal_pathways: Sequence[Any] = (),
                 reconciliations: Sequence[Any] = (),
                 competitor_reactions: Sequence[Any] = (),
                 information_priorities: Sequence[Any] = (),
                 limitations: Sequence[str] = ()) -> dict:
    """Assemble one company's sanitized strategic intelligence.

    Only INFORMATIVE reconciliations cross. A founder does not benefit from
    "we are still waiting", and shipping every open expectation would bury
    the mismatches that actually mean something.
    """
    from . import expectation as EXP

    show, sentence = _displayer(subject_id, display_name)
    payload: Dict[str, Any] = {
        "export_version": EXPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "company_id": company_id,
        "company_display_name": display_name or subject_id or company_id,
        "subject_names": sorted({n for n in
                                 (list(subject_names) + [display_name,
                                                         subject_id])
                                 if (n or "").strip()}),
        "as_of": as_of[:10],
        "freshness": _freshness(as_of),
        "strategic_beliefs": [_belief(b, show, sentence) for b in beliefs],
        "hidden_states": [_hidden(h, show) for h in hidden_states],
        "interactions": [_interaction(i) for i in interactions],
        "pricing_actions": [_gated(p) for p in pricing_actions],
        "causal_pathways": [_pathway(p) for p in causal_pathways],
        "expectation_mismatches": [
            _mismatch(r, show) for r in reconciliations
            if getattr(r, "outcome", "") in EXP.INFORMATIVE],
        "competitor_reactions": [_reaction(r) for r in competitor_reactions],
        "information_priorities": [_priority(p, show)
                                   for p in information_priorities],
        "limitations": list(limitations),
        "disclaimer": DISCLAIMER,
        "interpretation_allowed": list(INTERPRETATION_ALLOWED),
        "interpretation_forbidden": list(INTERPRETATION_FORBIDDEN),
    }
    if market_structure is not None:
        payload["market_structure"] = _structure(market_structure)

    ids: Set[str] = set()
    _collect_ids(payload, ids)
    payload["evidence_ids"] = sorted(ids)

    assert_sanitized(payload)
    return payload


# --- projectors: each one names exactly what crosses ----------------------
def _belief(b, show=lambda s: s, sentence=lambda s: s) -> dict:
    last = b.history[-1] if b.history else None
    return {"proposition": sentence(b.proposition), "subject": show(b.subject),
            "confidence": b.posterior_probability,
            "direction_of_last_change": last.direction if last else None,
            "last_updated": b.last_updated,
            # A belief declared this session has no update history yet. Its
            # basis is the reason it was opened, not an empty string — a
            # founder reading "confidence 0.62, basis: (nothing)" is being
            # shown a number with no argument behind it.
            "basis": last.basis if last else b.confidence_basis,
            "update_method": last.method if last else "DECLARED",
            "evidence_ids": list(b.supporting_evidence_ids)
            + list(b.contradicting_evidence_ids),
            "limitations": list(b.limitations)}


def _hidden(h, show=lambda s: s) -> dict:
    top = h.top(4)
    state, p = h.leading
    moved = h.history[-1].moved() if h.history else ()
    return {"subject": show(h.subject), "leading_state": state,
            "leading_probability": p,
            "alternatives": [{"state": s, "probability": v}
                             for s, v in top[1:]],
            "moved": [{"state": s, "from": round(a, 4), "to": round(c, 4)}
                      for s, a, c in moved],
            "as_of": h.last_updated,
            "evidence_ids": list(h.history[-1].evidence_ids)
            if h.history else [],
            "certainty_note": ("Posture is inferred from public action and "
                               "is never certain; rival postures remain "
                               "live at the stated weights.")}


def _interaction(i) -> dict:
    return {"focal_actor": i.focal_actor,
            "responding_actor": i.responding_actor,
            "initial_action": i.initial_action, "response": i.response,
            "at": i.at, "response_lag_days": i.response_lag_days,
            "payoff_change": i.payoff_change, "payoff_note": i.payoff_note,
            "inferred_objective": i.inferred_objective,
            "alternative_explanations": list(i.alternative_explanations),
            "evidence_ids": list(i.evidence_ids), "status": i.status}


def _structure(s) -> dict:
    d = s.as_dict()
    return {"market_definition": d["market_definition"],
            "strategic_job": d["strategic_job"],
            "buyer_groups": d["buyer_groups"],
            "concentration": d["concentration"],
            "concentration_note": d["concentration_note"],
            "facts": d["facts"],
            "unassessed_dimensions": d["unassessed_dimensions"]}


def _gated(g) -> dict:
    d = g.as_dict()
    return {"kind": d["kind"], "applies": d["applies"],
            "applies_because": d["applies_because"],
            "mechanism": d["mechanism"], "findings": d["findings"],
            "risks": d["risks"], "evidence_ids": d["evidence_ids"],
            "limitations": d["limitations"]}


def _pathway(p) -> dict:
    d = p.as_dict()
    return {"name": d["name"], "narrative": d["narrative"],
            "nodes": d["nodes"], "status": d["status"],
            "total_lag_days": d["total_lag_days"],
            "weakest_link": d["weakest_link"],
            "edges": [{"cause": e["cause"], "effect": e["effect"],
                       "direction": e["direction"],
                       "mechanism": e["mechanism"], "lag_days": e["lag_days"],
                       "status": e["status"],
                       "competing_explanations": e["competing_explanations"],
                       "evidence_ids": e["evidence_ids"]}
                      for e in d["edges"]]}


def _mismatch(r, show=lambda s: s) -> dict:
    return {"subject": show(r.subject), "expected_event": "",
            "expected_direction": None,
            "observed_direction": r.observed_direction,
            "outcome": r.outcome, "rationale": r.rationale,
            "evaluated_at": r.evaluated_at, "preregistered_at": None,
            "falsifier": None, "evidence_ids": list(r.evidence_ids)}


def _reaction(r) -> dict:
    d = r.as_dict()
    return {"responder": d["responder"], "response": d["response"],
            "confidence": d["confidence"],
            "payoff_effect": d["payoff_effect"],
            "rationale": d["rationale"], "precedents": d["precedents"],
            "second_order": d["second_order"],
            "evidence_ids": d["evidence_ids"],
            "is_prediction": d["is_prediction"]}


def _priority(p, show=lambda s: s) -> dict:
    d = p.as_dict()
    return {"subject": show(d["subject"]),
            "candidate_observation": d["candidate_observation"],
            "observation_kind": d["observation_kind"],
            "expected_date": d["expected_date"], "priority": d["priority"],
            "falsifies": d["falsifies"], "limitation": d["limitation"]}


def _freshness(as_of: str) -> dict:
    return {"status": "observed", "as_of": as_of[:10], "age_days": 0,
            "stale": False,
            "note": "reflects strategic evidence available on this date"}


def _collect_ids(node: Any, into: Set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence_ids" and isinstance(value, (list, tuple)):
                into.update(str(v) for v in value)
            else:
                _collect_ids(value, into)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_ids(item, into)


def write_export(payload: dict, root=".") -> pathlib.Path:
    """Publish to the read-only strategic export directory."""
    assert_sanitized(payload)
    out = (pathlib.Path(root) / "reports/market/strategic"
           / f"{payload['company_id']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True,
                              default=str))
    tmp.replace(out)
    return out
