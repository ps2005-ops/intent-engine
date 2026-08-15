"""The two snapshot contracts, read as untrusted bytes from either side.

TRANSPORT NEUTRALITY IS THE POINT, §3
--------------------------------------
`read_market_snapshot` and `read_founder_snapshot` take a **dict**. Nothing in
this module knows where the dict came from. A file, an HTTP body, an object
store, a test fixture and a hand-written literal all reach the same code, and
the join downstream is identical for all five. `market.dossier_transport`
already ships these bytes over HTTP, so filesystem-only was never true; this
module makes it un-assumable.

THE UNKNOWN-FIELD POLICY IS TIERED, AND THAT IS THE LESSON, §11
----------------------------------------------------------------
`external_intel.strategic_contract` fails closed on every unknown field at any
depth. For a payload rendered verbatim to a founder that is right. It is also
exactly what kept the bridge silently shut for 22 dossiers: the producer began
emitting `company_display_name`, the consumer had never heard of it, and every
dossier was refused. Nobody saw it, because a refused dossier and a company
nobody analysed look the same.

So this contract splits the judgement rather than repeating it:

* an unknown field whose NAME implies authority, tenancy, population or
  privacy is refused outright — fail closed, because the cost of guessing
  wrong is a leak;
* any other unknown field is IGNORED and RECORDED in `unknown_fields`.

The recording is what makes fail-open safe. A producer that has moved ahead of
a consumer shows up as a non-zero counter in telemetry (§28) instead of a
warning log nobody reads. Silence was the defect, not strictness.

WHAT MARKET MAY NEVER SAY
--------------------------
`_MARKET_FORBIDDEN` is not an allowlist miss, it is a refusal. A market
snapshot carrying `tenant_id` is not an unrecognised producer, it is a payload
claiming authority over private founder data on the strength of public
evidence. It is refused before anything else is read (§10, §30).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Mapping, Optional, Tuple

from intent_engine.demo_dossier import vocabulary as V

MARKET_CONTRACT = "market_demo_snapshot.v1"
FOUNDER_CONTRACT = "founder_demo_snapshot.v1"

#: The major version this side reads. A payload from a different major is
#: INCOMPATIBLE and is not partially salvaged: a reader that guesses at a
#: shape it has never seen is the thing this whole seam exists to prevent.
READS_MAJOR = 1

_VERSION_RE = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<major>\d+)$")


class SnapshotRefused(ValueError):
    """The payload carried something this side will not read."""


# --- a ref block is never a bare list -------------------------------------
# WHY EVERY REFERENCE BLOCK CARRIES ITS OWN STATE
#
# `causal_result_refs: []` cannot distinguish "causal analysis ran and found
# nothing" from "causal analysis was never attempted" from "the producer is
# too old to send this block". Those are three different sentences on a page,
# and only one of them is "no effect". Collapsing them is §21's entire
# subject, so the distinction is enforced in the CONTRACT rather than
# reconstructed by the assembler — a bare list cannot be sent at all.
REF_AVAILABLE = "AVAILABLE"
REF_UNAVAILABLE = "UNAVAILABLE"
REF_NOT_ATTEMPTED = "NOT_ATTEMPTED"
REF_REFUSED = "REFUSED"
REF_STATES = (REF_AVAILABLE, REF_UNAVAILABLE, REF_NOT_ATTEMPTED, REF_REFUSED)

#: None of these is a measured zero, and a surface must assert against the set
#: rather than testing for an empty `ids`.
REF_NOT_A_ZERO = frozenset({REF_UNAVAILABLE, REF_NOT_ATTEMPTED, REF_REFUSED})

_REF_BLOCK = {"state": ..., "ids": ..., "count": ..., "note": ...}


@dataclass(frozen=True)
class RefBlock:
    """A bounded reference to canonical objects that live in another store.

    Holds IDS, never bodies. The dossier is a materialized view over two
    systems of record; copying the records in would make it a third system of
    record, which the ADR rejects as OPTION C.
    """
    state: str = REF_UNAVAILABLE
    ids: Tuple[str, ...] = ()
    #: The producer's own count. Read rather than derived from `len(ids)`,
    #: because `ids` is bounded (see `MAX_REFS`) and a truncated list would
    #: otherwise silently restate itself as a smaller population.
    count: int = 0
    note: str = ""
    #: The producer's own outcome histogram, when it publishes one, e.g.
    #: `{"PANEL_UNAVAILABLE": 5}`. TYPED, because the alternative is parsing
    #: the note: every live causal block is a refusal, and a surface that
    #: cannot tell a refusal from an estimate without reading prose will
    #: eventually render one as the other.
    states: Mapping = field(default_factory=dict)
    #: Rows the producer tracked and could not identify -- a hidden state
    #: whose posterior is uniform. Neither a finding nor an absence.
    unidentified: int = 0

    @property
    def available(self) -> bool:
        return self.state == REF_AVAILABLE

    @property
    def is_zero(self) -> bool:
        """True only for a block that ran and found nothing.

        The name is deliberate: `not block.ids` is the bug this replaces.
        """
        return self.state == REF_AVAILABLE and self.count == 0

    @property
    def is_refusal(self) -> bool:
        """The producer ran, produced rows, and every one declines to answer.

        This is NOT `is_zero`: a refusal has rows, each naming the
        prerequisite it lacked. The two need opposite treatment downstream --
        a zero ends an enquiry, a refusal starts one (what would resolve it,
        what is that worth).
        """
        return bool(self.states) and all(
            V.is_causal_refusal(s) for s in self.states)

    def as_dict(self) -> dict:
        out = {"state": self.state, "ids": list(self.ids),
               "count": self.count, "note": self.note}
        if self.states:
            out["states"] = dict(self.states)
        if self.unidentified:
            out["unidentified"] = self.unidentified
        return out


#: A reference list is bounded. A dossier that carried every evidence id for
#: 100 companies would be a copy of both stores, and the `count` field exists
#: so bounding does not lie about size.
MAX_REFS = 64


def _ref_block(node: Any) -> RefBlock:
    if not isinstance(node, Mapping):
        return RefBlock(state=REF_UNAVAILABLE,
                        note="the producer sent no block here")
    state = str(node.get("state") or REF_UNAVAILABLE)
    if state not in REF_STATES:
        return RefBlock(state=REF_REFUSED,
                        note=f"unreadable block state {state!r}")
    ids = tuple(str(i) for i in (node.get("ids") or ())
                if not isinstance(i, (dict, list, tuple)))[:MAX_REFS]
    raw_count = node.get("count")
    count = raw_count if isinstance(raw_count, int) and raw_count >= 0 \
        else len(ids)
    raw_states = node.get("states")
    states = ({str(k): int(v) for k, v in raw_states.items()
               if isinstance(v, int)}
              if isinstance(raw_states, Mapping) else {})
    raw_unidentified = node.get("unidentified")
    return RefBlock(state=state, ids=ids, count=count,
                    note=str(node.get("note") or ""), states=states,
                    unidentified=(raw_unidentified
                                  if isinstance(raw_unidentified, int)
                                  and raw_unidentified >= 0 else 0))


def _empty_ref(note: str) -> RefBlock:
    return RefBlock(state=REF_UNAVAILABLE, note=note)


# --- the allowlists --------------------------------------------------------
_SUMMARY = {"state": ..., "note": ..., "value": ..., "as_of": ...}

#: Evidence independence, as a founder-facing projection (§24). Every field is
#: a COUNT or a STATE that the producer measured; none of it is a judgement,
#: and there is deliberately no confidence number — how much to believe a
#: claim needs to see the claim, and a number derived from these counts would
#: launder a row count into an authority it has not earned.
_INDEPENDENCE_BLOCK = {
    "state": ..., "documents": ..., "independent_origins": ...,
    "independent_origin_count": ..., "source_families": ...,
    "corroboration_state": ..., "corroboration_reason": ...,
    "concentration_ratio": ..., "unknown_lineage": ...,
    "duplicate_documents": ..., "republications": ...,
    "contradiction_refs": _REF_BLOCK,
    # The sentence a surface may render verbatim. Carried rather than
    # rebuilt, so the wording wall cannot be re-implemented per surface.
    "plain_statement": ...,
}

MARKET_ALLOWED: Dict[str, Any] = {
    "contract_version": ..., "snapshot_id": ...,
    "company_id": ..., "canonical_name": ..., "subject_names": ...,
    "market_run_id": ..., "analysis_id": ...,
    "runtime_sha": ..., "generated_at": ..., "known_at": ...,
    "evidence_cutoff": ...,
    "availability": ..., "unavailable_reason": ...,
    "market_population": ...,
    "coverage_state": ...,
    "source_health_summary": _SUMMARY,
    "evidence_summary": _SUMMARY,
    "evidence_reference_ids": _REF_BLOCK,
    "evidence_independence_state": ...,
    "economic_state_refs": _REF_BLOCK,
    "demand_state_refs": _REF_BLOCK,
    "belief_refs": _REF_BLOCK,
    # `unidentified` counts hidden states the market engine TRACKED and could
    # not identify, because their posterior is uniform. It is not a ref and
    # not a zero: without it, "no posture" and "a posture nobody could
    # distinguish from the prior" are the same bytes on this side, and the
    # market engine currently reports the latter for 22 of 26 companies.
    "hidden_state_refs": dict(_REF_BLOCK, unidentified=...),
    "thesis_refs": _REF_BLOCK,
    "thesis_revision_refs": _REF_BLOCK,
    "expectation_refs": _REF_BLOCK,
    "reconciliation_refs": _REF_BLOCK,
    "contradiction_refs": _REF_BLOCK,
    "causal_question_refs": _REF_BLOCK,
    # `states` carries the resolution-state histogram, e.g.
    # {"PANEL_UNAVAILABLE": 5}. Without it a surface cannot tell an estimate
    # from a refusal without dereferencing every id -- and the refusal is the
    # case a CEO screen most needs to render honestly, because "the engine
    # asked and the data could not answer" is a finding, not an absence.
    "causal_result_refs": dict(_REF_BLOCK, states=...),
    "replay_refs": _REF_BLOCK,
    "adversary_refs": _REF_BLOCK,
    "learning_summary": _SUMMARY,
    "provenance_summary": _SUMMARY,
}

#: One sanitized provenance record (§12). Every field here is publicly
#: checkable: a title, a URL, who wrote it, who served it, who it is about.
#: There is deliberately NO source_id, run id or graph node id — those are
#: storage identity, and exporting one under a friendlier name is the leak
#: this block exists to make impossible to write by accident.
_PROVENANCE_RECORD = {
    "provenance_id": ..., "title": ..., "url": ...,
    # The three that must not collapse: who WROTE it, who SERVED it, who it
    # is ABOUT. Reading the host as the author is what made a company's own
    # 10-K look like independent government confirmation.
    "author": ..., "host": ..., "subject": ..., "self_authored": ...,
    "source_class": ..., "evidence_type": ...,
    "published_at": ..., "retrieved_at": ..., "freshness": ...,
    "lineage": ..., "independence_bearing": ..., "origin_group": ...,
    "passage": ..., "plain_statement": ..., "visibility": ...,
}

#: Absence is a STATE here, never an empty list (§13).
_PROVENANCE_BLOCK = {
    "contract": ..., "state": ..., "reason": ...,
    "records": [_PROVENANCE_RECORD],
}

FOUNDER_ALLOWED: Dict[str, Any] = {
    "contract_version": ..., "snapshot_id": ...,
    "company_id": ..., "canonical_name": ..., "domain": ..., "ticker": ...,
    "analysis_id": ..., "run_id": ...,
    "runtime_sha": ..., "generated_at": ..., "known_at": ...,
    "evidence_cutoff": ...,
    "availability": ..., "unavailable_reason": ...,
    # AUTHORITY, and the only side permitted to state it. See §10.
    "tenant_id": ..., "tenant_state": ...,
    "data_population": ...,
    "coverage_state": ...,
    "ceo_answer_coverage": _SUMMARY,
    "recommendation_ref": ..., "recommendation_standing": ...,
    "what_changed_ref": ..., "what_changed_your_mind_ref": ...,
    "decision_impact_state": ...,
    "living_decision_refs": _REF_BLOCK,
    "mdr_refs": _REF_BLOCK,
    "mve_refs": _REF_BLOCK,
    "internal_impact_state": ...,
    "internal_graph_availability": ...,
    "evidence_reference_ids": _REF_BLOCK,
    "evidence_independence_state": ...,
    # THE STRUCTURE BEHIND THE STATE (§24). The scalar above says whether
    # independence was measured; it cannot say what a founder needs next,
    # which is how many separate accounts there are and whose. Carried as a
    # projection of the canonical assessment — counts, origins and the
    # deterministic sentence — and never as a re-derivation of it.
    "evidence_independence": _INDEPENDENCE_BLOCK,
    "product_surfaces": {name: ... for name in V.PRODUCT_SURFACES},
    "provenance_summary": _SUMMARY,
    # THE CLAIM-LEVEL PROJECTION, beside the runtime summary above. The
    # summary says which build produced the analysis; this says where the
    # analysis got its facts, which is the question a buyer actually asks.
    "claim_provenance": _PROVENANCE_BLOCK,
    "learning_summary": _SUMMARY,
}

#: Fields a MARKET snapshot may never carry, at any depth. Not "unrecognised"
#: — refused. Market intelligence is derived from public evidence and has no
#: standing to name a tenant, a scope or a private row.
_MARKET_FORBIDDEN = frozenset({
    "tenant_id", "tenant_state", "scope", "tenant_scope", "private_refs",
    "internal_refs", "data_population", "authorization", "credential",
})

#: Fields added after the first v1 producer shipped. Absent from an older
#: producer's payload, and read as FIELD_UNAVAILABLE rather than as zero.
#: A snapshot missing any of these is OLDER_SUPPORTED, not INCOMPATIBLE.
MARKET_ADDITIVE = frozenset({"evidence_independence_state", "learning_summary",
                             "provenance_summary", "reconciliation_refs",
                             "contradiction_refs"})
FOUNDER_ADDITIVE = frozenset({"evidence_independence_state",
                              "evidence_independence",
                              "learning_summary", "provenance_summary",
                              "claim_provenance",
                              "what_changed_your_mind_ref"})

#: An unknown field whose NAME implies authority, identity partitioning,
#: privacy or population is refused rather than ignored (§11). Matching on the
#: name is a heuristic and is deliberately over-broad: the cost of refusing a
#: harmless field named `tenant_colour` is a producer change, and the cost of
#: ignoring one named `tenant_override` is a cross-tenant leak.
_SECURITY_SENSITIVE = (
    "tenant", "scope", "auth", "credential", "token", "secret", "password",
    "private", "privacy", "population", "permission", "acl", "owner",
    "visibility", "sensitivity", "restricted", "confidential", "api_key",
    "signature", "grant", "role", "impersonat",
)

#: Trading internals, restated here for the same reason `strategic_contract`
#: restates them: this package cannot import the producer's list, and if the
#: two disagree the stricter side must win.
_BANNED_SUBSTRINGS = (
    "win rate", "win_rate", "sharpe", "alpha", "profit factor",
    "profit_factor", "expectancy", "net return", "net_return",
    "paper book", "paper_book", "shadow portfolio", "shadow_portfolio",
    "position size", "position_size", "signal fired", "signal_fired",
    "strategy key", "strategy_key", "buy signal", "sell signal",
    "long position", "short position", "price target", "target price",
)

#: MATCHED ON WORD BOUNDARIES, NOT AS RAW SUBSTRINGS.
#:
#: "alpha" inside "Alphabet Inc." is not a trading internal, and a plain
#: substring scan refused every founder-facing text that named one of the
#: largest public companies in the world — a company squarely inside the
#: validation universe this programme is built around. The refusal was total:
#: one word in one sentence rejected the whole snapshot.
#:
#: The wall itself is not relaxed. "generated alpha of 3%" still matches,
#: because there the term stands as its own word; only "alphabet", "alphas"
#: and their like stop matching. Multi-word phrases keep their internal
#: spacing and are anchored the same way.
_BANNED_PATTERN = re.compile(
    r"(?<![0-9a-z])(?:%s)(?![0-9a-z])"
    % "|".join(re.escape(term) for term in _BANNED_SUBSTRINGS), re.I)


def is_security_sensitive(name: str) -> bool:
    """Whether an unrecognised field name must fail closed rather than be
    ignored. Exported because the break proofs assert on it directly."""
    low = str(name).lower()
    return any(token in low for token in _SECURITY_SENSITIVE)


def _scan_text(node: Any, path: str = "") -> None:
    if isinstance(node, str):
        found = _BANNED_PATTERN.search(node)
        if found:
            raise SnapshotRefused(
                f"{path or 'root'}: text contains {found.group(0).lower()!r}, "
                f"a trading internal that may not reach a founder surface")
    elif isinstance(node, Mapping):
        for key, value in node.items():
            _scan_text(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _scan_text(item, f"{path}[{i}]")


def _forbidden_scan(node: Any, forbidden: frozenset, path: str = "") -> None:
    """A forbidden name anywhere, at any depth, refuses the whole payload."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if str(key).lower() in forbidden:
                raise SnapshotRefused(
                    f"{path or 'root'}: field {key!r} is refused on this "
                    f"side; a market snapshot has no standing to state it")
            _forbidden_scan(value, forbidden, f"{path}.{key}" if path
                            else str(key))
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _forbidden_scan(item, forbidden, f"{path}[{i}]")


