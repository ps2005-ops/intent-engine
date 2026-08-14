"""`strategic_market_intel.v1` — the founder-side consumer, enforced again.

WHY THE ALLOWLIST IS DECLARED TWICE
------------------------------------
The market engine's `strategic_export` already validates this payload against
an allowlist on the way out. This module declares its own and validates again
on the way in, and that duplication is deliberate — it is the point, not an
oversight.

The producer lives in a package this one CANNOT IMPORT. `intent_engine.market`
does not exist on this branch, and must not: the moment founder code can
import trading code, the guarantee stops being structural and starts being a
promise about what people will remember not to do. So the two sides share a
schema, never a module.

That means the file on disk is UNTRUSTED INPUT. It may have been written by an
older producer, a newer one, a hand edit, or a copy from another environment.
A consumer that trusts the producer's validation is a consumer that renders
whatever the file happens to contain. This one re-derives the judgement:
a field absent from `ALLOWED` fails the whole read, at any depth, including
inside lists.

WHAT IS REFUSED IN TEXT, NOT ONLY IN STRUCTURE
-----------------------------------------------
Structure alone cannot catch a trading internal written into a permitted free
text field — `basis`, `rationale` and `note` all accept prose by design.
`_BANNED_SUBSTRINGS` scans every string that survives the structural pass, so
a win rate that arrives inside a sentence is refused exactly like one that
arrives inside a key.

ABSENCE IS A READING, NOT A BLANK
----------------------------------
There is no market engine writing to the founder deployment, so on most runs
this returns `available: False`. That is the honest state and it is rendered
as such: what would have been read, and what its absence costs the decision.
It is never an empty heading, never a zero, and never a silently skipped
section. `unavailable()` always carries a reason a founder can act on.

STRATEGIC CONTEXT NEVER PROMOTES A READING
-------------------------------------------
`changes_readiness` is False, permanently. A bounded or withheld company stays
bounded however rich the strategic dossier is. External context qualifies a
decision the company's own evidence drives; it cannot manufacture one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from intent_engine.external_intel import standing_ceiling as SC

SCHEMA_VERSION = "strategic_market_intel.v1"

# Posture and strategic interaction move on filings and announcements, not on
# closes, so the tolerance is wider than the price export's seven days. Past
# this the dossier describes a company that has since acted.
MAX_AGE_DAYS = 21

DISCLAIMER = (
    "Descriptive strategic context derived from public evidence. Not a "
    "recommendation, not a forecast, and not a statement about any "
    "investment position.")


class StrategicLeak(RuntimeError):
    """The file carried a field this side refuses to render."""


def company_key(subject: str) -> str:
    """Map a company name to its dossier filename.

    PART OF THE CONTRACT, not a local convenience. The producer derives the
    same key independently, and if the two ever disagree the symptom is
    silent: no file is found, the section never appears, and nothing reports
    an error because "no dossier published" is a legitimate state. A test
    pins the exact outputs so the two implementations can be checked against
    one table rather than against each other.
    """
    return re.sub(r"[^a-z0-9]+", "-", (subject or "").strip().lower()
                  ).strip("-")


# --- the allowlist, re-declared on purpose (see module docstring) ----------
# WHAT THE evidence_ids ARE WORTH, decided by the side that owns the judgement.
#
# `evidence_ids` is a list of ROWS, and a consumer holding only that list can
# do exactly one thing with it: count it. Counting is the defect — three sites
# carrying one press release put three ids in that list, and every reader
# downstream, human or machine, sees three.
#
# This block is the same evidence normalized: how many things ACTUALLY
# happened, how much independent support may honestly be claimed, the weight a
# conclusion may take from it, and the sentence to say about it. This side
# consumes it and must never re-derive it — re-deriving from source counts is
# the arithmetic that is wrong.
_TRUST = {
    "contract": ..., "standing": ..., "raw_accounts": ...,
    "distinct_events": ..., "independent_support": ..., "weight": ...,
    "sentence": ...,
    # The grouping itself. Without it this side would know that three rows are
    # one occurrence but not WHICH three, and so could not build a graph that
    # walks a rendered sentence back to the rows under it. Normalization
    # groups rather than deletes, and this is the part that proves it.
    "events": [{"event_id": ..., "standing": ..., "accounts": ...,
                "weight": ..., "evidence_ids": ...}],
}

_BELIEF = {
    "proposition": ..., "subject": ..., "confidence": ...,
    "direction_of_last_change": ..., "last_updated": ..., "basis": ...,
    "update_method": ..., "evidence_ids": ..., "limitations": ...,
    "evidence_trust": _TRUST,
}

_HIDDEN = {
    "subject": ..., "leading_state": ..., "leading_probability": ...,
    "alternatives": [{"state": ..., "probability": ...}],
    "moved": [{"state": ..., "from": ..., "to": ...}],
    "as_of": ..., "evidence_ids": ..., "certainty_note": ...,
}

_INTERACTION = {
    "focal_actor": ..., "responding_actor": ..., "initial_action": ...,
    "response": ..., "at": ..., "response_lag_days": ...,
    "payoff_change": ..., "payoff_note": ..., "inferred_objective": ...,
    "alternative_explanations": ..., "evidence_ids": ..., "status": ...,
}

ALLOWED: Dict[str, Any] = {
    "export_version": ..., "generated_at": ..., "company_id": ...,
    # The producer's human-readable name for the same company. Same class as
    # `company_id` and equally safe: it is the subject of the analysis, not a
    # market internal.
    #
    # ITS ABSENCE HAD BROKEN THE ENTIRE BRIDGE. This side fails closed on any
    # unknown field, which is the correct posture and is why nothing leaked --
    # but the producer has been emitting `company_display_name` on every
    # dossier, so every one of the 22 published dossiers was refused, silently,
    # for as long as both sides have existed. The market engine reported
    # "22 dossiers published" and the founder rendered none of them.
    #
    # Nobody could see it: the refusal is caught, logged at warning level and
    # degrades to no strategic section, which is also the normal appearance of
    # a company the market has simply never looked at. It took consumption
    # telemetry to tell those two apart, and it found this on its first run
    # against real dossiers.
    "company_display_name": ...,
    # The producer's alias set for the same company, e.g.
    # ["Caterpillar", "Caterpillar Inc.", "caterpillar"]. Same class again,
    # and useful on this side for the identity check rather than despite it.
    # Surfaced only after `company_display_name` was allowed, because
    # validation fails on the FIRST unknown field -- so the mismatch had to be
    # measured, fixed and re-measured rather than diagnosed once.
    "subject_names": ...,
    "as_of": ...,
    "freshness": {"status": ..., "as_of": ..., "age_days": ...,
                  "stale": ..., "note": ...},
    "strategic_beliefs": [_BELIEF],
    "hidden_states": [_HIDDEN],
    "interactions": [_INTERACTION],
    "market_structure": {
        "market_definition": ..., "strategic_job": ..., "buyer_groups": ...,
        "concentration": ..., "concentration_note": ...,
        "facts": [{"dimension": ..., "finding": ..., "status": ...,
                   "evidence_ids": ..., "limitation": ...}],
        "unassessed_dimensions": ...,
    },
    "pricing_actions": [{
        "kind": ..., "applies": ..., "applies_because": ...,
        "mechanism": ..., "findings": ..., "risks": ...,
        "evidence_ids": ..., "limitations": ...,
    }],
    "causal_pathways": [{
        "name": ..., "narrative": ..., "nodes": ..., "status": ...,
        "total_lag_days": ..., "weakest_link": ...,
        "edges": [{"cause": ..., "effect": ..., "direction": ...,
                   "mechanism": ..., "lag_days": ..., "status": ...,
                   "competing_explanations": ..., "evidence_ids": ...}],
    }],
    "expectation_mismatches": [{
        "subject": ..., "expected_event": ..., "expected_direction": ...,
        "observed_direction": ..., "outcome": ..., "rationale": ...,
        "evaluated_at": ..., "preregistered_at": ..., "falsifier": ...,
        "evidence_ids": ...,
    }],
    "competitor_reactions": [{
        "responder": ..., "response": ..., "confidence": ...,
        "payoff_effect": ..., "rationale": ..., "precedents": ...,
        "second_order": ..., "evidence_ids": ..., "is_prediction": ...,
    }],
    "information_priorities": [{
        "subject": ..., "candidate_observation": ...,
        "observation_kind": ..., "expected_date": ..., "priority": ...,
        "falsifies": ..., "limitation": ...,
    }],
    # V4. The economy, arriving rather than being rebuilt on this side.
    #
    # DECLARED TWICE ON PURPOSE, like every other block here: this package
    # cannot import the market package, so the two allowlists are independent
    # and a field the producer adds without adding it here is refused. That is
    # the safe direction and it is also how the whole bridge stayed silently
    # closed for 22 dossiers, so a new block on one side is a change on both
    # sides or it is not a change at all.
    "economic_context": {
        "conditions": [{"area": ..., "state_kind": ..., "standing": ...,
                        "moved": ..., "reason": ...}],
        "conditions_tracked": ..., "conditions_known": ..., "note": ...,
    },
    "economic_theses": [{
        "thesis_id": ..., "claim": ..., "standing": ..., "question": ...,
        "horizon_days": ..., "macro_conditions": ..., "exposures": ...,
        "mechanism": ..., "falsifier": ...,
        # A thesis that arrived without its rivals would be rendered as the
        # only explanation, so this field is read on the way in and the
        # consumer refuses to treat an assertable thesis that lacks it.
        "alternatives": ..., "unknowns": ...,
        "decision_implication": ..., "confidence_in_words": ...,
        "evidence_ids": ...,
        # The producer's adjudicated ceiling and the words it forbids. Read
        # rather than re-derived from the standing, because a second
        # derivation is a second copy of the rule and the two drift. This
        # side may narrow it — and does, below, whenever it downgrades a
        # thesis after the ceiling was already computed.
        "ceiling": ..., "forbidden_words": ...,
    }],
    # THESIS HISTORY. Without it this consumer could not tell a thesis that
    # has never moved from a thesis whose history was not transported, and
    # "what changed your mind" needs opposite answers for the two. The STATUS
    # is read rather than inferred from the list's length: an empty list is
    # produced by both.
    "thesis_history": {"status": ..., "revisions": ..., "moved": ...,
                       "note": ...},
    "thesis_revisions": [{
        "revision_id": ..., "thesis_id": ..., "previous_revision": ...,
        "transition": ..., "changed_at": ..., "changed_fields": ...,
        "knowledge_effect_ids": ..., "triggering_evidence": ...,
        "previous_standing": ..., "new_standing": ..., "reason": ...,
    }],
    "limitations": ..., "evidence_ids": ..., "evidence_trust": _TRUST,
    "disclaimer": ...,
    "interpretation_allowed": ..., "interpretation_forbidden": ...,
}

#: Standings the founder side will render as a conclusion. Mirrors the
#: producer's ASSERTABLE set and is stated here because this package cannot
#: import it; if the two ever disagree, the stricter reading is this one.
_ASSERTABLE_STANDINGS = frozenset({"SUPPORTED", "TESTED"})

# Independently maintained. The producer has its own list; if one side gains a
# term the other has not, the stricter side wins, which is the safe direction.
_BANNED_SUBSTRINGS = (
    "win rate", "win_rate", "sharpe", "alpha", "profit factor",
    "profit_factor", "expectancy", "net return", "net_return",
    "paper book", "paper_book", "shadow portfolio", "shadow_portfolio",
    "position size", "position_size", "signal fired", "signal_fired",
    "strategy key", "strategy_key", "buy signal", "sell signal",
    "long position", "short position", "price target", "target price",
)


def _validate(node: Any, spec: Any, path: str) -> None:
    if spec is ...:
        if isinstance(node, dict):
            raise StrategicLeak(
                f"{path or 'root'}: an object arrived where the schema "
                f"declares a leaf; an undeclared structure is refused")
        if isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                if isinstance(item, (dict, list, tuple)):
                    raise StrategicLeak(
                        f"{path}[{i}]: nested structure inside a leaf list")
        return
    if isinstance(spec, list):
        if not isinstance(node, (list, tuple)):
            raise StrategicLeak(f"{path}: expected a list")
        inner = spec[0] if spec else ...
        for i, item in enumerate(node):
            _validate(item, inner, f"{path}[{i}]")
        return
    if isinstance(spec, dict):
        if not isinstance(node, dict):
            raise StrategicLeak(f"{path}: expected an object")
        for key, value in node.items():
            if key not in spec:
                raise StrategicLeak(
                    f"unknown field {key!r} at {path or 'root'}: this side "
                    f"fails closed rather than rendering a field it has "
                    f"never seen")
            _validate(value, spec[key], f"{path}.{key}" if path else str(key))
        return
    raise StrategicLeak(f"{path}: malformed schema")  # pragma: no cover


#: MATCHED ON WORD BOUNDARIES, NOT AS RAW SUBSTRINGS. See the twin comment in
#: `demo_dossier.contracts`: a plain substring scan refused every text naming
#: "Alphabet Inc." because "alpha" is inside it, and the refusal was total.
#: The wall is unchanged for trading language — "generated alpha of 3%" still
#: matches, because there the term stands as its own word.
_BANNED_PATTERN = re.compile(
    r"(?<![0-9a-z])(?:%s)(?![0-9a-z])"
    % "|".join(re.escape(term) for term in _BANNED_SUBSTRINGS), re.I)


def _scan_text(node: Any, path: str = "") -> None:
    if isinstance(node, str):
        found = _BANNED_PATTERN.search(node)
        if found:
            raise StrategicLeak(
                f"{path}: text contains {found.group(0).lower()!r}, a trading "
                f"internal that may not reach a founder surface")
    elif isinstance(node, dict):
        for key, value in node.items():
            _scan_text(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _scan_text(item, f"{path}[{i}]")


def validate(payload: dict) -> None:
    """Both gates, on the way in. Raises `StrategicLeak` on any refusal."""
    _validate(payload, ALLOWED, "")
    _scan_text(payload)


# --- belief maturity --------------------------------------------------------
#
# WHY A FOUNDER MAY NOT BE SHOWN "62% CONFIDENCE"
# -----------------------------------------------
# The producer is explicit that `update_method` is "never decorative": only
# EMPIRICAL_BAYES derives likelihoods from measured base rates. A
# CALIBRATED_HEURISTIC is "a bounded step scaled by evidence quality, honest
# about being a heuristic", and DECLARED means the belief was OPENED by its
# evidence and never revised since.
#
# 0.618 from an opening heuristic and 0.618 from a posterior that survived
# three contradictions are different claims about the world, and printing both
# as "62% confidence" makes the weaker one unfalsifiable-sounding. A reader who
# sees two decimal places reasonably infers something was measured.
#
# So maturity is derived HERE, once, from the fields the producer actually
# publishes, and every founder surface reads it from this function. A surface
# computing its own would be the mechanism by which the narrative and the
# dashboard come to disagree about the same belief.
NEWLY_DECLARED = "NEWLY_DECLARED"
REVISED = "REVISED"
TESTED = "TESTED"
REPEATEDLY_SUPPORTED = "REPEATEDLY_SUPPORTED"
UNDER_REVIEW = "UNDER_REVIEW"
WEAKENED = "WEAKENED"
RETIRED = "RETIRED"

MATURITIES = frozenset({NEWLY_DECLARED, REVISED, TESTED, REPEATEDLY_SUPPORTED,
                        UNDER_REVIEW, WEAKENED, RETIRED})

#: The only update method whose number is a measurement rather than a step
#: size. Deliberately a whitelist: a method added upstream must be classified
#: here before its figure can reach a founder as a percentage.
NUMERIC_METHODS = frozenset({"EMPIRICAL_BAYES"})

#: Words for a heuristic reading. The bands are wide on purpose -- narrow ones
#: would reintroduce the precision the words exist to avoid.
_PLAUSIBILITY = ((0.75, "well supported by the current evidence"),
                 (0.60, "moderately plausible"),
                 (0.45, "roughly balanced against the alternatives"),
                 (0.0, "weakly supported"))


def belief_maturity(belief: dict) -> str:
    """How much this belief has been through, from what the producer states.

    Conservative by construction: anything unrecognised reads as newly
    declared, because treating an unknown method as tested is the failure that
    matters. The reverse understates a belief and costs nothing.
    """
    method = str(belief.get("update_method") or "").upper()
    direction = belief.get("direction_of_last_change")
    if belief.get("retired"):
        return RETIRED
    if method == "DECAY":
        # Absence moved it toward uncertainty; no new evidence arrived.
        return UNDER_REVIEW
    if not direction:
        return TESTED if method in NUMERIC_METHODS else NEWLY_DECLARED
    lowered = str(direction).lower()
    if lowered in ("down", "weaker", "negative", "-"):
        return WEAKENED
    if method in NUMERIC_METHODS:
        return REPEATEDLY_SUPPORTED
    return REVISED


def confidence_is_numeric(belief: dict) -> bool:
    """Whether this belief's figure may be printed as a percentage."""
    return str(belief.get("update_method") or "").upper() in NUMERIC_METHODS


