"""Scrap-metal coarse-estimate domain -- the ORIGINAL use case this whole
project traces back to, not built until now. Mirrors
core/image_verification.py's isolated-call scaffold (one minimal, separate
Claude vision call), but the output is a coarse, honestly-labeled
COMPARATIVE grade impression, never a composition percentage.

This ceiling is not a limitation to work around -- it's load-bearing. A
vision model cannot see hidden material composition from a photo, the same
reason professional scrap buyers still carry XRF meters despite decades of
visual experience. Nothing in ScrapEstimate or SCRAP_SYSTEM_PROMPT below
asks for or permits a per-lot purity/alloy/composition estimate, anywhere.
category_typical_yield_note is one deliberate exception, narrowly scoped: a
cited, industry-sourced range for the IDENTIFIED ITEM TYPE in general, never
a claim about this specific lot's actual measured content.

Review-only, mirroring /verify -- NO correction loop attached. Grading
feedback is almost certainly criterion-shaped, the exact confirmed failure
mode found during image-verification's checkpoint. Not attempted here.

STRUCTURAL FIX (see the 9-photo sequential-run checkpoint): the visual
judgment of the CURRENT photo is computed by a call that NEVER receives any
prior-lot text -- identical whether it's the 1st photo for an entity or the
50th. comparison_note is a SEPARATE, deterministic computation built from
prior lots' STORED STRUCTURED FIELDS (parsed back from JSON behind
_SCRAP_CHECK_MARKER), never re-judging what the current photo shows.

condition_note (compute_condition_note): a plain-language, buyer-recognizable
synthesis of oxidation_level + grade_impression + visible_contamination.
Fully deterministic, never asked of the LLM.

category_proportions / material_composite: a SECOND real extraction task,
added after two measured reliability passes (v1: unstable free-text
vocabulary; v2: closed taxonomy + 3 votes, dominant category stabilized but
secondary categories still wobbled and "unclear" never fired). v3 (this
version): 5 votes instead of 3, and bin-wobble is turned into HONEST RANGE
WIDTH (union of observed bins) rather than resolved away.

MATH REVISION (this pass) -- fixes a real defect the first composite build
had: percentages exceeding 100% on 7 of 8 real test photos. Root cause: the
original normalization scaled every category's range by a single factor to
force the MIDPOINT to sum to 100%, which can push a dominant category's own
HIGH end past 100. Fixed at the root, not with a cosmetic clamp, via two
independent changes:
1. _normalize_category_shares now only corrects shares when the aggregate is
   actually inconsistent (sum of lows > 100, or sum of highs < 100) --
   scaling lows DOWN only if they jointly overclaim, highs UP only if they
   jointly underclaim, using a SINGLE scalar per side (not per-category
   weights), which provably preserves each category's own low <= high
   ordering and keeps every individual value in [0, 100].
2. compute_material_composite no longer sums independent low x low / high x
   high products across categories (which can exceed 100% even when the
   shares themselves are valid, since it doesn't respect the constraint that
   shares must sum to 100). It computes two candidate weighted averages per
   material -- one using weight_low (each category's normalized low share /
   sum of lows) and one using weight_high (normalized high share / sum of
   highs), each a valid probability distribution (nonnegative, summing to
   1) -- applied to BOTH the material profile's low and high fraction:
       val_A_lo = sum(weight_low_i  * material_lo_i), val_A_hi = sum(weight_low_i  * material_hi_i)
       val_B_lo = sum(weight_high_i * material_lo_i), val_B_hi = sum(weight_high_i * material_hi_i)
       composite_lo = min(val_A_lo, val_B_lo);  composite_hi = max(val_A_hi, val_B_hi)
   An earlier version of this fix used weight_low ONLY for the low output
   and weight_high ONLY for the high output -- that is NOT safe: the two
   weight vectors favor different categories, so it's possible for
   sum(weight_low_i * material_lo_i) to exceed sum(weight_high_i *
   material_hi_i) when the categories they emphasize have very different
   material profiles (found by real property-fuzz testing, not by
   inspection -- see git history of this file). The min/max-of-two-
   weightings construction above is provably safe: for ANY single fixed
   weighting w (nonnegative, summing to 1), sum(w_i * material_lo_i) <=
   sum(w_i * material_hi_i) pointwise, since material_lo_i <= material_hi_i
   for every category. So composite_lo = min(val_A_lo, val_B_lo) <= val_A_lo
   <= val_A_hi <= max(val_A_hi, val_B_hi) = composite_hi, ALWAYS -- ordering
   is guaranteed by that chain of inequalities, not asserted. Each val_* is
   itself a weighted average of values within [0, 100], so it's within
   [0, 100] too (basic convexity), and min/max of in-bounds values stays in
   bounds. Both guarantees (bounded, ordered) are arithmetic consequences of
   the formula, never a clamp. Property-tested in tests/test_scrap_estimate.py.

Per-supplier calibration (compute_material_composite's calibrated_yields
param, _compute_calibrated_yields): once >=3 real weigh-ins exist for an
entity where a given category was DOMINANT in the matched estimate, this
entity's own observed yield for that category (actual_material_pct /
dominant_category_share_fraction, averaged across qualifying weigh-ins) is
used in place of the generic/cited industry range for that category,
labeled accordingly. Falls back to the generic range with an explicit "no
weigh-ins yet" label until 3 weigh-ins exist for a category. Every rendered
estimate that still uses ANY generic (uncalibrated) category states "Range
narrows as real weigh-ins accumulate for this supplier" -- the day-one width
is a starting point, not the product's ceiling.

Within-bin refinement (_refine_unanimous_category): when all 5
category_proportions votes agree on the SAME bin for a category (genuine
unanimity, not just meeting the inclusion threshold), one additional narrow
query asks whether the true share sits in the lower/middle/upper third of
that bin's range -- narrowing width specifically where the signal was
already maximally consistent, never where votes wobbled.

Shipment-level aggregation (aggregate_shipment_estimates): combines multiple
photos' composites as independent samples of ONE underlying population (the
same physical shipment), narrowing width by 1/sqrt(N) -- the standard
reduction from averaging N independent measurements of the same quantity.
This is a real, named, load-bearing ASSUMPTION (independent per-photo
estimation error, not systematically correlated by lighting/angle), stated
explicitly, not proven.

Windings copper-fraction sourcing: a real web search was run (Okon
Recycling, ScrapMonster-adjacent sources, scrap-forum discussion, stator-
stripping-equipment vendor pages) specifically for a citable copper fraction
of an ALREADY-STRIPPED stator/winding assembly, distinct from whole-motor
figures. None of the three sources fetched gave a specific figure for this
-- all only discuss whole-motor copper content (7-18%, already cited) or
extraction-equipment recovery RATES (92-99% of however much copper is
present, a different quantity entirely). The 20-40% assumption range for
exposed_copper_windings_stators is kept, unchanged, explicitly still an
assumption, not narrowed on vibes.

The calibration loop and everything above it deliberately does NOT auto-
adjust anything without a person's real weigh-in data driving it -- surfacing
the gap/using calibrated yields once enough real data exists is honest and
useful; nothing here invents calibration from fewer than 3 real weigh-ins.

Cross-field physical-coherence check (compute_coherence_note): copper_exposure
and category_proportions are two INDEPENDENT isolated LLM judgments about the
same photo, but they describe physically linked facts -- e.g. "exposed,
stripped copper windings visible" and "the exposed_copper_windings_stators
category is a minimal-or-absent share of the sample" cannot both be true of
the same photo. This is the "structured priors over statistical rediscovery"
principle (see PROGRESS.md's Design principles section) applied literally:
the link between these fields is a free consistency constraint from known
physical structure, not something to infer statistically. When the two
judgments disagree, the check does NOT silently reconcile them (neither
field is more "authoritative" -- both are single-photo visual impressions);
it surfaces the disagreement in the rendered output and drops confidence one
level, so the person reading the estimate treats the ranges with real
caution rather than false precision. A hard `assert` (not a soft flag) also
guards the one invariant that should already be structurally impossible:
material_composite computed for a non-scrap-metal lot.

PERMANENT BOUNDARY, do not build under any future rewording: no per-lot
composition percentage claimed as a MEASUREMENT, ever. No claim of a
specific ISRI/HMS grade code for these motor/alternator/generator photos --
ISRI's HMS (Heavy Melting Steel) designations describe structural steel
scrap (plate, structural shapes, pipe over a minimum thickness); the
material this domain has actually been tested against does not meet that
definition, so no HMS code is ever computed or asserted here ("HMS-class"
below is informal shorthand for "predominantly ferrous," never an assertion
that a specific ISRI grade applies). If this exact request resurfaces
reworded, point back to this paragraph rather than re-deriving the argument.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from .entity_memory import DEFAULT_PATH, EntityMemoryRecord, EntityMemoryWriter, JsonlEntityMemoryWriter, read_records
from .llm_client import LLMClient

FAST_MODEL = "claude-haiku-4-5-20251001"

GradeImpression = Literal["looks_strong", "looks_average", "looks_weak", "unclear", "not_applicable"]
OxidationLevel = Literal["low", "moderate", "heavy", "unclear", "not_applicable"]
CopperExposure = Literal["exposed_stripped", "enclosed_housing", "mixed", "unclear", "not_applicable"]
Confidence = Literal["low", "medium", "high"]

ScrapCategory = Literal[
    "sealed_motors_alternators_starters",
    "exposed_copper_windings_stators",
    "large_industrial_machinery",
    "aluminum_dominant_items",
    "loose_mixed_steel",
    "non_metal_contamination",
    "other_unidentifiable",
]
ProportionBin = Literal["unclear", "minimal", "some", "about_a_quarter", "about_half", "majority", "nearly_all"]

_SCRAP_CHECK_MARKER = "[scrap-metal check] "
_WEIGHIN_MARKER = "[scrap-metal weigh-in] "
_NO_PRIOR_LOTS_MESSAGE = "No prior lots on record yet for this entity."

_OXIDATION_RANK = {"low": 0, "moderate": 1, "heavy": 2}
_GRADE_RANK = {"looks_weak": 0, "looks_average": 1, "looks_strong": 2}

_CATEGORY_PROPORTION_VOTES = 5  # real, accepted cost -- see module docstring
_MIN_VOTES_FOR_CATEGORY_INCLUSION = 3  # of 5 -- a genuine majority, not a bare "appeared twice"
_MIN_WEIGHINS_FOR_CALIBRATION = 3

_BIN_ORDER = ["minimal", "some", "about_a_quarter", "about_half", "majority", "nearly_all"]
_BIN_NUMERIC_RANGES: Dict[str, Tuple[float, float]] = {
    "minimal": (0, 5),
    "some": (5, 15),
    "about_a_quarter": (15, 30),
    "about_half": (30, 60),
    "majority": (50, 80),
    "nearly_all": (80, 100),
}

MANDATORY_COMPOSITE_HEDGE = (
    "Sample-based visual approximation. Assumes this photo is representative of the full "
    "shipment. Ranges are wide where visual category judgment was less stable. Not a "
    "substitute for a weigh-in."
)
GENERIC_YIELD_EXPECTATION_NOTE = "Range narrows as real weigh-ins accumulate for this supplier."

# Each category's assumed copper/aluminum/ferrous/excluded fraction (low, high)
# as a PERCENTAGE OF THAT CATEGORY'S OWN SHARE. "excluded" is 100 for
# non-metal/unidentified categories (nothing there counts toward any metal),
# 0 for the five real material categories. "cited" distinguishes a real,
# sourced industry figure from a stated, explicitly-labeled ASSUMPTION where
# no citable figure was found.
_CATEGORY_MATERIAL_PROFILES = {
    "sealed_motors_alternators_starters": {
        "copper": (7, 18), "aluminum": (0, 3), "ferrous": (79, 93), "excluded": (0, 0),
        "cited": True,
        "note": "Cited: 7-18% copper for motor/alternator-type units (industry sources: Okon "
                "Recycling, ScrapMonster, Taylor's Junkyard); remainder assumed predominantly steel housing.",
    },
    "exposed_copper_windings_stators": {
        "copper": (20, 40), "aluminum": (0, 2), "ferrous": (58, 80), "excluded": (0, 0),
        "cited": False,
        "note": "ASSUMPTION, not an industry-cited figure. A real web search was run specifically "
                "for a stripped-stator-copper-fraction figure (Okon Recycling, a scrap-forum "
                "discussion, a stator-stripping-equipment vendor page) -- none gave a figure for "
                "this distinct from whole-motor copper content or equipment recovery RATES (a "
                "different quantity). Kept unchanged at a wide 20-40% copper by weight -- stripped "
                "stators are copper-richer than a sealed unit but still include a steel lamination "
                "core, not pure copper wire.",
    },
    "large_industrial_machinery": {
        "copper": (2, 6), "aluminum": (0, 3), "ferrous": (91, 98), "excluded": (0, 0),
        "cited": False,
        "note": "ASSUMPTION: large industrial machinery (gearboxes, engine blocks, big housings) "
                "assumed predominantly ferrous/HMS-class with a small incidental copper allowance "
                "for internal wiring/motors; no specific citable source for this exact category.",
    },
    "aluminum_dominant_items": {
        "copper": (0, 2), "aluminum": (60, 85), "ferrous": (13, 40), "excluded": (0, 0),
        "cited": False,
        "note": "ASSUMPTION: aluminum-dominant items (heat sinks, aluminum housings/frames) "
                "assumed 60-85% aluminum by weight; no specific citable industry source for this "
                "exact category, a reasoned range only.",
    },
    "loose_mixed_steel": {
        "copper": (0, 3), "aluminum": (0, 3), "ferrous": (90, 98), "excluded": (0, 0),
        "cited": False,
        "note": "ASSUMPTION: loose mixed steel (frames, brackets, misc ferrous) assumed "
                "predominantly ferrous with minor incidental copper/aluminum allowance; no "
                "specific citable source.",
    },
    "non_metal_contamination": {
        "copper": (0, 0), "aluminum": (0, 0), "ferrous": (0, 0), "excluded": (100, 100),
        "cited": True,
        "note": "By definition non-metal -- fully excluded from copper/aluminum/ferrous.",
    },
    "other_unidentifiable": {
        "copper": (0, 0), "aluminum": (0, 0), "ferrous": (0, 0), "excluded": (100, 100),
        "cited": True,
        "note": "Unidentified material -- conservatively excluded from all material estimates "
                "rather than guessed at.",
    },
}
_MATERIAL_CATEGORIES = (
    "sealed_motors_alternators_starters", "exposed_copper_windings_stators",
    "large_industrial_machinery", "aluminum_dominant_items", "loose_mixed_steel",
)


class MaterialComposite(BaseModel):
    """Auditable output of the deterministic composite computation --
    pre-normalization AND normalized shares are both kept, so the raw
    per-category judgment is never hidden behind the final blended numbers.
    copper/aluminum/hms_ferrous_pct_range are each guaranteed within [0, 100]
    as an arithmetic consequence of the weighted-average formula used to
    compute them (see module docstring), not a post-hoc clamp."""

    category_proportions: Dict[str, str]  # aggregated (voted) bin per category
    raw_category_shares_pct: Dict[str, List[float]]  # [low, high], BEFORE normalization
    normalized_category_shares_pct: Dict[str, List[float]]  # [low, high], AFTER normalization
    excluded_categories: List[str]  # categories resolved as genuinely "unclear" -- omitted, not guessed at
    category_yield_sources: Dict[str, str] = Field(default_factory=dict)  # per-category: cited/generic/calibrated label
    copper_pct_range: List[float]
    aluminum_pct_range: List[float]
    hms_ferrous_pct_range: List[float]
    non_metal_excluded_pct_range: List[float]
    used_any_generic_yield: bool = False  # drives GENERIC_YIELD_EXPECTATION_NOTE in rendering
    hedge: str = MANDATORY_COMPOSITE_HEDGE


class ScrapEstimate(BaseModel):
    is_scrap_metal_lot: bool
    category_note: Optional[str] = None
    grade_impression: GradeImpression
    oxidation_level: OxidationLevel
    visible_contamination: List[str]
    copper_exposure: CopperExposure
    category_typical_yield_note: Optional[str] = None
    condition_note: Optional[str] = None
    material_composite: Optional[MaterialComposite] = None
    coherence_note: Optional[str] = None
    track_record_note: Optional[str] = None
    comparison_note: Optional[str] = None
    scrap_score: Optional[int] = None
    confidence: Confidence
    reasoning: str


class WeighInRecord(BaseModel):
    """A REAL ground-truth record -- entity_id is carried by the
    EntityMemoryRecord it's written into, not duplicated here. Captures the
    matched estimate's predicted ranges AND its dominant material category
    (+ that category's normalized share midpoint) at write time, so future
    calibration can back-solve "what copper/aluminum/ferrous fraction would
    make this real result consistent with the dominant category's share" --
    see _compute_calibrated_yields. Known, honest limitation: matching is
    "most recent prior estimate for this entity" -- if multiple lots were
    estimated between a photo being taken and its weigh-in being recorded,
    this could match the wrong one. Not solved here; would need an explicit
    estimate identifier threaded through, not built without a real need."""

    photo_ref: str
    actual_copper_pct: float
    actual_aluminum_pct: float
    actual_ferrous_pct: float
    estimated_copper_pct_range: Optional[List[float]] = None
    estimated_aluminum_pct_range: Optional[List[float]] = None
    estimated_ferrous_pct_range: Optional[List[float]] = None
    dominant_category: Optional[str] = None
    dominant_category_share_pct: Optional[float] = None  # midpoint, at estimate time


SCRAP_SYSTEM_PROMPT = """You are giving a coarse, VISUAL-ONLY impression of a \
photographed lot of scrap metal, for a person to use as ONE input among several -- \
not a definitive grade, and NEVER a per-lot material composition estimate. You \
cannot see inside the metal or determine its actual alloy or purity from a photo \
-- no visual signal can supply that, the same reason professional scrap buyers \
still use XRF meters despite decades of visual experience. Do not estimate, guess, \
or imply a composition percentage, purity level, or specific alloy for THIS lot \
anywhere in your answer (category_typical_yield_note below is the one narrow, \
clearly-labeled exception).

Judge ONLY the attached photo. You have no information about any other lot or any \
prior submission -- there is none to consider.

is_scrap_metal_lot: true if the photo shows metal scrap destined for melting or \
recycling -- deteriorated, disassembled, or clearly scrap-bound material. false if \
it shows intact, functional, or new/lightly-used equipment (e.g. on pallets, still \
assembled, not degraded) that is NOT scrap in the traditional sense. If false, set \
grade_impression and oxidation_level to "not_applicable" -- do not force a scrap \
grade onto something that isn't scrap.

category_note: if is_scrap_metal_lot is false, briefly say what the photo actually \
shows instead (e.g. "appears to be intact/new equipment on pallets, not \
deteriorated scrap"). Empty string if is_scrap_metal_lot is true.

grade_impression: a rough, COMPARATIVE visual impression only -- "looks_strong" \
(substantial, clean, minimal visible degradation), "looks_average", "looks_weak" \
(heavily degraded, thin, fragmented), "unclear" if the photo doesn't show enough \
to judge even roughly, or "not_applicable" per is_scrap_metal_lot above. This is \
an impression from appearance alone, not a grade determination.

oxidation_level: "low", "moderate", "heavy", "unclear", or "not_applicable" -- \
based only on visible rust, corrosion, or discoloration in the photo.

visible_contamination: list any non-metal materials visibly attached or mixed in \
(e.g. "plastic housing", "insulation", "dirt/debris") -- empty list if none is \
visible. Only list what is actually visible, never inferred from context.

copper_exposure: "exposed_stripped" if copper windings or wiring are directly \
visible or already stripped out of their housing -- a genuinely visually \
tractable distinction, since exposed copper has a distinctive color/sheen \
separable by sight from surrounding iron or steel. "enclosed_housing" if the \
copper is sealed inside an intact motor/alternator casing with no windings \
visible -- you CANNOT determine anything about the copper inside a sealed \
housing from a photo, so never comment on its condition or amount with any \
confidence in that case. "mixed" if the lot shows both. "unclear" if you can't \
tell. "not_applicable" if is_scrap_metal_lot is false or the item type doesn't \
involve copper windings at all.

category_typical_yield_note: ONLY populate this if you can confidently identify \
the general item TYPE (e.g. "small/fractional electric motors," "DC motors") AND \
a real industry-typical range applies. Use ONLY these reference figures, do not \
invent different numbers: fractional/small electric motors run approximately \
9-10% copper by weight; DC motors run approximately 15-18% copper; the general \
range across motor types is 7-18% copper, with steel making up roughly 90% of the \
remainder. Always name a source when you cite a figure -- attribute it to \
"industry sources (Okon Recycling, ScrapMonster, Taylor's Junkyard)". This MUST \
be phrased as a category-typical range for the identified item type in general, \
NEVER as a measurement or estimate of THIS specific lot's actual content -- e.g. \
say "small electric motors like these typically run about 9-10% copper by weight \
(industry sources: Okon Recycling, ScrapMonster, Taylor's Junkyard), though this \
specific lot's actual composition cannot be determined from a photo," never "this \
lot contains 9-10% copper." Leave as an empty string if the item type isn't \
confidently identified or no typical range applies.