def _sift(node: Mapping, spec: Mapping, path: str,
          unknown: list) -> None:
    """Walk the payload, refusing security-sensitive unknowns and recording
    the rest. Structure is checked; unrecognised descriptive shape is not
    fatal (see the module docstring)."""
    for key, value in node.items():
        where = f"{path}.{key}" if path else str(key)
        if key not in spec:
            if is_security_sensitive(key):
                raise SnapshotRefused(
                    f"unknown security-sensitive field {key!r} at "
                    f"{path or 'root'}: this side fails closed on any field "
                    f"that could carry authority it cannot evaluate")
            unknown.append(where)
            continue
        inner = spec[key]
        if isinstance(inner, Mapping) and isinstance(value, Mapping):
            _sift(value, inner, where, unknown)


def contract_state(version: Any, expected: str, present: frozenset,
                   additive: frozenset) -> Tuple[str, Tuple[str, ...]]:
    """Decide SUPPORTED / OLDER_SUPPORTED / INCOMPATIBLE, and name what is
    missing. Missing additive fields read FIELD_UNAVAILABLE downstream — never
    zero, never an empty list."""
    got = _VERSION_RE.match(str(version or ""))
    want = _VERSION_RE.match(expected)
    if not got or not want or got.group("name") != want.group("name"):
        return V.CONTRACT_INCOMPATIBLE, ()
    if int(got.group("major")) != READS_MAJOR:
        return V.CONTRACT_INCOMPATIBLE, ()
    missing = tuple(sorted(additive - present))
    return (V.OLDER_SUPPORTED if missing else V.SUPPORTED), missing


