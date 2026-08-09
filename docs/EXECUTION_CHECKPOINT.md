# Execution checkpoint — V3 multi-actor economic intelligence

Machine-readable continuation state. A completed slice is a checkpoint, not an
endpoint: this file exists so the mission survives a context boundary instead
of restarting from an audit.

Updated 2026-08-08, V4 SESSION 1.

## V4 session 3 — evidence learns what it changed

V3 FROZEN at market `2ee1635` / founder `247ad23`. Production `119d345`
untouched. PAPER in all three plists.

### The seam was in the wrong place

`affected_hypotheses` and its neighbours live on MicroEvidence, which is built
from a document BEFORE any belief exists for it to affect. At that moment there
is nothing true to write there — which is why all 316 rows carried empty
tuples, and why filling them in later from text similarity would have been a
guess wearing a provenance field.

An effect is a fact about a STATE CHANGE, so `KnowledgeEffect` is its own
append-only record written where the state changes. `belief_formation.propose`
already knew which evidence opened which belief and which went nowhere; it
counted the second and discarded the first.

    316 / 316 evidence rows attributed, 0 unattributed
    201 changed something · 115 changed nothing
    855 effects: 428 NO_CHANGE · 405 CREATED · 11 RESOLVED
                 8 SUPPORTED · 3 CONTRADICTED

NO_CHANGE is half the log and is the half that matters: without it, "we
accepted 316 rows" and "we learned 316 things" are the same number.

### The correction I owe the previous run

The reward audit reported HACKABLE because a volume attack topped the table.
Measured properly, that attack picks independent reporting, which has the
HIGHEST knowledge-change rate in the corpus:

    family                   n   change  discrim   dup    mean reward
    independent_reporting  146    0.76     0.06   0.03       +2.06
    regulatory_filing       84    0.52     0.00   0.75       +0.86
    analyst_coverage        22    0.45     0.05   0.09       +1.48
    company_owned           64    0.56     0.00   0.73       -0.09

The volume arm and the value arm are the same arm. Hackability now tests
whether an attack wins WHILE CHANGING LESS than the best honest policy.
**REWARD_HACKABLE = False.** The finding underneath is that the VOI heuristic
is wrong for this corpus: it prefers filings, and 75% of filing rows repeat a
fact the ledger already holds.

### Two NOs closed

DEMAND_CHAIN: nine states, because backlog rising is equally consistent with
orders rising and shipments slipping. Cancellations are a LEAK, not a step.
Live: 15 of 26 companies show any state, 21 of 260 states measured, every chain
UNKNOWN overall — the corpus, not the layer.

PRESENTATION: 12 sections generated from the thesis, the headline verb bound to
the standing by table, and the alternatives and falsifier slides REQUIRED.

### numeric_values, finally, and why the yield is 6%

Subject-first extraction: a digit no economic subject claims is discarded. Two
precision defects the live corpus found — a $400M buyback read as revenue, and
`EUR 9.3 billion total net sales` read as the 2.9 billion net income figure
because the scan only looked forward.

### The bottleneck now

`PROSPECTIVE_RESEARCH_LOG`. The log is still reconstructed from evidence that
SURVIVED, so every action that returned nothing is missing and every rate over
it is biased toward success. Until choices are written down before their
outcomes, no learned policy can be shown to beat the heuristic.

### Break proofs

Session 3: **21/21**, after four NOT_CAUGHT each named a test that did not
discriminate its guard. `run_all` now takes a mutation lock — the previous
session ran two scripts against one worktree and they corrupted each other's
restores.

### Readiness

    PASS 11 · PARTIAL 25 · BLOCKED_DATA 1 · NO 1

against session 2's PASS 9 · PARTIAL 22 · BLOCKED_DATA 1 · NO 2.

## V4 session 2 — the economy stops being one series, and the reasoning gets a shape

V3 is FROZEN at market `2ee1635` / founder `247ad23`. Production `119d345`
untouched. PAPER enforced in all three plists.

### Source coverage: 1 condition -> 15 of 30

| publisher | keyless | gives |
|---|---|---|
| US Treasury FiscalData | yes | note rate, bill rate, interest expense |
| Bank of Canada Valet | yes | policy rate, 2y/10y yields, USDCAD, BCPI, energy |
| Statistics Canada WDS | yes | unemployment, CPI, GDP, manufacturing, wages, housing |
| US BLS | **503 on every probe** | adapter written, reports by name each cycle |
| FRED, EIA, Census | key required | not attempted |

StatCan is the only source that publishes its own release date. Everything else
assumes one, deliberately late.

### Two defects the live data found

The federal interest-expense endpoint returns three accounting lines a month
under one security type and the amortised PREMIUM line is negative; sorted
last, it made the United States look paid 0.134bn a month to borrow. And a 2-
and a 10-year yield are both MARKET_RATE, so the engine's reading of Canadian
rates flipped between them on ties and reported a 0.7-point move that was a
change of subject. `PRIMARY_SERIES` and an `area` on every figure close both.

### The measurement that matters most

    method            silhouette  coherence  stability  utility
    RULE                   -0.09       1.03       1.00    +0.23   <- useful
    KMEANS                  0.46       0.97       1.00    -0.00
    GAUSSIAN_MIXTURE        0.46       0.97       1.00    -0.00

The fitted models have the best geometry and carry no information about the
next CPI change. The stated economic rule has the worst silhouette of the three
and is the only partition that reduces held-out error. Statistical quality and
economic utility are tracked separately because they disagree.

### Forecast baselines, on real series

    TREASURY_NOTES_AVG_RATE   AR1 skill 0.40   beats the random walk decisively
    STATCAN CPI               DRIFT skill 0.95 beats it slightly
    BOC 10-year yield         AR1 skill 0.96   barely beats it
    STATCAN unemployment      nothing beats the random walk

### The reward is hackable, and the reason is the finding

`affected_causal_nodes`, `affected_hypotheses`, `affected_hidden_states` and
`numeric_values` are empty on **all 316** evidence rows. Three of the reward's
four positive terms are therefore unmeasurable, only independence and
duplication remain, and under that reduced reward ATTACK_VOLUME ties the best
honest policy. The audit reports HACKABLE=True rather than hiding it.

Family mean reward on the reconstructed log:

    independent_reporting  +0.773    analyst_coverage  +0.709
    regulatory_filing      +0.050    company_owned     -0.934

Filings score low because 75% of their rows repeat a fact already in the
ledger, which is a defect in the filing adapter and not a fact about filings.

### What now exists and runs every cycle

| object | live measurement |
|---|---|
| `macro_state` | 15/30 tracked conditions, 3 areas, 2 derived spreads |
| `macro_expectation` | 6 baselines, scored against the random walk |
| `unsupervised` | regimes, exposure clusters, 14 anomalies, all with questions |
| `research_policy` | 316-row reconstructed log, 6 policies, reward audit |
| `economic_thesis` | 7 theses, 3 alternatives each, 28 falsifiers, 2 contested |
| `founder_v4_view` | briefing + Q&A + challenge refusal + DecisionImpact |
| `internal_state` | synthetic enterprise, permission and provenance walls |
| bridge | economic block crosses `strategic_market_intel.v1` both ways |