confidence: "low" if the photo is ambiguous, poorly lit, or shows only part of the \
lot; "high" only if the visual signal is genuinely clear; "medium" otherwise. \
Default to "low" rather than overstating confidence from a single photo.

reasoning: one or two sentences grounded in what is actually visible in the photo \
-- never reference this specific lot's composition, purity, or alloy content."""

SCRAP_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_scrap_metal_lot": {"type": "boolean"},
        "category_note": {"type": "string", "maxLength": 200},
        "grade_impression": {
            "type": "string",
            "enum": ["looks_strong", "looks_average", "looks_weak", "unclear", "not_applicable"],
        },
        "oxidation_level": {"type": "string", "enum": ["low", "moderate", "heavy", "unclear", "not_applicable"]},
        "visible_contamination": {"type": "array", "items": {"type": "string"}},
        "copper_exposure": {
            "type": "string",
            "enum": ["exposed_stripped", "enclosed_housing", "mixed", "unclear", "not_applicable"],
        },
        "category_typical_yield_note": {"type": "string", "maxLength": 400},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {"type": "string", "maxLength": 400},
    },
    "required": [
        "is_scrap_metal_lot", "category_note", "grade_impression", "oxidation_level", "visible_contamination",
        "copper_exposure", "category_typical_yield_note", "confidence", "reasoning",
    ],
}