@dataclass(frozen=True)
class _Snapshot:
    """Shared shape. Both snapshots answer the same four questions: who is
    this about, when was it true, may I read it, and what did it refuse."""
    availability: str = V.UNAVAILABLE
    reason: str = ""
    contract_state: str = V.CONTRACT_INCOMPATIBLE
    contract_version: str = ""
    snapshot_id: str = ""
    company_id: str = ""
    canonical_name: str = ""
    analysis_id: str = ""
    runtime_sha: str = ""
    generated_at: str = ""
    known_at: str = ""
    evidence_cutoff: str = ""
    coverage_state: str = V.FIELD_UNAVAILABLE
    evidence_independence_state: str = V.INDEPENDENCE_UNAVAILABLE
    unknown_fields: Tuple[str, ...] = ()
    missing_fields: Tuple[str, ...] = ()

    @property
    def has_content(self) -> bool:
        return self.availability in V.HAS_CONTENT_STATES


@dataclass(frozen=True)
class MarketDemoSnapshot(_Snapshot):
    """Market's bounded, sanitized statement about one company."""
    market_run_id: str = ""
    market_population: str = ""
    subject_names: Tuple[str, ...] = ()
    source_health_summary: Optional[dict] = None
    evidence_summary: Optional[dict] = None
    learning_summary: Optional[dict] = None
    provenance_summary: Optional[dict] = None
    blocks: Dict[str, RefBlock] = field(default_factory=dict)

    def block(self, name: str) -> RefBlock:
        """Never a KeyError, and never a bare empty list: a block the producer
        did not send reads UNAVAILABLE with a reason."""
        return self.blocks.get(name) or _empty_ref(
            f"the market producer sent no {name}")


