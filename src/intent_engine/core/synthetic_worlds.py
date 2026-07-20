"""T009 — Synthetic-world reasoning evaluation (founder-approved 2026-07-19,
raised to HIGH priority same day; Phase 3 of the densification plan,
built as the plan's EVALUATION variant — explicitly NOT model training).

WHAT THIS IS: fictional companies, industries, and events with CONSTRUCTED
ground-truth outcomes, used to test the mechanism engine's causal
reasoning with zero memorization risk. A world plants the observable
symptoms of a known mechanism in fully fictional dress — written to read
as close to a real analyst situation brief as possible (concrete
magnitudes, named fictional actors, market texture) — and the engine is
scored on recovering the constructed ground truth it cannot possibly have
memorized. Realism is deliberate (founder direction 2026-07-19: "as close
to the real world as possible; work the base well"): the harder the
worlds look like real situations while remaining invented, the more the
result measures reasoning rather than pattern lookup.

WHAT THIS IS NOT (recorded so it can never be misquoted): NOT a
forward-market accuracy measure, NOT calibration evidence, NOT a
marketing claim, and NOT training — no model weights, prompts, enums, or
library data are changed by anything here. It is a reasoning DIAGNOSTIC.
Its second output is an expressiveness map of the frozen TriggerCondition
enum: which mechanisms it can uniquely discriminate and which collapse
into tied classes (evidence for the founder's deferred enum decision —
evidence, not a recommendation). The generator is also the reusable BASE
for any future synthetic-world work; using it to produce training data
would be a separate capability requiring its own founder approval.

Two layers:
- OFFLINE (this module + tests, zero LLM calls): deterministic generator,
  leakage walls, matcher-level eval.
- LIVE (scripts/run_synthetic_world_eval.py --live, Mac only): the frozen
  extraction prompt reads each fictional narrative -> conditions ->
  matcher. Gated: sandbox has no Anthropic egress; the harness asserts
  the extraction prompt's sha256 is byte-identical to the frozen
  gate-verified value before any call.

Determinism: every function is pure given (seed, library); the default
world set is reproducible byte-for-byte (asserted in tests).
"""

from __future__ import annotations

import re
from random import Random
from typing import Dict, List, NamedTuple, Sequence, Tuple

from .mechanism_library import Mechanism, TriggerCondition, load_mechanisms, match_mechanisms

DEFAULT_SEED = 20260719

# --- fictional entity generation -------------------------------------------
# Syllable-combinatoric names: pronounceable, plainly invented, and checked
# (leakage wall e) against the real library text so no generated entity can
# collide with a documented historical actor.

_NAME_PREFIXES = (
    "Vel", "Nor", "Quen", "Zar", "Tal", "Mir", "Osk", "Fen", "Dru", "Hax",
    "Lom", "Bryn", "Cal", "Yst", "Pel", "Gorv", "Wex", "Jun", "Ard", "Sil",
)
_NAME_SUFFIXES = (
    "trix", "dyne", "mera", "vault", "forge", "gate", "lyth", "cor", "nova",
    "band", "stell", "quill", "mark", "field", "row",
)
_NAME_FORMS = ("Systems", "Holdings", "Group", "Industries", "Partners", "Labs")
_LENDER_FORMS = ("Mercantile Bank", "Commercial Credit", "Finance House", "Lending Co-operative")
_REGULATOR_FORMS = ("Standards Authority", "Licensing Board", "Oversight Commission")

_SECTORS = (
    "modular seawall construction", "orbital greenhouse logistics",
    "synthetic resin recycling", "autonomous barge freight",
    "geothermal data-cooling", "vertical mushroom farming",
    "industrial kelp processing", "drone-swarm land surveying",
    "prefabricated habitat manufacturing", "closed-loop battery refurbishing",
    "high-altitude wind capture", "cargo airship leasing",
)


def _invented_token(rng: Random) -> str:
    return rng.choice(_NAME_PREFIXES) + rng.choice(_NAME_SUFFIXES)


def _company_name(rng: Random) -> str:
    return _invented_token(rng) + " " + rng.choice(_NAME_FORMS)


