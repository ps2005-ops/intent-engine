# Adaptive Strategic Intelligence — final verdict

```
QUALIFYING_SHA   807a414361b0fbc1999b4595e875c67e2a20524a
LIVE_SHA         807a414361b0fbc1999b4595e875c67e2a20524a
PRODUCT FROZEN   YES — no product code changed between the freeze and the last company
SERVICE          https://intent-engine-preview-bridge.onrender.com
BOOT             4382f79befa14b4d
```

## Result

```
COMPLETE_COMPANY_PASS            0/10
  of which blocked solely by
  one systemic, diagnosed defect   7
  blocked by retrieval             1
  blocked by a profile seam        1
  blocked by an evidence span      1

DEMO_READY                       NO
```

**0/10 is the strict reading and it is the honest headline.** It is also, on
its own, misleading, because the gates say something quite different:

```
IDENTITY                         10/10
EVIDENCE SURFACE                 10/10
Q&A ANSWERED                     60/60
Q&A COMPANY-SPECIFIC             60/60
Q&A SUBSTANTIVE (body >=40w)     42/60
FOLLOW-UP CONTEXT                10/10
CROSS-COMPANY CONTAMINATION      0
RAW ENUM / INTERNAL TERM LEAKS   0
ENDLESS SPINNERS                 0
DARK MODE CONTRAST FAILURES      0  (1,554 elements)
LIGHT MODE CONTRAST FAILURES     0  (1,554 elements)

of the nine companies that produced a report:
COMPANY_PROFILE                  8/9
STRATEGIC_LENS                   8/9   (8/8 inside the expected family)
WHY_THIS_COMPANY                 8/9
DECISION OR DEFENSIBLE ABSTENTION 8/9
CAUSAL_OR_INVESTIGATION          8/9
COUNTEREVIDENCE_OR_LIMITATION    9/9
CEO_ROLE / STRATEGY_ROLE         9/9 / 9/9
ROLE FACT INVARIANCE             9/9
DECISION_READING_AVAILABLE       0/9   (8 defensible abstentions, 1 fail)
UNEXPLAINED TEMPLATE COLLAPSES   1     (Cyera vs Druva, cause identified)
ATTRIBUTION / SPAN DEFECTS       1     (ZoomInfo, an SEC bullet fragment)
```

## Why nothing reached a decision-grade reading

`0/9`, and it is an environment fact rather than a reasoning failure. The
preview reports `DISCOVERY_NOT_RUN` — *"no search was run"* — so no independent
third-party source can be found. Every source on every run was company-owned:
`0 of 6` independent for Highspot, `0 of 4` for Slalom, `0 of 8` for Point B.
The product states this as a limit of retrieval and not as a finding about the
company, which is correct and is asserted by test.

Eight of the nine therefore abstained, and the abstention is the product
evidence: profile YES, lens YES, decision reading NO, rendered as potential
domains labelled *not current recommendations*, an investigation chain, and a
block naming the evidence limitation and what would unlock a reading.

**The decision-grade path is unexercised on this deployment.** Nothing in this
matrix demonstrates it works live.

## The four defects that block the gate

**1. One run, two business models — 7 of 10.** `/intro` establishes the model
from the company's own words; `/xray` says it has not been established. The
correlation with the model's source is exact: every company classified at
rung 3 (`SUBJECT_PUBLISHED_EVIDENCE`) carries it, ZoomInfo at rung 2 does not,
and the two unclassified companies agree on both surfaces. Rung 3 is the rung
this phase added; it is the only one the X-Ray path cannot reach.

Cause traced to a producer, not guessed: the panel prints
`AnalysisSelection.why_this_question`, which `analysis_selection.select` sets to
`profile.profile_limitation` when the profile is unknown, and
`decision_synthesis._select()` calls `AS.select` with manifest and registrant
only. Four call sites were missing rung 3; one was fixed in the freeze commit;
the one feeding this panel needs `published_text` threaded through
`decision_synthesis.compose`, across two modules.

**Not fixed, deliberately.** It was found hours before the freeze and the fix
is a cross-module parameter. Making it unvalidated would have turned this
qualification into a guess about a build nobody had measured.

**2. Point B — the classifier reads excerpts, not documents.** Eight of its own
pages retrieved including `/About`, and still `UNKNOWN`. Offline its homepage
classifies `PEOPLE_OR_ROUTE_BASED_SERVICES` at 10.0 against 4.0. The corpus
handed to the classifier is observation excerpts selected for other purposes.
Slalom escaped this only because its excerpt happened to contain "consulting
services" — which is why the same seam produced a pass and a failure in one
cohort.

**3. Monte Carlo Data — retrieval refused, and the page said so well.** Every
`montecarlodata.com` URL returned "unsafe redirect: the page redirected off the
approved domain", G2 returned 401/403, and the page rendered: *"There is no
result to show — we do not invent one… A failed retrieval is not evidence that
anything is missing in the real world"*, with a per-source ledger. That is
correct behaviour. Its one real defect is that the ledger sets URLs in `<code>`
without `overflow-wrap`, so it overflows 85px at 375px.

**4. ZoomInfo — one quotation is an SEC bullet fragment**, beginning `•` and
ending mid-list on a comma, plus one quotation rendered twice.

## What held

- **Five distinct lenses across eight companies**, every one inside its
  expected family, each publishing its score, runner-up and refusals.
- **The consultancy repair works live.** Slalom moved from `UNKNOWN`/`NNN` on
  the previous build to `PEOPLE_OR_ROUTE_BASED_SERVICES`/`YYN`, with domains
  that are consultancy-shaped: *which client exposure is concentrated*, *which
  practice to staff against*, *what a client is about to decide*.
- **Zero cross-company contamination** across 60 answers.
- **Zero invented findings.** The company with nothing retrieved answered
  "there is not enough public evidence to answer that confidently".
- **33/33 break proofs**, up from 27, six added this session and all catching.
- **10,896 tests**, 0 failed, on the frozen tree.

## Performance

```
CORE   p50 25.2s   p90 44.9s   max 49.3s   min 6.3s
surface sweep (6 pages)  p50 90.6s   max 173.6s
wall incl. 7 Q&A turns   p50 228.0s  max 339.5s
```

Free-instance CPU throttling dominates the surface and wall figures; one
`/brief` returned status 0 (a client timeout, counted as infrastructure).

## Verdict

The adaptive layer does what this phase claimed: it reads a private company
from its own words, selects a defensible lens, says what is different about
that company, and refuses to recommend when the evidence will not carry a
recommendation — and says so in a way a chief executive can act on. Nine of
ten companies produced a coherent, provenance-clean, role-stable, contamination-
free report, and the tenth failed loudly and honestly.

It is not demo-ready. One diagnosed defect puts a contradiction one click from
the headline on seven of ten companies, and it lands precisely on the private
companies this work exists to serve.