CATEGORY_PROPORTIONS_SYSTEM_PROMPT = """You are estimating the rough visual makeup \
of a photographed lot of scrap-related material, broken into a FIXED set of \
categories. Every visible item belongs to EXACTLY ONE category -- a sealed motor \
counts ONLY as sealed_motors_alternators_starters, never additionally as exposed \
copper windings, because its windings are inside it, not a separate share of the \
sample. Do not double-count.

Categories:
- sealed_motors_alternators_starters: intact units, housings still on, copper not visible
- exposed_copper_windings_stators: stripped units, copper windings directly visible
- large_industrial_machinery: gearboxes, engine blocks, large housings/casings
- aluminum_dominant_items: heat sinks, aluminum housings/frames
- loose_mixed_steel: frames, brackets, miscellaneous ferrous scrap
- non_metal_contamination: plastic, rubber, debris, non-metal material
- other_unidentifiable: visible material you cannot confidently assign to any category above

For EACH category that is actually present, estimate its rough visual proportion \
of the whole sample using ONLY these bins: "minimal", "some", "about_a_quarter", \
"about_half", "majority" (more than half), "nearly_all", or "unclear". Only \
include a category in your answer if it is actually visible in the photo -- omit \
categories with zero presence entirely, do not include them at a "minimal" \
placeholder.

If a category's share genuinely cannot be visually judged -- heavy occlusion, deep \
mixed piling where you can only see the top layer, or items too jumbled to \
attribute confidently to one category over another -- you MUST answer "unclear" \
for that category rather than estimating. A confident-looking breakdown of a pile \
you can only see the top of is worse than an honest "unclear". For example: if a \
bin is packed so densely that you can only see the very top layer of items and \
have no way to know what's underneath, the categories you can't verify below the \
surface must be "unclear", not guessed at from what little is visible. Similarly, \
if multiple categories are jumbled together so thoroughly that you cannot tell \
which specific items belong to which category, mark those categories "unclear" \
rather than inventing a specific split."""