class WorldCast(NamedTuple):
    company: str
    rival: str
    lender: str
    regulator: str
    sector: str


def _cast(rng: Random) -> WorldCast:
    return WorldCast(
        company=_company_name(rng),
        rival=_company_name(rng),
        lender=_invented_token(rng) + " " + rng.choice(_LENDER_FORMS),
        regulator="the " + _invented_token(rng) + " " + rng.choice(_REGULATOR_FORMS),
        sector=rng.choice(_SECTORS),
    )


# --- condition -> realistic fictional symptom units ------------------------
# Each of the 16 frozen enum conditions gets >=2 original two-sentence
# paraphrase units with seeded numeric parameters drawn from realistic
# ranges — analyst-brief texture, zero real-world anchors. The leakage
# walls below assert none of these (nor any assembled narrative) contains
# an enum token, an enum phrase, a mechanism name, a real-world anchor, or
# an 8-word shingle of library text — the extractor must map MEANING to
# condition, never string-match.

# param -> (low, high, decimals); drawn per-world from the seeded rng.
_PARAM_SPECS: Dict[str, Tuple[float, float, int]] = {
    "dd_pct": (22, 38, 0),        # peak-to-now decline, %
    "spread_pts": (5.2, 9.5, 1),  # risky-vs-safe borrowing premium, pts
    "short_yld": (4.4, 5.6, 1),   # short government paper yield, %
    "long_yld": (3.1, 4.2, 1),    # long government paper yield, %
    "yoy_now": (6.0, 11.0, 1),    # price growth now, %
    "yoy_prior": (2.1, 3.4, 1),   # price growth a year ago, %
    "unemp_delta": (0.4, 0.9, 1), # jobless-rate rise over two quarters, pts
    "debt_share": (80, 95, 0),    # % of buildout funded by borrowing
    "leverage_x": (3.2, 5.4, 1),  # liabilities-to-equity multiple
    "cap_growth": (40, 70, 0),    # capacity growth, %
    "order_growth": (3, 8, 0),    # order-book growth, %
    "supplier_share": (85, 96, 0),# top-3 suppliers' share of input, %
    "market_share": (72, 90, 0),  # top-3 firms' share of market, %
    "rev_mult": (9, 16, 0),       # price-implied revenue multiple
    "peer_mult": (2, 3, 0),       # peer-average revenue multiple
    "cross_share": (30, 60, 0),   # balance-sheet share owed to industry peers, %
    "retention_pp": (4, 9, 0),    # retention gain at doubled scale, pts
    "match_hours": (48, 96, 0),   # rival price-match lag, hours
    "filings_per_q": (5, 9, 0),   # regulator touchpoints per quarter
    "attach_pct": (25, 45, 0),    # cross-sell attach rate, %
}