@dataclass(frozen=True)
class FounderDemoSnapshot(_Snapshot):
    """Founder's bounded statement, produced AFTER authorization."""
    run_id: str = ""
    domain: str = ""
    ticker: str = ""
    tenant_id: str = ""
    tenant_state: str = ""
    data_population: str = ""
    ceo_answer_coverage: Optional[dict] = None
    recommendation_ref: str = ""
    recommendation_standing: str = V.FIELD_UNAVAILABLE
    what_changed_ref: str = ""
    what_changed_your_mind_ref: str = ""
    decision_impact_state: str = V.IMPACT_UNAVAILABLE
    internal_impact_state: str = "INTERNAL_DATA_UNAVAILABLE"
    internal_graph_availability: str = V.UNAVAILABLE
    product_surfaces: Dict[str, str] = field(default_factory=dict)
    learning_summary: Optional[dict] = None
    provenance_summary: Optional[dict] = None
    #: The claim-level projection. None when the producer did not run, which
    #: is a fact about us; an empty `records` list carrying a STATE is a fact
    #: about the company. The two are never merged.
    claim_provenance: Optional[dict] = None
    #: The structure behind `evidence_independence_state` (§24). None when the
    #: producer sent none — an older producer is OLDER_SUPPORTED, not wrong.
    evidence_independence: Optional[dict] = None
    blocks: Dict[str, RefBlock] = field(default_factory=dict)

    def block(self, name: str) -> RefBlock:
        return self.blocks.get(name) or _empty_ref(
            f"the founder producer sent no {name}")