### Break proofs

V4 session 2: **36/36 held**. Seven came back NOT_CAUGHT first and every one
named a test that did not discriminate its guard rather than a guard that did
not hold. V4 session 1: 12/12 after one anchor was updated for the new `area`
parameter.

### The bottleneck, measured

`EVIDENCE_LINKAGE`. Not source coverage any more — that moved from 1 condition
to 15. The producer writes evidence rows whose "what did this touch" fields are
empty on every row, which makes the research reward unfalsifiable, keeps
`decision_relevant` and `resolved_open_question` at zero, and leaves the
discriminating term structurally unmeasurable.

### Verified live

One production-equivalent PAPER cycle, EXIT=0, runtime pinned to the branch
tip. In the persisted report:

    macro_state       OBSERVED 13, INFERRED 2, UNKNOWN 15; 2344 history rows
    unsupervised      113 discoveries (102 anomalies, 11 regimes),
                      3 methods scored, 1 economically useful
    research_policy   107-row log, best FIXED_INDEPENDENT_REPORTING,
                      beats_random true, deployable false
    reward_audit      hackable true, top ATTACK_VOLUME
    economic_thesis   6 theses, 24 falsifiers, 2 contested, 0 assertable
    founder_v4        6 briefings over 2 subjects, all carrying alternatives

102 anomalies is a generous detector on 2344 rows, not 102 findings. Ranking
them by value of information is the next thing that layer needs.

### Break proofs, whole-project

    V4 session 2   36/36     V4 session 1   12/12
    wave 11 55/55  wave 10 41/41  wave 9 32/32  wave 8 21/21
    wave 4 35/35   wave 3 14/14
    wave 12 64/65  wave 7 21/22  -- two PRE-EXISTING stale anchors, on files
                                    this session never touched

A caution learned the hard way: two break-proof scripts run concurrently
against one worktree mutate the same files and produce DIRTY_RESTORE and
spurious ANCHOR_MISSING. Run them serially, and check `git status` before
staging anything after a break-proof run.

### V4 readiness, session 2

    PASS 9 · PARTIAL 22 · BLOCKED_DATA 1 · NO 2

against session 1's PASS 3 · PARTIAL 10 · BLOCKED_DATA 1 · UNMEASURABLE 1 ·
NO 5. NO: DEMAND_CHAIN, PRESENTATION.

### First executable continuation

Populate `affected_causal_nodes` and `affected_hypotheses` at the point evidence
is written, so the research reward has more than independence and duplication
to work with and the reward audit can stop reporting HACKABLE.

## V4 session 1 — the engine gets an economy, and the causal layer gets a memory

V3 is FROZEN at market `2ee1635` / founder `247ad23`. Nothing on the V3
contracts was renamed, duplicated or reopened; the founder preview still
serves `247ad23` and production is untouched at `119d345`.

### The bottleneck was measured, not guessed

Every economic chain was decapitated. The ledger holds only company-scoped
evidence, so MACRO_STATE had no possible source — not unobserved,
UNREACHABLE — and the top link of every subject's chain sat at UNKNOWN
permanently: known 4, unknown 3, links {UNKNOWN: 4, HYPOTHESIZED: 2}.

### What now exists and runs every cycle

| object | live measurement |
|---|---|
| `macro_state` | 24 monthly figures persisted; MARKET_RATE OBSERVED, moving UP; 16 of 17 conditions UNKNOWN |
| `company_exposure` | 26 companies × 10 dimensions; 3 rated, 257 UNKNOWN |
| `transmission` | 2 dated falsifiable hypotheses, provenance to both ends |
| `economic_chain` | known nodes 4 → 5; names its own weakest link |

### The observability repair

The whole causal layer — chain, causal calibration, counterfactual memory,
world model, VOI, belief maturity — was computed every cycle and dropped from
the persisted report. None of it had a history, so a regime change was
structurally unobservable. The comment above the report payload had already
predicted this exact seam. Now persisted as a bounded projection.

### V4 readiness

    PASS 3 · PARTIAL 10 · BLOCKED_DATA 1 · UNMEASURABLE 1 · NO 5

NO: demand chain, second-order effects, scenarios, internal company model,
founder consumption. FOUNDER_DECISION_VALUE is UNMEASURABLE by construction
until a V4 object crosses the bridge.

### First executable continuation

Widen macro source coverage. 16 of 17 conditions are UNKNOWN because one
keyless publisher covers one condition, and every downstream axis — exposure
routes, transmissions, regime detection — is rate-limited by it. FRED needs an
owner-supplied key; BLS and Treasury series do not.

## V3 final closure — the bridge carries trust, end to end, in production

### The producer was never live

The runtime was pinned at `94fa091`, the PARENT of the trust producer. Every
one of the 23 published dossiers was accepted by the founder contract and
none carried a standing, so the layer existed on both sides and crossed
between them nowhere. Repinned to `ed4b7f4` and ran the production-equivalent
night cycle; 23 of 24 dossiers now carry one.

| measured live | |
|---|---|
| raw evidence rows | 146 |
| distinct occurrences | 75 |
| rows of inflation removed | 71 |
| companies rated | 23 |
| companies with NO inflation | 13 |

The last row is the control: normalization discriminates rather than
discounting. Canadian National's five rows are five separate occurrences and
credit the full 5.0; Shopify's twenty-three credit 8.0 where a row count
would have credited 23; Stripe's twelve credit 2.0.

### Q&A was the surface that inflated the evidence

The one screen a founder uses to ask how strong the evidence is answered
"Probably — 3 independent source(s) support this", where `independent` meant
"the publisher is not the company". Three outlets rewriting one release
satisfied it three times, and the sentence leaked `corroboration` — banned
founder-facing vocabulary — because it was assembled after `_plain` ran.

It now reads the canonical standing and derives none. It is also PINNED to
the dossier revision the analysis read: the file on disk is live, so
answering a week-old analysis from today's dossier would reopen the
two-interpreters split along the time axis.

### Decision impact is measured, not asserted

On the live Shopify dossier: DECISION_CHANGING over 23 provenance rows,
changing ASSUMPTION, BOUNDED_CONCLUSION, EVIDENCE_REQUIREMENT,
MONITORING_PRIORITY and STRATEGIC_MECHANISM.

### Two guards had quietly stopped working

`w12-8` pointed at a line the claim-level roll-up had renamed, so the harness
reported ANCHOR_MISSING rather than a pass — it had been testing nothing. And
five assertions pinned counts against the ledger production writes to
nightly; running one cycle turned them red with no code change, each one
reporting the engine LEARNING as a failure.

### Test gate

| | |
|---|---|
| market suite | 4552 passed / 4 skipped / EXIT=0 |
| founder suite | 4659 passed / 16 skipped / EXIT=0 |
| market break proofs | 76/76 HELD |
| founder break proofs | 20/20 HELD |
| paper + retention | 98 passed |

