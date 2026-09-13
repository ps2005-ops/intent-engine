"""The canonical 100-company validation universe.

ONE MANIFEST, AND THIS MODULE IS THE ONLY READER
-------------------------------------------------
`docs/execution/v5/COMPANY_VALIDATION_MANIFEST.yaml` is authoritative. There
is deliberately no second copy — no list in a test, no list in a script, no
generator carrying the same names. A population that exists twice will
disagree with itself eventually, and second-pass metrics computed against a
silently changed population are worse than no metrics: they look like
progress.

The cohort assignment is not stored-and-trusted. It is stored AND re-derivable
from the manifest's own fields by `derive_cohorts`, and a test recomputes it.
That way a hand edit that moves one company between cohorts is caught, rather
than becoming the new truth.

THE MANIFEST IS CONFIGURATION, NOT EVIDENCE
--------------------------------------------
Nothing analysed at runtime may write here. A company's own website saying
"move this company to DEVELOPMENT" is a string in a document, and the only
reason to say so explicitly is that this program has already had to prove the
same property for market snapshots. `load()` returns frozen records and there
is no setter.

IT IS ALSO NOT AN ANSWER KEY
-----------------------------
The manifest records why a company is USEFUL TO TEST. It never records what
the answer should be. `_no_answer_key` refuses any field that would turn a
validation universe into a scoring rubric — because once an expected
recommendation is written down, every later measurement is measuring
agreement with the person who wrote it.
"""
from __future__ import annotations

import collections
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

CONTRACT = "company_validation_manifest.v1"

#: The one authoritative location. Resolved from this file so it does not
#: depend on the working directory.
MANIFEST_PATH = (pathlib.Path(__file__).resolve().parents[3] / "docs" /
                 "execution" / "v5" / "COMPANY_VALIDATION_MANIFEST.yaml")

TOTAL = 100
COHORT_TARGETS = {"DEVELOPMENT": 60, "REGRESSION": 20, "BLIND_HOLDOUT": 20}
COHORTS = tuple(COHORT_TARGETS)

NORTH_AMERICA = frozenset({"USA", "CANADA", "MEXICO"})

#: §14. Every one of these must be genuinely represented, so the universe
#: cannot reach 100 by repeating one archetype.
SECTOR_MINIMUMS = {
    "SOFTWARE_PLATFORM": 8, "SEMICONDUCTOR": 4, "INDUSTRIAL": 4,
    "FINANCIAL_REGULATED": 6, "HEALTHCARE": 4, "CONSUMER": 6,
    "INFRASTRUCTURE": 6, "MATERIALS_ENERGY": 6, "SERVICES": 2,
}

#: Attribute minimums, checked separately from sector because they cut across
#: it: a capital-intensive software company and a capital-light industrial
#: both exist and both are interesting.
ATTRIBUTE_MINIMUMS = {
    "capital_intensive": 20, "cyclical": 15, "multi_segment": 12,
    "private": 8, "sparse_or_withheld": 5, "identity_hard": 10,
    "heavily_regulated": 15, "canadian": 20,
}

#: Fields that would make this an answer key rather than a test universe.
FORBIDDEN_PREFIXES = ("expected_", "correct_", "ground_truth_", "should_")
FORBIDDEN_FIELDS = frozenset({
    "expected_recommendation", "expected_thesis", "expected_causal_effect",
    "expected_confidence", "expected_adversary_output", "answer", "label",
    "correct_answer", "target_recommendation",
})

