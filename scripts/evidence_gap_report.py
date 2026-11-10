"""Which missing evidence category blocks the most VALID hypotheses?

Aggregates the typed corroboration diagnostics across the whole universe and
every hypothesis kind. The question is deliberately not "which unlocks the most
trades" -- that would rank by trade count, which this project does not optimise.
It is "which category blocks the most otherwise-viable reasoning paths".
"""
import collections
import json
import pathlib
import sys

from intent_engine.market.corroboration import (
    REQUIREMENTS, assess, category_of, is_independent,
)

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                   else "reports/reality_day6.json")
KINDS = [k for k in REQUIREMENTS]


def main():
    rows = json.loads(SRC.read_text())
    # what each company actually retrieved, as source classes
    blocked = collections.Counter()
    independence_fail = collections.Counter()
    relevance_fail = collections.Counter()
    present_irrelevant = collections.Counter()
    viable_paths = collections.Counter()
    per_company = {}

    for row in rows:
        cid = row["company"]
        # a company with no evidence at all cannot be a relevance failure --
        # it is an independence failure by absence, counted separately
        classes = (["company_owned", "executive_statement", "investor_material"]
                   if row.get("evidence", 0) else [])
        cats = {category_of(c) for c in classes}
        indep = {c for c in cats if is_independent(c)}
        per_company[cid] = {"categories": sorted(cats),
                            "independent": sorted(indep), "kinds": {}}

        for kind in KINDS:
            r = assess(classes, hypothesis_kind=kind)
            per_company[cid]["kinds"][kind] = r.as_dict()
            if r.satisfied:
                viable_paths[kind] += 1
                continue
            for m in r.missing:
                blocked[m] += 1
            if not indep:
                independence_fail[kind] += 1
            else:
                relevance_fail[kind] += 1
                for c in indep:
                    present_irrelevant[c] += 1

    print("=" * 74)
    print("DAY 8 — EVIDENCE GAP, aggregated across universe x hypothesis kind")
    print("=" * 74)
    print(f"companies: {len(rows)}   hypothesis kinds: {len(KINDS)}   "
          f"paths evaluated: {len(rows)*len(KINDS)}\n")

    print("BLOCKED HYPOTHESES BY MISSING CATEGORY")
    print(f"{'category':<18}{'paths blocked':>15}{'share':>10}")
    total = sum(blocked.values())
    for cat, n in blocked.most_common():
        print(f"{cat:<18}{n:>15}{n/total*100:>9.0f}%")

    print("\nMARGINAL DECISION PATHS EACH CATEGORY WOULD VALIDLY UNLOCK")
    print("(paths where this category alone satisfies the requirement)")
    marginal = collections.Counter()
    for row in rows:
        classes = (["company_owned", "executive_statement", "investor_material"]
                   if row.get("evidence", 0) else [])
        for kind in KINDS:
            if assess(classes, hypothesis_kind=kind).satisfied:
                continue
            for cat in REQUIREMENTS[kind].required:
                if assess(classes + [_class_for(cat)],
                          hypothesis_kind=kind).satisfied:
                    marginal[cat] += 1
    for cat, n in marginal.most_common():
        print(f"  {cat:<18}{n:>5} paths")

    print(f"\nindependence failures (no independent evidence at all): "
          f"{sum(independence_fail.values())}")
    print(f"relevance failures (independent but wrong kind): "
          f"{sum(relevance_fail.values())}")
    print(f"categories present but irrelevant: "
          f"{dict(present_irrelevant) or 'none'}")
    print(f"\nviable paths today: {dict(viable_paths) or 'none'}")

    out = {"blocked": dict(blocked), "marginal": dict(marginal),
           "independence_failures": sum(independence_fail.values()),
           "relevance_failures": sum(relevance_fail.values()),
           "viable": dict(viable_paths), "per_company": per_company}
    pathlib.Path("reports/evidence_gap.json").write_text(json.dumps(out, indent=1))
    return out


_CLASS = {"customer_voice": "customer_voice", "industry": "independent_reporting",
          "institutional": "third_party_filing", "regulatory": "regulator_filing",
          "macro": "macro_series", "analyst": "analyst_coverage",
          "alternative": "alternative_data"}


def _class_for(category):
    return _CLASS.get(category, "company_owned")


if __name__ == "__main__":
    main()
