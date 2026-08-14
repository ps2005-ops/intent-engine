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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import demo_snapshot_export as DSE
from . import strategic_export as SE

EXPORT_DIR = "reports/market/strategic"


def _runtime_sha() -> str:
    """The market runtime's provenance, for the neutral read model.

    A dossier assembled from two sides must record which code produced each,
    or a change of behaviour between versions looks like a change in the
    company.
    """
    try:
        from .runtime_provenance import provenance
        # `runtime_git_sha` is the field name `runtime_provenance` actually
        # emits. Getting it wrong is invisible: the snapshot publishes an
        # empty sha, the dossier records "no market runtime", and nothing
        # anywhere raises. A test pins the two together.
        return str((provenance() or {}).get("runtime_git_sha") or "")
    except Exception:  # noqa: BLE001 - provenance must never fail a publish
        return ""


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
            # The engine's OWN subject string, verbatim — the market universe
            # company id a belief was keyed on. It is not a display name and
            # must not be shown to a founder; `publish` maps it to one.
            "subject": (_display_name(beliefs.get(key, ()))
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


def _causal_for(resolutions: Sequence[Any], subject_id: str) -> list:
    """This subject's causal resolutions, refusals included."""
    out = []
    for r in resolutions or ():
        question = (r.get("question") if isinstance(r, dict)
                    else getattr(r, "question", None)) or {}
        company = (question.get("company_id") if isinstance(question, dict)
                   else getattr(question, "company_id", ""))
        if str(company or "") == str(subject_id):
            out.append(r)
    return out


def _causal_questions_for(resolutions: Sequence[Any], subject_id: str) -> list:
    """The questions behind this subject's resolutions.

    Read off the resolutions rather than collected separately: a question
    published without its resolution would say the engine asked and leave the
    answer -- including the refusal -- invisible.
    """
    out = []
    for r in _causal_for(resolutions, subject_id):
        question = (r.get("question") if isinstance(r, dict)
                    else getattr(r, "question", None))
        if question:
            out.append(question)
    return out


def _expectations_for(expectations: Sequence[Any], subject_id: str) -> list:
    """This subject's expectations only.

    An expectation belongs to whoever it is about. Publishing the whole
    ledger under one company would attribute another company's preregistered
    test to this one, which is the cross-subject contamination the export
    wall exists to prevent.
    """
    out = []
    for e in expectations or ():
        subject = (e.get("subject") if isinstance(e, dict)
                   else getattr(e, "subject", ""))
        if str(subject or "") == str(subject_id):
            out.append(e)
    return out


def _belongs(thesis: Any, subject_id: str) -> bool:
    """Whether this thesis is about this subject, by id and never by text."""
    if isinstance(thesis, dict):
        subject = str(thesis.get("subject") or "")
    else:
        subject = str(getattr(thesis, "subject", "") or "")
    return subject == subject_id


def _revisions_for(revisions: Sequence[Any], theses: Sequence[Any]) -> list:
    """Revisions belonging to these theses, matched on thesis_id.

    Matched by ID rather than by claim text, deliberately. Two theses can
    carry byte-identical claims — G-THE-004 was exactly that, and matching on
    wording silently merged them and dropped four snapshots a night.
    """
    ids = set()
    for thesis in theses:
        if isinstance(thesis, dict):
            ids.add(str(thesis.get("thesis_id") or ""))
        else:
            ids.add(str(getattr(thesis, "thesis_id", "") or ""))
    ids.discard("")
    out = []
    for revision in revisions:
        if isinstance(revision, dict):
            tid = str(revision.get("thesis_id") or "")
        else:
            tid = str(getattr(revision, "thesis_id", "") or "")
        if tid and tid in ids:
            out.append(revision)
    return out


def publish(result, *, root=".", market_structures: Sequence[Any] = (),
            pricing_actions: Sequence[Any] = (),
            causal_pathways: Sequence[Any] = (),
            identities: Optional[Dict[str, Any]] = None,
            evidence_rows: Sequence[Any] = (),
            economic_theses: Sequence[Any] = (),
            thesis_revisions: Sequence[Any] = (),
            #: Real preregistered expectations. None (the default) keeps the
            #: previous behaviour exactly, so a caller that does not pass them
            #: is unchanged rather than silently publishing an empty block.
            expectations: Optional[Sequence[Any]] = None,
            #: Causal resolutions, refusals included. None keeps the old
            #: behaviour; passing them is what stops a refusal being
            #: published as "this subsystem did not run".
            causal_resolutions: Optional[Sequence[Any]] = None,
            #: Measured economic conditions, and the RAW ledger rows the
            #: exposure reader needs. Both or neither: an economy with no
            #: exposure profile is a story that applies to every company
            #: equally, which is the one thing `company_exposure` exists to
            #: refuse. None keeps the previous behaviour exactly.
            economic_states: Optional[Sequence[Any]] = None,
            exposure_rows: Optional[Sequence[Any]] = None,
            history_available: bool = True,
            limitations: Sequence[str] = ()) -> dict:
    """Write one sanitized export per company with something to say.

    `identities` maps this engine's internal subject (the market universe's
    `company_id`, which is what a belief's `subject` actually holds) to the
    names a founder would recognise: `{"microsoft": ("Microsoft Corporation",
    ("Microsoft", "Microsoft Corp"))}`.

    IT IS NOT COSMETIC, AND THAT WAS MEASURED
    -----------------------------------------
    Without it this module filed `microsoft.json`, and the founder side —
    which knows the company as whatever its operator typed — looked for
    `microsoft-corporation.json`. It found nothing, on every company, and
    reported "no strategic reading has been published", which is a legitimate
    sentence and so nothing anywhere raised. The bridge had a producer, a
    consumer, an allowlist enforced at both ends and a full test suite, and it
    carried zero dossiers.

    So the file is keyed on the name the other side can actually derive, and
    the payload states its subject as well, because a key both sides have to
    compute the same way is the thing that just failed.

    Returns a report the cycle can print: what was published, what was
    skipped for having no material, and what was REFUSED because the
    allowlist caught a field on its way out.
    """
    grouped = bundles(result, market_structures=market_structures,
                      pricing_actions=pricing_actions,
                      causal_pathways=causal_pathways)
    # WHICH ECONOMY REACHES WHICH COMPANY.
    #
    # Publishing the measured economy to every company would put the same
    # sixteen conditions on twenty-six dossiers -- a macro dashboard, which is
    # exactly what §4 asks this NOT to be. A condition crosses only where this
    # company's own evidence establishes an exposure that transmits it, which
    # is `company_exposure.conditions_transmission`, unchanged.
    #
    # 266 of 270 dimensions are UNKNOWN in the live corpus and that is the
    # honest reading: an exposure model with every dimension populated is one
    # that has been guessing from a sector table.
    _economy = list(economic_states or ())
    _profiles: Dict[str, Any] = {}
    if economic_states is not None and exposure_rows:
        from . import company_exposure as _CX
        for _subject in sorted({str(r.get("subject_company") or "")
                                for r in exposure_rows
                                if isinstance(r, dict)
                                and r.get("record") == "evidence"
                                and r.get("subject_company")}):
            _profiles[_subject] = _CX.profile(exposure_rows,
                                              company_id=_subject)

    def _economy_for(subject_id: str):
        """The conditions that reach THIS company, or a stated absence.

        Returns None when no economy was supplied at all -- which must stay
        distinguishable from "the economy is measured and none of it reaches
        this company", the answer for 23 of 27 live companies.
        """
        if economic_states is None:
            return None
        from . import company_exposure as _CX
        profile = _profiles.get(subject_id) or {}
        if not profile:
            return []
        return [s for s in _economy
                if any(_CX.conditions_transmission(profile.get(d), s)
                       for d in _CX.DIMENSIONS)]
    identities = identities or {}
    published: List[str] = []
    refused: List[dict] = []
    unnamed: List[str] = []
    snapshots: List[str] = []
    snapshot_refused: List[dict] = []
    for key, bundle in grouped.items():
        subject_id = bundle["subject"]
        display, aliases = _identity_for(subject_id, identities)
        if not display:
            # No display name was supplied, so the old key stands. The dossier
            # is still correct and still published; it simply cannot be found
            # by name, and that is reported rather than left to be discovered
            # as another silent absence.
            unnamed.append(key)
        file_key = company_key(display) or key
        try:
            payload = SE.build_export(
                company_id=file_key, as_of=result.as_of,
                subject_id=subject_id, display_name=display,
                subject_names=aliases,
                beliefs=bundle["beliefs"],
                hidden_states=bundle["hidden_states"],
                interactions=bundle["interactions"],
                market_structure=bundle["market_structure"],
                pricing_actions=bundle["pricing_actions"],
                causal_pathways=bundle["causal_pathways"],
                reconciliations=bundle["reconciliations"],
                information_priorities=bundle["information_priorities"],
                # The WHOLE ledger, not this company's slice. Event identity
                # clusters by wording and date, so it is safe across subjects
                # and the export only reads back the ids its own beliefs cite.
                evidence_rows=evidence_rows,
                # THE HISTORY LEG. `economic_theses` was an accepted export
                # field with an allowlist entry that this call site never
                # passed, and revisions had no field at all — so the consumer
                # received a current view and no record of how it got there.
                # Both are filtered to THIS subject by id: a thesis history
                # is only meaningful against the thesis it belongs to.
                economic_theses=[t for t in economic_theses
                                 if _belongs(t, subject_id)],
                thesis_revisions=_revisions_for(
                    thesis_revisions,
                    [t for t in economic_theses
                     if _belongs(t, subject_id)]),
                history_available=history_available,
                limitations=list(limitations))
            SE.write_export(payload, root=root)
        except SE.ExportLeak as exc:
            # Fail closed, loudly, and per company. Never counted as a
            # publish, never counted as "nothing to say".
            refused.append({"company_id": file_key, "reason": str(exc)})
            continue
        published.append(file_key)
        # The neutral read model's market leg, emitted from the SAME bundle
        # rather than from a demo-only path (§12). It carries ids and states
        # only; blocks this cycle did not compute are passed as None and
        # serialize as UNAVAILABLE, never as an empty list.
        try:
            DSE.write_snapshot(DSE.build_snapshot(
                company_id=file_key, as_of=result.as_of,
                canonical_name=display or file_key, subject_names=aliases,
                market_run_id=str(getattr(result, "run_id", "") or ""),
                runtime_sha=_runtime_sha(),
                beliefs=bundle["beliefs"],
                # ALREADY IN THE BUNDLE, and already shipped to the strategic
                # export for 22 of 26 companies. The demo contract simply had
                # no field for it, so the product showed nothing.
                hidden_states=bundle["hidden_states"],
                theses=[t for t in economic_theses
                        if _belongs(t, subject_id)],
                thesis_revisions=_revisions_for(
                    thesis_revisions,
                    [t for t in economic_theses if _belongs(t, subject_id)]),
                reconciliations=bundle["reconciliations"],
                # `information_priorities` was passed here as the expectation
                # block. It is a DIFFERENT thing, and it is empty in 26/26
                # exports, while the ledger holds real preregistered
                # expectations with falsifiers and evaluation windows. The
                # snapshot was reading the wrong field, so "no expectations"
                # was a wiring artefact and not a finding.
                expectations=(_expectations_for(expectations, subject_id)
                              if expectations is not None
                              else bundle["information_priorities"]),
                evidence_rows=evidence_rows,
                # Deliberately NOT passed: this cycle does not compute them,
                # and `None` is the honest statement of that. Passing `()`
                # here would publish "we looked and found no causal result",
                # which is a finding nobody made.
                # THE CAUSAL TRUTH LEG. The router asked real questions and
                # refused them for a named missing prerequisite. Publishing
                # None said "did not run", which is a different claim and a
                # false one -- and it is the claim that made the product look
                # like it has no causal capability at all.
                causal_questions=(_causal_questions_for(causal_resolutions,
                                                        subject_id)
                                  if causal_resolutions is not None else None),
                causal_results=(_causal_for(causal_resolutions, subject_id)
                                if causal_resolutions is not None else None),
                replay_episodes=None, adversary_cases=None,
                demand_states=None, contradictions=None,
                # THE ECONOMY THIS COMPANY IS ACTUALLY EXPOSED TO. `None` was
                # passed here unconditionally, so `ECONOMIC_STATE_NOT_RUN` was
                # a wiring artefact: the macro layer holds 2,466 observations
                # and 16 anchored conditions, and the cycle already computes
                # both the states and the exposure profiles.
                economic_states=_economy_for(subject_id),
            ), root=root)
            snapshots.append(file_key)
        except DSE.SnapshotLeak as exc:
            snapshot_refused.append({"company_id": file_key,
                                     "reason": str(exc)})
    return {
        "contract": SE.EXPORT_VERSION,
        "as_of": result.as_of,
        "companies_with_material": len(grouped),
        "published": sorted(published),
        "refused": refused,
        "unnamed": sorted(unnamed),
        "demo_snapshots": sorted(snapshots),
        "demo_snapshots_refused": snapshot_refused,
        "directory": str(pathlib.Path(root) / EXPORT_DIR),
        "note": ("a company with no belief, posture move, mismatch or "
                 "information priority is not given an empty dossier"),
        "unnamed_note": ("a dossier published under an internal id only; the "
                         "founder side cannot find it by company name"),
    }


def _identity_for(subject_id: str, identities: Dict[str, Any]
                  ) -> Tuple[str, Tuple[str, ...]]:
    """The display name and aliases for one internal subject.

    Accepts either `{id: "Display Name"}` or `{id: ("Display Name", aliases)}`
    so a caller with only a name is not forced to invent an alias list.
    """
    entry = identities.get(subject_id) or identities.get(
        company_key(subject_id))
    if entry is None:
        return "", ()
    if isinstance(entry, str):
        return entry.strip(), ()
    display, aliases = "", ()
    try:
        display, aliases = entry[0], tuple(entry[1])
    except (TypeError, IndexError, KeyError):
        return (str(entry).strip(), ())
    return str(display).strip(), tuple(str(a) for a in aliases if a)