CATEGORY_PROPORTIONS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "category_proportions": {
            "type": "object",
            "properties": {c: {"type": "string", "enum": _BIN_ORDER + ["unclear"]} for c in ScrapCategory.__args__},
        },
    },
    "required": ["category_proportions"],
}

_TERTILE_SYSTEM_PROMPT_TEMPLATE = """You previously assessed that the category "{category}" \
occupies approximately "{bin_value}" of this photographed sample ({low:.0f}-{high:.0f}% of \
the whole). Within that specific range, is the actual visual share closer to the LOWER \
third, MIDDLE third, or UPPER third of {low:.0f}-{high:.0f}%? Judge only from what is \
actually visible in the photo -- if you genuinely cannot tell, choose "middle" as the \
conservative default, do not guess toward an extreme."""

TERTILE_REFINEMENT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"tertile": {"type": "string", "enum": ["lower", "middle", "upper"]}},
    "required": ["tertile"],
}


def compute_scrap_score(
    grade_impression: GradeImpression,
    oxidation_level: OxidationLevel,
    contamination_count: int,
    is_scrap_metal_lot: bool,
) -> Optional[int]:
    """Deterministic 1-10 score, computed here in code -- never asked of or
    asserted by the LLM, same discipline as luck_test.py's
    compute_diversification_signal(). None if is_scrap_metal_lot is False."""
    if not is_scrap_metal_lot:
        return None

    grade_points = {"looks_strong": 8, "looks_average": 5, "looks_weak": 2, "unclear": 4}
    oxidation_adjustment = {"low": 1, "moderate": 0, "heavy": -2, "unclear": -1}

    base = grade_points.get(grade_impression, 4)
    adjustment = oxidation_adjustment.get(oxidation_level, -1)
    contamination_penalty = min(contamination_count, 3)

    score = base + adjustment - contamination_penalty
    return max(1, min(10, score))


def compute_condition_note(
    grade_impression: GradeImpression,
    oxidation_level: OxidationLevel,
    visible_contamination: List[str],
    is_scrap_metal_lot: bool,
) -> Optional[str]:
    """Deterministic, plain-language condition synthesis a scrap buyer would
    recognize. Never names a specific ISRI/HMS grade code -- see module
    docstring's permanent boundary. None if is_scrap_metal_lot is False."""
    if not is_scrap_metal_lot:
        return None

    oxidation_phrases = {
        "low": "minimal oxidation", "moderate": "moderate oxidation", "heavy": "heavy oxidation",
        "unclear": "oxidation level not clearly visible",
    }
    grade_phrases = {
        "looks_strong": "solid overall condition", "looks_average": "average condition",
        "looks_weak": "significantly degraded condition", "unclear": "condition not clearly visible",
    }

    segments = [
        oxidation_phrases.get(oxidation_level, "oxidation level not clearly visible"),
        grade_phrases.get(grade_impression, "condition not clearly visible"),
    ]
    if visible_contamination:
        segments.append(f"non-metal attachments present ({', '.join(visible_contamination)}) -- would need sorting before processing")
    else:
        segments.append("no non-metal attachments visible")

    return ", ".join(segments) + "."


def _read_prior_scrap_estimates(
    entity_id: str, path: Union[str, Path] = DEFAULT_PATH, limit: int = 3
) -> List[ScrapEstimate]:
    """Prior scrap-metal-tagged ScrapEstimates for this entity, most recent
    first -- parsed back from decision_text's stored JSON. A record that
    fails to parse is skipped rather than crashing retrieval."""
    records = [r for r in read_records(entity_id, path=path) if r.decision_text.startswith(_SCRAP_CHECK_MARKER)]
    records.sort(key=lambda r: r.timestamp, reverse=True)

    estimates = []
    for record in records:
        if len(estimates) >= limit:
            break
        try:
            estimates.append(ScrapEstimate.model_validate_json(record.decision_text[len(_SCRAP_CHECK_MARKER):]))
        except ValueError:
            continue
    return estimates