def confidence_language(belief: dict) -> str:
    """A phrase a founder can act on, matched to what the number can bear.

    Not a reflexive removal of every number: an EMPIRICAL_BAYES posterior IS a
    measurement and says so. What is refused is a heuristic step presented in
    the same grammar as a measured one.
    """
    try:
        value = float(belief.get("confidence") or 0)
    except (TypeError, ValueError):
        value = 0.0
    if confidence_is_numeric(belief):
        return f"held at {value:.0%} confidence, from measured base rates"
    for floor, words in _PLAUSIBILITY:
        if value >= floor:
            return f"the current evidence makes this {words}"
    return "the current evidence is not strong enough to lean on"


#: What each maturity means, in a founder's terms rather than the engine's.
MATURITY_WORDS = {
    NEWLY_DECLARED: ("a newly formed reading, not a tested conclusion"),
    REVISED: ("revised since it was opened, as later evidence arrived"),
    TESTED: ("tested against measured base rates rather than assumed"),
    REPEATEDLY_SUPPORTED: ("supported again by evidence arriving after it "
                           "was opened"),
    UNDER_REVIEW: ("drifting toward uncertainty because no new evidence has "
                   "arrived"),
    WEAKENED: ("weaker than when it was opened, after contrary evidence"),
    RETIRED: ("withdrawn, and kept only as a record"),
}


