"""Scrap-metal coarse-estimate domain -- the ORIGINAL use case this whole
project traces back to, not built until now. Mirrors
core/image_verification.py's isolated-call scaffold (one minimal, separate
Claude vision call), but the output is a coarse, honestly-labeled
COMPARATIVE grade impression, never a composition percentage claimed as a
MEASUREMENT.

This ceiling is not a limitation to work around -- it's load-bearing. A
vision model cannot see hidden material composition from a photo, the same
reason professional scrap buyers still carry XRF meters despite decades of
visual experience. Nothing in ScrapEstimate or SCRAP_SYSTEM_PROMPT below
asks for or permits a per-lot purity/alloy/composition MEASUREMENT,
anywhere. The one number this domain does surface (yield_assessment's
copper/aluminum/ferrous ranges) comes from a deterministic, cited/
calibrated TABLE LOOKUP for the lot's classified TYPE in general, never
from asking the vision model to measure or regress THIS lot's actual
content -- see ARCHITECTURAL REPLACEMENT below for why that distinction is
the entire point of this module's design.

Review-only, mirroring /verify -- NO correction loop attached. Grading
feedback is almost certainly criterion-shaped, the exact confirmed failure
mode found during image-verification's checkpoint. Not attempted here.

STRUCTURAL FIX #1 (see the 9-photo sequential-run checkpoint, first
confirmed instance of context anchoring in this module): the visual
judgment of the CURRENT photo is computed by a call that NEVER receives any
prior-lot text -- identical whether it's the 1st photo for an entity or the
50th. comparison_note is a SEPARATE, deterministic computation built from
prior lots' STORED STRUCTURED FIELDS (parsed back from JSON behind
_SCRAP_CHECK_MARKER), never re-judging what the current photo shows.

condition_note (compute_condition_note): a plain-language, buyer-recognizable
synthesis of oxidation_level + grade_impression + visible_contamination.
Fully deterministic, never asked of the LLM.

ARCHIVED: category_proportions / compute_material_composite (a
compositional per-photo estimate -- category proportions x yield fractions
per category, blended into a whole-lot composite). This was built, then
measurably underperformed a plain base-rate lookup on real photos:
- v1 (free-text categories): unstable vocabulary, "unclear" never fired.
- v2 (closed taxonomy, 3 votes): dominant category stabilized, secondary
  categories still wobbled.
- v3 (5 votes, honest bin-union width): shipped, then found to produce
  impossible >100% bounds on 7 of 8 real photos (up to 143.2%) from a
  midpoint-forcing normalization bug -- fixed at the root (constrained
  normalization + a provably-bounded min/max-of-two-weightings formula,
  not a clamp), re-verified clean (0 out-of-bounds, average width cut from
  29.62pp to 12.33pp).
That the underlying APPROACH still measurably underperformed a base-rate
lookup -- not merely that it had a fixable bug -- is what triggered the
architectural replacement below, rather than a seventh incremental patch.
compute_material_composite, _extract_and_aggregate_category_proportions,
_normalize_category_shares, and aggregate_shipment_estimates are all KEPT,
still fully tested (see tests/test_scrap_estimate.py), but no longer called
by estimate_scrap_lot() or rendered to any user -- pure reference code, in
case a real future need reintroduces per-photo compositional estimation.

ARCHITECTURAL REPLACEMENT: base rate + deviation. The core insight: material
yield for a given TYPE of scrap (sealed motors run 7-18% copper, DC motors
15-18%, etc.) is already known and cited -- it doesn't need to be
re-derived from a photo every time. What a photo CAN tell you is whether
THIS lot looks unusual for its type. So:
1. lot_type (added to the main isolated judgment call, a closed-taxonomy
   CLASSIFICATION -- the task family that has tested reliable throughout
   this module, e.g. grade_impression/copper_exposure/is_scrap_metal_lot --
   never a quantity regression, the family that failed as
   category_proportions) identifies which of 5 known categories (or
   "unclear"/"not_applicable") the lot belongs to.
2. _CATEGORY_MATERIAL_PROFILES (the SAME cited/assumption table the old
   composite math used) is looked up DIRECTLY by lot_type -- no blending,
   no per-photo composite math, so the >100%-bound failure mode from the
   old design is now structurally impossible, not merely patched again.
3. assess_copper_richness() -- see STRUCTURAL FIX #2 below for why this is
   designed the way it is -- supplies the ONLY other signal: whether THIS
   photo looks visibly copper-richer or -poorer than typical scrap motor/
   machinery lots IN GENERAL.
4. compute_deviation_from_richness() is a plain, deterministic, fully-
   enumerated, API-free function that joins (1) and (3): a low-baseline
   type (sealed motors, large machinery, aluminum items, loose steel)
   showing unusually_copper_rich is a genuine upside flag; a high-baseline
   type (exposed copper windings) showing unusually_copper_poor is a
   genuine downside flag; every other combination is "looks_typical" (the
   richness observed is already consistent with that type's own baseline).
No adjusted number is EVER invented for a deviation -- the flag + evidence
+ direction is the entire vision contribution to yield_assessment; the
actual copper/aluminum/ferrous ranges always come from the table (or
per-supplier calibration, unchanged in spirit from before -- see below).

STRUCTURAL FIX #2 (assess_copper_richness's actual design, the reason this
replacement took two attempts): the FIRST version of the deviation call
(assess_deviation, since removed) told the vision call the lot's classified
type AND its numeric baseline in the same prompt, then asked it to judge
"typical vs. deviation" against that baseline. A real 5-runs-x-3-photos
reliability test showed the model anchoring on the offered label: on a
photo that was genuinely, heavily copper-rich (exposed stator windings
dominating every bin), it answered "looks_typical...consistent with the
expected 7-18% copper-by-weight range for sealed motors" in 4 of 5 runs,
rationalizing visibly exposed copper as normal FOR THE LABEL IT WAS GIVEN.
This is the THIRD confirmed instance of the same failure family in this
module (after STRUCTURAL FIX #1's prior-lot narrative anchoring, and the
old composite math's per-category ceiling-blending): a call that has
access to contaminating context will use it to rationalize, rather than
independently re-assess. The durable fix, both previous times, was
REMOVING the contaminating information from the call -- never instructing
the model to ignore it (an option-1-style prompt revision was explicitly
rejected here for exactly this reason). So assess_copper_richness() -- the
final version -- receives NO lot-type label, NO baseline range, NO base-
rate number, only the photo and a generic question about visible copper
richness relative to scrap motor/machinery lots IN GENERAL. Classification
and baseline only ever meet the richness signal afterward, in
compute_deviation_from_richness(), a plain function, in code, fully
testable without any API call. Re-tested with the SAME bar after this
change: the same photo now reads unusually_copper_rich in 5 of 5 runs.

Per-supplier calibration (compute_yield_assessment's calibrated_yields
param, _compute_calibrated_yields): once >=3 real weigh-ins exist for an
entity for a given lot_type, this entity's own observed yield for that
type (actual_material_pct, averaged across qualifying weigh-ins -- lot_type
is now a WHOLE-LOT classification, not a share of the sample, so no share-
fraction back-solving is needed the way the old per-category version
required) is used in place of the generic/cited industry range for that
type, labeled accordingly. Falls back to the generic range with an
explicit "no weigh-ins yet" label until 3 weigh-ins exist for a type. Every
rendered estimate that still uses a generic (uncalibrated) yield states
"Range narrows as real weigh-ins accumulate for this supplier" -- the
day-one width is a starting point, not the product's ceiling.

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
and lot_type are two INDEPENDENT judgments from the SAME isolated call, but
they describe physically linked facts -- e.g. "exposed, stripped copper
windings visible" and "classified as sealed_motors_alternators_starters"
cannot both be true of the same photo. This is the "structured priors over
statistical rediscovery" / information-hiding principle (see PROGRESS.md's
Design principles section) applied literally: the link between these
fields is a free consistency constraint from known physical structure, not
something to infer statistically. When the two judgments disagree, the
check does NOT silently reconcile them (neither field is more
"authoritative" -- both are single-photo visual impressions); it surfaces
the disagreement in the rendered output and drops confidence one level.
This function used to check a SECOND conflict (category mix dominated by
sealed motors, but the computed composite's copper ceiling exceeded) --
that check no longer applies and has been REMOVED, not silently dropped:
in the base-rate + deviation design, lot_type's base rate is a direct table
lookup, never a blend across categories, so there is no composite ceiling
left to exceed. That this old failure mode is now structurally impossible
is a real, structural benefit of the replacement, not an incidental one.

WIDTH REDUCTION PASS (three structural changes, none asking vision to guess
a quantity):

1. Motor sub-type classification (classify_motor_subtype,
   _MOTOR_SUBTYPE_PROFILES, _resolve_profile_type): a SECOND, still
   presence/absence-shaped classification -- "what size/kind of sealed unit
   is visibly dominant," never a quantity guess -- fired only when the
   coarse lot_type is sealed_motors_alternators_starters, to look up a
   narrower cited range where the photo genuinely supports it
   (small_fractional_motors 9-10% Cu, dc_motors 15-18%,
   automotive_alternators_starters ~10-14% -- the last one newly sourced
   from a real 1976 US Bureau of Mines dismantling study, narrower than the
   generic 7-18% because it's specific to vehicle-parts scrap rather than
   motors in general). "mixed_sealed_motors" is the explicit, honest
   fallback to the full coarse range -- never forced. Reliability-tested
   the same way as everything else: 5 runs on photos 1, 4, 7. Photos 1
   (5/5 automotive_alternators_starters) and 7 (5/5 mixed_sealed_motors)
   were stable and met the shipping bar. Photo 4 was NOT stable (3/5
   mixed_sealed_motors, 2/5 small_fractional_motors) -- reported honestly,
   not hidden: on a genuinely borderline lot, sub-type narrowing may apply
   inconsistently across repeated estimates of the same photo. Shipped
   anyway per the stated bar (photos 1 and 7), with this limitation on the
   record rather than silently accepted.
2. The two remaining uncited profiles (exposed_copper_windings_stators,
   large_industrial_machinery) were searched again, specifically. Neither
   search turned up a citable figure more specific than what's already
   cited elsewhere (whole-motor copper content, or unrelated recovery-rate/
   background material) -- both stay explicit assumptions, and now say so
   with a literal "(uncited estimate)" tag in the rendered yield_source,
   so a person can see at a glance which numbers are earned and which are
   assumed, never narrowed on vibes just because they were asked about again.
3. GENERIC_YIELD_EXPECTATION_NOTE is now the headline promise, not a
   footnote: "Range reflects industry-wide variance. After ~3 real
   weigh-ins for this supplier, it narrows to their actual observed
   yields." -- appended to every rendered estimate still using an
   uncalibrated (cited or uncited) yield.

FINAL WIDTH REDUCTION PASS -- four mechanisms, all calculation/voting-
based, zero new external data, zero model-guessed quantities. Goal: copper
and aluminum each to ~4pp or their honest floor; ferrous is no longer an
independent lookup at all (see below).

1. Voted classification (vote_lot_type, vote_motor_subtype,
   vote_copper_richness, _vote_modal_or_fallback): lot_type, sub_type, and
   richness are each now 5-VOTE modal decisions, not single isolated
   calls. Modal wins on a STRICT plurality; a genuine tie at the top falls
   back to the coarser/more conservative option ("unclear" for lot_type,
   "mixed_sealed_motors" for sub_type, "typical_mixed_scrap" for
   richness) rather than arbitrarily picking among tied options. lot_type
   was extracted out of the main isolated judgment call into its own
   isolated call specifically so it could be voted without re-generating
   grade/oxidation/etc. five times for no reason -- those fields were
   never found unstable. Real result: photo 4's previously-unstable
   sub-type call (3/5 vs. 2/5 in a single-shot test) resolved to the SAME
   modal answer (small_fractional_motors) across 2 repeated aggregate
   votes -- a real, measured stabilization, though not full unanimity (so
   refinement, below, correctly does not fire for it). lot_type itself
   also showed real cross-session variance before voting (photo 4 read
   sealed_motors in one single-shot run, exposed_copper_windings in
   another); voting resolved it unanimously to sealed_motors across 2
   repeated aggregate votes in this pass's own testing.
2. Within-range refinement (refine_subtype_within_range, _tertile_to_range):
   fires ONLY when vote_motor_subtype() came back genuinely unanimous
   (5/5) on a real (non-"mixed") sub-type -- one additional bounded call
   asking whether the visible mix sits in the lower/middle/upper THIRD of
   that sub-type's own cited range (e.g. 10-14% Cu -> ~1.3pp slices),
   mapped in code exactly like the archived category_proportions
   pipeline's _refine_unanimous_category. Reliability-gated before
   shipping, per the checkpoint's explicit bar: 5 runs on photo 1, came
   back 5/5 "middle" -- stable, shipped.
3. Shipment aggregation (aggregate_shipment_yield_assessments): same-
   resolved-type photos are combined by RANGE INTERSECTION (each photo's
   range is an independent, valid bound on the shipment's one true value,
   so the true value must lie in all of them -- a real, stated assumption:
   material uniformity across the photographed sub-lots, not proven;
   non-overlapping ranges fall back to the union rather than reporting an
   empty/inverted range). Mixed-resolved-type photos use an equal-weight
   blend instead, with its own weaker, explicitly stated assumption (no
   per-photo share signal exists in this architecture to weight by real
   proportion).
4. Richness-conditioned tail trim (apply_richness_trim): deterministic,
   asymmetric, exactly two rules, both rule-stated in code, never a
   model-chosen number. Unanimous (5/5) typical_mixed_scrap trims the TOP
   20% of the range (evidence contradicts the richest tail); unanimous
   unusually_copper_rich trims the BOTTOM 20% (evidence contradicts the
   poorest tail). Deliberately NOT extended to unanimous
   unusually_copper_poor (no rule was specified for it in the checkpoint
   that requested this trim -- inventing one would be exactly the kind of
   uncited narrowing this domain's history argues against). Any vote
   split or cannot_assess: no trim. Applied identically to copper and
   aluminum (a stated simplification -- the richness signal isn't
   independently re-validated for aluminum specifically).

FERROUS IS NO LONGER AN INDEPENDENT LOOKUP. It is the ARITHMETIC
COMPLEMENT of the final copper+aluminum ranges (100% minus their ranges),
computed AFTER every mechanism above has already narrowed copper/aluminum.
This is stated plainly in the rendered output every time. It is a real
property of the math, not a limitation: ferrous can never be narrower than
copper and aluminum's own combined uncertainty, because it IS that
uncertainty, restated. Narrowing copper/aluminum via voting, refinement,
or trimming automatically narrows ferrous too, with no separate mechanism
needed or possible.

Honest floors, not fake precision: where a photo's resolved type has no
sub-type system (exposed_copper_windings_stators, large_industrial_
machinery, aluminum_dominant_items, loose_mixed_steel), or the sub-type
call didn't resolve unanimously, copper's range stays at its full cited/
uncited table width (minus whatever the richness trim removes) -- no
narrower number is ever manufactured because 4pp was the goal. A true 16pp
after all four mechanisms beats a fake 4pp, every time.

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

from .entity_memory import DEFAULT_PATH, EntityMemoryRecord, EntityMemoryWriter, SqliteEntityMemoryWriter, read_records
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

LotType = Literal[
    "sealed_motors_alternators_starters",
    "exposed_copper_windings_stators",
    "large_industrial_machinery",
    "aluminum_dominant_items",
    "loose_mixed_steel",
    "unclear",
    "not_applicable",
]
Deviation = Literal["looks_typical", "looks_better_than_typical", "looks_worse_than_typical", "cannot_assess"]
CopperRichness = Literal["unusually_copper_rich", "typical_mixed_scrap", "unusually_copper_poor", "cannot_assess"]

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
GENERIC_YIELD_EXPECTATION_NOTE = (
    "Range reflects industry-wide variance. After ~3 real weigh-ins for this supplier, "
    "it narrows to their actual observed yields."
)

# Each category's assumed copper/aluminum/ferrous/excluded fraction (low, high)
# as a PERCENTAGE OF THAT CATEGORY'S OWN SHARE. "excluded" is 100 for
# non-metal/unidentified categories (nothing there counts toward any metal),
# 0 for the five real material categories. "cited" distinguishes a real,
# sourced industry figure from a stated, explicitly-labeled ASSUMPTION where
# no citable figure was found.
# Named once, reused in both the profile note below AND in the cited
# yield_source label surfaced to the user -- the whole point of "cited" is
# that a person can see where the number came from, not just that it was
# labeled "cited" without saying by whom.
_CITED_SOURCES_TEXT = "Okon Recycling, ScrapMonster, Taylor's Junkyard"

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
        "note": "ASSUMPTION, not an industry-cited figure. A real web search was run TWICE for a "
                "stripped-stator-copper-fraction figure -- first pass: Okon Recycling, a scrap-forum "
                "discussion, a stator-stripping-equipment vendor page; second pass (re-confirmed): "
                "Bluedog Wire Stripper's stator-recycling-machine blog post, Okon Recycling's electric-"
                "motor-recycling guide. Both passes returned only whole-motor copper content (7-18%, "
                "already cited elsewhere) or extraction-equipment recovery RATES (a different quantity) "
                "-- nothing specific to an ALREADY-STRIPPED stator/winding pile. Kept unchanged at a "
                "wide 20-40% copper by weight -- stripped stators are copper-richer than a sealed unit "
                "but still include a steel lamination core, not pure copper wire.",
    },
    "large_industrial_machinery": {
        "copper": (2, 6), "aluminum": (0, 3), "ferrous": (91, 98), "excluded": (0, 0),
        "cited": False,
        "note": "ASSUMPTION: large industrial machinery (gearboxes, engine blocks, big housings) "
                "assumed predominantly ferrous/HMS-class with a small incidental copper allowance for "
                "internal wiring/motors. A real web search was run specifically for a gearbox/large-"
                "machinery-scrap copper-fraction figure -- results only covered electric-motor copper "
                "content (already cited elsewhere) and general industrial-copper-recycling background, "
                "nothing specific to gearbox/large-machinery scrap. No citable source found; kept as a "
                "stated assumption, not narrowed on vibes.",
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
    """ARCHIVED -- no longer computed by estimate_scrap_lot() or rendered to
    users. Retired along with category_proportions/compute_material_composite
    in the base-rate + deviation replacement (see module docstring's
    ARCHITECTURAL REPLACEMENT section): compositional estimation from
    photos (category proportions x yield fractions) measurably
    underperformed a plain base-rate lookup on real photos (a >100%-bound
    defect, fixed, then superseded entirely rather than patched again).
    Kept, still fully tested (see tests/test_scrap_estimate.py), purely as
    a working reference in case a real future need reintroduces per-photo
    compositional estimation -- nothing in the live path constructs one.

    Auditable output of the deterministic composite computation --
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