def _compute_deterministic_comparison(
    current_is_scrap_metal_lot: bool,
    current_grade_impression: GradeImpression,
    current_oxidation_level: OxidationLevel,
    current_copper_exposure: CopperExposure,
    prior_estimates: List[ScrapEstimate],
) -> str:
    """Fully deterministic -- no LLM call, no re-judging what the current
    photo shows."""
    most_recent = prior_estimates[0]

    if not current_is_scrap_metal_lot or not most_recent.is_scrap_metal_lot:
        return "Not compared to the prior lot -- different category of item, not a like-for-like scrap comparison."

    parts = []

    current_ox_rank = _OXIDATION_RANK.get(current_oxidation_level)
    prior_ox_rank = _OXIDATION_RANK.get(most_recent.oxidation_level)
    if current_ox_rank is not None and prior_ox_rank is not None:
        if current_ox_rank > prior_ox_rank:
            parts.append(f"more oxidized than the prior lot ({most_recent.oxidation_level} -> {current_oxidation_level})")
        elif current_ox_rank < prior_ox_rank:
            parts.append(f"less oxidized than the prior lot ({most_recent.oxidation_level} -> {current_oxidation_level})")
        else:
            parts.append(f"similar oxidation to the prior lot ({current_oxidation_level})")

    current_grade_rank = _GRADE_RANK.get(current_grade_impression)
    prior_grade_rank = _GRADE_RANK.get(most_recent.grade_impression)
    if current_grade_rank is not None and prior_grade_rank is not None:
        if current_grade_rank > prior_grade_rank:
            parts.append(f"grade impression better than the prior lot ({most_recent.grade_impression} -> {current_grade_impression})")
        elif current_grade_rank < prior_grade_rank:
            parts.append(f"grade impression worse than the prior lot ({most_recent.grade_impression} -> {current_grade_impression})")
        else:
            parts.append(f"similar grade impression to the prior lot ({current_grade_impression})")

    comparable_copper_states = ("exposed_stripped", "enclosed_housing", "mixed")
    if current_copper_exposure in comparable_copper_states and most_recent.copper_exposure in comparable_copper_states:
        if current_copper_exposure == most_recent.copper_exposure:
            parts.append(f"same copper exposure as the prior lot ({current_copper_exposure})")
        else:
            parts.append(f"copper exposure differs from the prior lot ({most_recent.copper_exposure} -> {current_copper_exposure})")

    if not parts:
        return "Not enough comparable structured data from the prior lot to make a meaningful comparison."
    return "Compared to the most recent prior lot: " + "; ".join(parts) + "."


# --- category_proportions: 5-vote extraction + honest-width aggregation ----


def _extract_category_proportions_once(image_path: Union[str, Path], client: LLMClient) -> Dict[str, str]:
    """ONE isolated call -- zero prior-lot text, same isolation guarantee as
    the main judgment call above."""
    result = client.call_tool(
        system=CATEGORY_PROPORTIONS_SYSTEM_PROMPT,
        user_message="Estimate the category proportions in the attached photo.",
        tool_name="record_category_proportions",
        tool_description="Record the category proportions.",
        input_schema=CATEGORY_PROPORTIONS_TOOL_SCHEMA,
        max_tokens=400,
        image_path=image_path,
    )
    return result["category_proportions"]


def _refine_unanimous_category(
    image_path: Union[str, Path], client: LLMClient, category: str, bin_value: str
) -> Tuple[float, float]:
    """Fires ONLY when all 5 votes agreed on bin_value for this category
    (genuine unanimity). One additional narrow, isolated query -- still zero
    prior-lot text -- narrows the bin's full range to whichever third the
    model judges the true share falls in."""
    low, high = _BIN_NUMERIC_RANGES[bin_value]
    third = (high - low) / 3
    result = client.call_tool(
        system=_TERTILE_SYSTEM_PROMPT_TEMPLATE.format(category=category, bin_value=bin_value, low=low, high=high),
        user_message="Which third applies?",
        tool_name="record_tertile_refinement",
        tool_description="Record which third of the range applies.",
        input_schema=TERTILE_REFINEMENT_TOOL_SCHEMA,
        max_tokens=50,
        image_path=image_path,
    )
    tertile = result["tertile"]
    if tertile == "lower":
        return (low, low + third)
    if tertile == "upper":
        return (high - third, high)
    return (low + third, high - third)


def _resolve_category_range(observed_bins: List[str]) -> Optional[Tuple[float, float]]:
    """Given a category's observed bin values across qualifying votes:
    - if a majority said "unclear", the category is genuinely unclear --
      returns None, excluded rather than guessed at.
    - a stray minority "unclear" is ignored; range computed from concrete bins.
    - if all concrete votes agree on one bin, that bin's own numeric range.
    - if votes wobbled across 2+ distinct bins, the UNION of all observed
      bins' ranges -- honest width, not a false-precision average."""
    unclear_count = observed_bins.count("unclear")
    if unclear_count > len(observed_bins) / 2:
        return None

    concrete_bins = [b for b in observed_bins if b != "unclear"]
    if not concrete_bins:
        return None

    distinct = set(concrete_bins)
    if len(distinct) == 1:
        return _BIN_NUMERIC_RANGES[concrete_bins[0]]

    los = [_BIN_NUMERIC_RANGES[b][0] for b in distinct]
    his = [_BIN_NUMERIC_RANGES[b][1] for b in distinct]
    return (min(los), max(his))


def _aggregate_category_votes(
    votes: List[Dict[str, str]]
) -> Tuple[Dict[str, str], Dict[str, Tuple[float, float]], List[str], Dict[str, str]]:
    """Aggregates N raw votes into: (1) the modal bin per category, (2) each
    category's numeric share RANGE, (3) categories excluded as genuinely
    unclear, (4) categories that were UNANIMOUS -- every one of the N votes
    mentioned this category AND agreed on the exact same (non-unclear) bin --
    mapped to that bin, for the caller to decide whether to refine."""
    category_bins = defaultdict(list)
    for vote in votes:
        for category, bin_value in vote.items():
            category_bins[category].append(bin_value)

    modal_bins = {}
    share_ranges = {}
    excluded = []
    unanimous = {}
    for category, bins in category_bins.items():
        if len(bins) < _MIN_VOTES_FOR_CATEGORY_INCLUSION:
            continue

        counts = Counter(bins)
        max_count = max(counts.values())
        modal = [b for b, c in counts.items() if c == max_count]
        modal_bins[category] = modal[0] if len(modal) == 1 else min(
            modal, key=lambda b: _BIN_ORDER.index(b) if b in _BIN_ORDER else -1
        )

        if len(bins) == len(votes) and len(set(bins)) == 1 and bins[0] != "unclear":
            unanimous[category] = bins[0]

        share_range = _resolve_category_range(bins)
        if share_range is None:
            excluded.append(category)
        else:
            share_ranges[category] = share_range

    return modal_bins, share_ranges, excluded, unanimous


def _extract_and_aggregate_category_proportions(
    image_path: Union[str, Path], client: LLMClient
) -> Tuple[Dict[str, str], Dict[str, Tuple[float, float]], List[str]]:
    """Runs _CATEGORY_PROPORTION_VOTES (5) independent isolated extractions,
    aggregates them, then refines any UNANIMOUS category's range with one
    additional narrow query (see _refine_unanimous_category) -- wobbling
    categories keep their full-bin (or union) width untouched."""
    votes = [_extract_category_proportions_once(image_path, client) for _ in range(_CATEGORY_PROPORTION_VOTES)]
    modal_bins, share_ranges, excluded, unanimous = _aggregate_category_votes(votes)

    for category, bin_value in unanimous.items():
        share_ranges[category] = _refine_unanimous_category(image_path, client, category, bin_value)

    return modal_bins, share_ranges, excluded


def _normalize_category_shares(share_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, Tuple[float, float]]:
    """Corrects share ranges ONLY when they're jointly inconsistent: scales
    ALL lows down (by a single scalar) only if they jointly overclaim
    (sum > 100), and ALL highs up (by a single scalar) only if they jointly
    underclaim (sum < 100). Using one scalar per side (not per-category
    weights) provably preserves each category's own low <= high ordering
    (scaling lows down only shrinks them, scaling highs up only grows them,
    so low stays <= high) and keeps every individual value in [0, 100]
    (each scaled value is a fraction of a sum that itself includes it, so it
    can never exceed the target 100). Left entirely unscaled when the raw
    ranges already satisfy sum(low) <= 100 <= sum(high) -- the common case."""
    if not share_ranges:
        return {}

    sum_low = sum(lo for lo, _ in share_ranges.values())
    sum_high = sum(hi for _, hi in share_ranges.values())

    factor_low = 100.0 / sum_low if sum_low > 100 else 1.0
    factor_high = 100.0 / sum_high if 0 < sum_high < 100 else 1.0

    return {c: (lo * factor_low, hi * factor_high) for c, (lo, hi) in share_ranges.items()}