Production `119d345` untouched. PAPER enforced in all three plists.

## V3 closure run — memory closed, strategic reasoning blocked on data

### Every memory-critical object now survives a restart

Six record kinds added and proven across a process boundary: counterfactual
adjudication (the known LOST one), falsifier, response watch, strategic
objective, strategic interaction, observed response episode.

Durability audit over **23** V3 object kinds:

| standing | count |
|---|---|
| DURABLE | 5 |
| DERIVED (recomputable) | 10 |
| UNUSED contract | 8 |
| **LOST** | **0** |

A conflicting adjudication APPENDS with `supersedes` — "we changed our mind"
is a different fact from "we always thought this". An observed episode that
claims `preregistered` is refused outright.

### Falsifiers are validated, not accepted

"The narrative shifts against them" is refused as unobservable: no source can
report it, so the engine could never notice it arriving. "The number moves"
is refused as non-discriminating. **EXPIRED is not RESOLVED_SURVIVED** — a
window that closed with nobody reporting is an absence of evidence, and
counting it as survival lets a belief harden on silence. The generated
research question is neutral by construction.

### Research priorities ask for observations

Six generated from measured gaps, routed by MISSING FACT: a release note
cannot say who a product is for, a pricing page cannot say when something
shipped. Leading phrasing is refused structurally.

### Dependency is not usage

`DEPENDS_ON` requires a materiality marker the DOCUMENT supplies. Measured
over the live ledger: **4 USES, 0 dependencies** — the ledger is built from
earnings and award evidence, not risk-factor sections. An ACQUISITION gap,
now a ranked priority. Found on the way: "Fast-growing" offered as a
supplier, the third module to meet that shape.

### Measured bottleneck, not asserted

| | stage | throughput |
|---|---|---|
| primary | RESPONSE_OBSERVABILITY | **0.00** |
| secondary | RECONCILIATION | 0.15 |

`STRATEGIC_INTERACTION` is reported as never fed rather than as zero — a
stage nobody fed has not failed.

### V3 readiness

    PASS 8 · PARTIAL 5 · BLOCKED 1 · UNMEASURABLE 1

Blocking axis: **STRATEGIC_REASONING** — every contract exists and is
durable; no counterparty publishes a dated action stream. Statuses are
counted, never averaged.

### Blocked by real-world data, not by effort

    BLOCKED: two-sided timeline, historical sequence, live interaction,
             live preregistration, response reconciliation
    REASON:  no counterparty publishes a dated action stream
    OWNER-CONTROLLED: no

### Product regression — clean on four live subjects

| subject | outcome | identity | leakage | jargon | inflation |
|---|---|---|---|---|---|
| Shopify | full reading | ok | none | none | none |
| Datadog | full reading | ok | none | none | none |
| Stripe | full reading | ok | none | none | none |
| Brightledger | bounded failure | ok | none | none | none |

Zero source-count inflation phrases on any page, and none of 18 internal
tokens appears. Economic chain re-scored: **toyota** leads at 42, tied with
honda; weakest link MARGIN->GUIDANCE. Zero-trade learning verified — no
cycle row carries a trade, order, position or broker field at all.

### Still executable, not done this run

Founder trust is computed market-side and **not yet consumed by a rendered
page**; product regression not re-run since wave 8; DecisionImpact not
re-measured under normalized trust; economic chain not re-scored.


## Wave 12 — production writes, and the reader stops being misled

### PRIORITY 1 DONE — the nightly cycle persists what it accepts

Wave 11 built `record_relationship`; **nothing called it**. The missing line
was in `source_acquisition_step`: `accepted` went into
`payload["relationships"]` — a run report — and nowhere else. Six waves of
discovery landed in a JSON file the next process never read.

It writes AFTER the measured verdict, so a family that did not reach
INTEGRATE contributes nothing. Proven the only way that counts:

    cycle runs → process exits → FRESH process loads the edge
    second identical cycle → no second edge

The summary carries `persistence_gap` = accepted − persisted − already-held,
which must be zero on a real run.

`knowledge_retention` gains **DISCOVERED_NOT_PERSISTED** — the state wave 11
could not express. Its audit had said "a write path exists" and been
satisfied while production forgot four rivalries a night. A quiet night
(nothing accepted) is explicitly not a gap.

### FOUNDER EVIDENCE TRUST — done, and it moves weight not just words

The market layer has known since wave 8 that 133 of 155 events are
same-origin. **None of it had ever reached a reader.**

| | |
|---|---|
| rows a page could have called "sources" | **295** |
| actual observations | **163** |
| inflation avoided | **132 (45%)** |

Weight is computed FIRST and the sentence derived from it, so the two cannot
disagree — changing only wording would leave the belief maturing on three
copies while the prose said otherwise. Dependent re-reporting weighs exactly
what a single source weighs, **not slightly more**.

A reader gets ordinary words: *"Several reports trace back to the same
underlying announcement, so we treat them as one observation rather than
independent confirmation."* A reader never gets SAME_ORIGIN, effective-account
counts or a dependency class — asserted across every standing.

### The operator report finally shows the split

`learning_health_step` now persists ECONOMIC_KNOWLEDGE_GAIN,
SYSTEM_CAPABILITY_GAIN, CALIBRATION_GAIN and FOUNDER_UTILITY_GAIN, with
KNOWLEDGE_RETENTION beside them and never inside. A cycle that accepts four
relationships and persists none reads DEGRADED, gap 4, economic gain **0**.

### BLOCKER 3 HOLDS — measured per actor now, not asserted

| actor | retrieved | actions | orderable | standing |
|---|---|---|---|---|
| Shopify | 1 | 7 | **7** | OBSERVABLE |
| Salesforce | 2 | 2 | 1 | THIN |
| Adobe Commerce | 1 | 0 | 0 | NOT_OBSERVABLE |
| BigCommerce | 2 | 0 | 0 | NOT_OBSERVABLE |

Salesforce's single orderable action belongs to a **third party**
(Missionforce) and concerns national security, not commerce — so it is not
relevant to the rivalry. Adobe Commerce's release-note page is a table of
contents. No two-sided timeline, therefore no sequence, no interaction, no
preregistration.

### Not reached in wave 12

§10-§17 (sequences, interaction, preregistration, response watch) blocked on
blocker 3. §23 (counterfactual adjudication retention), §25 (near-miss
priorities), §26 (source routing), §27 (SUPPLIES/DEPENDS_ON), §28 (chain
re-run), §29 (macro guard), §30 (product regression) and §31 (falsifier)
were not run.

## Wave 11 — both blockers broken, and a third one located

### BLOCKER 1 CLEARED — rivalry survives the process

The store had `record_evidence`, `record_expectation`, `record_cycle`,
`record_reconciliation` and `record_lifecycle`, and **no way to record a
relationship at all**. The seam was not broken; it did not exist.