class YieldAssessment(BaseModel):
    """The live replacement for MaterialComposite. copper/aluminum_pct_range
    are a deterministic TABLE LOOKUP for the classified (possibly voted +
    sub-typed + within-range-refined + richness-trimmed) resolved type
    (calibrated override if enough real weigh-ins exist for this supplier's
    own resolved type) -- never a photo-derived composite.
    ferrous_pct_range is NOT independently looked up or narrowed -- it is
    the ARITHMETIC COMPLEMENT of the final copper/aluminum ranges (100% -
    their ranges), computed AFTER every narrowing mechanism has already
    applied to copper/aluminum. It can never be narrower than what
    copper+aluminum's own combined uncertainty implies -- that's a stated
    property of this domain's math, not a limitation to work around.
    deviation and visible_evidence come from a fully separate, blind vision
    call (assess_copper_richness, voted) that never sees lot_type or any
    baseline number; compute_deviation_from_richness() is the only place
    the two meet, in code. trim_notes records which deterministic
    richness-conditioned trims (see apply_richness_trim) actually fired --
    empty if none did. note is the fully-rendered deterministic text (see
    compute_yield_assessment)."""

    lot_type: str
    copper_pct_range: List[float]
    aluminum_pct_range: List[float]
    ferrous_pct_range: List[float]
    yield_source: str  # "cited industry range (no weigh-ins yet)" / "(uncited estimate) -- ..." / "calibrated from N real weigh-ins for this supplier"
    deviation: Deviation
    visible_evidence: List[str]
    trim_notes: List[str] = Field(default_factory=list)
    note: str


