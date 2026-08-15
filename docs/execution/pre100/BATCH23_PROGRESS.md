# BATCH 23 — PRE100 UI integration

Start `71788f9` (deployed). Market `9b01ff1`, production `cfd4c3b` untouched.
Backend frozen: no acquisition, relevance, independence or discovery change.

## D6 UPSTREAM — CLOSED at the producer
`company_name` was a local argument used to build one sentence and was NOT a
field on FounderDecision. So a decision rebuilt from its own serialised form
had no subject at all, and every surface had to guess — which is why the live
brief read "this company" while the page title read "Caterpillar Inc.".

Now: `company_name` and `identity_state` are fields, set once in
`compose_decision`, and they round-trip through `as_dict`/`decision_from_dict`.
IDENTITY_MISSING makes the fallback *visible* rather than indistinguishable
from a company actually called "this company". The defensive wording is kept.

## HYDRATION — BUILT (`founder_brief/hydration.py`)
A projection over canonical outputs, not a system. READY is caused by a
producer having produced; nothing consults a clock. Four tiers ordered by
what a READER can act on (T0 identity → T1 what we already knew → T2 what the
evidence says → T3 what it means), so the page is worth reading before it is
finished.

PENDING / RUNNING / READY / BOUNDED / DEGRADED kept distinct: a blocked
retrieval and a quiet company must not look identical — the same error already
corrected at the independence, discovery, evidence-family and history layers.
Latency targets are REPORTED, never enforced. An unmeasured duration is None,
never 0 (0 reads as instant, the flattering direction).

## SECOND ITERATION — RENDERED on the X-Ray
Projection only; the engine is unchanged. `_ITERATION_COPY` holds one customer
sentence per state in ONE place, so surfaces cannot drift the way the two
hardcoded history paragraphs did.
Exact replay renders: "Nothing arrived that we did not already hold, so no new
learning was recorded" + "This did not add to what the system knows."
No comparison renders NO card — an empty card would imply a comparison that
found nothing.

## STILL OPEN
Hydration is not yet wired to the progress page; second-iteration is not yet
computed per-run in the service (no prior-run lookup); Full Analysis /
Presentation state population, CEO Q&A exercise, Personal AI integration,
live journeys, acceptance, security, zero-Anthropic.