The three wave-5 rivalries are back, and **not from memory**: the extractor
was re-run over 35 freshly retrieved pages and the same three came out of
the same evidence, plus a fourth.

| | |
|---|---|
| claims extracted | 11 |
| durable edges | **4** |
| loaded by a FRESH process | **4** |

Identity is the SCOPE, not the id — ids are content hashes that move when an
extractor changes. Symmetric predicates sort the pair; asymmetric ones keep
direction; the same pair contesting a different object stays two claims;
retirement is an append, never a delete.

One claim would have become permanent junk: *"Is migrating from Shopify to
BigCommerce difficult?"* was persisted with buyer **"Is"**. Same shape as
wave 9's "Regular releases keep your org secure", in a different module.

### The same defect was on the critical path

`CrossActorExpectation` had no write path either. A preregistration whose
record does not survive the process **cannot claim it preceded the
evidence**, which is its entire content. It persists now; its outcome is a
SEPARATE row, so the expectation cannot be edited to carry its own answer;
and an outcome for an expectation nobody registered is refused.

`knowledge_retention` makes the class mechanical instead of lucky — both
instances were found by hand, one wave apart, because somebody counted. The
audit reads **DEGRADED** and names a third: 8 counterfactual episodes whose
adjudication is re-derived every run and stored nowhere.

### BLOCKER 2 CLEARED — three dates, not one

| | before | after |
|---|---|---|
| actions | 23 | 7 |
| distinct event times | **1** (the fetch date) | — |
| orderable dates | **0** | **4** |

`RetrievedDocument` never captured publication metadata although the parser
extracts it. Entry pages carry it, index pages mostly do not, and that is
exactly why entry pages can be ordered.

**The year inference fabricated a date on its first run, and that is why the
rule is now a refusal.** shopify.dev/changelog reports `modified_date`
2026-07-21 while its newest entry is marked 08.03 — metadata older than the
page's own content — so "an entry cannot predate its publication" rolled an
August 2026 entry back into **2025**. A wrong date on the axis a timeline is
ordered by is worse than no date.

### BLOCKER 3 — no rival publishes a dated stream

All 7 orderable actions are **Shopify's**. A candidate sequence needs
orderable actions from BOTH sides of a durable rivalry, and no counterparty
has any: Salesforce's releases page yields one undated action, BigCommerce
and Magento yield nothing.

    persistence   ✓
    temporal truth ✓
    counterparty observability ✗   <- the wall now

### The suite was asserting a snapshot of a live artifact

Production ran a cycle mid-session — ledger 366 → 421 rows — and **fourteen
assertions across eight files went red with no code change**. They pinned
constants against an append-only production file, so they were written green
with a built-in expiry. All are migrated to the invariant they were about.

Two were not brittleness. `learning_acceleration.report` **crashed** on the
live ledger: a share of 8.0 out of 6.0. The guard was right that the numbers
count different populations and wrong that it is a defect — a window revises
beliefs declared in EARLIER windows, so `belief_revision_rate` is a ratio,
not a share. And the economic chain's strongest candidate **changed from
honda to toyota on new evidence**, which is §24's reassessment arriving by
itself.

### Not reached in wave 11

§10-§16 (timelines, sequences, live interaction, preregistration, response
watch) are blocked on blocker 3, not on effort. §17-§19 (Founder evidence
trust), §22-§23 (near-miss priorities, routing), §25 (product regression) and
§26 (falsifier migration) were not run.

## Wave 10 — two structural blockers, both located

### `release_notes` was luck, and the sample says so

Twelve official release-note surfaces across four rivals returned **11
distinct documents**. The yield went DOWN.

| | wave 9 | wave 10 |
|---|---|---|
| documents | 3 | **11** |
| established objects | 1 | **1** |
| est/document | 0.333 | **0.091** |

Same single object — "Shopify Shipping expands to Italy and Spain". Eight of
twelve surfaces returned nothing; **BigCommerce and Magento returned nothing
from any of their six.** Maturity now requires ACTOR DIVERSITY as well as
document count, because only two of four actors published anything reachable
and only one produced an object: the family's apparent yield was one
company's changelog.

### Context recovery works and has nothing to work on

`ActionContext` takes the heading and immediate neighbours and stops at a
section boundary. Live recovery: **zero**.

Before the index rule it "recovered" three, and all three were leaks —
`checkout` borrowed from the entry above, and a buyer built from two
navigation labels run together ("Sidekick app extensionsApp store"). An
index page's sentences are not context for one another, and a window widened
until a buyer appears will always find one belonging to something else.

14 of 15 live actions come from two index pages. The seven changelog ENTRY
pages, where context WOULD work, produce **zero actions** — the announcement
is in the page TITLE and the detector reads only body text.

### BLOCKER 1 — the rivalry edges do not persist

`competitor_map_entries` is **0**, and COMPETES_WITH has **zero edges** in
the actor-relationship graph, which holds 25 edges across only two of eleven
predicates (SELLS_TO, PARTNERS_WITH). The three rivalry claims were produced
during a wave-5 run and written nowhere. **This is a storage gap, not an
evidence gap**, and it is why the episode ranker cannot read its own input.

### BLOCKER 2 — every action is dated the day we fetched it

23 live actions carry **one distinct `event_time`**: 2026-08-08.
`action_object_acquisition` passes `event_time=document.retrieved_at`.

§7 asks what happened when and §8 asks for "A followed by B within a
plausible window". Neither has meaning when every delta is zero, and a
timeline built on retrieval dates would order actions by the order we
happened to fetch them **and would look exactly like a real one**. Same
class as the wave-5 evidence id hashing `observed_at`; it survived because
nothing downstream had ever ordered actions.

### Episode ranking, on the pairs that exist

| pair | actions | standing |
|---|---|---|
| Salesforce vs Shopify | 6 / 16 | **MEDIUM** |
| Magento vs Shopify | 0 / 16 | NOT_OBSERVABLE |
| Magento vs Shopify Plus | 0 / 0 | NOT_OBSERVABLE |

Observability is first-class and separate from validity: a rivalry can be
real and unlearnable. Salesforce/Shopify is held at MEDIUM because the
source family behind it is PROVISIONAL.

### Learning split, formalised and enforced

| channel | wave 10 |
|---|---|
| ECONOMIC_KNOWLEDGE | **0** |
| SYSTEM_CAPABILITY | 6 movements |
| CALIBRATION | 0 — all six tracks UNMEASURABLE |
| FOUNDER_UTILITY | 0 |

`learning_channels.movement` REFUSES to file a pipeline repair as economic
knowledge. Three waves running, the engine has improved its instrument and
learned nothing new about the market — the correct reading, and the reason
the split exists.

### Not reached in wave 10

§9-§15 (response memory, live interaction, preregistration, response watch,
objective hypotheses) are blocked by the two blockers above, not by effort.
§18/§19 (Founder evidence trust), §23/§24 (near-miss research priorities),
§25 (economic chain re-run), §26 (product regression), §27 (falsifier
migration) were not run. Product regression was judged least urgent because
no Founder surface changed this wave — §26's stated reason for requiring it
was the Founder provenance work, which is itself not done.