class ScrapEstimate(BaseModel):
    is_scrap_metal_lot: bool
    category_note: Optional[str] = None
    grade_impression: GradeImpression
    oxidation_level: OxidationLevel
    visible_contamination: List[str]
    copper_exposure: CopperExposure
    condition_note: Optional[str] = None
    yield_assessment: Optional[YieldAssessment] = None
    coherence_note: Optional[str] = None
    track_record_note: Optional[str] = None
    comparison_note: Optional[str] = None
    scrap_score: Optional[int] = None
    confidence: Confidence
    reasoning: str


class WeighInRecord(BaseModel):
    """A REAL ground-truth record -- entity_id is carried by the
    EntityMemoryRecord it's written into, not duplicated here. Captures the
    matched estimate's predicted ranges AND its classified lot_type at
    write time. Since lot_type is a WHOLE-LOT classification (not a share
    of the sample the way the old dominant_category was), the weigh-in's
    real material percentages directly ARE this entity's observed yield
    for that lot_type -- no share-fraction back-solving needed (see
    _compute_calibrated_yields). Known, honest limitation: matching is
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
    lot_type: Optional[str] = None


SCRAP_SYSTEM_PROMPT = """You are giving a coarse, VISUAL-ONLY impression of a \
photographed lot of scrap metal, for a person to use as ONE input among several -- \
not a definitive grade, and NEVER a per-lot material composition estimate. You \
cannot see inside the metal or determine its actual alloy or purity from a photo \
-- no visual signal can supply that, the same reason professional scrap buyers \
still use XRF meters despite decades of visual experience. Do not estimate, guess, \
or imply a composition percentage, purity level, or specific alloy for THIS lot \
anywhere in your answer -- any typical-yield figure for an item's type is looked \
up separately, deterministically, in code, never stated by you.

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
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {"type": "string", "maxLength": 400},
    },
    "required": [
        "is_scrap_metal_lot", "category_note", "grade_impression", "oxidation_level", "visible_contamination",
        "copper_exposure", "confidence", "reasoning",
    ],
}

# lot_type was originally bundled into the main call above; extracted into
# its own isolated call so it can be 5-VOTED independently (see WIDTH
# REDUCTION PASS 2 in the module docstring) without re-generating
# grade/oxidation/etc. five times for no reason -- those fields were never
# found unstable, only lot_type and sub_type were.

LOT_TYPE_SYSTEM_PROMPT = """You are classifying the OVERALL TYPE of a photographed \
lot of scrap metal, already confirmed to be scrap-bound material.

Judge ONLY the attached photo. You have no information about any other lot or any \
prior submission -- there is none to consider.

lot_type: classify the OVERALL lot into exactly one of: "sealed_motors_alternators_starters" \
(intact units, housings still on, copper not visible), "exposed_copper_windings_stators" \
(stripped units, copper windings directly visible and dominant), "large_industrial_machinery" \
(gearboxes, engine blocks, large housings/casings), "aluminum_dominant_items" (heat sinks, \
aluminum housings/frames), "loose_mixed_steel" (frames, brackets, miscellaneous ferrous \
scrap), or "unclear" (genuinely mixed across several of the above with no single dominant \
type, or too jumbled/occluded to classify confidently -- prefer this honestly over forcing \
a single category onto a mixed pile). This is a classification of what TYPE of lot it is, \
never a composition percentage.

reasoning: one or two sentences grounded in what is actually visible in the photo."""

LOT_TYPE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "lot_type": {
            "type": "string",
            "enum": [
                "sealed_motors_alternators_starters", "exposed_copper_windings_stators",
                "large_industrial_machinery", "aluminum_dominant_items", "loose_mixed_steel",
                "unclear",
            ],
        },
        "reasoning": {"type": "string", "maxLength": 400},
    },
    "required": ["lot_type", "reasoning"],
}


