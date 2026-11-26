"""The earlier 75-company universe (ASI-25 + Next-40 + Final-Ten), re-run on a
candidate through the SAME journey as prospect-100.

Each company keeps the entity id, typed prefixes and category its own cohort
script declared. Final-Ten rows carry a domain rather than an entity id; their
journey confirms the suggestion by name, as that cohort's harness did.

  JOURNEY_BASE=http://127.0.0.1:PORT PYTHONPATH=src python \
      scripts/prospect100/resume/regression75_pass.py \
      --out reports/prospect100_resume/regression75/s1 --shard 1/2
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent.parent))

import asi25_qualification as A  # noqa: E402
import final_ten_qualification as F  # noqa: E402
import next40_owner as OWNER  # noqa: E402
import next40_qualification as NQ  # noqa: E402


def universe() -> list:
    rows = []
    for n, name, eid, prefixes, cat in A.TWENTY_FIVE:
        rows.append((len(rows) + 1, name, eid, list(prefixes), f"ASI25/{cat}"))
    for n, name, eid, prefixes, cat in NQ.FORTY:
        rows.append((len(rows) + 1, name, eid, list(prefixes), f"NEXT40/{cat}"))
    from intent_engine.company_ingestion.catalog import CATALOG_REGISTRY
    by_domain = {p.primary_domain: p.entity_id for p in CATALOG_REGISTRY}
    for name, domain, cat in F.TEN:
        rows.append((len(rows) + 1, name, by_domain.get(domain, ""),
                     [name], f"TEN/{cat}"))
    assert len({r[1] for r in rows}) == 75, "the regression universe is 75"
    return rows


def main() -> int:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    order = universe()
    if "--shard" in sys.argv:
        i, n = (int(x) for x in sys.argv[sys.argv.index("--shard") + 1]
                .split("/"))
        order = order[i - 1::n]
    NQ.FORTY = order
    NQ.COHORTS = {"ALL": [r[0] for r in order]}
    NQ.STATE = out / "state.json"
    NQ.ROOT = out
    OWNER.LOCK = out / "owner.json"
    sys.argv = [sys.argv[0], "--cohort", "ALL"]
    return NQ.main()


if __name__ == "__main__":
    raise SystemExit(main())