CONDITION_SYMPTOMS: Dict[str, Tuple[str, ...]] = {
    "adjacent_market_bundling_opportunity": (
        "Roughly {attach_pct}% of {company}'s customers already buy a neighboring service the firm resells informally. Folding that adjoining line into the core {sector} offering would reach accounts {rival} cannot serve with its narrower catalogue.",
        "Management's board memo highlights an adjoining product category with {attach_pct}% organic attach among existing accounts. Packaging it with the main platform is an opening none of the incumbent rivals is positioned to match.",
    ),
    "binding_mutual_commitment_exists": (
        "{company} is party to a standing industry pact under which any member drawn into a commercial dispute must be backed by the others, with penalty clauses for abstention. Counsel confirms there is no unilateral exit short of a two-year notice period.",
        "A signed mutual-support compact obliges each member firm, {company} included, to honor the others' obligations in full if called upon. The agreement has already been invoked once this year against a smaller member.",
    ),
    "capacity_investment_outpacing_demand_signal": (
        "Announced {sector} capacity is on track to grow {cap_growth}% within eighteen months, while industry order books have expanded only {order_growth}% over the same span. {lender} financed three of the five new facilities without customer commitments attached.",
        "New plants are being financed far faster than bookings justify: capacity up {cap_growth}%, confirmed orders up {order_growth}%. Several projects broke ground before a single anchor customer signed.",
    ),
    "concentrated_supplier_base": (
        "Three producers control roughly {supplier_share}% of the industry's critical input, and {company} single-sources its highest-grade feedstock from one of them. Procurement's contingency list has no qualified alternative at current specifications.",
        "{company}'s cost base hangs on an input market where the top three vendors hold {supplier_share}% share between them. A capacity outage at any one of them has no near-term substitute.",
    ),
    "credit_spreads_elevated": (
        "Lower-rated {sector} issuers now pay {spread_pts} percentage points over safe benchmarks to borrow, the widest premium in the sector index's history. Two recent note offerings were pulled for lack of demand at the offered coupon.",
        "The premium lenders demand from the industry's riskier borrowers has widened to {spread_pts} points over the safe rate. {lender} has quietly stopped extending unsecured lines to sub-prime names in the space.",
    ),
    "curve_inverted": (
        "Short-dated government paper in the region yields {short_yld}%, above the {long_yld}% on long-dated bonds — the reward for lending long has flipped negative. Bank margins on maturity transformation are compressing accordingly.",
        "The domestic bond market now pays {short_yld}% at the short end against {long_yld}% at the long end. Funding desks describe the flip as the tightest they have worked through.",
    ),
    "debt_financed_expansion": (
        "About {debt_share}% of {company}'s buildout is funded with borrowed money, taking liabilities to {leverage_x} times equity. {lender} holds the senior tranche and has begun asking for weekly covenant reporting.",
        "The expansion program is bankrolled almost entirely by debt — {debt_share}% of committed capital — leaving the balance sheet levered at {leverage_x}x. Interest cover would thin sharply in any revenue stall.",
    ),
    "drawdown_gt_20pct": (
        "The {sector} benchmark has fallen {dd_pct}% from its peak of nine weeks ago, with the selling broad rather than confined to weak names. Margin desks report clients trimming positions into the decline.",
        "Prices across {sector} assets sit {dd_pct}% below their recent high after a fast, indiscriminate slide. Fund redemption notices in the space have doubled quarter over quarter.",
    ),
    "few_dominant_competitors": (
        "Three firms — {company}, {rival}, and one smaller operator — hold about {market_share}% of the market between them. Entry at scale has not succeeded in a decade.",
        "The market is effectively a three-firm contest, with the leaders controlling {market_share}% of volume. Customers report no credible fourth option at national scale.",
    ),
    "frequent_regulatory_interaction": (
        "{company} logs {filings_per_q} formal touchpoints with {regulator} per quarter, and no product change ships without its sign-off. Two senior hires this year came directly from the agency's technical staff.",
        "Firms in this space live under {regulator}: {filings_per_q} filings a quarter and pre-clearance on every material product decision. Compliance is the second-largest cost line after payroll.",
    ),
    "inflation_rising": (
        "Consumer prices in the region are rising {yoy_now}% year over year, up from {yoy_prior}% a year ago, with the acceleration broad across staples and services. Wage settlements are beginning to reference the new pace.",
        "Household price growth has quickened for four straight quarters and now runs {yoy_now}% annually against {yoy_prior}% previously. Suppliers are writing escalator clauses into new contracts.",
    ),
    "interconnected_counterparty_exposure": (
        "Roughly {cross_share}% of the industry's aggregate balance sheet consists of obligations to other firms in the same industry — mutual lending, shared settlement lines, cross-held paper. A failure at any mid-sized member would transmit within days.",
        "Balance sheets across the {sector} space are densely cross-linked: {cross_share}% of liabilities are owed peer-to-peer, much of it callable on short notice. Risk officers privately concede no firm can fail alone.",
    ),
    "network_effects_present": (
        "Each new participant makes {company}'s platform more valuable to every existing one; retention runs {retention_pp} points higher in regions where the user base has doubled. The dynamic compounds rather than saturates so far.",
        "{company}'s service grows stickier with scale — cohort retention improves {retention_pp} points as local density doubles. Rivals with smaller networks lose share on identical pricing.",
    ),
    "symmetric_competitor_response_expected": (
        "Every list-price move {company} has made in three years was matched by {rival} within {match_hours} hours, and vice versa. Both sales teams openly quote the other's sheet in negotiations.",
        "Pricing in the market is mirror-fast: rivals match within {match_hours} hours, and all sides know it. No move has produced a lasting share shift in recent memory.",
    ),
    "unemployment_momentum_triggered": (
        "The regional jobless rate has risen {unemp_delta} points over two quarters after a long stretch at cycle lows, and layoff announcements are accelerating. Hiring plans in the latest business survey rolled over for the first time in years.",
        "Joblessness is now climbing quarter over quarter — up {unemp_delta} points from its low — while vacancy postings thin. Temporary-staffing hours, the early gauge, turned down first.",
    ),
    "valuation_disconnected_from_fundamentals": (
        "Market prices imply {rev_mult} times current revenue for {sector} firms against a {peer_mult}x average elsewhere, a gap present earnings cannot begin to support. New entrants are being funded at those marks on projections alone.",
        "{company} trades at {rev_mult}x revenue while comparable businesses outside the theme fetch {peer_mult}x. The premium rests on a growth story no current operating figure yet evidences.",
    ),
}