def market_unavailable(reason: str, company_id: str = "",
                       availability: str = V.UNAVAILABLE
                       ) -> MarketDemoSnapshot:
    """An absent market snapshot, carrying why. There is no bare False here,
    and `UNAVAILABLE` is never rendered as "the market found nothing"."""
    return MarketDemoSnapshot(availability=availability, reason=reason,
                              company_id=company_id)


def founder_unavailable(reason: str, company_id: str = "",
                        availability: str = V.UNAVAILABLE
                        ) -> FounderDemoSnapshot:
    return FounderDemoSnapshot(availability=availability, reason=reason,
                               company_id=company_id)


def _summary(node: Any) -> Optional[dict]:
    return dict(node) if isinstance(node, Mapping) else None


def _age_days(a: str, b: str) -> Optional[int]:
    try:
        return abs((date.fromisoformat(str(b)[:10])
                    - date.fromisoformat(str(a)[:10])).days)
    except (ValueError, TypeError):
        return None


_MARKET_BLOCKS = ("evidence_reference_ids", "economic_state_refs",
                  "demand_state_refs", "belief_refs", "hidden_state_refs",
                  "thesis_refs",
                  "thesis_revision_refs", "expectation_refs",
                  "reconciliation_refs", "contradiction_refs",
                  "causal_question_refs", "causal_result_refs",
                  "replay_refs", "adversary_refs")

