"""Part 5 (iteration-loop / self-evaluation layer), first build step: the
diagnosis registry.

Per the approved Part 5 proposal (PROGRESS.md): a closed, enumerable
failure-signature taxonomy, each mapped to a real candidate fix category
already used at least once in this project -- restructured as a
machine-consultable lookup, not prose a human re-reads and pattern-matches
by hand each time.

Scope discipline, per direct instruction: this module is ONLY the
registry (data) and the matching layer (diagnose()). No live loop, no
orchestrator, no budget machinery, no bar objects -- those wait on what
scripts/replay_diagnosis_registry.py's replay against this project's own
real, already-resolved failure episodes shows.

The one real disambiguation this registry needs, not a flat 1:1 map:
`unstable_across_reruns` has two candidate fixes depending on whether the
CURRENT extraction is already a closed taxonomy (needs more votes +
honest uncertainty representation) or still free-text (needs the taxonomy
change first, a more foundational fix). Every other signature is a
straight lookup.

`novelty_or_scope_gap` -- and any signature this registry doesn't
recognize at all -- always resolves to `no_fix_escalate`. This registry
fails CLOSED: it never guesses a fix category it has no real precedent
for.
"""

from typing import List, NamedTuple

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

FailureSignature = Literal[
    "unstable_across_reruns",
    "anchors_on_offered_context",
    "bound_violated",
    "cross_field_incoherent",
    "citation_unresolvable",
    "stable_but_non_discriminating",
    "novelty_or_scope_gap",
]

FixCategory = Literal[
    "closed_taxonomy_extraction",
    "self_consistency_voting",
    "information_hiding",
    "deterministic_bounded_composition",
    "cross_field_coherence_check",
    "citation_computed_in_code",
    "design_level_fix_required",
    "no_fix_escalate",
]

ExtractionShape = Literal["free_text", "closed_taxonomy", "unknown"]


class RegistryEntry(NamedTuple):
    signature: FailureSignature
    fix_category: FixCategory
    rationale: str


REGISTRY: List[RegistryEntry] = [
    RegistryEntry(
        "unstable_across_reruns", "closed_taxonomy_extraction",
        "Free-text extraction is inherently unstable across reruns -- a closed "
        "taxonomy removes the degrees of freedom causing the instability. The "
        "more foundational of the two unstable_across_reruns fixes; tried first "
        "when the current extraction shape is free-text or unknown.",
    ),
    RegistryEntry(
        "unstable_across_reruns", "self_consistency_voting",
        "Extraction that is ALREADY a closed taxonomy but still unstable across "
        "reruns needs more samples plus an honest uncertainty representation "
        "(e.g. a bin-union width), not a taxonomy change it already has.",
    ),
    RegistryEntry(
        "anchors_on_offered_context", "information_hiding",
        "A judgment or generation changes when a suspect contextual field "
        "(a label, a baseline, contaminating scaffolding text) is present vs. "
        "withheld -- remove the field from the call. Never instruct the model "
        "to ignore it; that has never been the durable fix in this project. "
        "This signature covers TWO distinct mechanisms with the same "
        "diagnostic test and the same fix: (1) classification bias -- a "
        "judgment call rationalizes toward an offered label/baseline "
        "(episode 3, assess_deviation label anchoring); (2) generation "
        "leak / imitation -- scaffolding text present in gathered examples "
        "recurs verbatim in generated output because the imitation learner "
        "treats it as a recurring content element (episode 4, mom's-captions "
        "prefix leak). Either way the test is: does withholding the suspect "
        "field change the output? If yes, hide the field structurally.",
    ),
    RegistryEntry(
        "bound_violated", "deterministic_bounded_composition",
        "A hard mathematical or logical constraint the output can never "
        "violate is broken -- fix with a provably-bounded formula, never a "
        "clamp.",
    ),
    RegistryEntry(
        "cross_field_incoherent", "cross_field_coherence_check",
        "Two independent judgments describing the same underlying fact "
        "disagree -- add a deterministic check that surfaces the disagreement, "
        "never one that silently reconciles it.",
    ),
    RegistryEntry(
        "citation_unresolvable", "citation_computed_in_code",
        "A claimed citation doesn't resolve to a real record that was actually "
        "fed into the call -- move citation computation from asked-of-the-model "
        "to computed-in-code.",
    ),
    RegistryEntry(
        "stable_but_non_discriminating", "design_level_fix_required",
        "Output is stable across reruns AND across genuinely different "
        "inputs -- near-total insensitivity to input variation, "
        "indistinguishable from a constant predictor (backtest v1: 17/18 "
        "cases flagged 'majority risky' whether the case was a $30k "
        "reversible stunt or a $1.2B capital failure; out-of-sample "
        "confirmation: the job-application agent's top_n=10 "
        "bullet-selection degeneracy). Not a rerun-instability problem, "
        "not a single suspect field, no bound broken, no fields "
        "disagreeing -- the pipeline is MISSING A STAGE or has a "
        "degenerate selection rule. ENCODED, UNVALIDATED: no shipped fix "
        "of this category exists yet in this project (the evaluation-stage "
        "design is proposed, build-deferred). The fix is design-level and "
        "requires a human decision -- it is never a mechanical retry. "
        "Detection is deterministic: check_discrimination_bar().",
    ),
    RegistryEntry(
        "novelty_or_scope_gap", "no_fix_escalate",
        "No known signature fits. Escalate. Never guess a fix.",
    ),
]

_FIX_BY_SIGNATURE = {
    entry.signature: entry.fix_category
    for entry in REGISTRY
    if entry.signature != "unstable_across_reruns"
}


def diagnose(signature: str, extraction_shape: str = "unknown") -> FixCategory:
    """The thin matching layer. Pure lookup, with the one real
    disambiguation the registry needs (see module docstring). Fails
    CLOSED: any signature not in REGISTRY -- including a raw string that
    isn't one of the 7 known FailureSignature values -- returns
    "no_fix_escalate" rather than raising or guessing."""
    if signature == "unstable_across_reruns":
        if extraction_shape == "closed_taxonomy":
            return "self_consistency_voting"
        return "closed_taxonomy_extraction"

    return _FIX_BY_SIGNATURE.get(signature, "no_fix_escalate")


def check_discrimination_bar(
    predictions: List[str],
    ground_truth: List[str],
    baseline_predictions: List[str],
    margin: float = 0.10,
) -> bool:
    """Deterministic detector for `stable_but_non_discriminating`.

    Narrowly scoped helper next to its registry row -- NOT a general
    shared bar-tier module, per the recorded 'documented pattern, not
    shared code' resolution.

    Compares the system's accuracy against a trivial baseline predictor's
    accuracy on the same real ground truth. Returns True when the bar
    FLAGS the signature (the system fails to beat the baseline by more
    than `margin`) -- i.e. True means 'non-discriminating, do not trust
    the accuracy number'. Returns False when discrimination is real.

    Computed in code, never asked of a model. The margin exists because
    backtest v1 proved a degenerate classifier can still nominally beat a
    baseline (66.7% vs. 61.1%) purely by riding the base rate -- a small
    raw edge over 'always predict the majority class' is not evidence of
    discrimination.
    """
    n = len(ground_truth)
    if n == 0 or len(predictions) != n or len(baseline_predictions) != n:
        raise ValueError(
            "predictions, ground_truth, and baseline_predictions must be "
            "non-empty and the same length"
        )
    accuracy = sum(p == g for p, g in zip(predictions, ground_truth)) / n
    baseline_accuracy = sum(
        b == g for b, g in zip(baseline_predictions, ground_truth)
    ) / n
    return accuracy < baseline_accuracy + margin