def classify_lot_type_once(image_path: Union[str, Path], client: LLMClient) -> str:
    """ONE isolated call -- zero prior-lot text. Returns just the lot_type
    string; called 5x by estimate_scrap_lot() and modal-voted (see
    _vote_modal_or_fallback)."""
    result = client.call_tool(
        system=LOT_TYPE_SYSTEM_PROMPT,
        user_message="Classify the overall lot type in the attached photo.",
        tool_name="record_lot_type",
        tool_description="Record the lot type classification.",
        input_schema=LOT_TYPE_TOOL_SCHEMA,
        max_tokens=300,
        image_path=image_path,
    )
    return result["lot_type"]

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


# --- Motor sub-type classification (width reduction #1) -------------------
# Not yet wired into estimate_scrap_lot() until its own reliability test
# passes -- same discipline as assess_copper_richness. A second, FINER
# classification, fired ONLY when the coarse lot_type is
# sealed_motors_alternators_starters, to look up a narrower cited range
# where the photo genuinely supports it. Still a presence/absence-shaped
# judgment (the reliable task family), never a quantity guess: "what
# size/kind of sealed unit is visibly dominant," not "what fraction is
# copper." "mixed_sealed_motors" is the explicit, honest fallback -- never
# force a narrow sub-type range a genuinely mixed or ambiguous photo doesn't
# support.

MotorSubtype = Literal["small_fractional_motors", "dc_motors", "automotive_alternators_starters", "mixed_sealed_motors"]


class MotorSubtypeAssessment(BaseModel):
    subtype: MotorSubtype
    reasoning: str


MOTOR_SUBTYPE_SYSTEM_PROMPT = """You are classifying which SPECIFIC kind of sealed \
motor/alternator/starter unit is VISIBLY DOMINANT in this photographed lot -- a finer \
classification than "sealed motors" alone, used only to look up a more specific \
(narrower) cited copper-yield range where the photo genuinely supports it.

Judge ONLY the attached photo. You have no information about any other lot or any \
prior submission -- there is none to consider.

subtype: "small_fractional_motors" if small, compact electric motors (fractional \
horsepower -- e.g. small appliance/pump/fan motors) are visibly dominant. \
"dc_motors" if larger DC motors (visible brush/commutator housings, larger overall \
size than fractional motors) are visibly dominant. "automotive_alternators_starters" \
if automotive alternators and/or starter motors specifically are visibly dominant -- \
distinctive cylindrical housing, pulley or ring gear, mounting ears/brackets. \
"mixed_sealed_motors" if the lot shows a genuine mix of the above with no single type \
visibly dominant, or if you cannot confidently tell which specific kind is dominant -- \
prefer this honestly over forcing a specific subtype the photo doesn't clearly support.

reasoning: one or two sentences grounded in what is actually visible in the photo."""

MOTOR_SUBTYPE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "subtype": {
            "type": "string",
            "enum": ["small_fractional_motors", "dc_motors", "automotive_alternators_starters", "mixed_sealed_motors"],
        },
        "reasoning": {"type": "string", "maxLength": 400},
    },
    "required": ["subtype", "reasoning"],
}


def classify_motor_subtype(image_path: Union[str, Path], client: LLMClient) -> MotorSubtypeAssessment:
    """ONE isolated call -- zero prior-lot text. Fired only when the coarse
    lot_type is sealed_motors_alternators_starters."""
    result = client.call_tool(
        system=MOTOR_SUBTYPE_SYSTEM_PROMPT,
        user_message="Classify the dominant sealed-motor subtype in the attached photo.",
        tool_name="record_motor_subtype",
        tool_description="Record the motor subtype classification.",
        input_schema=MOTOR_SUBTYPE_TOOL_SCHEMA,
        max_tokens=300,
        image_path=image_path,
    )
    return MotorSubtypeAssessment.model_validate(result)


# Sub-type base rates -- narrower than the coarse sealed_motors_alternators_
# starters range (7-18%) where a real citable figure supports it.
# automotive_alternators_starters is sourced from a real 1976 US Bureau of
# Mines dismantling study (see the note below); the other two reuse the
# same industry-source figures the coarse profile already cites for
# specific motor types. aluminum/ferrous are NOT independently re-sourced
# per sub-type (out of scope for this pass) -- they reuse the coarse
# profile's own assumption (0-3% aluminum) with ferrous as the remainder,
# same derivation style as every other profile in this table.
_MOTOR_SUBTYPE_PROFILES = {
    "small_fractional_motors": {
        "copper": (9, 10), "aluminum": (0, 3), "ferrous": (87, 91), "excluded": (0, 0),
        "cited": True,
        "note": "Cited: 9-10% copper for small/fractional electric motors (industry sources: "
                "Okon Recycling, ScrapMonster, Taylor's Junkyard).",
    },
    "dc_motors": {
        "copper": (15, 18), "aluminum": (0, 3), "ferrous": (79, 85), "excluded": (0, 0),
        "cited": True,
        "note": "Cited: 15-18% copper for DC motors (industry sources: Okon Recycling, "
                "ScrapMonster, Taylor's Junkyard).",
    },
    "automotive_alternators_starters": {
        "copper": (10, 14), "aluminum": (0, 3), "ferrous": (83, 90), "excluded": (0, 0),
        "cited": True,
        "note": "Cited: ~10-14% copper for automotive starters/alternators specifically, derived "
                "from a real 1976 US Bureau of Mines dismantling study (Salt Lake City Metallurgy "
                "Research Center, 'Metal Recovery by Dismantling of Scrapped Starter Motors, Auto "
                "Generators, and Alternators') reporting copper recovery by weight per unit "
                "(starters ~2.8 lb Cu per ~20-25 lb unit; alternators ~1.5 lb Cu per ~12-15 lb "
                "unit), via 911Metallurgist's summary of the study. Narrower than the generic "
                "sealed-motor range because it's specific to this vehicle-parts category rather "
                "than motors in general.",
    },
}


def _resolve_profile_type(coarse_lot_type: str, subtype: Optional[str]) -> str:
    """The actual profile-table key used for base-rate lookup and
    calibration: the sub-type, when the coarse type is
    sealed_motors_alternators_starters AND the sub-type call resolved to
    something more specific than "mixed_sealed_motors" (i.e. the photo
    visually supported a narrower classification); the coarse lot_type
    otherwise. This is the one place a narrower sub-type range is ever
    substituted in -- never forced when the photo didn't support it."""
    if coarse_lot_type == "sealed_motors_alternators_starters" and subtype and subtype != "mixed_sealed_motors":
        return subtype
    return coarse_lot_type


# --- Voting (width reduction pass, change 1): lot_type, sub_type, and
# richness each become 5-vote modal decisions -- the same self-consistency
# machinery already proven for the archived category_proportions pipeline,
# applied here to fix the exact instability the single-shot sub-type
# reliability test found on photo 4 (3/5 mixed_sealed_motors, 2/5
# small_fractional_motors in one run of 5). Modal resolution with a
# CONSERVATIVE/COARSER fallback on a genuine tie -- never arbitrarily pick
# among tied specific options, same discipline as every "unclear" default
# elsewhere in this module.

_VOTE_COUNT = 5


def _vote_modal_or_fallback(votes: List[str], fallback: str) -> Tuple[str, bool]:
    """Modal value wins if it has a STRICT plurality (more votes than every
    other option) -- a 3-of-5 vs. 2-of-5 split, for example, already has a
    clear winner and does NOT hit the fallback. Only a genuine tie at the
    top (e.g. 2-2-1) falls back to the given conservative/coarser value.
    Returns (resolved_value, is_unanimous) -- is_unanimous is True only when
    every vote agreed, used to gate the within-range refinement step and
    the richness-conditioned trim."""
    counts = Counter(votes)
    max_count = max(counts.values())
    winners = [v for v, c in counts.items() if c == max_count]
    resolved = winners[0] if len(winners) == 1 else fallback
    is_unanimous = len(set(votes)) == 1
    return resolved, is_unanimous


def vote_lot_type(image_path: Union[str, Path], client: LLMClient, votes: int = _VOTE_COUNT) -> Tuple[str, bool, List[str]]:
    """5 isolated classify_lot_type_once() calls, modal-resolved. Ties fall
    back to "unclear" -- the coarsest, most conservative answer, never a
    guess between two specific categories."""
    raw_votes = [classify_lot_type_once(image_path, client) for _ in range(votes)]
    resolved, is_unanimous = _vote_modal_or_fallback(raw_votes, fallback="unclear")
    return resolved, is_unanimous, raw_votes


