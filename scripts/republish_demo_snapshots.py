#!/usr/bin/env python3
"""Republish the demo snapshots from the persisted ledger.

WHY THIS EXISTS
---------------
The snapshots a founder deployment reads are written by the learning cycle,
which runs on its own schedule. When the SNAPSHOT CONTRACT gains a block --
hidden state, expectations, causal truth -- every snapshot already on disk
is silently a version behind, and the product shows UNAVAILABLE for
intelligence the engine computed weeks ago.

Re-running a whole learning cycle to fix that would ingest new evidence and
move beliefs, which is a different operation with different risks. This does
strictly less: it reads what the ledger already holds and re-emits the
published view of it.

IT INVENTS NOTHING. Every row comes from the ledger; hidden states are bound
by the same `hidden_state_binding.bind` production uses, over the same
evidence. A company the ledger has nothing for is not published.

Usage:
    PYTHONPATH=src python3 scripts/republish_demo_snapshots.py \
        --root /path/to/market/runtime [--as-of YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.market import hidden_state_binding as HSB      # noqa: E402
from intent_engine.market import learning_store as LS             # noqa: E402
from intent_engine.market import strategic_publish as SEP         # noqa: E402
from intent_engine.market.strategic_publish import company_key    # noqa: E402


class LedgerView:
    """The subset of a cycle result that `bundles()` actually reads.

    Named a view rather than a result because it is one: no cycle ran, no
    belief moved, and nothing here is a new finding. `_seen` collections are
    what this session observed, and this session observed nothing, so they
    carry the ledger's standing content and no more.
    """

    def __init__(self, *, as_of, run_id, beliefs, hidden_states,
                 reconciliations):
        self.as_of = as_of
        self.run_id = run_id
        self.beliefs_after = tuple(beliefs)
        self.hidden_states_after = tuple(hidden_states)
        self.reconciliations_seen = tuple(reconciliations)
        self.priorities_seen = ()
        self.interactions_seen = ()


def _subjects(beliefs, hidden_states):
    out = set()
    for row in list(beliefs) + list(hidden_states):
        subject = (row.get("subject") if isinstance(row, dict)
                   else getattr(row, "subject", "")) or ""
        if subject:
            out.add(str(subject))
    return out


def _identities(root, subjects):
    """subject string -> (display name, aliases), from the LAST REAL CYCLE.

    WHY NOT DERIVE IT FROM THE SUBJECT
    ----------------------------------
    The ledger keys beliefs on "Cloudflare". A founder types "Cloudflare,
    Inc.". `company_key` turns those into `cloudflare` and `cloudflare-inc`,
    which are different files -- and a snapshot the founder side cannot find
    by name is exactly the failure `strategic_publish.publish` documents as
    having carried zero dossiers with a full test suite passing.

    So the canonical names are not re-derived here. They are read back from
    the strategic exports the last real cycle published, which is where the
    company registry's canonical name already landed.

    AN AMBIGUOUS ALIAS IS REFUSED, NOT GUESSED. One alias matching two
    companies would file a dossier under the wrong identity, and "Linear"
    matching "Linear Minerals Corp." is a real instance of this from an
    earlier batch. A subject nobody can name is reported and skipped; its
    dossier keeps the ledger key, which is findable by nobody and wrong for
    nobody.
    """
    import collections
    import json
    alias_to: dict = collections.defaultdict(set)
    meta: dict = {}
    for path in sorted((pathlib.Path(root) / "reports/market/strategic")
                       .glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        display = str(payload.get("company_display_name") or "")
        names = [str(n) for n in (payload.get("subject_names") or [])]
        if not display:
            continue
        meta[display] = tuple(names)
        for name in set(names) | {display}:
            alias_to[name].add(display)

    identities, unnamed, ambiguous = {}, [], []
    for subject in sorted(subjects):
        owners = alias_to.get(subject) or set()
        if len(owners) == 1:
            display = next(iter(owners))
            identities[subject] = (display, meta.get(display, ()))
        elif owners:
            ambiguous.append((subject, sorted(owners)))
        else:
            unnamed.append(subject)
    return identities, unnamed, ambiguous


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--as-of", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = pathlib.Path(args.root).expanduser()
    store = LS.LearningStore(root / LS.DEFAULT_PATH)
    evidence = store.evidence()
    beliefs = store.beliefs()
    # `observed_at` is when this side SAW the row. It is the only date the
    # ledger guarantees, and it is deliberately not read as when the fact
    # occurred -- the export states an evidence cutoff, not an event date.
    as_of = args.as_of or max(
        [str(getattr(e, "observed_at", "") or "") for e in evidence] or [""])
    if not as_of:
        print("REFUSED: the ledger carries no dated evidence; there is no "
              "as-of to publish against.")
        return 2

    hidden_states, _obs, hs_refused = HSB.bind(evidence, as_of=as_of)
    reconciliations = store.reconciliations()

    print(f"ledger        {root / LS.DEFAULT_PATH}")
    print(f"as_of         {as_of}")
    print(f"evidence      {len(evidence)}")
    print(f"beliefs       {len(beliefs)}")
    print(f"hidden_states {len(hidden_states)} (refused {len(hs_refused)})")
    print(f"expectations  {len(store.expectations())}")
    print(f"causal        {len(store.causal_estimates())}")
    print(f"theses        {len(store.thesis_snapshots())}")

    view = LedgerView(as_of=as_of, run_id=f"republish-{as_of}",
                      beliefs=beliefs, hidden_states=hidden_states,
                      reconciliations=reconciliations)
    subjects = _subjects(beliefs, hidden_states)
    identities, unnamed, ambiguous = _identities(root, subjects)
    print(f"subjects      {len(subjects)}")
    print(f"identities    {len(identities)} named"
          f" / {len(unnamed)} unnamed / {len(ambiguous)} ambiguous")
    for subject in unnamed:
        print(f"  UNNAMED   {subject!r} -- no published export claims this "
              f"alias; its dossier keeps the ledger key")
    for subject, owners in ambiguous:
        print(f"  AMBIGUOUS {subject!r} -> {owners}; REFUSED rather than "
              f"filed under a guess")
    if args.dry_run:
        keys = sorted({company_key(d) for d, _ in identities.values()})
        print(f"DRY RUN -- would publish {len(keys)} keys: {keys[:6]}"
              f"{' ...' if len(keys) > 6 else ''}")
        return 0

    # THE ECONOMY, AND THE ROWS THAT SAY WHO IS EXPOSED TO IT. Read from the
    # ledger file directly because the exposure reader filters on `record`,
    # which the typed rows' `as_dict()` does not carry -- reading it the other
    # way silently matches nothing and reports every company unexposed.
    import json as _json
    raw_rows = []
    ledger = root / LS.DEFAULT_PATH
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    raw_rows.append(_json.loads(line))
                except ValueError:
                    continue
    from intent_engine.market import macro_state as MS
    history = [MS.from_dict(r) for r in raw_rows
               if r.get("record") == "macro_observation"]
    econ = list(MS.all_states(history, as_of=as_of)) if history else []
    anchored = [s for s in econ if s.anchors]
    print(f"economic     {len(econ)} state(s), {len(anchored)} anchored")

    report = SEP.publish(
        view, root=str(root), identities=identities,
        evidence_rows=evidence,
        economic_states=anchored, exposure_rows=raw_rows,
        economic_theses=store.thesis_snapshots(),
        thesis_revisions=store.thesis_revisions(),
        expectations=store.expectations(),
        causal_resolutions=store.causal_estimates(),
        history_available=True)
    print(f"\npublished     {len(report.get('published') or [])}")
    print(f"snapshots     {len(report.get('demo_snapshots') or [])}")
    print(f"refused       {len(report.get('refused') or [])}")
    print(f"snap refused  {len(report.get('demo_snapshots_refused') or [])}")
    for row in (report.get("refused") or [])[:5]:
        print(f"  REFUSED {row}")
    for row in (report.get("demo_snapshots_refused") or [])[:5]:
        print(f"  SNAPSHOT REFUSED {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