def _dominant_material_category(normalized_shares: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float]]:
    """The material category (excluding non_metal_contamination/
    other_unidentifiable) with the highest normalized share midpoint, plus
    that midpoint -- used both for display and for calibration back-solving."""
    material_shares = {c: v for c, v in normalized_shares.items() if c in _MATERIAL_CATEGORIES}
    if not material_shares:
        return None, None
    category, (lo, hi) = max(material_shares.items(), key=lambda kv: (kv[1][0] + kv[1][1]) / 2)
    return category, (lo + hi) / 2


def _compute_calibrated_yields(
    entity_id: str, path: Union[str, Path] = DEFAULT_PATH
) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """For each ScrapCategory, if >=_MIN_WEIGHINS_FOR_CALIBRATION real
    weigh-ins exist where that category was DOMINANT in the matched
    estimate, back-solves this entity's own observed yield:
    implied_yield = actual_material_pct / dominant_category_share_fraction.
    Averages implied yields across qualifying weigh-ins; if they all
    coincide exactly, adds a small +/-1pp band rather than presenting a
    fake-precise point. Returns {} entries for categories without enough
    qualifying weigh-ins -- callers fall back to the generic range for those."""
    weighins = _read_prior_weighins(entity_id, path=path, limit=50)

    per_category = defaultdict(lambda: {"copper": [], "aluminum": [], "ferrous": []})
    per_category_counts = defaultdict(int)
    for w in weighins:
        if not w.dominant_category or not w.dominant_category_share_pct:
            continue
        share_fraction = w.dominant_category_share_pct / 100
        if share_fraction <= 0:
            continue
        per_category[w.dominant_category]["copper"].append(w.actual_copper_pct / share_fraction)
        per_category[w.dominant_category]["aluminum"].append(w.actual_aluminum_pct / share_fraction)
        per_category[w.dominant_category]["ferrous"].append(w.actual_ferrous_pct / share_fraction)
        per_category_counts[w.dominant_category] += 1

    calibrated = {}
    for category, materials in per_category.items():
        if per_category_counts[category] < _MIN_WEIGHINS_FOR_CALIBRATION:
            continue
        entry = {"_count": per_category_counts[category]}
        for material, values in materials.items():
            lo, hi = min(values), max(values)
            if lo == hi:
                lo, hi = max(0.0, lo - 1), min(100.0, hi + 1)
            entry[material] = (round(lo, 1), round(hi, 1))
        calibrated[category] = entry
    return calibrated


def compute_material_composite(
    modal_bins: Dict[str, str],
    share_ranges: Dict[str, Tuple[float, float]],
    excluded_categories: List[str],
    calibrated_yields: Optional[Dict[str, Dict]] = None,
) -> Optional[MaterialComposite]:
    """Deterministic composite -- no LLM call. See module docstring's MATH
    REVISION section for the full derivation: for each material, computes
    two candidate weighted averages across categories (one using each
    category's normalized-low-share weighting, one using its normalized-
    high-share weighting), each applied to BOTH the material profile's low
    and high fraction, then takes composite_lo = min of the two "low
    fraction" results and composite_hi = max of the two "high fraction"
    results. This guarantees composite_lo <= composite_hi and both within
    [0, 100] as an arithmetic consequence of the formula (proof in the
    docstring), never a clamp. calibrated_yields (per
    _compute_calibrated_yields) is used in place of the generic/cited
    profile for any category it covers. Returns None if there's nothing to
    compute from."""
    if not share_ranges:
        return None

    normalized = _normalize_category_shares(share_ranges)
    calibrated_yields = calibrated_yields or {}

    sum_low = sum(lo for lo, _ in normalized.values())
    sum_high = sum(hi for _, hi in normalized.values())
    n = len(normalized)

    weight_low = {c: (lo / sum_low if sum_low > 0 else 1 / n) for c, (lo, _) in normalized.items()}
    weight_high = {c: (hi / sum_high if sum_high > 0 else 1 / n) for c, (_, hi) in normalized.items()}

    category_profiles = {}
    category_yield_sources = {}
    used_any_generic = False

    for category in normalized:
        profile = _CATEGORY_MATERIAL_PROFILES.get(category)
        if profile is None:
            continue

        if category in calibrated_yields:
            cal = calibrated_yields[category]
            cu = cal.get("copper", profile["copper"])
            al = cal.get("aluminum", profile["aluminum"])
            fe = cal.get("ferrous", profile["ferrous"])
            category_yield_sources[category] = f"calibrated from {cal['_count']} real weigh-ins for this supplier"
        else:
            cu, al, fe = profile["copper"], profile["aluminum"], profile["ferrous"]
            if category in _MATERIAL_CATEGORIES:
                used_any_generic = True
                category_yield_sources[category] = (
                    "cited industry range (no weigh-ins yet)" if profile["cited"]
                    else "generic assumption (no weigh-ins yet)"
                )
        category_profiles[category] = {"copper": cu, "aluminum": al, "ferrous": fe, "excluded": profile["excluded"]}

    def _bounded_range(material: str) -> Tuple[float, float]:
        val_a_lo = sum(weight_low[c] * category_profiles[c][material][0] for c in category_profiles)
        val_a_hi = sum(weight_low[c] * category_profiles[c][material][1] for c in category_profiles)
        val_b_lo = sum(weight_high[c] * category_profiles[c][material][0] for c in category_profiles)
        val_b_hi = sum(weight_high[c] * category_profiles[c][material][1] for c in category_profiles)
        return min(val_a_lo, val_b_lo), max(val_a_hi, val_b_hi)

    copper_lo, copper_hi = _bounded_range("copper")
    aluminum_lo, aluminum_hi = _bounded_range("aluminum")
    ferrous_lo, ferrous_hi = _bounded_range("ferrous")
    excluded_lo, excluded_hi = _bounded_range("excluded")

    return MaterialComposite(
        category_proportions=modal_bins,
        raw_category_shares_pct={c: [round(lo, 1), round(hi, 1)] for c, (lo, hi) in share_ranges.items()},
        normalized_category_shares_pct={c: [round(lo, 1), round(hi, 1)] for c, (lo, hi) in normalized.items()},
        excluded_categories=excluded_categories,
        category_yield_sources=category_yield_sources,
        copper_pct_range=[round(copper_lo, 1), round(copper_hi, 1)],
        aluminum_pct_range=[round(aluminum_lo, 1), round(aluminum_hi, 1)],
        hms_ferrous_pct_range=[round(ferrous_lo, 1), round(ferrous_hi, 1)],
        non_metal_excluded_pct_range=[round(excluded_lo, 1), round(excluded_hi, 1)],
        used_any_generic_yield=used_any_generic,
    )