def maturity_sentence(belief: dict) -> str:
    return MATURITY_WORDS.get(belief_maturity(belief),
                              MATURITY_WORDS[NEWLY_DECLARED])


@dataclass(frozen=True)
class StrategicIntel:
    """The founder-facing view of one company's strategic dossier."""
    available: bool
    reason: str = ""
    company_id: str = ""
    #: The producer's own display name for the subject, when it stated one.
    #: Preferred over `company_id` wherever a founder can see it: `company_id`
    #: is a slug, and "microsoft is seeing demand strengthen" is a sentence
    #: about a key, not about a company.
    display_name: str = ""
    #: Every name the producer says this dossier is about. Used to find the
    #: dossier, never rendered.
    subject_names: Tuple[str, ...] = ()
    as_of: str = ""
    age_days: Optional[int] = None
    stale: bool = False
    beliefs: Tuple[dict, ...] = ()
    postures: Tuple[dict, ...] = ()
    interactions: Tuple[dict, ...] = ()
    mismatches: Tuple[dict, ...] = ()
    reactions: Tuple[dict, ...] = ()
    pathways: Tuple[dict, ...] = ()
    priorities: Tuple[dict, ...] = ()
    market_structure: Optional[dict] = None
    #: V4. What the market engine measured about the economy, and what it
    #: concluded from it. None means the producer sent nothing — which is a
    #: different state from "it looked and the economy is quiet", and the two
    #: are never collapsed on the page.
    economic_context: Optional[dict] = None
    economic_theses: Tuple[dict, ...] = ()
    #: Recorded transitions, and the STATED status of whether history was
    #: transported at all. `thesis_history` is None when the producer sent
    #: no status — which this consumer treats as HISTORY_UNAVAILABLE rather
    #: than as "nothing moved", because an older producer that cannot send
    #: history must not be read as one reporting a quiet thesis.
    thesis_revisions: Tuple[dict, ...] = ()
    thesis_history: Optional[dict] = None
    limitations: Tuple[str, ...] = ()
    #: The dossier's own normalized standing, or None when the producer did
    #: not normalize. Those are different states and are kept different: a
    #: missing block means nobody looked, not "one observation".
    evidence_trust: Optional[dict] = None
    disclaimer: str = DISCLAIMER

    # External context never promotes a reading. Permanent, not a default.
    changes_readiness: bool = False

    @property
    def has_material(self) -> bool:
        """Whether anything here is worth a founder's attention.

        A dossier that validated cleanly and contains nothing is still an
        absence, and must be reported as one rather than as a section.
        """
        return bool(self.beliefs or self.postures or self.interactions
                    or self.mismatches or self.reactions or self.pathways
                    or self.priorities or self.market_structure)

    @property
    def subject(self) -> str:
        """The name to put in front of a founder. Never the slug if avoidable."""
        return self.display_name or self.company_id

    def as_dict(self) -> dict:
        return {"available": self.available, "reason": self.reason,
                "company_id": self.company_id,
                "display_name": self.display_name,
                "subject_names": list(self.subject_names),
                "as_of": self.as_of,
                "age_days": self.age_days, "stale": self.stale,
                "beliefs": list(self.beliefs), "postures": list(self.postures),
                "interactions": list(self.interactions),
                "mismatches": list(self.mismatches),
                "reactions": list(self.reactions),
                "pathways": list(self.pathways),
                "priorities": list(self.priorities),
                "market_structure": self.market_structure,
                "limitations": list(self.limitations),
                "evidence_trust": self.evidence_trust,
                "disclaimer": self.disclaimer,
                "has_material": self.has_material}


