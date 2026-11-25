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
        # WHAT THOSE evidence_ids ARE ACTUALLY WORTH.
        #
        # `evidence_ids` is a list of ROWS. Three sites carrying one press
        # release put three ids in it, and a consumer with nothing else to go
        # on can only count them — which is how "three sources confirm" gets
        # said about one announcement. This block is the same evidence,
        # normalized: how many things actually happened, how much independent
        # support may honestly be claimed, and the sentence to say about it.
        #
        # It crosses because the market layer OWNS this judgement. The founder
        # side must not re-derive it from source counts; that is the arithmetic
        # that is wrong in the first place.
        "evidence_trust": {
            "contract": None, "standing": None, "raw_accounts": None,
            "distinct_events": None, "independent_support": None,
            "weight": None, "sentence": None,
            # The grouping, so the consumer can walk an occurrence back to
            # every row that reported it. Normalization groups; it never
            # deletes, and this is what makes that checkable rather than
            # promised.
            "events": [{"event_id": None, "standing": None, "accounts": None,
                        "weight": None, "evidence_ids": None}],
        },
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
    # The whole dossier's evidence, normalized once. A consumer that renders a
    # confidence line about the company as a whole reads this rather than
    # counting `evidence_ids`.
    "evidence_trust": {
        "contract": None, "standing": None, "raw_accounts": None,
        "distinct_events": None, "independent_support": None,
        "weight": None, "sentence": None,
        "events": [{"event_id": None, "standing": None, "accounts": None,
                    "weight": None, "evidence_ids": None}],
    },
    # V4. THE ECONOMY, CROSSING. Without this block the founder side has to
    # rebuild the economics from scratch — which is how two systems end up
    # holding two different readings of the same rate move and neither knows
    # it. Every field is a projection of an EconomicThesis, so the standing
    # that crosses is the standing that was earned; nothing here may be
    # rendered more confidently than it arrives.
    "economic_context": {
        "conditions": [{"area": None, "state_kind": None, "standing": None,
                        "moved": None, "reason": None}],
        "conditions_tracked": None,
        "conditions_known": None,
        "note": None,
    },
    "economic_theses": [{
        "thesis_id": None, "claim": None, "standing": None,
        "question": None, "horizon_days": None,
        "macro_conditions": None, "exposures": None,
        "mechanism": None, "falsifier": None,
        # ALTERNATIVES ARE PART OF THE PAYLOAD, not an optional extra. A
        # consumer that receives a claim without its rivals has been handed a
        # leading explanation and will render it as the only one.
        "alternatives": None,
        "unknowns": None,
        "decision_implication": None,
        "confidence_in_words": None,
        "evidence_ids": None,
        # THE ADJUDICATED CEILING, not the standing alone. A consumer handed a
        # bare standing has to re-derive what it may say from it, and that
        # second derivation is where the two sides drift. What crosses is the
        # decision and the words it forbids; the consumer may make it
        # stricter, never looser.
        "ceiling": None,
        "forbidden_words": None,
    }],
    # THESIS HISTORY, WITHOUT WHICH "WHAT CHANGED YOUR MIND" CANNOT BE
    # ANSWERED HONESTLY. The consumer previously received the CURRENT thesis
    # and nothing about how it got there, so it could not tell a thesis that
    # has never moved from a thesis whose history was simply not transported
    # — and those need opposite answers. Today every live revision is
    # CREATED, so both readings produce the same sentence and the defect is
    # invisible; it starts giving a wrong answer the moment a thesis first
    # moves.
    #
    # `thesis_history` is a STATED STATUS rather than an inference from the
    # length of the list below. An empty list means "no revisions crossed",
    # which is exactly the ambiguity this field exists to remove.
    "thesis_history": {"status": None, "revisions": None, "moved": None,
                       "note": None},
    "thesis_revisions": [{
        "revision_id": None, "thesis_id": None, "previous_revision": None,
        "transition": None, "changed_at": None, "changed_fields": None,
        # The CAUSE, carried as ids rather than prose. A consumer that gets
        # "the view weakened" without the effect and evidence behind it can
        # render a claim it cannot substantiate, which is the failure the
        # whole provenance chain exists to prevent.
        "knowledge_effect_ids": None, "triggering_evidence": None,
        "previous_standing": None, "new_standing": None, "reason": None,
    }],
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


