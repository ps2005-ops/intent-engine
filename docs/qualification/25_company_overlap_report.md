# Overlap and collapse — two instruments

*Generated from `reports/asi25_state.json` at `712613b7588f`. Every total on this page is computed; none is typed.*

## The forty's own instrument (numerals stripped)

Comparable across cohorts because it is the same code over both
sets of captures.

| surface | 25 mean | 25 max | 25 >=0.98 | 40 mean | 40 max | 40 >=0.98 |
|---|---|---|---|---|---|---|
| intro | 0.6118 | 0.9027 | 0 | 0.6537 | 0.8794 | 0 |
| brief | 0.5943 | 0.9937 | 1 | 0.5797 | 0.9397 | 0 |
| full | 0.5164 | 0.9027 | 0 | 0.5469 | 0.9487 | 0 |
| xray | 0.7201 | 0.996 | 10 | 0.6867 | 0.9956 | 21 |
| history | 0.503 | 1.0 | 30 | 0.5264 | 1.0 | 18 |
| evidence | 0.3541 | 0.8667 | 0 | 0.3687 | 0.6651 | 0 |

Totals: 25-cohort 41 of 1800 pairs; 40-cohort 39 of 4680 pairs.

## The stricter instrument (numerals kept)

On a decision surface, stripping numerals is right: a shared number
is not a shared argument. On the HISTORY surface it removes almost
all of the content, because the years, the index values and the
base year **are** the page.

| surface | mean | max | >=0.98 |
|---|---|---|---|
| intro | 0.5846 | 0.925 | 0 |
| brief | 0.5673 | 0.9943 | 1 |
| full | 0.4918 | 0.925 | 0 |
| xray | 0.7012 | 0.9965 | 6 |
| history | 0.454 | 1.0 | 29 |
| evidence | 0.3225 | 0.8261 | 0 |

## Collapse classification

|  | forty's instrument | strict instrument |
|---|---|---|
| near-identical pairs (>=0.98) | 41 | 36 |
| EXPLAINED | 41 | 36 |
| UNEXPLAINED | 0 | 0 |
| pairs where NEITHER company abstained | 0 | 0 |

`UNEXPLAINED_COLLAPSES` is computed, not asserted: a pair is
explained only by a fact readable from the state file — a run that
abstained, or an identical history state (same level, same
dated-document count).

**The load-bearing number is the last row.** With most of this
cohort abstaining, "one of them abstained" explains almost any
pair by construction. Pairs between two *non-abstaining* companies
are the only ones where a shared reading would be two real
decisions collapsing onto each other.

## Every near-identical pair

| surface | a | b | jaccard | reasons |
|---|---|---|---|---|
| brief | Axonius | Clio | 0.9937 | both runs abstained, so there is no reading to collapse; identical history state: level ?, None dated document(s) |
| xray | Abnormal AI | Vanta | 0.9847 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| xray | Arctic Wolf | Motive | 0.9808 | one run abstained, so there is no reading to collapse |
| xray | Chainguard | Island | 0.9887 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| xray | Expel | Illumio | 0.9804 | both runs abstained, so there is no reading to collapse |
| xray | Expel | Material Security | 0.9803 | both runs abstained, so there is no reading to collapse |
| xray | Expel | Obsidian Security | 0.9803 | both runs abstained, so there is no reading to collapse |
| xray | Illumio | Material Security | 0.9803 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| xray | Illumio | Obsidian Security | 0.9803 | both runs abstained, so there is no reading to collapse |
| xray | Island | Vanta | 0.981 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| xray | Material Security | Obsidian Security | 0.996 | both runs abstained, so there is no reading to collapse |
| history | 1Password | Chainguard | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | 1Password | Huntress | 0.9849 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | 1Password | Illumio | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | 1Password | Island | 0.9924 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | 1Password | Material Security | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | 1Password | Vanta | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | 1Password | Verkada | 0.9962 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Abnormal AI | Snyk | 0.9829 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Chainguard | Huntress | 0.9886 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Chainguard | Illumio | 1.0 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Chainguard | Island | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Chainguard | Material Security | 1.0 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Chainguard | Vanta | 1.0 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Chainguard | Verkada | 1.0 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Huntress | Illumio | 0.9886 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Huntress | Island | 0.9849 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Huntress | Material Security | 0.9886 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Huntress | Vanta | 0.9886 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Huntress | Verkada | 0.9886 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Illumio | Island | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Illumio | Material Security | 1.0 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Illumio | Vanta | 1.0 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Illumio | Verkada | 1.0 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Island | Material Security | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Island | Vanta | 0.9962 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Island | Verkada | 0.9962 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Material Security | Vanta | 1.0 | both runs abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Material Security | Verkada | 1.0 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
| history | Okta | Procore | 0.9908 | one run abstained, so there is no reading to collapse |
| history | Vanta | Verkada | 1.0 | one run abstained, so there is no reading to collapse; identical history state: level C, 0 dated document(s) |
