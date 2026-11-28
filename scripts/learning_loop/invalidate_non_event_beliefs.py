"""Propose (default) or apply belief invalidations for beliefs whose WHOLE
evidence basis no longer classifies as an event routing to their family.

    propose:  invalidate_non_event_beliefs.py LEDGER OUT.jsonl
    apply:    invalidate_non_event_beliefs.py --apply ROOT PROPOSED.jsonl

The candidate rule is the classifier, not a pattern written here: a belief is
withdrawn only when every sentence that opened it now classifies to nothing,
or to a type that does not route to the belief's family. A belief with even
one surviving basis sentence is kept.

APPLY IS GATED ON THE READER. An invalidation record means nothing to a
runtime whose store does not mask it, and appending one there would look like
a correction while changing nothing. Apply refuses unless the learning store
importable from PYTHONPATH defines BELIEF_INVALIDATION -- run it with the
runtime's own src on PYTHONPATH after the runtime has been upgraded.
"""
import datetime as dt
import json
import pathlib
import sys

RULE = "non_event_basis.v1 (commercial_event_patterns: fund holding notices, unit grants)"


def propose(ledger: pathlib.Path, out: pathlib.Path) -> dict:
    from intent_engine.market import belief_formation as BF
    import re
    from intent_engine.market import event_patterns as E
    holding = [re.compile(p, re.I) for p in E.HOLDING_NOTICE_PATTERNS]
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    evidence = {r["evidence_id"]: r for r in rows if r.get("record") == "evidence"}
    routes = {}
    for etype, family, _ in BF._ROUTES:
        routes.setdefault(family, set()).add(etype)
    candidates = []
    for x in (r for r in rows if r.get("record") == "expectation"):
        basis = [evidence[i] for i in x.get("evidence_basis") or () if i in evidence]
        if not basis:
            continue
        now = [E.classify_sentence(e.get("fact") or "") for e in basis]
        # Scope is THIS rule: every basis sentence must be refused by a
        # holding-notice pattern. A basis rejected for another reason belongs
        # to whichever correction owns that reason, not to this one.
        if all(t not in routes.get(x.get("metric"), ()) for t in now) and all(
                any(h.search(e.get("fact") or "") for h in holding) for e in basis):
            candidates.append({
                "belief_id": x["hypothesis_id"], "expectation_id": x["expectation_id"],
                "family": x.get("metric"), "subject": x.get("subject"),
                "evidence_ids": [e["evidence_id"] for e in basis],
                "was": [e.get("evidence_type") for e in basis], "now": now,
                "facts": [e.get("fact", "")[:200] for e in basis],
                "rule": RULE,
                "reason": "every basis sentence is a holder's trade or a unit grant, "
                          "not an action of the subject"})
    out.write_text("".join(json.dumps(c, sort_keys=True) + "\n" for c in candidates))
    return {"expectations": sum(1 for r in rows if r.get("record") == "expectation"),
            "proposed": len(candidates), "out": str(out)}


def apply(root: pathlib.Path, proposed: pathlib.Path) -> dict:
    from intent_engine.market import learning_store as LS
    if not hasattr(LS, "BELIEF_INVALIDATION"):
        raise SystemExit(f"REFUSED: {LS.__file__} does not mask belief_invalidation; "
                         "upgrade the runtime first")
    from intent_engine.market import cycle as C
    from intent_engine.runtime.locks import JobLock
    today = dt.date.today().isoformat()
    appended = 0
    with JobLock(C.LOCK_NAME, root=root):
        store = LS.LearningStore(root / LS.DEFAULT_PATH)
        for line in proposed.read_text().splitlines():
            c = json.loads(line)
            appended += store.invalidate_belief(
                c["belief_id"], reason=c["reason"], rule=c["rule"],
                evidence_ids=c["evidence_ids"], at=today)
    return {"appended": appended, "store": LS.__file__}


if __name__ == "__main__":
    if sys.argv[1] == "--apply":
        print(json.dumps(apply(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))))
    else:
        print(json.dumps(propose(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))))