# Neutral filler: realistic corporate texture that implies NO enum
# condition. In control worlds this is joined by explicitly HEALTHY
# metrics (below) so the live extractor is tested against topical bait —
# a world can mention prices, suppliers, and debt while none of the
# conditions actually hold.
DISTRACTOR_SENTENCES: Tuple[str, ...] = (
    "{company} recently redesigned its logo and refreshed its brand palette.",
    "The {sector} trade association's annual conference drew record attendance this year.",
    "{company} opened a new office campus with an on-site cafeteria and gym.",
    "A long-serving board member retired after two decades with the firm.",
    "{company} published its annual sustainability report on schedule.",
    "Average employee tenure at {company} runs above the industry norm.",
    "The founder still hosts a monthly all-hands question session.",
    "{company} sponsors a regional robotics competition for secondary schools.",
)

HEALTHY_CONTROL_SENTENCES: Tuple[str, ...] = (
    "Consumer prices in the region are rising about two percent a year, in line with the long-run norm.",
    "{company} buys inputs from more than forty qualified vendors, none supplying over five percent of volume.",
    "The buildout is funded from retained earnings, with liabilities under half of equity.",
    "The {sector} benchmark trades within a few percent of its recent high on steady volume.",
    "Short-dated government paper yields comfortably less than long-dated bonds, as usual.",
    "Regional employment has been stable, with the jobless rate flat at cycle lows for six quarters.",
    "Lower-rated issuers in the space borrow at a modest, stable premium to safe benchmarks.",
    "Valuations sit near long-run averages for businesses of this margin profile.",
)


class SyntheticWorld(NamedTuple):
    world_id: str
    world_type: str  # "single" | "mixed" | "control"
    company: str
    sector: str
    narrative: str
    planted_conditions: Tuple[str, ...]
    ground_truth_mechanisms: Tuple[str, ...]  # () for control worlds


def _draw_params(rng: Random) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, (lo, hi, dec) in _PARAM_SPECS.items():
        val = rng.uniform(lo, hi)
        out[name] = f"{val:.{dec}f}" if dec else f"{int(round(val))}"
    # keep the yield pair economically coherent (short strictly above long)
    if float(out["short_yld"]) <= float(out["long_yld"]):
        out["short_yld"], out["long_yld"] = out["long_yld"], out["short_yld"]
        if out["short_yld"] == out["long_yld"]:
            out["short_yld"] = f"{float(out['short_yld']) + 0.4:.1f}"
    # inflation now strictly above prior
    if float(out["yoy_now"]) <= float(out["yoy_prior"]):
        out["yoy_now"] = f"{float(out['yoy_prior']) + 3.1:.1f}"
    return out


def _symptom(condition: str, variant: int, cast: WorldCast, params: Dict[str, str]) -> str:
    templates = CONDITION_SYMPTOMS[condition]
    return templates[variant % len(templates)].format(
        company=cast.company, rival=cast.rival, lender=cast.lender,
        regulator=cast.regulator, sector=cast.sector, **params)


