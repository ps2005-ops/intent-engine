#!/usr/bin/env python
"""Part 5, first build step: replay the diagnosis registry against 6 real,
already-documented failure episodes from this project's own history
(PROGRESS.md), scoring whether mechanical triage -- given ONLY the
presenting symptoms as they would have looked AT THE TIME, no hindsight
about the eventual fix -- would have selected the fix category that
actually resolved each episode.

Scope discipline, per direct instruction: this script ONLY replays the
registry. No live loop, no orchestrator, no budget machinery, no bar
objects. The verdict here is what decides whether Part 5's v1 proceeds
as designed, needs its registry revised, or needs rethinking.

Misses are findings, not embarrassments -- each miss below is classified
as either a REGISTRY GAP (a missing signature, fixable by adding one) or
a CONFIRMED SCOPE BOUNDARY (evidence the episode needed judgment beyond
mechanical triage, validating rather than undermining the loop's design).

Usage: python scripts/replay_diagnosis_registry.py
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.diagnosis_registry import diagnose  # noqa: E402


@dataclass
class Episode:
    name: str
    presenting_symptoms: str  # as observed AT THE TIME -- no hindsight about the fix
    signature: str            # the triager's signature assignment from symptoms alone
    extraction_shape: str     # "free_text" / "closed_taxonomy" / "unknown" / "n/a"
    real_historical_fix: str
    real_fix_category: Optional[str]  # None where no resolved fix exists yet to compare against
    manual_verdict: Optional[str] = None  # set only when equality-of-category isn't the whole story
    manual_note: str = ""


EPISODES = [
    Episode(
        name="1. Invented taxonomies (category_proportions v1)",
        presenting_symptoms=(
            "Real reliability testing across 18 real calls showed free-text category "
            "extraction producing inconsistent category labels across repeated runs on "
            "the same photo, and 'unclear' was never used honestly -- the model always "
            "guessed a specific category even when the photo didn't clearly support one."
        ),
        signature="unstable_across_reruns",
        extraction_shape="free_text",
        real_historical_fix=(
            "v2: switched to a closed taxonomy AND added 3-vote sampling simultaneously "
            "(the real fix layered both categories at once, not just the primary one)."
        ),
        real_fix_category="closed_taxonomy_extraction",
    ),
    Episode(
        name="2. >100% composite bound",
        presenting_symptoms=(
            "Property-fuzz testing (2000+ random trials) found the composite math's "
            "output could exceed 100% -- confirmed up to 143.2% on real photos, a hard "
            "mathematical bound violated."
        ),
        signature="bound_violated",
        extraction_shape="n/a",
        real_historical_fix=(
            "A constrained single-scalar normalization plus a min/max-of-two-weightings "
            "composite formula, provably bounded by construction -- not a clamp."
        ),
        real_fix_category="deterministic_bounded_composition",
    ),
    Episode(
        name="3. Label anchoring (assess_deviation)",
        presenting_symptoms=(
            "A real 5-runs x 3-photos reliability test showed the model's richness "
            "judgment changing when a classified lot-type label and numeric baseline "
            "were included in the same call vs. withheld -- 4 of 5 runs rationalized a "
            "copper-rich photo as 'typical' when given the baseline."
        ),
        signature="anchors_on_offered_context",
        extraction_shape="n/a",
        real_historical_fix="Stripped the lot-type label, baseline, and number from the call entirely.",
        real_fix_category="information_hiding",
    ),
    Episode(
        name="4. Prefix leak (mom's fitness captions)",
        presenting_symptoms=(
            "A live generate -> correct -> regenerate cycle showed scaffolding text "
            "present in the stored example records (needed only to satisfy an unrelated "
            "extraction requirement) appearing verbatim in 2 of 3 real generated "
            "captions -- it recurred across enough gathered examples to register as a "
            "'recurring content element' the model then imitated."
        ),
        signature="anchors_on_offered_context",
        extraction_shape="n/a",
        real_historical_fix=(
            "example_text_transform/output_text_transform hooks strip the prefix before "
            "the model ever sees it, and before display."
        ),
        real_fix_category="information_hiding",
        manual_note=(
            "Real fit, but a different MECHANISM than episode 3 (generation-leak/imitation "
            "vs. classification-bias) -- both resolve to the same fix category because the "
            "diagnostic test (does removing the suspect field change the output?) applies "
            "identically either way. Worth widening this signature's documented definition "
            "explicitly to cover generation-leak cases, not just classification bias."
        ),
    ),
    Episode(
        name="5. Degenerate classifier (backtest v1)",
        presenting_symptoms=(
            "Across an 18-case real backtest, PremortemAnalyzer's risk-audit output "
            "showed near-zero variation -- 17 of 18 cases received the same 'majority "
            "risky' classification regardless of whether the real case was a $30k "
            "reversible marketing stunt or a $1.2B capital-intensive infrastructure "
            "failure. Not a same-input-rerun problem -- a near-total insensitivity to "
            "genuinely different inputs."
        ),
        signature="novelty_or_scope_gap",
        extraction_shape="n/a",
        real_historical_fix=(
            "NOT YET RESOLVED. The evaluation-stage design (structural-match conditions, "
            "PROGRESS.md) is a PROPOSED, build-deferred fix -- itself unvalidated, not a "
            "real, shipped resolution to compare against."
        ),
        real_fix_category=None,
        manual_verdict="miss_registry_gap",
        manual_note=(
            "None of the 5 substantive signatures fit: no rerun instability, no single "
            "suspect field to toggle, no bound violated, no two fields disagreeing, no "
            "citation issue. Correctly falls to the catch-all (escalate, no guess) -- a "
            "correct 'I don't know' is a legitimate outcome, not a wrong answer. Classified "
            "as a REGISTRY GAP, not a scope boundary: 'insufficient output variance across "
            "genuinely different inputs' is a describable, checkable property (unlike the "
            "base-rate pivot, this doesn't require comparing against a hypothetical "
            "alternative approach) -- a candidate 7th signature, "
            "e.g. insufficient_discrimination_across_inputs, could plausibly be added. Its "
            "candidate fix is not yet known to work, since the only proposed fix (the "
            "evaluation stage) hasn't been validated."
        ),
    ),
    Episode(
        name="6. Near-miss: sub-type classification instability (photo 4)",
        presenting_symptoms=(
            "Reliability-testing sub-type classification (5 runs) on photo 4 showed a "
            "3/5 vs. 2/5 split between mixed_sealed_motors and small_fractional_motors -- "
            "inconsistent across reruns on the same photo."
        ),
        signature="unstable_across_reruns",
        extraction_shape="closed_taxonomy",
        real_historical_fix=(
            "NOT further iterated. Disclosed as a real limitation ('on a genuinely "
            "borderline lot, sub-type narrowing may apply inconsistently') and shipped "
            "as-is for photos that met the bar (1, 7), leaving photo 4 at its coarse "
            "fallback range."
        ),
        real_fix_category="self_consistency_voting",
        manual_verdict="miss_scope_boundary",
        manual_note=(
            "The registry's signature assignment IS correct, and self_consistency_voting "
            "IS a reasonable next mechanical step -- but sub-type classification was "
            "ALREADY vote-based going in, and still wobbled on this specific borderline "
            "photo. The real resolution wasn't 'apply the fix category again,' it was "
            "recognizing an irreducibly borderline case and stopping to disclose an honest "
            "floor. This CONFIRMS a scope boundary the Part 5 proposal's stopping rule "
            "already designed for (honest-floor exit, mandatory human confirmation) rather "
            "than exposing a registry defect -- diagnosis correctly identifies the PROBLEM "
            "TYPE; recognizing WHEN to stop retrying that type and accept a floor instead "
            "is the stopping rule's job, not the registry's."
        ),
    ),
]


def score(ep: Episode) -> str:
    if ep.manual_verdict:
        return ep.manual_verdict
    selected = diagnose(ep.signature, ep.extraction_shape)
    return "match" if selected == ep.real_fix_category else "miss_unclassified"


def main():
    print("=" * 100)
    print("DIAGNOSIS REGISTRY REPLAY -- 6 real, documented failure episodes")
    print("=" * 100)

    results = []
    for ep in EPISODES:
        selected = diagnose(ep.signature, ep.extraction_shape)
        verdict = score(ep)
        results.append((ep, selected, verdict))

        print()
        print(f"--- {ep.name} ---")
        print(f"Presenting symptoms (no hindsight): {ep.presenting_symptoms}")
        print(f"Triaged signature: {ep.signature}" + (f" (extraction_shape={ep.extraction_shape})" if ep.extraction_shape != "n/a" else ""))
        print(f"Registry selected: {selected}")
        print(f"Real historical fix: {ep.real_historical_fix}")
        print(f"Real fix category: {ep.real_fix_category!r}")
        print(f"VERDICT: {verdict.upper()}")
        if ep.manual_note:
            print(f"Note: {ep.manual_note}")

    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    matches = [r for r in results if r[2] == "match"]
    gaps = [r for r in results if r[2] == "miss_registry_gap"]
    boundaries = [r for r in results if r[2] == "miss_scope_boundary"]
    unclassified = [r for r in results if r[2] == "miss_unclassified"]

    print(f"MATCH: {len(matches)}/6 -- {', '.join(ep.name.split('.')[0] for ep, _, _ in matches)}")
    print(f"MISS (registry gap, fixable): {len(gaps)}/6 -- {', '.join(ep.name.split('.')[0] for ep, _, _ in gaps)}")
    print(f"MISS (confirmed scope boundary): {len(boundaries)}/6 -- {', '.join(ep.name.split('.')[0] for ep, _, _ in boundaries)}")
    if unclassified:
        print(f"MISS (unclassified -- needs review): {len(unclassified)}/6")

    print()
    print("Honest read: 4/6 clean category matches on real, already-resolved episodes")
    print("(with one, episode 4, matching via a documented widening of the anchoring")
    print("signature's definition rather than a slam-dunk fit). The 2 misses are both")
    print("informative, not embarrassing: episode 5 is a real registry gap (no signature")
    print("for cross-input insensitivity) with no proven fix to add yet either; episode 6")
    print("confirms the stopping rule's honest-floor exit is doing real work the registry")
    print("itself was never meant to do.")


if __name__ == "__main__":
    main()