def vote_motor_subtype(image_path: Union[str, Path], client: LLMClient, votes: int = _VOTE_COUNT) -> Tuple[str, bool, List[str]]:
    """5 isolated classify_motor_subtype() calls, modal-resolved. Ties fall
    back to "mixed_sealed_motors" -- the coarse, honest fallback, never a
    guess between two specific sub-types."""
    raw_assessments = [classify_motor_subtype(image_path, client) for _ in range(votes)]
    subtypes = [a.subtype for a in raw_assessments]
    resolved, is_unanimous = _vote_modal_or_fallback(subtypes, fallback="mixed_sealed_motors")
    return resolved, is_unanimous, subtypes


def vote_copper_richness(
    image_path: Union[str, Path], client: LLMClient, votes: int = _VOTE_COUNT
) -> Tuple[str, bool, List[str], List[str]]:
    """5 isolated assess_copper_richness() calls, modal-resolved. Ties fall
    back to "typical_mixed_scrap" -- the neutral default, never a guess
    between rich and poor. visible_evidence returned is the UNION of
    evidence from votes that agreed with the resolved verdict only --
    evidence backing a minority/disagreeing vote doesn't support the
    majority conclusion, so it's not surfaced."""
    raw_assessments = [assess_copper_richness(image_path, client) for _ in range(votes)]
    verdicts = [a.visible_copper_richness for a in raw_assessments]
    resolved, is_unanimous = _vote_modal_or_fallback(verdicts, fallback="typical_mixed_scrap")
    evidence = []
    for a in raw_assessments:
        if a.visible_copper_richness == resolved:
            for e in a.visible_evidence:
                if e not in evidence:
                    evidence.append(e)
    return resolved, is_unanimous, evidence, verdicts


# --- STAGE 1 of the architectural replacement: base-rate + deviation ------
# Not yet wired into estimate_scrap_lot(). Defined here so the required
# reliability test (5 runs x 3 photos) exercises the REAL production prompt
# and schema, not a throwaway copy. See module docstring's ARCHITECTURAL
# REPLACEMENT section once the test passes and this is wired in.
#
# STRUCTURAL INFORMATION-HIDING, not a prompt instruction: the first attempt
# at this (assess_deviation, since removed) told the vision call the lot's
# classified type AND its numeric baseline in the same prompt, then asked it
# to judge "typical vs. deviation" against that baseline -- a real 5x3 test
# showed the model anchoring on the offered label, rationalizing visibly
# exposed copper as "typical for sealed motors" 4 of 5 times on a photo that
# was actually copper-rich. This is the THIRD confirmed instance of the same
# failure family (after prior-lot narrative anchoring, and per-category
# ceiling-blending in the old composite math): the durable fix each time was
# REMOVING the contaminating information from the call, never instructing
# the model to ignore it. So the vision call below receives NO lot-type
# label, NO baseline range, NO base-rate number -- only the photo and a
# generic question about visible copper richness compared to scrap motor/
# machinery lots in general. Classification and baseline only meet this
# richness signal afterward, in compute_deviation_from_richness(), a plain
# deterministic function with every combination enumerated and testable
# without any API call.

# The only lot type whose OWN base rate is already copper-rich (20-40%) --
# "unusually_copper_rich" is EXPECTED/consistent for this type (no flag);
# every other type's base rate is low, so "rich" there is a real upside
# surprise and "poor" is unremarkable (see compute_deviation_from_richness).
_HIGH_COPPER_BASELINE_TYPES = ("exposed_copper_windings_stators",)


class RichnessAssessment(BaseModel):
    """Vision's ONLY job in the replacement design: a 4-class presence/
    absence-style judgment about visible copper richness IN GENERAL (the
    task family that tested reliable), never a quantity regression (the
    family that failed as category_proportions) and never a judgment
    relative to a specific classification or number (the anchoring failure
    found in the first version of this redesign). No adjusted number is
    ever derived from this -- the flag + evidence is the entire vision
    contribution; the actual number always comes from the deterministic
    base-rate table, joined in code by compute_deviation_from_richness."""

    visible_copper_richness: CopperRichness
    visible_evidence: List[str]
    reasoning: str


RICHNESS_SYSTEM_PROMPT = """You are assessing how much copper-bearing material is \
visually apparent in a photographed lot of scrap motors, machinery, or electrical \
equipment, compared to scrap motor/machinery lots IN GENERAL. You have not been told \
and should not assume any specific classification or numeric baseline for this lot -- \
judge only against your general sense of typical scrap motor/machinery lots. You \
cannot measure composition directly from a photo -- any richness or poorness claim \
must be grounded in something specifically VISIBLE, never inferred or guessed.

Judge ONLY the attached photo. You have no information about any other lot or any \
prior submission -- there is none to consider.

visible_copper_richness: "unusually_copper_rich" ONLY if exposed copper windings or \
stripped copper is VISIBLY DOMINANT in the photo -- clearly more bare copper material \
than a typical scrap motor/machinery lot would show. "typical_mixed_scrap" if the lot \
looks like an ordinary mix for this kind of material -- nothing about copper content \
stands out as unusual either way; this is the default, not a weaker answer than a \
rich/poor call. "unusually_copper_poor" ONLY if the lot is visibly ferrous-dominant \
with little-to-no copper-bearing material evident anywhere (e.g. plain steel/iron \
scrap, or heavy non-metal dilution). "cannot_assess" if the photo does not show enough \
to judge (too occluded, poorly lit, or too small a fraction of the lot visible).

visible_evidence: REQUIRED, non-empty list naming EXACTLY what is visible that \
justifies "unusually_copper_rich" or "unusually_copper_poor" (e.g. "exposed copper \
windings visibly dominant across every unit in the photo", "entirely plain steel \
brackets and frames, no copper-bearing components visible anywhere"). If you cannot \
name specific visible evidence, you MUST answer "typical_mixed_scrap" or \
"cannot_assess" instead -- an unsupported claim is worse than an honest \
"typical_mixed_scrap". Leave empty for "typical_mixed_scrap" or "cannot_assess".

reasoning: one or two sentences grounded in what is actually visible in the photo."""

RICHNESS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "visible_copper_richness": {
            "type": "string",
            "enum": ["unusually_copper_rich", "typical_mixed_scrap", "unusually_copper_poor", "cannot_assess"],
        },
        "visible_evidence": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string", "maxLength": 400},
    },
    "required": ["visible_copper_richness", "visible_evidence", "reasoning"],
}


def assess_copper_richness(image_path: Union[str, Path], client: LLMClient) -> RichnessAssessment:
    """ONE isolated call -- zero prior-lot text, and (per the redesign)
    zero lot-type/baseline text either. Takes no lot_type argument on
    purpose -- there is nothing about classification for this function to
    receive or leak."""
    result = client.call_tool(
        system=RICHNESS_SYSTEM_PROMPT,
        user_message="Assess the visible copper richness of the attached photo.",
        tool_name="record_richness_assessment",
        tool_description="Record the copper richness assessment.",
        input_schema=RICHNESS_TOOL_SCHEMA,
        max_tokens=400,
        image_path=image_path,
    )
    return RichnessAssessment.model_validate(result)


def _enforce_richness_evidence_rule(richness: CopperRichness, visible_evidence: List[str]) -> CopperRichness:
    """Deterministic safety net for the schema's own instruction: a rich/
    poor claim with no named visible evidence is not trustworthy --
    downgrade to typical_mixed_scrap rather than trust an unsupported
    claim, even though the prompt already asks for this."""
    if richness in ("unusually_copper_rich", "unusually_copper_poor") and not visible_evidence:
        return "typical_mixed_scrap"
    return richness