## Wave 9 — the near-miss corpus was mostly an accounting error

The 89 UNKNOWN action objects wave 8 handed forward as a "training set" were
**26 distinct sentences**. The 112 actions were **32**. The 5 established
objects were **1**.

Three defects, each inflating in the same direction:

| defect | effect |
|---|---|
| in-page anchors fetched as separate documents | denominator ×4.5 on release_notes |
| actions counted per sighting, not per `action_id` | numerator ×5 |
| the page's owner used as the actor of every sentence on it | a fabricated action |

`action_id` was **already stable** across the duplicate retrievals, and
`all_objects` — a dict keyed by it — had been silently deduping to 1 the
whole time while the counters reported 5. Two numbers derived from the same
run disagreed by 5× and nothing compared them.

The third defect surfaced only after fixing the first two. The re-run
produced a SECOND established object: *"In 2020 Salesforce released B2B
Commerce Lightning Experience ... for B2B merchants"* — read off
**BigCommerce's** comparison page and attributed to BigCommerce. It
establishes both a what and a who, so it was simultaneously the best-formed
object in the corpus and the first invented one. Actions are now refused
when the sentence attributes them to a different KNOWN actor; the check is
gated on known names rather than capitalisation, because every sentence
begins with a capital and an ungated rule refused "Regular releases keep
your org secure" on the grounds that "Regular" is a company.

### Honest live state after the fixes

| | wave 8 claimed | actually |
|---|---|---|
| actions | 112 | **38** |
| established objects | 5 | **1** |
| release_notes est/doc | 0.556 | **0.333** (1 of 3) |

`release_notes` is still the only family that has ever established an
object, so the wave-8 ORDERING survives. What does not survive is the size
of the claim: one object from three documents is a single observation, not
a rate.

### The near-miss corpus, fully adjudicated

All 37 refusals were read by hand against their documents — the pool is
small enough to read completely, so it was not sampled.

| | count | share |
|---|---|---|
| **not an action at all** | **22** | **59.5%** |
| real actions | 15 | |
| — recoverable by extraction | 6 | 40.0% of real |
| — genuinely absent from source | 9 | |

So the ordering is **action-detector precision first, extraction recall
second, source content third** — and only the third needs more documents.
Wave 8 had assumed the opposite.

Twelve non-announcement shapes now refuse 22 of 22 non-actions while losing
0 of 16 real actions. That is IN-SAMPLE: the shapes were written against
this corpus, and the next unseen corpus is the only real test. Live effect
38 actions → 16, all adjudicated real, **established objects unchanged at 1**.

Two of the six recoverables have clean structural fixes — a buyer named in
the consequence clause ("so store owners have better control") and a named
edition with no price beside it ("Bundled with Unlimited Edition"). Both
move UNKNOWN → PARTIAL and neither reaches ESTABLISHED, which is correct:
one names a buyer and no what, the other a what and no buyer.

### What wave 9 did NOT reach

The episode branch was not started. No `StrategicEpisodeCandidate`, no
historical timelines, no candidate action→response sequences, no live
interaction and therefore no preregistered response. §5's release-note
expansion, §19's predicate coverage, §28's macro/capital check, §29's
learning-split module and §30's product regression were not run.

The reason is that §1 and §2 turned into a correction of wave 8 rather than
the training exercise they were scoped as, and the corrections were load
bearing: every count the episode ranker would have consumed was inflated
between 2.4× and 5×, and one of the two "established" objects was invented.
Ranking episode candidates on those numbers would have chosen a pair for
reasons that were not real.

### Learning split for this wave

| kind | this wave |
|---|---|
| ECONOMIC_KNOWLEDGE_GAIN | **none** — established objects still 1 |
| SYSTEM_LEARNING_GAIN | action corpus 38 → 16 all-real; 3 counting defects fixed; near-miss corpus exists and is fully adjudicated |
| MODEL_CALIBRATION_GAIN | none — no prediction was tested |
| FOUNDER_UTILITY_GAIN | none — no surface changed |

A cleaner denominator is not a new fact about the world, and this table
exists so that improvement can never again be reported as knowledge.

## Pinned state

| what | where |
|---|---|
| market head | `HEAD of feat/strategic-response-learning` (see git log) |
| V3 closure break proofs | **76/76** through the hardened harness |
| market runtime | **`079128b` — NOT repinned; owner action below** |
| founder head | `c1c1cb8` (branch `feat/consumption-emitter`) |
| founder preview | LIVE, verified this wave against four subjects |
| production `main` | `119d345` — **untouched, do not target** |
| PAPER | structurally enforced in all three launchd plists |
| market suite | 4540 passed / 4 skipped / EXIT=0 |
| founder suite | 4575 passed / 6 skipped / EXIT=0 |

## Wave 8

| slice | evidence it is real |
|---|---|
| Object dimensions + query planner | dimension model, planner that may choose where to look |
| Object-bearing acquisition | 66 live documents, **1 ESTABLISHED object** — the first |
| Source dependence | 5 "independent-account" events were really **2** |
| Break proofs 18/18 → **21/21** | four came back NOT_CAUGHT and each named a real defect |
| ACTION_OBJECT source performance | release_notes moves **last → first** on measurement |
| Economic chain reassessed | honda KEPT; **stripe falls out of the top five** |
| Product regression | 4 live subjects; identity, leakage, scaffolding all clean |

### The bottleneck did not move, and that IS the finding

An action's object must come from its own document. Over 66 live documents
from six families, exactly ONE object reached ESTABLISHED — a named product
entering named markets. Everything else is PARTIAL or UNKNOWN because the
document names the thing and not the buyer.

The relevance rerun then found that the one established object is
**IRRELEVANT** to all three rivalries, for a stated, non-circular reason. So:

    STRATEGIC INTERACTION       0
    CROSS-ACTOR EXPECTATION     0
    RESPONSE                    not searched — correctly

Nothing is preregistered because nothing qualified. §9's ordering held: no
expectation was written, so no response could be searched for one.

### Four break proofs failed first, and that is where the wave paid

- `PRICE_CHANGE`'s row in the dimension table was **asserted by nothing**.
  Emptying it to `()` left the whole suite green.
- The `GENERIC_FAMILIES` score penalty sat BELOW the coverage filter and
  **could never execute**. Its test asked "if the homepage is in the list, is
  it below pricing?" — and the homepage is never in the list.
- Two proofs were paired with tests that could not observe them.

### `event_identity.group` read dicts as empty

Every field was read with `getattr`, so the JSONL ledger's dict rows produced
empty strings, hashed to one core, and folded **249 rows into ONE event** with
an empty subject. No error — just an answer that looks like a spectacularly
well-corroborated occurrence. Both shapes now reach the same 155 events,
asserted, and `event_corroboration` borrows the same reader so the two cannot
drift apart.

### ACTION_OBJECT source performance, measured

