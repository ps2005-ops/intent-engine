#!/usr/bin/env python
"""Supersede the six July FRED forecasts closed 'unresolvable' before publication.

Default: copies the ledger to --work, applies there, and prints the proposal
with before/after Brier by source. The source ledger is hashed before and
after and must be unchanged.

    PYTHONPATH=src python scripts/propose_july_supersessions.py \
        --ledger ~/intent-engine/data/prediction_ledger.db \
        --audit reports/forecast_audit/overdue_resolutions_2026-11-10.jsonl \
        --work <scratch dir>

`--in-place` applies to --ledger itself. That is a production write: run it
only with approval, after a verified backup.
"""
import argparse, hashlib, json, shutil, sqlite3, sys
from pathlib import Path

from intent_engine.core import prediction_ledger as PLG


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _brier(path):
    out = {}
    for src in ("market", "baseline"):
        s = PLG.brier_summary(source=src, path=path)
        out[src] = {"n": s.count, "mean_brier": None if s.mean_brier is None
                    else round(s.mean_brier, 4)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--work")
    ap.add_argument("--in-place", action="store_true")
    a = ap.parse_args(argv)
    if not a.in_place and not a.work:
        ap.error("--work is required unless --in-place")
    src_hash = _sha(a.ledger)
    target = Path(a.ledger)
    if not a.in_place:
        Path(a.work).mkdir(parents=True, exist_ok=True)
        target = Path(a.work) / "prediction_ledger.db"
        if target.exists():
            print(f"refusing to overwrite {target}", file=sys.stderr)
            return 2
        shutil.copy2(a.ledger, target)
    before = _brier(target)
    rows = [json.loads(l) for l in open(a.audit, encoding="utf-8")]
    applied = []
    for r in rows:
        pid = r["prediction_id"]
        obs = r["observation"]
        published = obs.get("first_published") or "unknown"
        flags = r.get("flags") or []
        note = (f"Audit {r['audit_as_of']}: {r['grader_note']} Grader "
                f"{r['grader']}. Flags: {' | '.join(flags) or 'none'}.")
        new = PLG.supersede_unresolvable(pid, r["audit_outcome"],
                                         evidence_note=note,
                                         data_first_published=published,
                                         path=target)
        applied.append({"id": pid[:8], "resolve_by": new.resolve_by,
                        "probability": new.probability, "outcome": new.outcome,
                        "brier": round(new.brier_component, 4),
                        "flags": len(flags), "row_written_at": new.resolved_at})
    after = _brier(target)
    n_rows = sqlite3.connect(target).execute(
        "select count(*) from predictions").fetchone()[0]
    print(json.dumps({"mode": "IN_PLACE" if a.in_place else "COPY",
                      "target": str(target), "source_sha256_before": src_hash[:16],
                      "source_unchanged": a.in_place or _sha(a.ledger) == src_hash,
                      "appended": applied, "rows_after": n_rows,
                      "brier_before": before, "brier_after": after}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