GENERATOR_VERSION = "1.1"
# v1.1 (2026-07-20, from the first LIVE run's key negative finding): the
# v1.0 opener said "its principal competitor is {rival}" in EVERY world,
# and the live extractor read that as few_dominant_competitors 67 times
# where it was not planted (precision 0.68 with perfect 1.00 recall; 5/8
# controls lost clean silence to it). That was a generator artifact, not
# purely a model failure — so the opener is now CONDITIONAL: worlds that
# plant few_dominant_competitors keep the concentrated phrasing (their
# symptom sentence agrees); all other worlds describe a broad field, which
# turns the named rival into honest counter-evidence bait instead of an
# accidental oligopoly cue. v1.0's live results stay on record; live
# numbers for v1.1 need a fresh Mac run.


def _opener(cast: WorldCast, planted: Sequence[str]) -> str:
    lead = f"Situation brief, prepared for the board of {cast.company}. "
    if "few_dominant_competitors" in planted:
        return lead + (
            f"{cast.company} operates in the {cast.sector} industry, where its "
            f"principal competitor is {cast.rival}."
        )
    return lead + (
        f"{cast.company} operates in the {cast.sector} industry, one of a "
        f"broad field of firms competing there that includes {cast.rival}."
    )


def _build_narrative(rng: Random, cast: WorldCast,
                     conditions: Sequence[str], variant: int) -> str:
    params = _draw_params(rng)
    units = [_symptom(c, variant + i, cast, params) for i, c in enumerate(conditions)]
    filler = [
        s.format(company=cast.company, sector=cast.sector)
        for s in rng.sample(DISTRACTOR_SENTENCES, 3)
    ]
    body = units + filler
    rng.shuffle(body)
    return " ".join([_opener(cast, conditions)] + body)


def generate_worlds(
    seed: int = DEFAULT_SEED,
    singles_per_mechanism: int = 3,
    mixed_count: int = 12,
    control_count: int = 8,
) -> List[SyntheticWorld]:
    """The full deterministic world set: for each of the 23 mechanisms,
    `singles_per_mechanism` fictional worlds planting exactly that
    mechanism's trigger set; `mixed_count` two-mechanism worlds planting
    the union of two distinct trigger sets; `control_count` healthy-world
    controls where the constructed truth is that NOTHING is in play."""
    rng = Random(seed)
    mechanisms = sorted(load_mechanisms(), key=lambda m: m.mechanism_id)
    worlds: List[SyntheticWorld] = []

    for m in mechanisms:
        for k in range(singles_per_mechanism):
            cast = _cast(rng)
            narrative = _build_narrative(rng, cast, sorted(m.trigger_conditions), k)
            worlds.append(SyntheticWorld(
                world_id=f"single-{m.mechanism_id}-{k}",
                world_type="single", company=cast.company, sector=cast.sector,
                narrative=narrative,
                planted_conditions=tuple(sorted(m.trigger_conditions)),
                ground_truth_mechanisms=(m.mechanism_id,),
            ))

    distinct_pairs = [
        (a, b) for i, a in enumerate(mechanisms) for b in mechanisms[i + 1:]
        if set(a.trigger_conditions) != set(b.trigger_conditions)
    ]
    for k, (a, b) in enumerate(rng.sample(distinct_pairs, mixed_count)):
        cast = _cast(rng)
        planted = tuple(sorted(set(a.trigger_conditions) | set(b.trigger_conditions)))
        narrative = _build_narrative(rng, cast, planted, k)
        worlds.append(SyntheticWorld(
            world_id=f"mixed-{a.mechanism_id}--{b.mechanism_id}",
            world_type="mixed", company=cast.company, sector=cast.sector,
            narrative=narrative, planted_conditions=planted,
            ground_truth_mechanisms=tuple(sorted((a.mechanism_id, b.mechanism_id))),
        ))

    for k in range(control_count):
        cast = _cast(rng)
        healthy = [
            s.format(company=cast.company, sector=cast.sector)
            for s in rng.sample(HEALTHY_CONTROL_SENTENCES, 4)
        ]
        filler = [
            s.format(company=cast.company, sector=cast.sector)
            for s in rng.sample(DISTRACTOR_SENTENCES, 3)
        ]
        body = healthy + filler
        rng.shuffle(body)
        worlds.append(SyntheticWorld(
            world_id=f"control-{k}", world_type="control", company=cast.company,
            sector=cast.sector, narrative=" ".join([_opener(cast, ())] + body),
            planted_conditions=(), ground_truth_mechanisms=(),
        ))

    return worlds