> **CORRECTED IN WAVE 9 — the numbers below count OCCURRENCES, not actions.**
> One page reached through in-page anchors was retrieved as up to five
> documents, and one announcement found on each was counted as up to five
> actions. The honest figures are in the wave-9 section: **1** established
> object from **3** release-note documents, not 5 from 9. The ORDERING was
> right; the size of the claim was not.

| family | retrieved | actions | established | est/doc |
|---|---|---|---|---|
| release_notes | 9 | 89 | **5** | **0.556** |
| pricing_page | 15 | 12 | 0 | 0.000 |
| product_launch_page | 15 | 7 | 0 | 0.000 |
| comparison_page | 12 | 2 | 0 | 0.000 |
| migration_page | 10 | 0 | 0 | 0.000 |
| solution_page | 5 | 2 | 0 | 0.000 |

The editorial prior said launch pages name their buyer. They do not. Ranking
this question by ACTION count would have sent the next budget to pricing
pages, which returned 12 actions and established nothing. Every family is
PROVISIONAL against a 20-document floor: this orders the next budget and
settles nothing.

### Economic chain

Honda remains strongest raw (35) and normalized (22) and is KEPT unmodified.
Its weakest UNKNOWN link is `ORDERS -> COMPANY_DEMAND`.

What normalization changed is who is behind it: **stripe falls out of the top
five**, 68% of its rows being further accounts of events already on the
ledger, against honda's 48% and cloudflare's 9%. What it did not change is
structure — every link status and weakest link is identical. Dropping a
duplicate account of a covered stage drops no stage.

### Product regression, live

| subject | outcome |
|---|---|
| Shopify | full reading; filing prose, decision, options, falsifier |
| Cloudflare | reading **withheld**, and says the absence is the finding |
| Brightledger | no report; 23 sources each named with their own reason |
| Olo | awaiting source confirmation, four-part failure shape intact |

Identity, cross-company leakage, and multi-actor scaffolding: all clean.
**One wart:** the awaiting-confirmation page is served with HTTP **400**.
The page is right; the status says the client erred, and anything polling by
status code reads a legitimate intermediate state as a bad request.

### OWNER_ACTION_REQUIRED

```bash
cd /Users/prathamsharma/intent-engine-market && git checkout <latest market SHA>
```

Refused by the permission classifier in waves 4 and 5. Not retried further,
per instruction. The runtime therefore still runs `079128b` and does not run
the wave-4 or wave-5 work.

## Wave 7

| slice | evidence it is real |
|---|---|
| CompetitiveObject from the document | precision 1.0 on a shaped corpus; 5 live actions, **0 ESTABLISHED** |
| The three items wave 6 owed | routing by question type, competitor VOI, founder multi-actor view |
| Event identity | 249 rows → 155 events; **5 with independent accounts** |
| Wave-7 break proofs | **22/22** through the hardened harness |

### The object must come from the document

`competitive_objects.extract` has NO parameter through which an object can
be supplied — asserted on the signature — and reads neither the universe nor
the curated list. ESTABLISHED needs TWO axes: a what and a who. A product
with no buyer could be sold to anybody.

Live: 5 real actions survive the tightened announcement patterns (16 → 5).
Of those, **0 ESTABLISHED, 1 PARTIAL, 4 UNKNOWN.** Interactions stay at zero
for the most precise reason yet — not "we don't watch the rival", not "no
actions exist", but "no action names both what it contests and who is
choosing".

Relevance now runs on `overlap`, and the string comparison against the
action's own label is DELETED: keeping it would have reintroduced exactly
what the module refuses to trust. ADJACENT never reaches RELEVANT.

### Event identity — corroboration is not a later outcome

249 evidence rows describe **155 occurrences**. 49 have several accounts; 5
are corroborated across different source ROLES.

Figures are the key and period markers are not figures. Keying on "Q2" as
though it were a number split accounts of one print; excluding period
markers took the ledger from 170 events to 155 and surfaced the 5
independent-account events, up from zero.

No row is merged away. The ledger can now say "three independent sources
corroborated the opening event and none counted as a later outcome".

One contract detail: the observation payload IS `reconcile`'s argument
list, so a corroboration count added there becomes a keyword argument. It
lives in the refusal telemetry instead.

### Performance

| stage | ms |
|---|---|
| action-object extraction | 0.015 |
| event identity (249 rows) | 4.93 |
| observation binding, index supplied | 1.24 |
| observation binding, recomputing | 6.25 |

Binding regressed 1.2 → 6.3 ms because event grouping ran inside it. `bind`
now accepts a precomputed `event_index`; the fallback keeps every existing
call site working.

## Wave 6

| slice | evidence it is real |
|---|---|
| Clause-scoped rivalry | 8 mixed-clause shapes hold; measured 0 false refusals before the change |
| Hardened break-proof harness | rejects the exact wave-5 no-op; wave 4 35/35, wave 5 32/32 through it |
| Rival actions + relevance | 16 actions live; **0 RELEVANT** and the reason is non-circular |
| Cross-actor expectations | menu, backwards-dating and closed windows all refused structurally |
| Sample-size maturity | every rate carries numerator/denominator/maturity |

### The circularity wave 6 found

Relevance first scored **18 RELEVANT pairs** — every Salesforce AI-agent post
counted as contesting an e-commerce platform, because the harness that
fetched them had LABELLED them "E-commerce platform" and `assess` trusted the
label. An action's competitive object must be established by its own
document or relevance means nothing. `object_established` is now required.

Honest count: **0 RELEVANT**, 24 IRRELEVANT (wrong party), 24 UNKNOWN
(object not established). That is what `action_does_not_provoke_a_response`
actually meant.

### Rival action source coverage, measured

| rival | documents | actions | note |
|---|---|---|---|
| Salesforce | 6 | 12 | mostly narrative, not announcements |
| Shopify | 2 | 4 | same |
| Magento | 0 | 0 | business.adobe.com yielded nothing |
| BigCommerce | 0 | 0 | same |

### Learning health, with its denominator

| rate | pair | maturity |
|---|---|---|
| self_test_rate | 20/25 | EARLY |
| false_positive_rate | 23/90 | USABLE |
| knowledge_freshness | 491/598 | MATURE |
| contradiction_reachability | 2/5 | INSUFFICIENT_SAMPLE |

**DEGRADING is retained**, resting on false_positive_rate (USABLE), not on
the EARLY self-test rate. The levels are unchanged; what the engine claims
to know from them is what changed.

### The break-proof harness is now permanent

Five conditions, and a proof failing any of them is INVALID rather than
merely uncaught: source hash must change, the test must have been green,
must go red, must go red for the STATED reason, and must restore to
identical bytes with `__pycache__` cleared. Six tests drive it against its
own failure modes.

## Wave 5