#: Banned terms that are ordinary words inside real company names. Matched on
#: WORD BOUNDARIES rather than as bare substrings, because "alpha" as a bare
#: substring refuses `Alphabet Inc.` — a top-five public company whose export
#: therefore failed closed with a message about trading internals. The term is
#: still caught where it is actually a trading claim ("our alpha was 3%").
_WORD_BOUNDED = frozenset({"alpha", "expectancy", "sharpe"})
_BOUNDED_PATTERNS = {
    term: __import__("re").compile(r"\b" + term + r"\b")
    for term in _WORD_BOUNDED
}


def _scan_text(node: Any, path: str = "") -> None:
    """Catch internals leaking inside otherwise-permitted free text."""
    if isinstance(node, str):
        low = node.lower()
        for banned in _BANNED_SUBSTRINGS:
            pattern = _BOUNDED_PATTERNS.get(banned)
            hit = pattern.search(low) if pattern else (banned in low)
            if hit:
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
                 evidence_rows: Sequence[Any] = (),
                 economic_states: Sequence[Any] = (),
                 economic_theses: Sequence[Any] = (),
                 thesis_revisions: Sequence[Any] = (),
                 history_available: bool = True,
                 limitations: Sequence[str] = ()) -> dict:
    """Assemble one company's sanitized strategic intelligence.

    Only INFORMATIVE reconciliations cross. A founder does not benefit from
    "we are still waiting", and shipping every open expectation would bury
    the mismatches that actually mean something.
    """
    from . import expectation as EXP

    show, sentence = _displayer(subject_id, display_name)
    # Clustered once for the whole dossier, then read per belief.
    trust = _trust_index(evidence_rows)
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
        "strategic_beliefs": [_belief(b, show, sentence, trust)
                              for b in beliefs],
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
    if economic_states:
        payload["economic_context"] = _economic_context(economic_states)
    if economic_theses:
        payload["economic_theses"] = [_economic_thesis(t)
                                      for t in economic_theses]
    payload["thesis_revisions"] = [_revision(r) for r in thesis_revisions]
    payload["thesis_history"] = _thesis_history(thesis_revisions,
                                                history_available)

    ids: Set[str] = set()
    _collect_ids(payload, ids)
    payload["evidence_ids"] = sorted(ids)
    # The dossier's own standing, over every row anything in it cites. Built
    # from the same index, so it cannot disagree with the per-belief blocks.
    whole = _trust_for(sorted(ids), trust)
    if whole:
        payload["evidence_trust"] = whole

    assert_sanitized(payload)
    return payload


def _economic_context(states: Sequence[Any]) -> dict:
    """The economy as it crosses: only what is measured, and the gap count.

    UNKNOWN CONDITIONS DO NOT CROSS AS ROWS but their number does. Shipping
    thirty rows of "we do not measure this" would fill the founder's dossier
    with absences; shipping none of them would let fifteen measured conditions
    read as a complete picture. The count is the honest middle.
    """
    known = [s for s in states if getattr(s, "known", False)]
    return {
        "conditions": [{"area": getattr(s, "area", ""),
                        "state_kind": getattr(s, "state_kind", ""),
                        "standing": getattr(s, "standing", ""),
                        "moved": getattr(s, "moved", ""),
                        "reason": getattr(s, "reason", "")} for s in known],
        "conditions_tracked": len(states),
        "conditions_known": len(known),
        "note": ("an unmeasured condition is absent from this list and "
                 "counted in the gap; it is never a condition that did not "
                 "move"),
    }


#: What the consumer is entitled to conclude about thesis movement.
#: FOUR states, never three, and never two. An absent history, a readable
#: history holding nothing about this subject, and a history that recorded no
#: movement are three different facts, and the CEO answer differs between all
#: of them.
#:
#: The fourth was added after a live audit: 22 of the 25 published company
#: dossiers carried `revisions: 0` under the status
#: HISTORY_AVAILABLE_NO_MOVEMENT, whose note read "nothing has changed this
#: view yet" — about companies for which no view had ever been formed. An
#: empty list was being read as a finding about a thesis that did not exist.
HISTORY_AVAILABLE_NO_MOVEMENT = "HISTORY_AVAILABLE_NO_MOVEMENT"
HISTORY_AVAILABLE_MOVED = "HISTORY_AVAILABLE_MOVED"
HISTORY_AVAILABLE_NO_THESIS = "HISTORY_AVAILABLE_NO_THESIS"
HISTORY_UNAVAILABLE = "HISTORY_UNAVAILABLE"
HISTORY_STATES = (HISTORY_AVAILABLE_NO_MOVEMENT, HISTORY_AVAILABLE_MOVED,
                  HISTORY_AVAILABLE_NO_THESIS, HISTORY_UNAVAILABLE)

#: The transition that opens a thesis rather than moving it. A log of nothing
#: but these is a thesis that has never changed its mind.
_OPENING_TRANSITION = "CREATED"