# --- leakage walls ----------------------------------------------------------

# Leakage wall (c): real-world anchors that would let a reader shortcut to
# a memorized episode instead of reasoning causally. Word-boundary matched.
BANNED_REAL_ANCHORS: Tuple[str, ...] = (
    "lehman", "ltcm", "volcker", "covid", "knickerbocker", "caldwell",
    "oapec", "opec", "nikkei", "fomc", "fed", "treasury", "nber", "bls",
    "dow", "nasdaq", "aol", "warner", "paramount", "spacex", "enron",
    "bear stearns", "reserve primary", "black monday", "japan", "asia",
    "1873", "1907", "1929", "1930", "1933", "1973", "1982", "1987", "1990",
    "1997", "1998", "2000", "2002", "2008", "2011", "2020", "2021", "2022",
)

_ENUM_CONDITIONS: Tuple[str, ...] = tuple(TriggerCondition.__args__)


def _library_text_blobs() -> List[str]:
    blobs: List[str] = []
    for m in load_mechanisms():
        blobs.append(m.name)
        blobs.extend(m.causal_chain)
        for inst in m.historical_instances:
            blobs.append(inst.case)
            blobs.append(inst.source)
    return blobs


def _shingles(text: str, n: int = 8) -> set:
    words = re.findall(r"[a-z']+", text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def assert_leakage_walls(worlds: Sequence[SyntheticWorld]) -> None:
    """Zero-memorization-risk, enforced not assumed. Raises on the first
    violation: (1) no enum identifier token; (2) no space-joined enum
    phrase; (3) no mechanism_id or mechanism display name; (4) no banned
    real-world anchor (word-boundary); (5) no 8-word shingle shared with
    any library causal_chain/instance text; (6) planted conditions are
    valid members of the frozen enum."""
    mechanisms = load_mechanisms()
    mech_names = [m.name.lower() for m in mechanisms]
    mech_ids = [m.mechanism_id for m in mechanisms]
    library_shingles = set()
    for blob in _library_text_blobs():
        library_shingles |= _shingles(blob)

    for w in worlds:
        low = w.narrative.lower()
        for cond in _ENUM_CONDITIONS:
            if cond in low:
                raise ValueError(f"{w.world_id}: enum token {cond!r} leaked into narrative")
            phrase = cond.replace("_", " ")
            if phrase in low:
                raise ValueError(f"{w.world_id}: enum phrase {phrase!r} leaked into narrative")
        for mid in mech_ids:
            if mid in low or mid.replace("_", " ") in low:
                raise ValueError(f"{w.world_id}: mechanism id {mid!r} leaked into narrative")
        for name in mech_names:
            if name.lower() in low:
                raise ValueError(f"{w.world_id}: mechanism name {name!r} leaked into narrative")
        for anchor in BANNED_REAL_ANCHORS:
            if re.search(rf"\b{re.escape(anchor)}\b", low):
                raise ValueError(f"{w.world_id}: real-world anchor {anchor!r} leaked into narrative")
        overlap = _shingles(w.narrative) & library_shingles
        if overlap:
            raise ValueError(f"{w.world_id}: {len(overlap)} 8-word shingle(s) copied from library text")
        for cond in w.planted_conditions:
            if cond not in _ENUM_CONDITIONS:
                raise ValueError(f"{w.world_id}: planted condition {cond!r} is not in the frozen enum")


def assert_fictional_entities(worlds: Sequence[SyntheticWorld]) -> None:
    """Wall (e): no generated entity token appears anywhere in the real
    library text — the fictional cast is provably disjoint from the
    documented historical cast."""
    library_text = " ".join(_library_text_blobs()).lower()
    for w in worlds:
        base = w.company.split(" ")[0].lower()  # the invented token, minus the generic form word
        if base in library_text:
            raise ValueError(f"{w.world_id}: fictional entity {w.company!r} collides with library text")


# --- offline evaluation (matcher-level causal mapping) ----------------------

class WorldResult(NamedTuple):
    world_id: str
    world_type: str
    ground_truth: Tuple[str, ...]
    top_tier: Tuple[str, ...]       # mechanism_ids sharing the max overlap
    tier_size: int
    identified: bool                # constructed truth recovered (see scorer)
    unique_top: bool                # top tier is exactly the ground truth


def evaluate_world_conditions(world: SyntheticWorld,
                              conditions: Sequence[str]) -> WorldResult:
    """Score ONE world given a set of conditions (planted for the offline
    eval; model-extracted for the live leg — same scorer, so the two legs
    are directly comparable)."""
    ranked = match_mechanisms(list(conditions)) if conditions else []
    if not ranked:
        top: Tuple[str, ...] = ()
    else:
        max_overlap = ranked[0].overlap_count
        top = tuple(r.mechanism.mechanism_id for r in ranked if r.overlap_count == max_overlap)
    gt = set(world.ground_truth_mechanisms)
    if world.world_type == "control":
        identified = not ranked          # constructed truth: silence
        unique_top = not ranked
    elif world.world_type == "mixed":
        # each planted mechanism must surface with FULL own-set overlap
        by_id = {r.mechanism.mechanism_id: r for r in ranked}
        full = {m.mechanism_id: set(m.trigger_conditions) for m in load_mechanisms()}
        identified = all(
            g in by_id and by_id[g].overlap_count == len(full[g]) for g in gt
        )
        unique_top = set(top) == gt
    else:
        identified = gt <= set(top)
        unique_top = set(top) == gt
    return WorldResult(world.world_id, world.world_type, tuple(sorted(gt)),
                       top, len(top), identified, unique_top)


def run_offline_eval(worlds: Sequence[SyntheticWorld]) -> List[WorldResult]:
    return [evaluate_world_conditions(w, w.planted_conditions) for w in worlds]


def enum_expressiveness_map() -> Dict[str, Tuple[str, ...]]:
    """For every mechanism: the tied top class when exactly its own trigger
    set is observed — i.e., every mechanism the frozen enum CANNOT
    distinguish from it on its own best evidence (identical sets tie;
    supersets tie too, since overlap is capped by the observed set).
    Size-1 values are the uniquely-identifiable mechanisms. Pure library
    analysis, no worlds, no LLM."""
    mechanisms = load_mechanisms()
    out: Dict[str, Tuple[str, ...]] = {}
    for m in mechanisms:
        planted = set(m.trigger_conditions)
        tied = [
            x.mechanism_id for x in mechanisms
            if len(planted & set(x.trigger_conditions)) == len(planted)
        ]
        out[m.mechanism_id] = tuple(sorted(tied))
    return out


DIAGNOSTIC_DISCLAIMER = (
    "SCOPE (recorded so it cannot be misquoted): this is a causal-reasoning "
    "diagnostic on constructed fictional worlds. It is NOT a forward-market "
    "accuracy measure, NOT calibration evidence, NOT a marketing claim, and "
    "it changes no prompt, enum, or library data. Fictional worlds cannot "
    "be memorized; that is the point of the design."
)

_FORBIDDEN_REPORT_PATTERNS = (
    r"\bforecast accuracy\b", r"\btrack record\b", r"\bcalibrated\b",
    r"\bproves\b", r"\bmarket-beating\b",
)


def assert_report_language_walls(rendered: str) -> None:
    low = rendered.lower()
    violations = [p for p in _FORBIDDEN_REPORT_PATTERNS if re.search(p, low)]
    if violations:
        raise ValueError(f"Synthetic-eval report language wall violation(s): {violations}")
    if DIAGNOSTIC_DISCLAIMER not in rendered:
        raise ValueError("Synthetic-eval report missing the scope disclaimer")