def compute_deviation_from_richness(lot_type: str, richness: CopperRichness) -> Tuple[Deviation, str]:
    """The ONLY place classification (from the main isolated judgment call)
    and visible copper-richness signal (from the fully separate, blind
    assess_copper_richness call) ever meet -- a plain deterministic join,
    every combination enumerated explicitly, no API call, fully testable.
    Returns (deviation, join_reason) -- join_reason is used as a fallback
    explanation when the richness call's own visible_evidence is empty
    (the "consistent, no flag" cases)."""
    if richness == "cannot_assess":
        return "cannot_assess", "photo does not show enough to judge visible copper richness"

    is_high_baseline = lot_type in _HIGH_COPPER_BASELINE_TYPES

    if richness == "typical_mixed_scrap":
        return "looks_typical", ""

    if richness == "unusually_copper_rich":
        if is_high_baseline:
            return "looks_typical", "visible copper richness is consistent with this lot type's already-high base rate"
        return "looks_better_than_typical", "visibly more copper-bearing material than typical for this lot type"

    # richness == "unusually_copper_poor"
    if is_high_baseline:
        return "looks_worse_than_typical", "visibly less copper-bearing material than typical for this (normally copper-rich) lot type"
    return "looks_typical", "visible copper scarcity is consistent with this lot type's already-low base rate"


# --- Within-range refinement on unanimous sub-type (width reduction pass,
# change 2). Fires ONLY when vote_motor_subtype() came back unanimous (5/5)
# on a real (non-"mixed") sub-type -- one additional bounded call asking
# whether the visible mix sits in the lower/middle/upper THIRD of that
# sub-type's own cited range, mapped in code exactly like the archived
# category_proportions pipeline's _refine_unanimous_category. Gated behind
# its own reliability test (5 runs on photo 1) before shipping -- see
# _SUBTYPE_REFINEMENT_SHIPPED and the module docstring for the result.

_SUBTYPE_TERTILE_SYSTEM_PROMPT_TEMPLATE = """You previously classified this photographed \
lot's sealed-motor sub-type as "{subtype_label}", which has a typical copper range of \
{lo:g}-{hi:g}% by weight for that sub-type. Within that specific range, does the visible \
mix of units in this photo sit closer to the LOWER third, MIDDLE third, or UPPER third of \
{lo:g}-{hi:g}%? Judge only from what is actually visible -- if you genuinely cannot tell, \
choose "middle" as the conservative default, do not guess toward an extreme."""

SUBTYPE_TERTILE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"tertile": {"type": "string", "enum": ["lower", "middle", "upper"]}},
    "required": ["tertile"],
}


def refine_subtype_within_range(
    image_path: Union[str, Path], client: LLMClient, subtype: str, copper_range: Tuple[float, float]
) -> str:
    """ONE isolated call -- zero prior-lot text. Fires only when the caller
    has already confirmed vote_motor_subtype() was unanimous. Returns the
    raw "lower"/"middle"/"upper" tertile; _tertile_to_range() maps it to a
    numeric sub-range in code."""
    lo, hi = copper_range
    result = client.call_tool(
        system=_SUBTYPE_TERTILE_SYSTEM_PROMPT_TEMPLATE.format(subtype_label=subtype.replace("_", " "), lo=lo, hi=hi),
        user_message="Which third applies?",
        tool_name="record_subtype_tertile_refinement",
        tool_description="Record which third of the range applies.",
        input_schema=SUBTYPE_TERTILE_TOOL_SCHEMA,
        max_tokens=50,
        image_path=image_path,
    )
    return result["tertile"]


def _tertile_to_range(range_: Tuple[float, float], tertile: str) -> Tuple[float, float]:
    lo, hi = range_
    third = (hi - lo) / 3
    if tertile == "lower":
        return (lo, lo + third)
    if tertile == "upper":
        return (hi - third, hi)
    return (lo + third, hi - third)


# --- Richness-conditioned tail trim (width reduction pass, change 4).
# Deterministic, asymmetric, rule-stated -- never a model-chosen number.
# Fires ONLY on genuine unanimity (5/5) of the voted richness verdict.
# Exactly two rules, exactly as specified -- deliberately NOT extended to
# "unanimous unusually_copper_poor" (left as a no-trim case since no rule
# for it was specified; inventing one would be exactly the kind of
# uncited narrowing this domain's whole history argues against):
#   - unanimous typical_mixed_scrap: 5/5 votes say nothing unusual stands
#     out -- trim the TOP 20% of the range (the richest tail is
#     inconsistent with a unanimous "nothing rich about this" signal).
#   - unanimous unusually_copper_rich: 5/5 votes say the lot looks richer
#     than typical -- trim the BOTTOM 20% (the poorest tail is
#     inconsistent with a unanimous "this looks rich" signal).
#   - unusually_copper_poor unanimous, any vote split, or cannot_assess:
#     no trim.

def apply_richness_trim(
    range_: Tuple[float, float], richness_verdict: str, is_unanimous: bool
) -> Tuple[Tuple[float, float], Optional[str]]:
    """Returns (possibly-trimmed range, trim_note_or_None). Applied
    identically to both copper and aluminum ranges -- the richness signal
    is treated as informative about metal-composition tilt broadly, not
    independently re-validated for aluminum specifically (a stated
    simplification, not a separately measured fact)."""
    if not is_unanimous:
        return range_, None

    lo, hi = range_
    width = hi - lo

    if richness_verdict == "typical_mixed_scrap":
        return (lo, round(hi - 0.2 * width, 2)), "range trimmed: visual evidence inconsistent with upper tail"
    if richness_verdict == "unusually_copper_rich":
        return (round(lo + 0.2 * width, 2), hi), "range trimmed: visual evidence inconsistent with lower tail"
    return range_, None


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


def _compute_calibrated_yields(
    entity_id: str, path: Union[str, Path] = DEFAULT_PATH
) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """For each lot_type, if >=_MIN_WEIGHINS_FOR_CALIBRATION real weigh-ins
    exist where that type was the CLASSIFIED type of the matched estimate,
    uses this entity's own observed yield directly -- since lot_type (in
    the base-rate + deviation design) classifies the WHOLE lot rather than
    a share of it, a weigh-in's actual material percentages directly ARE
    the observed yield for that type; no share-fraction back-solving is
    needed (contrast the retired per-category-share version this replaced).
    Averages observed yields across qualifying weigh-ins; if they all
    coincide exactly, adds a small +/-1pp band rather than presenting a
    fake-precise point. Returns {} entries for lot_types without enough
    qualifying weigh-ins -- callers fall back to the generic range for those."""
    weighins = _read_prior_weighins(entity_id, path=path, limit=50)

    per_type = defaultdict(lambda: {"copper": [], "aluminum": [], "ferrous": []})
    per_type_counts = defaultdict(int)
    for w in weighins:
        if not w.lot_type:
            continue
        per_type[w.lot_type]["copper"].append(w.actual_copper_pct)
        per_type[w.lot_type]["aluminum"].append(w.actual_aluminum_pct)
        per_type[w.lot_type]["ferrous"].append(w.actual_ferrous_pct)
        per_type_counts[w.lot_type] += 1

    calibrated = {}
    for lot_type, materials in per_type.items():
        if per_type_counts[lot_type] < _MIN_WEIGHINS_FOR_CALIBRATION:
            continue
        entry = {"_count": per_type_counts[lot_type]}
        for material, values in materials.items():
            lo, hi = min(values), max(values)
            if lo == hi:
                lo, hi = max(0.0, lo - 1), min(100.0, hi + 1)
            entry[material] = (round(lo, 1), round(hi, 1))
        calibrated[lot_type] = entry
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