#: §23. Ten slots, each a predicate. Order is part of the contract: a slot
#: earlier in this tuple claims its company first, so the selection cannot
#: depend on iteration order anywhere else.
BREAKER_SLOTS: Tuple[Tuple[str, Any], ...] = (
    ("software_platform",
     lambda c: c.sector == "SOFTWARE_PLATFORM" and c.public_private ==
     "PUBLIC"),
    ("semiconductor", lambda c: c.sector == "SEMICONDUCTOR"),
    ("industrial_cyclical",
     lambda c: c.sector == "INDUSTRIAL" and c.cyclicality_class ==
     "CYCLICAL"),
    ("regulated_financial",
     lambda c: c.sector == "FINANCIAL_REGULATED" and c.regulatory_class ==
     "HEAVILY_REGULATED"),
    ("consumer_or_healthcare", lambda c: c.sector in ("CONSUMER",
                                                      "HEALTHCARE")),
    ("capital_intensive", lambda c: c.capital_intensity_class == "HIGH"),
    ("canadian", lambda c: c.country == "CANADA"),
    ("private_high_coverage",
     lambda c: c.public_private == "PRIVATE" and c.coverage_expectation ==
     "HIGH_COVERAGE"),
    ("private_sparse",
     lambda c: c.public_private == "PRIVATE" and c.sparse_or_withheld),
    ("identity_or_source_hard",
     lambda c: c.identity_difficulty != "NORMAL" or c.source_difficulty !=
     "NORMAL"),
)


class ManifestInvalid(ValueError):
    """The manifest is not a usable validation universe."""


#: Corporate suffixes stripped before comparing two names for identity. Not a
#: cleanup: "Cloudflare, Inc." and "cloudflare" are the same company, and a
#: comparison that says otherwise silently drops it out of the universe.
_SUFFIXES = (
    "incorporated", "inc", "corporation", "corp", "company", "co",
    "limited", "ltd", "ltee", "llc", "lp", "plc", "sab de cv", "sab",
    "sa de cv", "nv", "ag", "group", "holdings", "holding",
)


def _identity_key(value: str) -> str:
    """Normalise a company name to something two spellings can share."""
    import re
    text = re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())
    words = [w for w in text.split() if w]
    while words and words[-1] in _SUFFIXES:
        words.pop()
    # "the boeing company" and "boeing" must meet.
    if words and words[0] == "the":
        words = words[1:]
    return "-".join(words)


@dataclass(frozen=True)
class Company:
    company_id: str
    canonical_name: str
    domain: str
    ticker: Optional[str]
    country: str
    entity_type: str
    sector: str
    public_private: str
    cohort: str
    cohort_locked: bool
    capital_intensity_class: str
    cyclicality_class: str
    regulatory_class: str
    coverage_expectation: str
    source_difficulty: str
    identity_difficulty: str
    company_size_class: str
    business_model_class: str
    multi_segment: bool
    sparse_or_withheld: bool
    parent_company_id: Optional[str]
    aliases: Tuple[str, ...]
    breaker_dimensions: Tuple[str, ...]
    manifest_source: str
    inclusion_reason: str
    industry: str = "UNKNOWN"
    primary_geography: str = "NORTH_AMERICA"

    @property
    def is_holdout(self) -> bool:
        return self.cohort == "BLIND_HOLDOUT"


@dataclass(frozen=True)
class Manifest:
    version: str
    created_at: str
    governing_plan_version: str
    companies: Tuple[Company, ...]
    change_history: Tuple[dict, ...] = ()

    def by_id(self, company_id: str) -> Optional[Company]:
        for c in self.companies:
            if c.company_id == company_id:
                return c
        return None

    def resolve(self, *, domain: str = "", name: str = "",
                company_id: str = "") -> Optional[Company]:
        """Find the manifest entry for a company the pipeline just analysed.

        WHY AN ID LOOKUP IS NOT ENOUGH. The analysis resolves a company to its
        LEGAL name — "Cloudflare, Inc.", "The Boeing Company" — which
        normalises to `cloudflare-inc` and `the-boeing-company`, neither of
        which is a manifest id. Matching on the id alone found nothing for
        essentially every real company, so every dossier was stamped with no
        cohort and no manifest version, which is indistinguishable from a
        company legitimately outside the universe. Nothing raised.

        DOMAIN FIRST, because it is the one identifier the operator supplied
        and the registry resolved, rather than one this side derived. Name and
        alias matching follow, and a corporate suffix is stripped before
        comparing so a legal name still meets its manifest entry.
        """
        want_domain = (domain or "").strip().lower().lstrip(".")
        if want_domain.startswith("www."):
            want_domain = want_domain[4:]
        if want_domain:
            for c in self.companies:
                have = (c.domain or "").strip().lower()
                if have and (have == want_domain
                             or want_domain.endswith("." + have)):
                    return c
        if company_id:
            direct = self.by_id(company_id)
            if direct is not None:
                return direct
        key = _identity_key(name)
        if key:
            for c in self.companies:
                candidates = [c.canonical_name, c.company_id, *c.aliases]
                if any(_identity_key(x) == key for x in candidates):
                    return c
        return None

    def cohort(self, name: str) -> Tuple[Company, ...]:
        return tuple(c for c in self.companies if c.cohort == name)

    def tally(self, field: str) -> Dict[str, int]:
        return dict(sorted(collections.Counter(
            str(getattr(c, field)) for c in self.companies).items()))