def _revision(revision: Any) -> dict:
    """One recorded transition, as ids rather than prose."""
    def field(name, default=""):
        if isinstance(revision, dict):
            return revision.get(name, default)
        return getattr(revision, name, default)

    return {
        "revision_id": str(field("revision_id") or ""),
        "thesis_id": str(field("thesis_id") or ""),
        "previous_revision": str(field("previous_revision") or ""),
        "transition": str(field("transition") or ""),
        "changed_at": str(field("changed_at") or "")[:10],
        "changed_fields": list(field("changed_fields", ()) or ()),
        "knowledge_effect_ids": list(field("knowledge_effect_ids", ()) or ()),
        "triggering_evidence": list(field("triggering_evidence", ()) or ()),
        "previous_standing": str(field("previous_standing") or ""),
        "new_standing": str(field("new_standing") or ""),
        "reason": str(field("reason") or "")[:400],
    }


def _thesis_history(revisions: Sequence[Any], available: bool) -> dict:
    """The status the consumer must read INSTEAD of counting the list.

    Stated rather than inferred, because "no revisions crossed" and "no
    revision exists" produce the same empty list and require opposite
    answers from a CEO surface.
    """
    if not available:
        return {
            "status": HISTORY_UNAVAILABLE, "revisions": 0, "moved": 0,
            "note": ("thesis revision history was not available to this "
                     "export; the current view crossed without the record of "
                     "how it got there, and no claim about what changed it "
                     "can be supported"),
        }
    rows = [_revision(r) for r in revisions]
    if not rows:
        # THE STORE WAS READABLE AND HAD NOTHING FOR THIS SUBJECT. Falling
        # through to NO_MOVEMENT here is what put "nothing has changed this
        # view yet" into 22 dossiers describing companies about which no view
        # had ever been formed. Zero revisions is not a stable view; it is the
        # absence of one, and the honest answer to "what changed your mind" is
        # that there is no mind to have changed yet.
        return {
            "status": HISTORY_AVAILABLE_NO_THESIS, "revisions": 0, "moved": 0,
            "note": ("revision history was readable and holds no revision for "
                     "this subject; no economic view has been opened, so "
                     "there is nothing for evidence to have changed"),
        }
    moved = [r for r in rows if r["transition"] != _OPENING_TRANSITION]
    if moved:
        return {
            "status": HISTORY_AVAILABLE_MOVED, "revisions": len(rows),
            "moved": len(moved),
            "note": (f"{len(moved)} of {len(rows)} recorded revision(s) "
                     f"changed the view rather than opening it"),
        }
    return {
        "status": HISTORY_AVAILABLE_NO_MOVEMENT, "revisions": len(rows),
        "moved": 0,
        "note": ("revision history is present and every recorded revision "
                 "opens a thesis rather than moving one; nothing has changed "
                 "this view yet"),
    }