def unavailable(reason: str, company_id: str = "") -> StrategicIntel:
    """Every absence carries its reason. There is no bare `False` here."""
    return StrategicIntel(available=False, reason=reason,
                          company_id=company_id)


def _age_days(as_of: str, today: str) -> Optional[int]:
    try:
        return (date.fromisoformat(today[:10])
                - date.fromisoformat(as_of[:10])).days
    except (ValueError, TypeError):
        return None


def _economic_theses(payload: dict) -> Tuple[dict, ...]:
    """Read the economic theses, downgrading any that arrived without rivals.

    A thesis the producer marked SUPPORTED or TESTED but sent with an empty
    `alternatives` list would be rendered here as the only explanation there
    is. This side cannot check whether the producer's alternatives were real,
    but it can refuse to present a conclusion whose rivals are missing — so
    the standing is dropped to PROPOSED and the reason travels with it. Losing
    confidence is the safe direction; the page says less than the producer
    meant, which is exactly the tolerance the whole bridge is built on.
    """
    out = []
    for row in (payload.get("economic_theses") or ()):
        if not isinstance(row, dict):
            continue
        row = dict(row)
        standing = str(row.get("standing") or "")
        if standing in _ASSERTABLE_STANDINGS and not row.get("alternatives"):
            row["standing"] = "PROPOSED"
            row["downgraded_because"] = (
                f"arrived as {standing} with no alternative explanation; a "
                "leading explanation with no rivals renders as the only one")
        # THE CEILING IS RE-DECIDED AFTER THE DOWNGRADE, never before. It was
        # computed by the producer against the standing that was sent; a row
        # this side has just weakened would otherwise carry a ceiling
        # outranking the standing it exists to cap, and the downgrade would
        # change the word on the page and nothing about what may be said.
        row["ceiling"] = SC.ceiling_for(row)
        row["forbidden_words"] = list(
            SC.banned_words(row["ceiling"])
            + tuple(str(w) for w in (row.get("forbidden_words") or ())))
        out.append(row)
    return tuple(out)


