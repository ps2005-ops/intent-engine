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

## LIVE VERIFICATION on deployed 6d3c75f

D6 — **LIVE_VERIFIED**. The Cloudflare brief now reads "what Cloudflare, Inc.
has published is not enough to read a strategy from". Previously "this
company". Canonical identity reaches the page.

D8 — holding. "The company's own pages · 5 / Executive statements · 1 /
Filings and investor material · 2". No contradiction, no raw enums.

## D9 — NEW, SEV2, and it explains two batches of "UI live proof outstanding"

A live run exposes only:

    story, dashboard, brief, slides, sources, full

There is **no `/runs/<id>/xray`**. `xray.render` is reachable only at
`/demo-dossiers/<company>/xray`, which is the stored-dossier path, not the
live analysis path.

So the Economic History rendering (batch 21) and the Second Iteration
rendering (batch 23) are both correct, both unit-proven, and both on a surface
a live customer run never reaches. This is the same family as the inert
coverage fix: wired to a real consumer that is not the one on the customer
path.

It also explains why the last two reports both ended with "UI live proof
outstanding" for these capabilities — the proof was never going to arrive from
that route.

NEXT (highest value, cheap): render `_second_iteration_body` and the history
state into the BRIEF (`founder_brief/dossier.py`), which is the surface a live
run actually opens, or expose `/runs/<id>/xray`. Both engines and both
projections already exist; this is routing, not architecture.

## SECOND ITERATION — still not computed per run
`second_iteration.compare()` needs a PRIOR run for the same company. The
service has no prior-run lookup wired, so no live run carries a delta yet.
That is the other half of making the hero card real.