| slice | commit | evidence it is real |
|---|---|---|
| Self-test contamination repaired at its producer | `dbbe41b` | 0.857 → 0.400, zero bindings lost |
| Strict COMPETES_WITH contract | `8bb55d9` | precision 1.0 on a 10-case negative corpus |
| Health→action, analogy transfer, cross-layer consistency | `6b0c80b` | the same question plans differently when degraded |
| Real rivalry + game-theoretic state | `cef4e08` | 3 competitive edges, all with object and buyer |
| Wave-5 break proofs | this wave | **30/30**, each demonstrating RED |
| Founder failure-language pin | `c1c1cb8` | live against a site that errors on every path |

## THE SELF-TEST RATE HAD A PRODUCER

`evidence_id_for` hashed `observed_at` — the date the SWEEP RAN — into a
fact's identity. An unchanged page re-read on three nights became three
facts. The function's own docstring stated the requirement it was breaking.

| | before | after |
|---|---|---|
| evidence rows | 249 | 173 |
| self-tests refused | 18 | 2 |
| self_test_rate | 0.857 | **0.400** |
| no_readable_direction | 29 | 12 |
| bindings lost | — | **0** |

Decomposition: 28 `SAME_SOURCE_REPACKAGING`, 3
`SAME_EVENT_DIFFERENT_HEADLINE`. `observation_binding.diagnose` keeps the
class breakdown, and every class names a producer upstream of itself.

A re-read is recorded as an `evidence_seen` sighting — it cannot test a
belief — and sightings are idempotent on (evidence, date), so a replayed
session still leaves the ledger byte-identical.

## COMPETES_WITH — populated, strictly

A claim with no COMPETITIVE OBJECT is refused. Three real edges:

| a | b | object | buyer |
|---|---|---|---|
| Salesforce | Shopify | E-commerce platform | Alice |
| Magento | Shopify | E-commerce platform | VIA VAI |
| Magento | Shopify Plus | E-commerce platform | Bombay Shaving Company |

| family | docs | claims | /doc |
|---|---|---|---|
| customer_case_study | 22 | 3 | 0.136 |
| comparison_page | 10 | 0 | 0.000 |

The vendor's own `/compare` and `/alternatives` pages — the family whose
editorial purpose is naming the alternative — produced **zero**. Migration
stories inside customer case studies produced all three.

**The curated list and the corpus disagree completely.** The universe carries
`shopify.competitors = [amazon, bigcommerce, square]`; none appears in any
document, and neither discovered rival is on the list. Model knowledge is
used only as a scoreboard, asserted by test.

Built evidence types: DIRECT_COMPETITOR_STATEMENT,
CUSTOMER_ALTERNATIVE_EVALUATION, REPLACEMENT_MIGRATION, PRODUCT_SUBSTITUTE.
Four more are specified and NOT built, each listed with what it would need.

## WHY INTERACTIONS ARE STILL ZERO — and it is a new reason

    wave 4   no_competitor_relationships_available
    wave 5   action_does_not_provoke_a_response   (207 actions examined)

The rivals the corpus names — Magento, Salesforce — are companies this
engine does not track. An interaction needs an action from one side and a
response from the other, so a rivalry with ONE observed party cannot produce
one. `world_model.rivals_outside_the_observed_universe` names them.

**The bottleneck is now OBSERVATION OF THE NAMED RIVAL.** Two routes:
add discovered rivals to the tracked universe, or accept that rivalry found
in customer stories usually names companies outside it.

## Standing state

- **BELIEFS** 51 · 43 CANDIDATE / 6 SUPPORTED / 2 WEAKENING / 0 STALE
- **DECAY** cadence-aware, next window 2026-12-03; zero stale is legitimate
- **CAUSAL CALIBRATION** 2 UNMEASURABLE / 2 EMERGING; ESTABLISHED absent
- **COUNTERFACTUAL MEMORY** 5 episodes, and one now transfers: the
  Cloudflare lesson fires on an Etsy headline of the same shape, as an
  ANALOGY carrying no evidence ids and `is_evidence=False`
- **CALIBRATION CONSISTENCY** causal caps mechanism caps maturity; the real
  ledger reads zero incoherent pairs and the guard exists for when it does not
- **RESEARCH PLANNING** selection by predicate first; DEGRADING on re-reads
  measurably reorders the same question; ingestion never disabled wholesale
- **SOURCE PERFORMANCE** three families, all INDICATIVE, none ESTABLISHED
- **GAME-THEORETIC STATE** `StrategicObjectiveHypothesis` (born WEAK, ≥2
  alternatives, required expected_next_action) and `ActorResponsePattern`
  (one episode is a CANDIDATE; a different response CONTRADICTS) both exist
  and are unpopulated, correctly
- **PERFORMANCE** wave-5 additions total 9.69 ms/cycle; competitive
  extraction over 249 rows is 3.73 ms. No regression above 10%
- **BREAK PROOFS** 30/30. Two failed first-pass: one mutation was a no-op
  (`{} or {...}` evaluates to the second dict) and one guard was unreachable

## Remaining queue after wave 12, highest value first