def consume(payload: dict, *, expected_company: str = "",
            today: str = "") -> StrategicIntel:
    """Read one dossier, refusing anything this side cannot vouch for."""
    if not isinstance(payload, dict):
        return unavailable("The strategic dossier was not a readable object.")

    version = payload.get("export_version")
    if version != SCHEMA_VERSION:
        # A newer producer may be entirely correct and still carry fields this
        # renderer has never seen. Refusing is the safe reading.
        return unavailable(
            f"The strategic dossier is version {version!r}; this product "
            f"reads {SCHEMA_VERSION}. It was not rendered.")

    company = str(payload.get("company_id") or "")
    if expected_company and company and company != expected_company:
        return unavailable(
            f"The strategic dossier is for {company!r}, not the company in "
            f"this analysis. It was not rendered.", company_id=company)

    try:
        validate(payload)
    except StrategicLeak as exc:
        return unavailable(
            f"The strategic dossier was refused by the founder-side "
            f"contract: {exc}", company_id=company)

    as_of = str(payload.get("as_of") or "")
    today = today or date.today().isoformat()
    age = _age_days(as_of, today)
    stale = age is not None and age > MAX_AGE_DAYS
    if stale:
        return unavailable(
            f"The strategic dossier is {age} days old (limit "
            f"{MAX_AGE_DAYS}). A stale strategic reading is "
            f"indistinguishable from a current one on the page, so it was "
            f"not rendered.", company_id=company)

    def _rows(key: str) -> Tuple[dict, ...]:
        return tuple(r for r in (payload.get(key) or ())
                     if isinstance(r, dict))

    return StrategicIntel(
        available=True, company_id=company,
        display_name=str(payload.get("company_display_name") or ""),
        subject_names=tuple(str(x) for x in
                            (payload.get("subject_names") or ())),
        as_of=as_of, age_days=age,
        stale=False,
        beliefs=_rows("strategic_beliefs"),
        postures=_rows("hidden_states"),
        interactions=_rows("interactions"),
        mismatches=_rows("expectation_mismatches"),
        reactions=_rows("competitor_reactions"),
        pathways=_rows("causal_pathways"),
        priorities=_rows("information_priorities"),
        market_structure=(payload.get("market_structure")
                          if isinstance(payload.get("market_structure"), dict)
                          else None),
        economic_context=(payload.get("economic_context")
                          if isinstance(payload.get("economic_context"), dict)
                          else None),
        economic_theses=_economic_theses(payload),
        thesis_revisions=tuple(payload.get("thesis_revisions") or ()),
        thesis_history=payload.get("thesis_history"),
        limitations=tuple(str(x) for x in (payload.get("limitations") or ())),
        evidence_trust=(payload.get("evidence_trust")
                        if isinstance(payload.get("evidence_trust"), dict)
                        else None),
        disclaimer=str(payload.get("disclaimer") or DISCLAIMER))