def aggregate_shipment_estimates(estimates: List[ScrapEstimate]) -> Optional[MaterialComposite]:
    """Combines multiple photos' composites as independent samples of ONE
    underlying population (the SAME physical shipment, photographed multiple
    times/angles) -- NOT sequentially different lots (use comparison_note
    for that). Averages each material's range across photos, then narrows
    width by 1/sqrt(N) -- the standard reduction in uncertainty from
    averaging N independent measurements of the same quantity. This is a
    real, load-bearing, NAMED ASSUMPTION: independent per-photo estimation
    error, not systematically correlated by lighting/angle/position within
    the same shipment. Not a proven fact -- stated plainly, not hidden."""
    composites = [e.material_composite for e in estimates if e.material_composite]
    if not composites:
        return None
    n = len(composites)
    reduction = 1 / (n ** 0.5)

    def _combine(attr: str) -> List[float]:
        los = [getattr(c, attr)[0] for c in composites]
        his = [getattr(c, attr)[1] for c in composites]
        avg_lo, avg_hi = sum(los) / n, sum(his) / n
        mid = (avg_lo + avg_hi) / 2
        half_width = (avg_hi - avg_lo) / 2 * reduction
        return [round(max(0.0, mid - half_width), 1), round(min(100.0, mid + half_width), 1)]

    return MaterialComposite(
        category_proportions={},
        raw_category_shares_pct={},
        normalized_category_shares_pct={},
        excluded_categories=[],
        category_yield_sources={},
        copper_pct_range=_combine("copper_pct_range"),
        aluminum_pct_range=_combine("aluminum_pct_range"),
        hms_ferrous_pct_range=_combine("hms_ferrous_pct_range"),
        non_metal_excluded_pct_range=_combine("non_metal_excluded_pct_range"),
        used_any_generic_yield=any(c.used_any_generic_yield for c in composites),
        hedge=(
            MANDATORY_COMPOSITE_HEDGE + f" Combined from {n} photos of the same shipment, assuming "
            "independent per-photo estimation error (a stated assumption, not a proven fact about "
            "this specific shipment)."
        ),
    )


# --- Calibration loop: real weigh-ins, gap surfaced, never auto-adjusted ---


def _read_prior_weighins(entity_id: str, path: Union[str, Path] = DEFAULT_PATH, limit: int = 50) -> List[WeighInRecord]:
    records = [r for r in read_records(entity_id, path=path) if r.decision_text.startswith(_WEIGHIN_MARKER)]
    records.sort(key=lambda r: r.timestamp, reverse=True)
    results = []
    for record in records:
        if len(results) >= limit:
            break
        try:
            results.append(WeighInRecord.model_validate_json(record.decision_text[len(_WEIGHIN_MARKER):]))
        except ValueError:
            continue
    return results


def compute_track_record_note(entity_id: str, path: Union[str, Path] = DEFAULT_PATH) -> Optional[str]:
    """Deterministic, code-computed -- compares past weigh-ins against the
    estimate that preceded each. Surfaces the gap; does NOT auto-correct
    anything. None if no weigh-ins with a matched estimate exist yet."""
    weighins = _read_prior_weighins(entity_id, path=path)
    gaps = {"copper": [], "aluminum": [], "ferrous": []}
    for w in weighins:
        if w.estimated_copper_pct_range:
            gaps["copper"].append(sum(w.estimated_copper_pct_range) / 2 - w.actual_copper_pct)
        if w.estimated_aluminum_pct_range:
            gaps["aluminum"].append(sum(w.estimated_aluminum_pct_range) / 2 - w.actual_aluminum_pct)
        if w.estimated_ferrous_pct_range:
            gaps["ferrous"].append(sum(w.estimated_ferrous_pct_range) / 2 - w.actual_ferrous_pct)

    parts = []
    for material, diffs in gaps.items():
        if not diffs:
            continue
        avg_gap = sum(diffs) / len(diffs)
        direction = "high" if avg_gap > 0 else "low"
        parts.append(f"{material}: ran ~{abs(avg_gap):.1f}pp {direction} on average across {len(diffs)} weigh-in(s)")

    if not parts:
        return None
    return "Past estimates for this entity vs. real weigh-ins -- " + "; ".join(parts) + ". Not auto-adjusted; shown for reference only."


def record_actual_weighin(
    entity_id: str,
    photo_ref: str,
    actual_copper_pct: float,
    actual_aluminum_pct: float,
    actual_ferrous_pct: float,
    path: Union[str, Path] = DEFAULT_PATH,
    writer: Optional[EntityMemoryWriter] = None,
) -> WeighInRecord:
    """Writes a REAL ground-truth weigh-in. Looks up the most recent prior
    scrap estimate for this entity to capture its predicted composite ranges
    AND dominant category (for future calibration back-solving) alongside
    the real figures. Does NOT auto-adjust any future estimate."""
    prior_estimates = _read_prior_scrap_estimates(entity_id, path=path, limit=1)
    matched = prior_estimates[0] if prior_estimates else None
    matched_composite = matched.material_composite if matched else None

    dominant_category = dominant_share_pct = None
    if matched_composite:
        dominant_category, dominant_share_pct = _dominant_material_category(matched_composite.normalized_category_shares_pct)

    record = WeighInRecord(
        photo_ref=photo_ref,
        actual_copper_pct=actual_copper_pct,
        actual_aluminum_pct=actual_aluminum_pct,
        actual_ferrous_pct=actual_ferrous_pct,
        estimated_copper_pct_range=list(matched_composite.copper_pct_range) if matched_composite else None,
        estimated_aluminum_pct_range=list(matched_composite.aluminum_pct_range) if matched_composite else None,
        estimated_ferrous_pct_range=list(matched_composite.hms_ferrous_pct_range) if matched_composite else None,
        dominant_category=dominant_category,
        dominant_category_share_pct=dominant_share_pct,
    )

    writer = writer or JsonlEntityMemoryWriter(path=path)
    writer.write(
        EntityMemoryRecord(
            entity_id=entity_id,
            source="voice",
            decision_text=f"{_WEIGHIN_MARKER}{record.model_dump_json()}",
            goals=[],
            constraints=[],
        )
    )
    return record


_CONFIDENCE_DOWNGRADE = {"high": "medium", "medium": "low", "low": "low"}


def compute_coherence_note(
    copper_exposure: CopperExposure,
    is_scrap_metal_lot: bool,
    modal_bins: Dict[str, str],
    material_composite: Optional[MaterialComposite],
) -> Optional[str]:
    """Deterministic cross-field check -- no LLM call. copper_exposure and
    category_proportions are independent isolated judgments about the same
    photo, but they describe physically linked facts (see module
    docstring). Neither field is treated as authoritative over the other;
    a real disagreement is surfaced, never silently reconciled. Returns
    None when everything is coherent (the common case)."""
    assert is_scrap_metal_lot or material_composite is None, (
        "material_composite must never be computed for a non-scrap-metal lot"
    )
    if not is_scrap_metal_lot:
        return None

    conflicts = []

    exposed_bin = modal_bins.get("exposed_copper_windings_stators")
    if copper_exposure == "exposed_stripped" and exposed_bin in (None, "minimal"):
        share_description = (
            "no significant exposed-copper-windings share" if exposed_bin is None
            else "only a minimal exposed-copper-windings share"
        )
        conflicts.append(
            f"copper exposure suggests stripped/exposed copper windings, but category mix shows {share_description}"
        )

    if material_composite:
        sealed_bin = modal_bins.get("sealed_motors_alternators_starters")
        sealed_copper_ceiling = _CATEGORY_MATERIAL_PROFILES["sealed_motors_alternators_starters"]["copper"][1]
        if sealed_bin in ("majority", "nearly_all") and material_composite.copper_pct_range[1] > sealed_copper_ceiling:
            conflicts.append(
                f"category mix is dominated by sealed motors/alternators (cited ceiling ~{sealed_copper_ceiling:.0f}% copper), "
                f"but the computed copper range's high end ({material_composite.copper_pct_range[1]:.1f}%) exceeds that ceiling"
            )

    if not conflicts:
        return None
    return "visual judgments partially conflict -- " + "; ".join(conflicts) + "; treat ranges with extra caution"