1. **A dated action stream for ANY counterparty.** Measured per actor now:
   Shopify 7 orderable, Salesforce 1 (a third party's, irrelevant), Adobe
   and BigCommerce 0. Everything from sequences to preregistration waits on
   this one number moving for a second company. Try investor-relations feeds
   and dated press wires rather than more product surfaces.
2. **Counterfactual adjudication retention** — still LOST in the audit.
3. **Wire evidence_trust into the Founder surface.** The market-side
   translation exists and is measured; no rendered page consumes it yet, so
   the 45% inflation is still avoidable rather than avoided in product.
4. **SUPPLIES / DEPENDS_ON coverage** — the chain's UNKNOWN links are all
   upstream of the company.

## Remaining queue after wave 11, highest value first

1. **A dated action stream for any counterparty.** Shopify has one; nobody
   else does. Until a second actor has orderable actions, no candidate
   action->response sequence can exist, and everything downstream of it is
   blocked. Look for investor releases, press feeds and dated newsrooms
   rather than more changelogs.
2. **Wire persistence into the live cycle.** The write path exists and this
   wave used it from a script. Until `steps` calls it, production still
   forgets rivalries every night — `relationships_added` has been 0 in every
   cycle observation ever recorded.
3. **The counterfactual adjudication has nowhere to go.** The retention
   audit reads DEGRADED on it.
4. **Entry-page titles still yield no actions** (carried from wave 10), and
   entry pages are where the dates live.

## Remaining queue after wave 10, highest value first

1. **Persist the rivalry edges.** `competitor_map_entries` is 0. Until a
   COMPETES_WITH claim survives the run that made it, the episode ranker,
   the interaction record and every response test have no input.
2. **Give an action its own date.** Every action is stamped with the
   retrieval date, so no timeline can be ordered and no response window has
   meaning. Changelog entries carry "06.17" and "July 30, 2026"; this needs
   a dated-announcement extractor with a negative corpus.
3. **Read the entry-page title as an announcement.** Seven single-topic
   changelog pages yield zero actions because the announcement is the title.
   Needs a title-grammar pattern family AND a negative set — nav labels and
   section headers share the shape.
4. **BigCommerce and Magento are unobservable.** Zero documents from six
   official surfaces each. Either find a reachable surface or accept that
   two of three tracked rivalries can never produce an episode.

## Remaining queue after wave 9, highest value first

1. **The episode branch, on numbers that are now trustworthy.**
   `StrategicEpisodeCandidate`, timelines, candidate sequences, and the
   first live interaction. This was wave 9's stated mission and it was not
   started; the counts it depends on were being corrected instead.
2. **Release-note expansion (§5).** One established object from three
   documents is a single observation. Take the family past the
   20-document INDICATIVE floor before concluding anything from 0.333.
3. **The 9 genuinely-absent actions.** "Introducing Commerce Components."
   is a real launch that names no buyer anywhere in its sentence. Either
   the surrounding document says who it is for — §3's context expansion,
   not attempted — or this family cannot establish objects and the
   ordering is wrong.
4. **The precision shapes on an unseen corpus.** 22/22 and 0/16 are fit.
   A second rival set is the only honest test.
5. **The attribution gate knows only tracked names.** "VCARB Partners with
   Salesforce" and "Missionforce ... Unveils" are third-party actions kept
   because the gate has never heard of those actors.

## Remaining queue after wave 8, highest value first

1. **A rival document that names its buyer — still.** Six families, 66
   documents, one established object. The measurement now says WHERE to
   spend: `release_notes` is the only family that produced one, and it is
   PROVISIONAL at 9 documents. The next wave should take it past the
   20-document INDICATIVE floor before concluding anything from 0.556.
2. **The 74 UNKNOWN objects from release notes.** That family found 89
   actions and established 5. The other 84 are the largest single pool of
   near-misses in the corpus and nobody has read why they fail.
3. **HTTP 400 on the founder awaiting-confirmation page.** Founder branch,
   not reached across from this wave.
4. Announcement-grade retrieval for Magento and BigCommerce, both of which
   still yield no documents to the newsroom fetch.

## Queue carried from wave 7

1. **A rival document that names its buyer.** The object contract is built
   and measured; what is missing is the SOURCE. Pricing pages, launch pages
   and migration pages say who a thing is for. A rival's blog does not, and
   that is where all 5 live actions came from. `ACTION_OBJECT` already
   routes to the right families — nothing fetches them yet.
2. **Announcement-grade retrieval for Magento and BigCommerce**, both of
   which yielded zero documents to the two-hop newsroom fetch.
3. **The historical ledger still carries pre-fix duplicate rows**, so its
   measured self-test rate stays 0.857. The fix is prospective and
   append-only doctrine forbids rewriting; a ledger written under occurrence
   identity measures 0.400.
3. **self_test_rate is 0.400**, down from 0.857 and still high. The remaining
   classes are wire duplicates and aggregator headlines, which are correlated
   evidence rather than duplicates and need the design-effect penalty, not
   the dedupe.
4. Economic chain reassessment against the new relationships; VOI recompute
   with decision relevance; the 30-cycle acceleration window.

## Standing rules

- Commit and push every completed slice. Own your worktree path.
- A break proof only counts if it demonstrates RED before restore. Three
  waves running, the most valuable finding came from a proof FAILING.
- No causal edge is ever `OBSERVED`; none is promoted by a single test.
- `UNMEASURABLE`, `INSUFFICIENT_HISTORY` and `PROVISIONAL` are not zero.
- Before building a subsystem, check whether it already exists and is simply
  not wired. Seven for seven — `market_structure` is the latest.
- Integrate a source family on measured yield, and check the retrieval before
  believing the yield.
- A rivalry with no competitive object is refused. A motive with no
  alternatives is refused. One response is not a habit.

## V4 session — I-ACC-001 and the pillar reconciliation (2026-08-09)

Planner state is in `docs/execution/v4/`; this is the narrative record.

**The engine can now say it is barely learning, which it previously could
not.** Seven channels, derived from the effect log rather than cycle
counters, computed independently and never averaged. Live at `80f3aa5`:
ECONOMIC 29/402 changed (7.2%, MATURE) DEGRADING; RETENTION 402/402;
CALIBRATION 3/11 EARLY; SYSTEM 20/41 INSUFFICIENT_HISTORY; FOUNDER and
RESEARCH UNMEASURABLE; UNSUPERVISED 1/3 EARLY_WARNING.
`HIGH_ACTIVITY_LOW_LEARNING` fires on real data: 347 evidence rows, 373
attributions that moved nothing, **0 thesis transitions**.

Three defects in that node's own seam, all live, none of which had ever
raised or logged anything:

1. **A block that succeeded every cycle and reached no record.**
   `_knowledge_summary` is a whitelist projection and did not name
   `learning_acceleration`, so every cycle's result was dropped on the way to
   the dated artifact. The report meanwhile had a section *titled* LEARNING
   ACCELERATION rendering trading throughput. This is `a caller is not a
   call` inverted: there, a block raised every cycle and nothing projected
   the error; here, a block succeeded and nothing projected the result. Both
   are invisible for exactly as long as nobody asks the artifact a question
   it should be able to answer.

2. **An absent link reported as a measured zero.** The research channel's
   first implementation graded `0 of 14` outcomes productive. All 14 carry an
   EMPTY `knowledge_effect_ids` — nothing records what research produced, and
   that reads identically to research that produced nothing while being the
   opposite finding.

3. **Founder value was publication volume**: `len(strategic_export.published)`
   passed as `decision_impacts`.

**The window key was the trap.** `created_at` on 347 of 402 effects is the
evidence's observation date, set deliberately so `effect_id` stays stable
against nightly re-derivation. Windowing on it yields a learning history back
to February for a log whose write path landed on 2026-08-09 — retrieval time
wearing occurrence time's clothes, the same defect that blocks D-REP-002 one
layer down. Windows key on ledger append order instead.

**L-SRC-001**: source health is a persisted state per family per cycle. BLS
has returned 503 on every recorded cycle, and that fact was reported and
forgotten every time. The rule proven by mutation: a degraded source raises
uncertainty and NEVER weakens the claim — otherwise "we stopped looking"
becomes "we were wrong". An unrecognised failure is UNCLASSIFIED carrying its
message, never mapped onto the nearest known state.

**The five pillars were reconciled into the graph once**, as PROGRAM L, and
scoped by what this branch can honestly verify. The information barrier and
the tenant air-gap are NOT_APPLICABLE with their invariants recorded: a
private-data firewall built where there is no private data would report PASS,
which is the architecture-only completion this program keeps having to undo.

**D-REP-002 was not touched.** `macro_retrieval_months` is still 1 of 6.

### Added to the standing rules

- A channel that measures nothing must say UNMEASURABLE. A denominator of
  zero is not a rate of zero, and an absent link is not a measured failure.
- Never window learning on a date field a writer can set. Append order is the
  only write order the ledger actually has.
- NOT_CAUGHT on a break proof is a finding about the code. Proof 3 of v4h
  showed that admitting Founder objects to the economic channel changed the
  numerator and failed no test: every test asserted names, none asserted
  membership. Write the missing guard; do not repoint the proof.