def _field(obj: Any, name: str, default: Any = "") -> Any:
    """Read a field from an object OR a persisted row.

    Both shapes are real and both reach here: the cycle holds EconomicThesis
    objects, and `LearningStore.thesis_snapshots()` returns the rows it wrote.
    A getattr-only reader folded every snapshot into empty strings and then
    raised on the first attribute a dict does not have — the export failed
    closed for the whole company and reported `published: []`.
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _alternative(alt: Any) -> str:
    """A rival explanation, from either row shape."""
    if isinstance(alt, str):
        return alt
    return str(getattr(alt, "description", "") or "")


def _economic_thesis(thesis: Any) -> dict:
    """One thesis, with its rivals attached rather than summarised away."""
    from . import founder_v4_view as FV4

    mech = _field(thesis, "leading_mechanism", None)
    standing = str(_field(thesis, "standing") or "")
    # The derived implication needs the OBJECT's own logic and a persisted
    # row does not carry it. Asking for it from a dict raised; falling back
    # to the recorded field is the honest read, and an empty one is empty
    # rather than invented.
    if isinstance(thesis, dict):
        implication = str(thesis.get("decision_implication") or "")
    else:
        implication = FV4._implication(thesis)
    return {
        "thesis_id": str(_field(thesis, "thesis_id") or ""),
        "claim": str(_field(thesis, "claim") or ""),
        "standing": standing,
        "question": str(_field(thesis, "question") or ""),
        "horizon_days": int(_field(thesis, "horizon_days", 0) or 0),
        "macro_conditions": list(_field(thesis, "macro_conditions", ()) or ()),
        "exposures": list(_field(thesis, "exposures", ()) or ()),
        "mechanism": str(_field(mech, "description") or "") if mech else "",
        "falsifier": str(_field(mech, "falsifier") or "") if mech else "",
        # Alternatives are Mechanism OBJECTS on a live thesis and plain
        # strings on a persisted row. Reading `description` off a string
        # yields "" and stringifying a Mechanism ships its repr into the
        # dossier — both were shipped by one version of this line.
        "alternatives": [_alternative(a) for a in
                         (_field(thesis, "alternatives", ()) or ())],
        "unknowns": [str(u) for u in (_field(thesis, "unknowns", ()) or ())],
        "decision_implication": implication,
        "confidence_in_words": FV4._STANDING_WORDS.get(standing, ""),
        "evidence_ids": [str(e) for e in
                         (_field(thesis, "evidence_ids", ()) or ())],
        **_ceiling_fields(standing),
    }


def _ceiling_fields(standing: str) -> dict:
    """What the consumer may assert, decided here rather than re-derived there.

    An unrecognised standing is NOT mapped onto the nearest known one. It
    crosses as an empty ceiling, which the consumer treats as "assert
    nothing" — the failure of a producer to name its own standing is not
    evidence that the claim is weak, it is evidence that we do not know, and
    those license the same silence for different reasons.
    """
    from . import standing_wall as SW

    try:
        exported = SW.export(standing)
    except SW.StandingViolation:
        return {"ceiling": "", "forbidden_words": []}
    return {"ceiling": exported["ceiling"],
            "forbidden_words": exported["forbidden_words"]}

def _trust_index(evidence_rows: Sequence[Any]) -> Dict[str, Any]:
    """evidence_id -> the trust standing of the EVENT that row belongs to.

    Built once per export rather than per belief: event identity is a global
    clustering over the ledger, and clustering only the rows one belief cites
    would split an event whose other accounts were cited by a different
    belief — inventing independence out of the order the beliefs happen to be
    listed in.

    Rows the caller did not supply simply have no entry. That is why the
    absence of a trust block is a distinct state downstream from a block that
    says "one observation": the first means nobody looked.
    """
    from . import event_corroboration as EC
    from . import event_identity as EI
    from . import evidence_trust as ET

    rows = [r for r in (evidence_rows or ())]
    if not rows:
        return {}
    by_id = {_evidence_id(r): r for r in rows}
    index: Dict[str, Any] = {}
    for event in EI.group(rows):
        members = [by_id[eid] for eid in event.evidence_ids if eid in by_id]
        trust = ET.assess(EC.assess(event, members),
                          evidence_ids=event.evidence_ids)
        for eid in event.evidence_ids:
            index[eid] = trust
    return index


def _evidence_id(row) -> str:
    if isinstance(row, dict):
        return str(row.get("evidence_id") or "")
    return str(getattr(row, "evidence_id", "") or "")


def _trust_for(evidence_ids: Sequence[str], index: Dict[str, Any]
               ) -> Optional[dict]:
    """The claim-level standing for one object's cited rows.

    Deduplicated by EVENT, not by row: that is the entire point. Two rows of
    one occurrence contribute one event, and the claim is told so.
    """
    if not index:
        return None
    from . import evidence_trust as ET

    seen: Dict[str, Any] = {}
    for eid in evidence_ids or ():
        trust = index.get(str(eid))
        if trust is not None:
            seen.setdefault(trust.event_id, trust)
    if not seen:
        return None
    return ET.for_claim(list(seen.values()))


# --- projectors: each one names exactly what crosses ----------------------
def _belief(b, show=lambda s: s, sentence=lambda s: s, trust=None) -> dict:
    last = b.history[-1] if b.history else None
    evidence_ids = (list(b.supporting_evidence_ids)
                    + list(b.contradicting_evidence_ids))
    block = _trust_for(evidence_ids, trust or {})
    out = {"proposition": sentence(b.proposition), "subject": show(b.subject),
            "confidence": b.posterior_probability,
            "direction_of_last_change": last.direction if last else None,
            "last_updated": b.last_updated,
            # A belief declared this session has no update history yet. Its
            # basis is the reason it was opened, not an empty string — a
            # founder reading "confidence 0.62, basis: (nothing)" is being
            # shown a number with no argument behind it.
            "basis": last.basis if last else b.confidence_basis,
            "update_method": last.method if last else "DECLARED",
            "evidence_ids": evidence_ids,
            "limitations": list(b.limitations)}
    # Omitted rather than nulled when no rows were supplied: a consumer must
    # be able to tell "we normalized this and it is one observation" from
    # "nobody normalized this", and a key that is always present cannot.
    if block:
        out["evidence_trust"] = block
    return out


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