def _company(row: dict) -> Company:
    known = set(Company.__dataclass_fields__)
    unknown = [k for k in row if k not in known]
    _no_answer_key(row, unknown)
    kwargs = {k: v for k, v in row.items() if k in known}
    kwargs["aliases"] = tuple(row.get("aliases") or ())
    kwargs["breaker_dimensions"] = tuple(row.get("breaker_dimensions") or ())
    return Company(**kwargs)


def _no_answer_key(row: dict, unknown: Sequence[str]) -> None:
    """Refuse a row that encodes what the answer should be (§19)."""
    for key in row:
        low = str(key).lower()
        if low in FORBIDDEN_FIELDS or any(low.startswith(p)
                                          for p in FORBIDDEN_PREFIXES):
            raise ManifestInvalid(
                f"{row.get('company_id')}: field {key!r} encodes an expected "
                f"answer; the manifest records why a company is useful to "
                f"test, never what the analysis should conclude")


def load(path=None) -> Manifest:
    """Read the manifest. Frozen records; there is no writer here (§27)."""
    import yaml

    p = pathlib.Path(path or MANIFEST_PATH)
    if not p.exists():
        raise ManifestInvalid(f"no manifest at {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("contract") != CONTRACT:
        raise ManifestInvalid(
            f"{p}: contract is {raw.get('contract') if isinstance(raw, dict) else None!r}, "
            f"expected {CONTRACT!r}")
    return Manifest(
        version=str(raw.get("manifest_version") or ""),
        created_at=str(raw.get("created_at") or ""),
        governing_plan_version=str(raw.get("governing_plan_version") or ""),
        companies=tuple(_company(r) for r in (raw.get("companies") or ())),
        change_history=tuple(raw.get("change_history") or ()))


def derive_cohorts(companies: Sequence[Company]) -> Dict[str, str]:
    """Re-derive the cohort assignment from the manifest's own fields.

    Documented in the manifest header. Sorting by sector first spreads every
    sector across all three cohorts by construction, so no cohort can quietly
    accumulate the easy companies — which is the failure `derive` exists to
    make impossible rather than merely discouraged.
    """
    order = sorted(companies, key=lambda c: (c.sector, c.company_id))
    cycle = ["DEVELOPMENT", "DEVELOPMENT", "DEVELOPMENT", "REGRESSION",
             "BLIND_HOLDOUT"]
    return {c.company_id: cycle[i % 5] for i, c in enumerate(order)}


def _attributes(companies: Sequence[Company]) -> Dict[str, int]:
    return {
        "capital_intensive": sum(1 for c in companies
                                 if c.capital_intensity_class == "HIGH"),
        "cyclical": sum(1 for c in companies
                        if c.cyclicality_class == "CYCLICAL"),
        "multi_segment": sum(1 for c in companies if c.multi_segment),
        "private": sum(1 for c in companies
                       if c.public_private == "PRIVATE"),
        "sparse_or_withheld": sum(1 for c in companies
                                  if c.sparse_or_withheld),
        "identity_hard": sum(1 for c in companies
                             if c.identity_difficulty != "NORMAL"),
        "heavily_regulated": sum(1 for c in companies
                                 if c.regulatory_class == "HEAVILY_REGULATED"),
        "canadian": sum(1 for c in companies if c.country == "CANADA"),
    }


def validate(manifest: Manifest) -> List[str]:
    """Every reason this manifest is not a usable validation universe.

    Returns ALL problems rather than raising on the first. A validator that
    stops at the first fault makes fixing a manifest an iterative guessing
    game, and this program has already recorded what happens when validation
    fails on the FIRST unknown field: the mismatch has to be measured, fixed
    and re-measured one at a time.
    """
    problems: List[str] = []
    cs = manifest.companies

    if len(cs) != TOTAL:
        problems.append(f"expected {TOTAL} active companies, found {len(cs)}")

    ids = [c.company_id for c in cs]
    dupes = [k for k, v in collections.Counter(ids).items() if v > 1]
    if dupes:
        problems.append(f"duplicate company_id: {sorted(dupes)}")

    # Canonical identity, not display name (§20). A domain may legitimately
    # repeat ONLY where a parent/subsidiary relationship is declared.
    by_domain: Dict[str, List[Company]] = collections.defaultdict(list)
    for c in cs:
        by_domain[(c.domain or "").lower()].append(c)
    for domain, rows in sorted(by_domain.items()):
        if len(rows) > 1 and not any(r.parent_company_id for r in rows):
            problems.append(
                f"domain {domain!r} is shared by "
                f"{sorted(r.company_id for r in rows)} with no declared "
                f"parent/subsidiary relationship")

    names = collections.Counter((c.canonical_name or "").lower() for c in cs)
    dupe_names = [n for n, v in names.items() if v > 1]
    if dupe_names:
        problems.append(f"duplicate canonical_name: {sorted(dupe_names)}")

    alias_owner: Dict[str, str] = {}
    for c in cs:
        for alias in list(c.aliases) + [c.canonical_name]:
            key = str(alias).strip().lower()
            if not key:
                continue
            if key in alias_owner and alias_owner[key] != c.company_id:
                problems.append(
                    f"alias {alias!r} is claimed by both "
                    f"{alias_owner[key]} and {c.company_id}")
            alias_owner[key] = c.company_id

    tickers = collections.Counter(c.ticker for c in cs if c.ticker)
    dupe_tickers = [t for t, v in tickers.items() if v > 1]
    if dupe_tickers:
        problems.append(f"duplicate ticker: {sorted(dupe_tickers)}")

    for c in cs:
        if c.parent_company_id and not any(
                x.company_id == c.parent_company_id for x in cs):
            problems.append(
                f"{c.company_id}: parent {c.parent_company_id!r} is not in "
                f"the manifest")

    bad_cohorts = sorted({c.cohort for c in cs} - set(COHORTS))
    if bad_cohorts:
        problems.append(f"unknown cohort: {bad_cohorts}")
    counts = collections.Counter(c.cohort for c in cs)
    for name, target in COHORT_TARGETS.items():
        if counts.get(name, 0) != target:
            problems.append(
                f"cohort {name} has {counts.get(name, 0)}, expected {target}")

    unlocked = [c.company_id for c in cs if c.is_holdout and not
                c.cohort_locked]
    if unlocked:
        problems.append(f"blind holdout not locked: {sorted(unlocked)}")
    wrongly_locked = [c.company_id for c in cs if c.cohort_locked and not
                      c.is_holdout]
    if wrongly_locked:
        problems.append(
            f"cohort_locked set on a non-holdout: {sorted(wrongly_locked)}")

    outside = sorted({c.country for c in cs} - NORTH_AMERICA)
    if outside:
        problems.append(f"outside North America: {outside}")
    if not any(c.country == "USA" for c in cs):
        problems.append("no USA companies")
    if not any(c.country == "CANADA" for c in cs):
        problems.append("no Canadian companies")

    sectors = collections.Counter(c.sector for c in cs)
    for sector, minimum in sorted(SECTOR_MINIMUMS.items()):
        if sectors.get(sector, 0) < minimum:
            problems.append(
                f"sector {sector} has {sectors.get(sector, 0)}, "
                f"needs at least {minimum}")

    attrs = _attributes(cs)
    for name, minimum in sorted(ATTRIBUTE_MINIMUMS.items()):
        if attrs.get(name, 0) < minimum:
            problems.append(
                f"attribute {name} has {attrs.get(name, 0)}, "
                f"needs at least {minimum}")

    # Each cohort must be heterogeneous in its own right. All the hard
    # companies in DEVELOPMENT would make regression and holdout easy, and
    # the resulting pass rate would measure the split, not the product.
    for name in COHORTS:
        rows = manifest.cohort(name)
        if not rows:
            continue
        if len({c.sector for c in rows}) < 5:
            problems.append(
                f"cohort {name} spans only "
                f"{len({c.sector for c in rows})} sectors")
        if not any(c.country == "CANADA" for c in rows):
            problems.append(f"cohort {name} has no Canadian company")
        if not any(c.public_private == "PRIVATE" for c in rows):
            problems.append(f"cohort {name} has no private company")

    stored = {c.company_id: c.cohort for c in cs}
    if len(cs) == TOTAL and not dupes:
        derived = derive_cohorts(cs)
        drifted = sorted(k for k in stored if stored[k] != derived.get(k))
        if drifted:
            problems.append(
                f"stored cohorts differ from the documented rule: {drifted}")

    for c in cs:
        if not c.inclusion_reason:
            problems.append(f"{c.company_id}: no inclusion_reason")
        if not c.breaker_dimensions:
            problems.append(f"{c.company_id}: no breaker_dimensions")
        if c.entity_type not in ("OPERATING_COMPANY",
                                 "INVESTMENT_ORGANIZATION",
                                 "ADVISORY_ORGANIZATION"):
            problems.append(f"{c.company_id}: unknown entity_type "
                            f"{c.entity_type!r}")
    return problems


def breaker_ten(manifest: Manifest) -> Tuple[Company, ...]:
    """The deterministic first breaker wave (§23). SELECTION ONLY.

    Ten slots, filled in the fixed order of `BREAKER_SLOTS`, from DEVELOPMENT
    only. Deterministic from manifest metadata alone, so the ten are decided
    before any output is seen and cannot be swapped afterwards — which is the
    whole reason a selector exists rather than a list someone curates.

    WHY IT PREFERS UNSEEN SHAPES RATHER THAN THE LOWEST ID
    ------------------------------------------------------
    Taking the alphabetically first match per slot is deterministic and
    produced a bad wave: `capital_intensive` and `canadian` both resolved to
    Canadian gold miners, so two of ten slots tested one shape and the ten
    covered eight. The slots exist to buy COVERAGE, and a tie-break that
    ignores what the earlier slots already claimed spends them on duplicates.

    So the preference is: a (sector, country) pair nobody has taken, then a
    sector nobody has taken, then the lowest company_id. Every step is a
    total order over the manifest's own fields, so the result is still fixed
    before anything runs.
    """
    pool = sorted(manifest.cohort("DEVELOPMENT"), key=lambda c: c.company_id)
    chosen: List[Company] = []
    taken: set = set()
    seen_pairs: set = set()
    seen_sectors: set = set()
    for slot, predicate in BREAKER_SLOTS:
        matches = [c for c in pool
                   if c.company_id not in taken and predicate(c)]
        if not matches:
            raise ManifestInvalid(
                f"breaker slot {slot!r} cannot be filled from DEVELOPMENT; "
                f"the manifest does not contain the case it exists to test")
        pick = min(matches, key=lambda c: (
            (c.sector, c.country) in seen_pairs,
            c.sector in seen_sectors,
            c.company_id))
        taken.add(pick.company_id)
        seen_pairs.add((pick.sector, pick.country))
        seen_sectors.add(pick.sector)
        chosen.append(pick)
    return tuple(chosen)


def summary(manifest: Manifest) -> dict:
    """What the manifest IS. Deliberately no readiness or success figure —
    nothing has been run (§26)."""
    cs = manifest.companies
    return {
        "contract": CONTRACT,
        "manifest_version": manifest.version,
        "total_active": len(cs),
        "by_country": manifest.tally("country"),
        "by_cohort": manifest.tally("cohort"),
        "by_sector": manifest.tally("sector"),
        "by_entity_type": manifest.tally("entity_type"),
        "by_public_private": manifest.tally("public_private"),
        "by_coverage_expectation": manifest.tally("coverage_expectation"),
        "attributes": _attributes(cs),
        "breaker_dimensions": dict(sorted(collections.Counter(
            d for c in cs for d in c.breaker_dimensions).items())),
        "baseline_runs": 0,
        "note": ("no company in this manifest has been run; this describes "
                 "the universe, not any result over it"),
    }
