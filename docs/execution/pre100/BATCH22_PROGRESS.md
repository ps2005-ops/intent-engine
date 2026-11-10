# BATCH 22 — PRE100 integration

Start `26f8255` (deployed). Market `9b01ff1`, production `cfd4c3b` untouched.
ACQUISITION_PRE100_FROZEN = TRUE, not touched this run.

## D8 — FIXED AT THE SEAM
Root cause: `source_class_coverage` counted OBSERVATIONS while the
bibliography counted DOCUMENTS. A filing read but not extractable vanished
from the inventory and stayed in the source list — one page contradicting
itself.

Deeper cause: the family state was an INTEGER. Zero had to mean "never
looked", "was refused", "read it and it said nothing", and "cannot apply".

`company_ingestion/source_coverage.py` (source_class_coverage.v2) is now the
single typed object: PRESENT / RETRIEVED_NO_SIGNAL / BLOCKED / ATTEMPTED_NONE
/ NOT_ATTEMPTED, each carrying documents, observations and a reason.
`contradicts()` is the standing guard — a family holding documents while
claiming nothing was attempted is the defect itself.

Caterpillar's exact shape now reads: filings RETRIEVED_NO_SIGNAL (1 doc),
company pages BLOCKED, third-party NOT_ATTEMPTED. Legacy integer consumers
unchanged via `legacy_counts`; an older run with only the integer map still
renders as before (negative control).

## SECOND ITERATION — BUILT
`strategic_intelligence/second_iteration.py`. Evidence identity is the CONTENT
HASH, never URL or retrieval date, so a re-read cannot be credited as an
observation. Seven states; REPRESENTS_LEARNING deliberately includes
"tested and held", because a belief that survived new evidence is stronger
than one nothing challenged.

The two traps, both tested:
- exact replay (Run 3) reports NO_NEW_INFORMATION, learning False
- a reading that MOVED with no new evidence is INCOMPARABLE, not learning —
  that is instability, and calling it learning would hide it

## ECONOMIC HISTORY
Producer from batch 21 unchanged and wired.

## NOT DONE
Hydration, X-Ray/Full-Analysis rewrite, deck state population, CEO Q&A
exercise, Personal AI integration, live journeys 3-9, acceptance, hostile
buyer, security, zero-Anthropic. Second-iteration and coverage objects are
built and unit-proven but NOT yet rendered on a deployed page.