def compute_yield_assessment(
    lot_type: str,
    richness: CopperRichness,
    visible_evidence: List[str],
    calibrated_yields: Optional[Dict[str, Dict]] = None,
    subtype: Optional[str] = None,
    richness_is_unanimous: bool = False,
    refined_subtype_range: Optional[Tuple[float, float]] = None,
) -> Optional[YieldAssessment]:
    """The live replacement for compute_material_composite. copper/aluminum
    base rates are a deterministic TABLE LOOKUP for the RESOLVED type (see
    _resolve_profile_type -- the sub-type when the photo visually supports
    one, else the coarse lot_type; calibrated override if
    _compute_calibrated_yields has enough real weigh-ins for this
    supplier's own resolved type), never re-derived by the LLM.
    refined_subtype_range (from refine_subtype_within_range, only ever
    passed when vote_motor_subtype() came back unanimous AND the
    refinement mechanism passed its own reliability gate) narrows the
    COPPER range further, before calibration is even considered --
    calibration, being real ground truth, always wins over a cited-table
    refinement when both are available. apply_richness_trim() then narrows
    whatever copper/aluminum range is current (generic, cited, refined, OR
    calibrated -- trim is applied uniformly regardless of source, a
    deliberate simplification stated plainly here). ferrous_pct_range is
    NOT looked up -- it's computed as the arithmetic complement of the
    FINAL copper+aluminum ranges (100% - their ranges), so it automatically
    reflects every narrowing mechanism above and can never be narrower than
    their combined uncertainty implies.

    deviation is computed by compute_deviation_from_richness() against the
    COARSE lot_type (sub-typing narrows the NUMBER, not which categories
    are inherently copper-rich) -- the ONLY place lot_type and the richness
    signal meet for the deviation flag itself (separate from the trim,
    which narrows the range directly). No adjusted number is ever invented
    for a deviation -- the flag + evidence + direction is the entire vision
    contribution to that flag (see module docstring). Returns None if
    lot_type has no base rate to report ("unclear" or "not_applicable")."""
    if lot_type in ("unclear", "not_applicable"):
        return None

    resolved_type = _resolve_profile_type(lot_type, subtype)
    richness = _enforce_richness_evidence_rule(richness, visible_evidence)
    deviation, join_reason = compute_deviation_from_richness(lot_type, richness)

    calibrated_yields = calibrated_yields or {}
    profile = _CATEGORY_MATERIAL_PROFILES.get(resolved_type) or _MOTOR_SUBTYPE_PROFILES[resolved_type]

    if resolved_type in calibrated_yields:
        cal = calibrated_yields[resolved_type]
        copper_range = tuple(cal.get("copper", profile["copper"]))
        aluminum_range = tuple(cal.get("aluminum", profile["aluminum"]))
        yield_source = f"calibrated from {cal['_count']} real weigh-ins for this supplier"
    else:
        copper_range = tuple(refined_subtype_range) if refined_subtype_range is not None else tuple(profile["copper"])
        aluminum_range = tuple(profile["aluminum"])
        yield_source = (
            f"cited industry range -- {_CITED_SOURCES_TEXT} (no weigh-ins yet)" if profile["cited"]
            else "(uncited estimate) -- generic assumption, not independently sourced (no weigh-ins yet)"
        )

    trim_notes = []
    copper_range, copper_trim_note = apply_richness_trim(copper_range, richness, richness_is_unanimous)
    if copper_trim_note:
        trim_notes.append(f"copper {copper_trim_note}")
    aluminum_range, aluminum_trim_note = apply_richness_trim(aluminum_range, richness, richness_is_unanimous)
    if aluminum_trim_note:
        trim_notes.append(f"aluminum {aluminum_trim_note}")

    # Ferrous is the ARITHMETIC COMPLEMENT of the final copper+aluminum
    # ranges, never an independent lookup -- see module docstring and
    # YieldAssessment's docstring for why this is stated as a property of
    # the math, not a limitation.
    ferrous_range = (
        round(max(0.0, 100.0 - copper_range[1] - aluminum_range[1]), 1),
        round(min(100.0, 100.0 - copper_range[0] - aluminum_range[0]), 1),
    )

    lot_label = resolved_type.replace("_", " ")
    copper_range = (round(copper_range[0], 1), round(copper_range[1], 1))
    aluminum_range = (round(aluminum_range[0], 1), round(aluminum_range[1], 1))
    base_rate_text = f"Base rate for {lot_label}: {copper_range[0]:g}-{copper_range[1]:g}% Cu ({yield_source})."
    ferrous_text = (
        f"HMS-ferrous ({ferrous_range[0]:g}-{ferrous_range[1]:g}%) is the arithmetic complement of "
        f"copper+aluminum -- it cannot be narrower than their combined uncertainty."
    )

    if deviation == "looks_typical":
        note = f"{base_rate_text} No visible anomalies; expect a typical lot. {ferrous_text}"
    elif deviation == "cannot_assess":
        note = f"{base_rate_text} Photo does not show enough to judge whether this lot deviates from typical. {ferrous_text}"
    else:
        direction = "below" if deviation == "looks_worse_than_typical" else "above"
        evidence_text = "; ".join(visible_evidence) if visible_evidence else join_reason
        note = f"{base_rate_text} Flagged: {evidence_text}. Likely {direction} typical -- inspect before committing. {ferrous_text}"
    if trim_notes:
        note = f"{note} ({'; '.join(trim_notes)})"

    return YieldAssessment(
        lot_type=resolved_type,
        copper_pct_range=list(copper_range),
        aluminum_pct_range=list(aluminum_range),
        ferrous_pct_range=list(ferrous_range),
        yield_source=yield_source,
        deviation=deviation,
        visible_evidence=visible_evidence,
        trim_notes=trim_notes,
        note=note,
    )


def aggregate_shipment_estimates(composites: List[MaterialComposite]) -> Optional[MaterialComposite]:
    """ARCHIVED alongside compute_material_composite/category_proportions
    (see module docstring's ARCHITECTURAL REPLACEMENT section) -- no longer
    called by estimate_scrap_lot() or rendered to users. Takes MaterialComposite
    objects directly (not ScrapEstimate) since ScrapEstimate no longer
    carries a material_composite field in the live schema. Combines multiple
    photos' composites as independent samples of ONE underlying population
    (the SAME physical shipment, photographed multiple times/angles) -- NOT
    sequentially different lots (use comparison_note for that). Averages
    each material's range across photos, then narrows width by 1/sqrt(N) --
    the standard reduction in uncertainty from averaging N independent
    measurements of the same quantity. This is a real, load-bearing, NAMED
    ASSUMPTION: independent per-photo estimation error, not systematically
    correlated by lighting/angle/position within the same shipment. Not a
    proven fact -- stated plainly, not hidden."""
    composites = [c for c in composites if c]
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