_FOUNDER_BLOCKS = ("living_decision_refs", "mdr_refs", "mve_refs",
                   "evidence_reference_ids")


def read_market_snapshot(payload: Any, *, expected_company: str = "",
                         today: str = "") -> MarketDemoSnapshot:
    """Read one market snapshot from an already-deserialized payload.

    Transport-neutral by construction: this takes a mapping, not a path.
    """
    if not isinstance(payload, Mapping):
        return market_unavailable(
            "The market snapshot was not a readable object.",
            availability=V.REFUSED)

    company = str(payload.get("company_id") or "")
    state, missing = contract_state(payload.get("contract_version"),
                                    MARKET_CONTRACT, frozenset(payload),
                                    MARKET_ADDITIVE)
    if state == V.CONTRACT_INCOMPATIBLE:
        return MarketDemoSnapshot(
            availability=V.INCOMPATIBLE, company_id=company,
            contract_state=state,
            contract_version=str(payload.get("contract_version") or ""),
            reason=(f"The market snapshot declares "
                    f"{payload.get('contract_version')!r}; this side reads "
                    f"{MARKET_CONTRACT}. It was not joined."))

    unknown: list = []
    try:
        _forbidden_scan(payload, _MARKET_FORBIDDEN)
        _scan_text(payload)
        _sift(payload, MARKET_ALLOWED, "", unknown)
    except SnapshotRefused as exc:
        return MarketDemoSnapshot(
            availability=V.REFUSED, company_id=company, contract_state=state,
            reason=f"The market snapshot was refused: {exc}")

    if expected_company and company and company != expected_company:
        return MarketDemoSnapshot(
            availability=V.REFUSED, company_id=company, contract_state=state,
            reason=(f"The market snapshot is for {company!r}, not "
                    f"{expected_company!r}. It was not joined."))

    declared = str(payload.get("availability") or V.AVAILABLE)
    if declared not in V.AVAILABILITY_STATES:
        declared = V.REFUSED
    cutoff = str(payload.get("evidence_cutoff") or "")
    today = today or date.today().isoformat()
    if declared == V.AVAILABLE and cutoff:
        age = _age_days(cutoff, today)
        if age is not None and age > V.BOUNDED_WINDOW_DAYS:
            declared = V.STALE

    independence = str(payload.get("evidence_independence_state")
                       or V.INDEPENDENCE_UNAVAILABLE)
    if independence not in V.INDEPENDENCE_STATES:
        independence = V.INDEPENDENCE_UNAVAILABLE

    return MarketDemoSnapshot(
        availability=declared,
        reason=str(payload.get("unavailable_reason") or ""),
        contract_state=state,
        contract_version=str(payload.get("contract_version") or ""),
        snapshot_id=str(payload.get("snapshot_id") or ""),
        company_id=company,
        canonical_name=str(payload.get("canonical_name") or ""),
        analysis_id=str(payload.get("analysis_id") or ""),
        market_run_id=str(payload.get("market_run_id") or ""),
        market_population=str(payload.get("market_population") or ""),
        subject_names=tuple(str(n) for n in (payload.get("subject_names")
                                             or ())),
        runtime_sha=str(payload.get("runtime_sha") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        known_at=str(payload.get("known_at") or ""),
        evidence_cutoff=cutoff,
        coverage_state=str(payload.get("coverage_state")
                           or V.FIELD_UNAVAILABLE),
        evidence_independence_state=independence,
        source_health_summary=_summary(payload.get("source_health_summary")),
        evidence_summary=_summary(payload.get("evidence_summary")),
        learning_summary=_summary(payload.get("learning_summary")),
        provenance_summary=_summary(payload.get("provenance_summary")),
        blocks={name: _ref_block(payload.get(name))
                for name in _MARKET_BLOCKS},
        unknown_fields=tuple(unknown), missing_fields=missing)


def read_founder_snapshot(payload: Any, *, expected_company: str = "",
                          today: str = "") -> FounderDemoSnapshot:
    """Read one founder snapshot from an already-deserialized payload."""
    if not isinstance(payload, Mapping):
        return founder_unavailable(
            "The founder snapshot was not a readable object.",
            availability=V.REFUSED)

    company = str(payload.get("company_id") or "")
    state, missing = contract_state(payload.get("contract_version"),
                                    FOUNDER_CONTRACT, frozenset(payload),
                                    FOUNDER_ADDITIVE)
    if state == V.CONTRACT_INCOMPATIBLE:
        return FounderDemoSnapshot(
            availability=V.INCOMPATIBLE, company_id=company,
            contract_state=state,
            contract_version=str(payload.get("contract_version") or ""),
            reason=(f"The founder snapshot declares "
                    f"{payload.get('contract_version')!r}; this side reads "
                    f"{FOUNDER_CONTRACT}. It was not joined."))

    unknown: list = []
    try:
        _sift(payload, FOUNDER_ALLOWED, "", unknown)
    except SnapshotRefused as exc:
        return FounderDemoSnapshot(
            availability=V.REFUSED, company_id=company, contract_state=state,
            reason=f"The founder snapshot was refused: {exc}")

    if expected_company and company and company != expected_company:
        return FounderDemoSnapshot(
            availability=V.REFUSED, company_id=company, contract_state=state,
            reason=(f"The founder snapshot is for {company!r}, not "
                    f"{expected_company!r}. It was not joined."))

    declared = str(payload.get("availability") or V.AVAILABLE)
    if declared not in V.AVAILABILITY_STATES:
        declared = V.REFUSED

    independence = str(payload.get("evidence_independence_state")
                       or V.INDEPENDENCE_UNAVAILABLE)
    if independence not in V.INDEPENDENCE_STATES:
        independence = V.INDEPENDENCE_UNAVAILABLE

    surfaces = payload.get("product_surfaces")
    surfaces = {k: str(v) for k, v in surfaces.items()} \
        if isinstance(surfaces, Mapping) else {}
    # A backend cannot claim its own appearance. Any surface value this side
    # has not defined — including anything resembling a pass — is read as
    # UNMEASURED (§27).
    surfaces = {name: (surfaces.get(name) if surfaces.get(name)
                       in V.SURFACE_STATES else V.UNMEASURED)
                for name in V.PRODUCT_SURFACES}

    return FounderDemoSnapshot(
        availability=declared,
        reason=str(payload.get("unavailable_reason") or ""),
        contract_state=state,
        contract_version=str(payload.get("contract_version") or ""),
        snapshot_id=str(payload.get("snapshot_id") or ""),
        company_id=company,
        canonical_name=str(payload.get("canonical_name") or ""),
        analysis_id=str(payload.get("analysis_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        domain=str(payload.get("domain") or ""),
        ticker=str(payload.get("ticker") or ""),
        tenant_id=str(payload.get("tenant_id") or ""),
        tenant_state=str(payload.get("tenant_state") or ""),
        data_population=str(payload.get("data_population") or ""),
        runtime_sha=str(payload.get("runtime_sha") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        known_at=str(payload.get("known_at") or ""),
        evidence_cutoff=str(payload.get("evidence_cutoff") or ""),
        coverage_state=str(payload.get("coverage_state")
                           or V.FIELD_UNAVAILABLE),
        evidence_independence_state=independence,
        evidence_independence=(payload.get("evidence_independence")
                               if isinstance(
                                   payload.get("evidence_independence"), dict)
                               else None),
        ceo_answer_coverage=_summary(payload.get("ceo_answer_coverage")),
        recommendation_ref=str(payload.get("recommendation_ref") or ""),
        recommendation_standing=str(payload.get("recommendation_standing")
                                    or V.FIELD_UNAVAILABLE),
        what_changed_ref=str(payload.get("what_changed_ref") or ""),
        what_changed_your_mind_ref=str(
            payload.get("what_changed_your_mind_ref") or ""),
        decision_impact_state=str(payload.get("decision_impact_state")
                                  or V.IMPACT_UNAVAILABLE),
        internal_impact_state=str(payload.get("internal_impact_state")
                                  or "INTERNAL_DATA_UNAVAILABLE"),
        internal_graph_availability=str(
            payload.get("internal_graph_availability") or V.UNAVAILABLE),
        product_surfaces=surfaces,
        learning_summary=_summary(payload.get("learning_summary")),
        provenance_summary=_summary(payload.get("provenance_summary")),
        claim_provenance=(payload.get("claim_provenance")
                          if isinstance(payload.get("claim_provenance"), dict)
                          else None),
        blocks={name: _ref_block(payload.get(name))
                for name in _FOUNDER_BLOCKS},
        unknown_fields=tuple(unknown), missing_fields=missing)