def render_scrap_estimate_as_text(estimate: ScrapEstimate) -> str:
    """Multi-line, clearly-labeled rendering. category_typical_yield_note and
    the material_composite (if present) are surfaced on their own clearly-
    labeled lines, not buried in a trailing clause."""
    comparison = estimate.comparison_note or "no comparison available"

    if not estimate.is_scrap_metal_lot:
        category = estimate.category_note or "does not appear to be a scrap-metal lot"
        return (
            f"Not identified as scrap metal: {category}\n"
            f"Comparison: {comparison}\n"
            f"Reasoning: {estimate.reasoning}"
        )

    contamination = ", ".join(estimate.visible_contamination) if estimate.visible_contamination else "none visible"
    score_text = f"{estimate.scrap_score}/10" if estimate.scrap_score is not None else "n/a"

    lines = [
        f"Grade impression: {estimate.grade_impression}. Oxidation: {estimate.oxidation_level}. Scrap score: {score_text}.",
        f"Copper exposure: {estimate.copper_exposure}. Contamination: {contamination}.",
    ]
    if estimate.coherence_note:
        lines.append(f"Note: {estimate.coherence_note}")
    if estimate.condition_note:
        lines.append(f"Condition: {estimate.condition_note}")
    if estimate.category_typical_yield_note:
        lines.append(f"Typical yield reference: {estimate.category_typical_yield_note}")
    if estimate.material_composite:
        mc = estimate.material_composite
        lines.append(
            f"Estimated sample makeup -- copper: roughly {mc.copper_pct_range[0]}-{mc.copper_pct_range[1]}% of sample "
            f"weight; aluminum: roughly {mc.aluminum_pct_range[0]}-{mc.aluminum_pct_range[1]}%; "
            f"HMS-ferrous (predominantly ferrous scrap): roughly {mc.hms_ferrous_pct_range[0]}-{mc.hms_ferrous_pct_range[1]}%; "
            f"non-metal/unidentified (excluded above): roughly {mc.non_metal_excluded_pct_range[0]}-{mc.non_metal_excluded_pct_range[1]}%."
        )
        if mc.category_yield_sources:
            source_bits = "; ".join(f"{c}: {s}" for c, s in mc.category_yield_sources.items())
            lines.append(f"Yield sources -- {source_bits}.")
        if mc.excluded_categories:
            lines.append(f"Categories not reliably judgeable, omitted from the above: {', '.join(mc.excluded_categories)}.")
        lines.append(mc.hedge)
        if mc.used_any_generic_yield:
            lines.append(GENERIC_YIELD_EXPECTATION_NOTE)
    if estimate.track_record_note:
        lines.append(estimate.track_record_note)
    lines.append(f"Comparison: {comparison}")
    lines.append(f"Reasoning: {estimate.reasoning}")
    return "\n".join(lines)


def estimate_scrap_lot(
    image_path: Union[str, Path],
    entity_id: str,
    client: Optional[LLMClient] = None,
    path: Union[str, Path] = DEFAULT_PATH,
    writer: Optional[EntityMemoryWriter] = None,
) -> ScrapEstimate:
    client = client or LLMClient(model=FAST_MODEL)

    # Step 1: ISOLATED judgment -- no prior-lot text anywhere in this call.
    result = client.call_tool(
        system=SCRAP_SYSTEM_PROMPT,
        user_message="Give your impression of the attached photo.",
        tool_name="record_scrap_estimate",
        tool_description="Record the coarse visual scrap-metal estimate.",
        input_schema=SCRAP_TOOL_SCHEMA,
        max_tokens=600,
        image_path=image_path,
    )

    is_scrap_metal_lot = bool(result["is_scrap_metal_lot"])
    category_note = (result["category_note"] or "").strip() or None
    category_typical_yield_note = (result["category_typical_yield_note"] or "").strip() or None
    contamination = result["visible_contamination"]

    scrap_score = compute_scrap_score(
        grade_impression=result["grade_impression"],
        oxidation_level=result["oxidation_level"],
        contamination_count=len(contamination),
        is_scrap_metal_lot=is_scrap_metal_lot,
    )
    condition_note = compute_condition_note(
        grade_impression=result["grade_impression"],
        oxidation_level=result["oxidation_level"],
        visible_contamination=contamination,
        is_scrap_metal_lot=is_scrap_metal_lot,
    )

    # Step 2: category_proportions + material_composite -- ONLY for real
    # scrap-metal lots. 5 isolated votes + unanimous-only refinement +
    # deterministic aggregation/composite math, using this entity's own
    # calibrated yields wherever enough real weigh-ins exist.
    material_composite = None
    modal_bins = {}
    if is_scrap_metal_lot:
        modal_bins, share_ranges, excluded_categories = _extract_and_aggregate_category_proportions(image_path, client)
        calibrated_yields = _compute_calibrated_yields(entity_id, path=path)
        material_composite = compute_material_composite(modal_bins, share_ranges, excluded_categories, calibrated_yields)

    # Step 2b: cross-field physical-coherence check -- deterministic, no LLM
    # call. copper_exposure and category_proportions are independent
    # judgments about the same photo; a real disagreement is surfaced, not
    # silently reconciled, and drops confidence one level.
    coherence_note = compute_coherence_note(
        copper_exposure=result["copper_exposure"],
        is_scrap_metal_lot=is_scrap_metal_lot,
        modal_bins=modal_bins,
        material_composite=material_composite,
    )
    confidence = _CONFIDENCE_DOWNGRADE[result["confidence"]] if coherence_note else result["confidence"]

    # Step 3: comparison_note, computed deterministically from prior lots'
    # STORED STRUCTURED FIELDS -- no LLM call, never re-decides what the
    # current photo shows.
    prior_estimates = _read_prior_scrap_estimates(entity_id, path=path)
    if prior_estimates:
        comparison_note = _compute_deterministic_comparison(
            current_is_scrap_metal_lot=is_scrap_metal_lot,
            current_grade_impression=result["grade_impression"],
            current_oxidation_level=result["oxidation_level"],
            current_copper_exposure=result["copper_exposure"],
            prior_estimates=prior_estimates,
        )
    else:
        comparison_note = _NO_PRIOR_LOTS_MESSAGE

    # Step 4: track_record_note -- real weigh-in history for this entity, if any.
    track_record_note = compute_track_record_note(entity_id, path=path)

    estimate = ScrapEstimate(
        is_scrap_metal_lot=is_scrap_metal_lot,
        category_note=category_note,
        grade_impression=result["grade_impression"],
        oxidation_level=result["oxidation_level"],
        visible_contamination=contamination,
        copper_exposure=result["copper_exposure"],
        category_typical_yield_note=category_typical_yield_note,
        condition_note=condition_note,
        material_composite=material_composite,
        coherence_note=coherence_note,
        track_record_note=track_record_note,
        comparison_note=comparison_note,
        scrap_score=scrap_score,
        confidence=confidence,
        reasoning=result["reasoning"],
    )

    writer = writer or JsonlEntityMemoryWriter(path=path)
    writer.write(
        EntityMemoryRecord(
            entity_id=entity_id,
            source="voice",
            decision_text=f"{_SCRAP_CHECK_MARKER}{estimate.model_dump_json()}",
            goals=[],
            constraints=[],
        )
    )

    return estimate