#: A universe of a few dozen companies publishes a few dozen dossiers. The cap
#: exists so a directory that has grown unexpectedly degrades into a miss
#: rather than into a slow page.
MAX_DOSSIERS_SCANNED = 512

NO_DOSSIER = (
    "No strategic reading has been published for this company. Strategic "
    "posture, competitor reactions and preregistered expectations are not "
    "part of this analysis.")


def _read(path) -> Optional[dict]:
    """One dossier as a plain object, or None if it cannot be read at all."""
    import json

    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _declared_keys(payload: dict) -> set:
    """Every key this dossier claims to answer to, normalised.

    `company_id` is included because a producer that has not yet learned to
    state `subject_names` still answers to its own key, and this side must
    keep reading the dossiers that already exist.
    """
    names = [payload.get("company_id") or "",
             payload.get("company_display_name") or ""]
    names += [str(n) for n in (payload.get("subject_names") or ())
              if isinstance(n, (str, int, float))]
    return {k for k in (company_key(str(n)) for n in names) if k}


def resolve(directory, *, names: Sequence[str],
            today: str = "") -> StrategicIntel:
    """Find the dossier for a company known by any of `names`.

    WHY THIS EXISTS AND `load` WAS NOT ENOUGH
    -----------------------------------------
    `load` takes a path, and the caller built that path from `company_key` of
    the one name it happened to hold. Measured against the first real dossiers
    the market engine ever wrote, that join NEVER MATCHED: the producer files
    under its internal universe id (`microsoft.json`) and this side asks for
    the name a founder typed (`microsoft-corporation.json`). Both sides ran
    exactly as designed, both were tested, and the bridge carried nothing —
    silently, because "no dossier published" is a legitimate answer and so
    nothing raised.

    Two names for the same company is the normal case, not the edge case, so
    the fix is not a better convention. It is to stop inferring identity from
    a filename: a dossier is accepted when it NAMES the company it is about,
    and the filename is only a hint about where to look first.

    AMBIGUITY IS REFUSED, NOT RESOLVED
    ----------------------------------
    If two dossiers claim the same company, one of them is wrong and picking
    either would attribute half the evidence to the wrong subject — the same
    failure the market side already paid for when a mis-resolved registrant
    produced perfectly-classified events about the wrong company. Both are
    refused, with the reason.

    A FILE AT THE EXPECTED NAME WINS, AND WINS BEFORE THE SCAN
    ----------------------------------------------------------
    The scan exists to find a dossier filed under a name we did not guess; it
    is not a second opinion about one we did. So a file sitting at exactly
    `company_key(name).json` is taken, and a rival claim elsewhere in the
    directory does not make it ambiguous — the filename is the strongest
    identity assertion available, not the weakest. The consequence worth
    knowing is that ambiguity is detected among CLAIMS, not against the
    canonical file: `microsoft-corporation.json` is read even if some other
    dossier also lists "Microsoft Corporation" among its subjects.
    """
    import pathlib

    root = pathlib.Path(directory)
    keys, seen = [], set()
    for name in names:
        key = company_key(str(name or ""))
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    if not keys:
        return unavailable(
            "This analysis has no company name to look a strategic dossier "
            "up by, so none was read.")

    # Fast path: the producer's filename already agrees with a name we hold.
    for key in keys:
        candidate = root / f"{key}.json"
        if candidate.exists():
            return load(candidate, expected_company=key, today=today)

    if not root.is_dir():
        return unavailable(NO_DOSSIER, company_id=keys[0])

    wanted = set(keys)
    matches: List[Tuple[Any, dict]] = []
    renamed = 0
    for path in sorted(root.glob("*.json"))[:MAX_DOSSIERS_SCANNED]:
        payload = _read(path)
        if payload is None:
            continue
        # The producer writes `<company_id>.json`. A file whose declared id
        # disagrees with its own name has been moved or hand-edited, and a
        # dossier that two lookups would answer differently is not one this
        # side will render.
        if company_key(str(payload.get("company_id") or "")) != path.stem:
            renamed += 1
            continue
        if _declared_keys(payload) & wanted:
            matches.append((path, payload))

    if len(matches) > 1:
        return unavailable(
            f"{len(matches)} strategic dossiers claim to be about this "
            f"company ({', '.join(sorted(p.stem for p, _ in matches))}). "
            f"That is an upstream identity error, and choosing one of them "
            f"would attach the wrong company's evidence to this analysis, so "
            f"none was rendered.", company_id=keys[0])
    if not matches:
        extra = (f" {renamed} dossier(s) were skipped because their declared "
                 f"company did not match their filename." if renamed else "")
        return unavailable(NO_DOSSIER + extra, company_id=keys[0])

    path, payload = matches[0]
    return consume(payload, expected_company=str(payload.get("company_id")
                                                 or ""), today=today)


def load(path, *, expected_company: str = "",
         today: str = "") -> StrategicIntel:
    """Read a dossier from disk. A missing file is a reason, not an error."""
    import json
    import pathlib

    p = pathlib.Path(path)
    if not p.exists():
        return unavailable(NO_DOSSIER, company_id=expected_company)
    try:
        payload = json.loads(p.read_text())
    except (OSError, ValueError) as exc:
        kind = exc.__class__.__name__
        return unavailable(
            f"The strategic dossier could not be read ({kind}). It was not "
            f"rendered.", company_id=expected_company)
    return consume(payload, expected_company=expected_company, today=today)
