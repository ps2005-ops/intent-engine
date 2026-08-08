# Execution checkpoint — V3 multi-actor economic intelligence

Machine-readable continuation state. A completed slice is a checkpoint, not an
endpoint: this file exists so the mission survives a context boundary instead
of restarting from an audit.

Updated 2026-08-08, wave 9.

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
| wave-9 break proofs | **32/32** through the hardened harness |
| market runtime | **`079128b` — NOT repinned; owner action below** |
| founder head | `c1c1cb8` (branch `feat/consumption-emitter`) |
| founder preview | LIVE, verified this wave against four subjects |
| production `main` | `119d345` — **untouched, do not target** |
| PAPER | structurally enforced in all three launchd plists |
| market suite | 4375 passed / 4 skipped / EXIT=0 |
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
