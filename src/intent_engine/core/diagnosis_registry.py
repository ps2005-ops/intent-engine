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
    "novelty_or_scope_gap",
]

FixCategory = Literal[
    "closed_taxonomy_extraction",
    "self_consistency_voting",
    "information_hiding",
    "deterministic_bounded_composition",
    "cross_field_coherence_check",
    "citation_computed_in_code",
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
    isn't one of the 6 known FailureSignature values -- returns
    "no_fix_escalate" rather than raising or guessing."""
    if signature == "unstable_across_reruns":
        if extraction_shape == "closed_taxonomy":
            return "self_consistency_voting"
        return "closed_taxonomy_extraction"

    return _FIX_BY_SIGNATURE.get(signature, "no_fix_escalate")