def aggregate_shipment_yield_assessments(assessments: List[YieldAssessment]) -> Optional[YieldAssessment]:
    """The LIVE shipment-aggregation function (width reduction pass, change
    3) -- combines multiple photos' YieldAssessments as independent
    samples of ONE physical shipment, NOT sequentially different lots (use
    comparison_note for that).

    SAME resolved type across every photo: treated as independent samples
    each estimating the SAME single true shipment-wide yield -- so the
    true value must lie within EVERY photo's valid range, and the
    INTERSECTION of all ranges is itself a valid (and typically narrower)
    range for that value. This is mathematically sound ONLY under a real,
    named, stated ASSUMPTION: every photo's range genuinely brackets the
    same true value (i.e. the shipment is materially uniform across the
    photographed sub-lots) -- not proven, stated plainly. If the ranges
    don't overlap at all (a real disagreement between photos), the
    intersection would be empty/inverted; rather than silently picking one
    photo's range or reporting nonsense, this falls back to the UNION
    instead, an honest signal that the photos disagree more than the
    independence assumption expects.

    MIXED resolved types across photos: intersection is meaningless (the
    photos are about different categories with different true values), so
    this uses an EQUAL-WEIGHT blend across photos instead -- a real, named,
    ADDITIONAL assumption (each photo represents an equal fraction of the
    shipment by weight), weaker than the same-type case since there's no
    per-photo share signal in this architecture to weight by real
    proportion. Rougher than a same-type combination; labeled as such.

    Aluminum is combined the same way as copper. Ferrous is NEVER combined
    directly -- recomputed as the arithmetic complement of the combined
    copper+aluminum ranges, same discipline as compute_yield_assessment."""
    assessments = [a for a in assessments if a]
    if not assessments:
        return None
    n = len(assessments)
    resolved_types = sorted({a.lot_type for a in assessments})

    def _intersect_or_union(attr: str) -> List[float]:
        los = [getattr(a, attr)[0] for a in assessments]
        his = [getattr(a, attr)[1] for a in assessments]
        lo, hi = max(los), min(his)
        if lo > hi:
            lo, hi = min(los), max(his)
        return [round(lo, 1), round(hi, 1)]

    def _blend(attr: str) -> List[float]:
        los = [getattr(a, attr)[0] for a in assessments]
        his = [getattr(a, attr)[1] for a in assessments]
        return [round(sum(los) / n, 1), round(sum(his) / n, 1)]

    if len(resolved_types) == 1:
        combine = _intersect_or_union
        combine_note = (
            f"Combined from {n} photos of the same shipment, same classified type ({resolved_types[0].replace('_', ' ')}) "
            "-- ranges intersected, each treated as an independent, valid bound on the shipment's one true yield "
            "(a stated assumption: material uniformity across the photographed sub-lots, not proven)."
        )
    else:
        combine = _blend
        combine_note = (
            f"Combined from {n} photos of a MIXED-type shipment ({', '.join(t.replace('_', ' ') for t in resolved_types)}) "
            "-- equal-weight blend assumed (no per-photo share signal available in this architecture); "
            "treat as a rougher approximation than a same-type combination."
        )

    copper_range = combine("copper_pct_range")
    aluminum_range = combine("aluminum_pct_range")
    ferrous_range = [
        round(max(0.0, 100.0 - copper_range[1] - aluminum_range[1]), 1),
        round(min(100.0, 100.0 - copper_range[0] - aluminum_range[0]), 1),
    ]

    return YieldAssessment(
        lot_type=resolved_types[0] if len(resolved_types) == 1 else "mixed",
        copper_pct_range=copper_range,
        aluminum_pct_range=aluminum_range,
        ferrous_pct_range=ferrous_range,
        yield_source="combined across photos -- see note",
        deviation="looks_typical",
        visible_evidence=[],
        note=combine_note,
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
    scrap estimate for this entity to capture its predicted yield_assessment
    ranges AND classified lot_type alongside the real figures. Does NOT
    auto-adjust any future estimate."""
    prior_estimates = _read_prior_scrap_estimates(entity_id, path=path, limit=1)
    matched = prior_estimates[0] if prior_estimates else None
    matched_assessment = matched.yield_assessment if matched else None

    record = WeighInRecord(
        photo_ref=photo_ref,
        actual_copper_pct=actual_copper_pct,
        actual_aluminum_pct=actual_aluminum_pct,
        actual_ferrous_pct=actual_ferrous_pct,
        estimated_copper_pct_range=list(matched_assessment.copper_pct_range) if matched_assessment else None,
        estimated_aluminum_pct_range=list(matched_assessment.aluminum_pct_range) if matched_assessment else None,
        estimated_ferrous_pct_range=list(matched_assessment.ferrous_pct_range) if matched_assessment else None,
        lot_type=matched_assessment.lot_type if matched_assessment else None,
    )

    writer = writer or SqliteEntityMemoryWriter(path=path)
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

# lot_type values whose whole point is that copper is NOT expected to be
# visibly exposed -- if copper_exposure says otherwise for one of these, the
# two judgments genuinely conflict. exposed_copper_windings_stators is
# deliberately excluded (that's its own defining trait, not a conflict);
# "unclear"/"not_applicable"/None are excluded too (too uncertain to call a
# real contradiction).
_NON_EXPOSED_LOT_TYPES = (
    "sealed_motors_alternators_starters", "large_industrial_machinery",
    "aluminum_dominant_items", "loose_mixed_steel",
)


def compute_coherence_note(
    copper_exposure: CopperExposure,
    is_scrap_metal_lot: bool,
    lot_type: Optional[str],
) -> Optional[str]:
    """Deterministic cross-field check -- no LLM call. copper_exposure and
    lot_type are independent judgments from the SAME isolated call, but
    they describe physically linked facts (see module docstring): a lot
    classified as e.g. sealed_motors_alternators_starters should not also
    be described as showing stripped/exposed copper -- if it is, the two
    judgments genuinely disagree. Neither field is treated as authoritative
    over the other; a real disagreement is surfaced, never silently
    reconciled.

    The SECOND conflict this function used to check (category mix
    dominated by sealed motors, but the computed composite's copper
    ceiling exceeded) no longer applies and has been REMOVED, not silently
    dropped: in the base-rate + deviation design, lot_type is a single
    whole-lot classification and its base rate is a direct table lookup,
    never a blend across categories -- there is no composite ceiling left
    to exceed. That the old failure mode is now structurally impossible,
    rather than merely patched again, is the actual point of the
    architectural replacement.

    Returns None when everything is coherent (the common case)."""
    if not is_scrap_metal_lot:
        return None

    if copper_exposure == "exposed_stripped" and lot_type in _NON_EXPOSED_LOT_TYPES:
        return (
            "visual judgments partially conflict -- copper exposure suggests stripped/exposed copper "
            f"windings, but the lot was classified as {lot_type.replace('_', ' ')}, not an exposed-copper-"
            "windings type; treat ranges with extra caution"
        )
    return None


def render_scrap_estimate_as_text(estimate: ScrapEstimate) -> str:
    """Multi-line, clearly-labeled rendering. yield_assessment's note (if
    present) already contains the fully-composed base-rate + deviation
    text (see compute_yield_assessment) -- rendered as its own clearly-
    labeled line, not buried in a trailing clause."""
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
    if estimate.yield_assessment:
        ya = estimate.yield_assessment
        lines.append(f"Lot type: {ya.lot_type.replace('_', ' ')}.")
        lines.append(
            f"Estimated yield -- copper: roughly {ya.copper_pct_range[0]:g}-{ya.copper_pct_range[1]:g}% of "
            f"sample weight; aluminum: roughly {ya.aluminum_pct_range[0]:g}-{ya.aluminum_pct_range[1]:g}%; "
            f"HMS-ferrous (predominantly ferrous scrap): roughly {ya.ferrous_pct_range[0]:g}-{ya.ferrous_pct_range[1]:g}%."
        )
        lines.append(ya.note)
        if "no weigh-ins yet" in ya.yield_source:
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

    # Step 2: base-rate + deviation yield assessment -- ONLY for real
    # scrap-metal lots. Every classification below (lot_type, sub_type,
    # richness) is now a 5-VOTE modal decision (width reduction pass,
    # change 1) -- the accuracy centerpiece, ~5x calls, explicitly
    # accepted. lot_type is a fully separate isolated call (Step 1 no
    # longer determines it) so it can be voted without re-generating
    # grade/oxidation/etc. five times for no reason.
    lot_type = "not_applicable"
    yield_assessment = None
    if is_scrap_metal_lot:
        lot_type, _lot_type_unanimous, _ = vote_lot_type(image_path, client)

    if is_scrap_metal_lot and lot_type not in ("unclear", "not_applicable"):
        subtype = None
        refined_subtype_range = None
        if lot_type == "sealed_motors_alternators_starters":
            subtype, subtype_unanimous, _ = vote_motor_subtype(image_path, client)
            # Within-range refinement (width reduction pass, change 2):
            # fires ONLY on genuine 5/5 unanimity for a REAL (non-"mixed")
            # sub-type -- reliability-gated (5 runs on photo 1, came back
            # 5/5 stable, see module docstring) before being wired in here.
            if subtype_unanimous and subtype != "mixed_sealed_motors":
                base_range = _MOTOR_SUBTYPE_PROFILES[subtype]["copper"]
                tertile = refine_subtype_within_range(image_path, client, subtype, base_range)
                refined_subtype_range = _tertile_to_range(base_range, tertile)

        richness, richness_unanimous, evidence, _ = vote_copper_richness(image_path, client)
        calibrated_yields = _compute_calibrated_yields(entity_id, path=path)
        yield_assessment = compute_yield_assessment(
            lot_type, richness, evidence, calibrated_yields, subtype,
            richness_is_unanimous=richness_unanimous, refined_subtype_range=refined_subtype_range,
        )

    # Step 2b: cross-field physical-coherence check -- deterministic, no LLM
    # call. copper_exposure and lot_type are independent judgments from the
    # SAME isolated call; a real disagreement is surfaced, not silently
    # reconciled, and drops confidence one level.
    coherence_note = compute_coherence_note(
        copper_exposure=result["copper_exposure"],
        is_scrap_metal_lot=is_scrap_metal_lot,
        lot_type=lot_type,
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
        condition_note=condition_note,
        yield_assessment=yield_assessment,
        coherence_note=coherence_note,
        track_record_note=track_record_note,
        comparison_note=comparison_note,
        scrap_score=scrap_score,
        confidence=confidence,
        reasoning=result["reasoning"],
    )

    writer = writer or SqliteEntityMemoryWriter(path=path)
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
