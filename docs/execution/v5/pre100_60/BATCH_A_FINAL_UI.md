# Batch A — final, scored from the deployed UI

**Status: IN PROGRESS.** Window 1 read and scored; window 2 running.
Every dimension not actually read on a rendered page is recorded
`NOT_MEASURED`. No score in this document is inferred from a backend object.

Two sessions produced it. Session `53905f6a` drove the deployed guest
journeys and owns every rendered-page measurement; session `d8a05a86` owns the
repairs and the offline classification probe. Where a cause is stated below,
it also says **how it was established** — code-reading, offline execution, or a
capture — because two of this session's wrong turns were mechanisms asserted
from code-reading that a capture then contradicted.

## Deployed SHAs

| SHA | What it carried |
|---|---|
| `58ac7ef` | frequent-filer index repair (JPMorgan 0 → 4 candidates); the **before** baseline |
| `0420fb0` | bounded SEC retry, filing cache, the class gate, eight model-keyed tables |
| `98a7a17` | per-run retry ledger + operator telemetry |
| `975321c` | claim ownership in the mental model |
| `188da7c` | structured rows rendered, one competitive state |
| `cec9b2f` | archetype question coverage, the article fix |
| `71e4dc0` | claim ownership rewired on both routes — **current** |

## Template collapse — the headline number

Measured through the live `/conversation` route, ten board questions,
company name and page chrome removed, longest-variant-first, truncated at the
first chrome marker.

| | companies | identical answers |
|---|---|---|
| before, `58ac7ef` | Meta, Caterpillar | **10 / 10** |
| after, `0420fb0` | JPMorgan, NVIDIA, Walmart | **1 / 10** |

The remaining 1/10 was "Who's the real competitor?", fixed in `188da7c` and
awaiting re-measurement in window 2.

**The instrument lied three times before it told the truth**, and the honest
figure is the least flattering one. Naive similarity gave 0.915 (inflated by
shared chrome). Masking the company name and testing byte-equality gave 0/10
(deflated — chrome *after* the answer differs per company). Masking name
variants from a set gave 0/10 again (arbitrary iteration order replaced
"Caterpillar" before "Caterpillar Inc."). A fourth pass scored 0/10 because
"Why this matters" and "Low, by construction" are boilerplate tails that vary
by run rather than by company, making three identical answers look distinct.
**1/10 is the number to quote.**

## The eight are NOT one measured cohort

Window 1 ran on `0420fb0`; window 2 runs on `188da7c`, which carries three
further repairs including the one that fixes the competitor contradiction. So
these eight companies were **not** read on one build and this document must
not present them as a single cohort. Two consequences, both stated rather than
smoothed over:

- Any cross-company comparison that spans the two windows is confounded by the
  build, exactly as a NVIDIA-vs-Caterpillar comparison across `58ac7ef` and
  `0420fb0` would have been. Within-window comparisons are sound.
- **The JPMorgan ownership proof cannot come from window 2**, because
  JPMorgan is not in it. "Did `committing capital to capacity` leave
  JPMorgan's page" needs a JPMorgan re-run on `188da7c`. Until that run
  exists, that repair is **verified by test and NOT by capture**, and is
  recorded that way below.

## Reliability, window 1 (`0420fb0`)

| company | seconds | auto-advanced | false failure | manual recovery | wrong identity | board answers |
|---|---|---|---|---|---|---|
| JPMorgan Chase | 159 | yes | no | no | no | 10/10 |
| NVIDIA | 249 | yes | no | no | no | 10/10 |
| Walmart | 70 | yes | no | no | no | 10/10 |

Walmart and NVIDIA had both previously dead-ended on a SEC 429. Both
completed. `transient_retry_count` is **NOT_MEASURED**: it is operator-only by
design (§16 forbids asking a customer to understand a 429) and no guest route
exposes it. Completion is the observable; the count is not inferred from it.

## Classification — the prediction the pages are scored against

Resolved offline through the real EDGAR path at `0420fb0`, zero demo quota.
Full table in `batch_a_classification_probe.json`.

| company | SIC | model class | patterns | `capacity_ahead_of_demand` |
|---|---|---|---|---|
| Meta | 7370 | ADVERTISING_PLATFORM | 8 | no |
| Amazon | 5961 | MULTI_ENGINE_PLATFORM | 8 | no |
| NVIDIA | 3674 | DESIGN_AND_MANUFACTURE | 10 | **yes** |
| JPMorgan | 6021 | BALANCE_SHEET_OR_NETWORK | 11 | no |
| Walmart | 5331 | SCALE_RETAIL | 7 | no |
| Eli Lilly | 2834 | REGULATED_PRODUCT_OR_PROVIDER | 9 | no |
| Caterpillar | 3531 | MANUFACTURE_AND_AFTERMARKET | 10 | **yes** |
| Exxon | 2911 | COMMODITY_PRODUCER | 5 | **yes** |

`capacity_ahead_of_demand` now reaches exactly the three companies that
commit capital to physical capacity. Before `0420fb0` it reached Meta, whose
rendered page told a chief executive about take-or-pay terms and ageing
production lines.

**Known and bounded:** two pattern sets remain byte-identical across
different classes — Meta ≡ Amazon, NVIDIA ≡ Caterpillar. This is not the old
defect (UNKNOWN inheriting the library) but it is the same family, and it is a
live risk for §44 (Alphabet must differ from Meta) and §45 (five
semiconductors must not share an engine). Window 1 evidence suggests the class
tables carry differentiation downstream of the menu — JPMorgan, NVIDIA and
Walmart do not share a menu and differed 9/10 — so this is recorded as
bounded rather than closed.

## Defects found and repaired

Each is stated with its evidence, its root cause, and how the cause was
established.

### D1 · The class gate was never told who the company is
**Visible evidence:** Meta and Caterpillar answered 10/10 board questions
identically on `58ac7ef`; Meta's Full Analysis carried "committing capital to
capacity ahead of uncertain demand".
**Root cause:** `_patterns_for_company` asked `profile_for` for a
classification passing only a NAME. Meta and Amazon are not in the curated
100-company manifest, so both resolved to UNKNOWN, and UNKNOWN takes the whole
library by design. The positive-applicability repair in `patterns_for` was
correct and could not fire.
**Established by:** derived independently from two directions within a minute
— forward from the caller, and backward from the rendered text.
**Systemic class:** a fix that ships inert because its caller withholds the
input. **Fix:** the gate receives domain + registrant + subject-only evidence
text, from one shared `classification_inputs` owner. **Live reproof:** window 1,
three classes, three menu sizes, nine differing answers.

### D2 · Eight of eleven model-keyed tables did not cover the registry
**Root cause:** `MODEL_CLASSES` has twelve entries; only three tables covered
it. Missing rows for the three newest classes in metric selection, market
belief, micro mechanisms, history economics, the counterfactual line, history
regimes — and in `_MODEL_FOREIGN`, the detector that exists to catch
take-or-pay language in a business with no order book, which therefore could
not fail. The guard did not notice because `_tables()` **named** two tables
instead of discovering them: the same mistake in the test that the denylist
was in the code.
**Established by:** offline enumeration of module-level dicts.
**Fix:** all eight filled; the guard now discovers model-keyed tables across
eight modules; `NEW_MODEL_CLASS_13` requires every discovered table and every
pattern to fail closed on a class nobody has decided about.

### D3 · A 429 was marked retryable and never retried
**Root cause:** `safe_fetch` classified and returned. The only retry the
product performed was asking the customer to try again.
**Fix:** one canonical policy — bounded attempts, exponential backoff, a
per-host budget **and** a run-level ceiling, injected sleeper and jitter,
telemetry reaching `/status.json`.
**A measured decision inside it:** transport failures are **not** retried.
Retrying silence turned two dials into six against a dead host, defeating a
circuit breaker that counts candidates rather than attempts. The breaker owns
hosts that do not answer; retry owns live servers that answered "not now".
Both sessions reached this independently from the same failing test.
**Live reproof:** Walmart and NVIDIA, which had dead-ended on 429s, completed.

### D4 · One service serves every run, so a ledger on it is one budget for everyone
**Root cause:** the webapp builds exactly one `CompanyIngestionService`. The
first analysis would spend the retry budget and every later analysis in that
process would get a policy that never retries — a repair that works once per
deploy and then stops silently.
**Established by:** code-reading, then asserted structurally.
**Fix:** ledgers per run; an AST test fails if the webapp ever builds more
than one service.

### D5 · A rival's filing stated our business model
**Visible evidence:** JPMorgan's page, under "How the business actually works
→ Distribution model": *"Is committing capital to capacity ahead of the demand
for it"*, attributed to **Wells Fargo & Company**'s 10-K. The same run carried
a blank-check SPAC; Walmart's carried Ranpak, Ibotta and a 2023 BitNile filing.
**Root cause:** `build_mental_model` builds each component from whichever
observations carry the signal, regardless of author — and a run retrieves other
registrants' filings on purpose, because they are the only independent vantage
it can reach. `_named_rivals` already carried this rule, repaired when Meta's
introduction named AT&T and Alphabet. One defect, two producers, one fixed.
**A rejected fix, recorded because it is the instructive part:** filtering the
documents at the observation call site turns
`test_live_pipeline_reaches_complete_multi_class` red — a COMPLETE report
requires an independent source class and coverage is computed from those
observations, so it fails the cross-source bar on every run to fix a claim
nobody had made yet. A break proof pins that so it cannot return silently.
**Fix:** ownership is enforced where the claim is made. Support is restricted
to subject-speaking classes; contradiction is not.
**Live reproof: NOT YET.** Verified by unit test and break proof; the
rendered-page proof needs a JPMorgan re-run on `188da7c`.

### D6 · The product named the competitors, then denied having identified any
**Visible evidence:** 3 of 3 companies on `0420fb0`. Step 1 named rivals; Q&A
answered "No competitor has been selected for this company from the evidence."
**Root cause:** in `_route_answer`, a populated list of structured rows hit
`if isinstance(value[0], dict): return absent`. The read fallback that would
have answered correctly was skipped **precisely because the data was there** —
`value` is truthy, so the emptiness check never fired. It depends on the shape
of the composed decision, not on the company: three classes, three ladders,
three Bounded reads, one failure.
**Established by:** executing the router against the real field name.
**Three plausible-wrong mechanisms preceded it, and two were the reporting
session's own.** (1) "`level4_competition` is empty on the read Q&A builds",
carried for two sessions. (2) "`_ground` raised and was swallowed on that
request." (3) "Step 1 is overclaiming from class-level manifest peers and Q&A
is the accurate surface" — the repairing session's, asserted from code-reading
and disproved in one step by the captures: none of the three rendered strings
appears in any manifest peer list, and the ladder emits categories at
`CONTESTED_CATEGORY`. All three were plausible; none survived execution. That
is the honest shape of how this was found, and it is why the method is
recorded beside every cause in this document.
**Fix:** rows are rendered; an unrenderable row falls through to the canonical
read before anything reaches the absent copy. The branch serves every intent
whose field holds rows, so the repair is at the shape.

### D7 · Two producers could choose different strengths for one claim
Kept on its own merits and **explicitly not** the fix for D6. There is now one
competitive state carrying its basis — EVIDENCE / SAME_MODEL / SECTOR / NONE —
and the verb follows the basis. `STRUCTURAL_PEER` cannot reach the evidence
basis: the ladder defines that rung as "same business model; not a stated
rival", and rendering it as the strongest claim on the page is how Meta's
opening once named 37signals and Exxon's a gold miner.

### D8 · A markdown push destroyed a live analysis
**Visible evidence:** Meta's window-2 run (`01M0FQHQ9T31DH41DWEHVCDEW3`) ran
its full 556 seconds, never auto-advanced, and then returned 404 on all
thirteen routes: *"This session does not have an analysis with that id.
Analyses are kept per session and are cleared when the service restarts."*
The run and its quota slot were lost.
**Root cause:** three **docs-only** pushes to `v5/founder` during an open live
window. Render redeploys on any push to the tracked branch regardless of what
changed; guest sessions live in process memory; every in-flight run dies with
the restart. The repairing session had asserted "docs-only, so your window is
unaffected" without checking it.
**Established by:** the peer session's capture, immediately.
**Systemic class:** the deployed branch is also the artifact branch, so
writing a report is an operational act. This belongs under live reliability,
not tooling — the customer-visible version is a chief executive losing a
five-minute analysis because somebody shipped a README.
**Fix (proposed, not yet made):** separate the artifact branch from the
deployed branch. Gating pushes on "nobody is holding a window" is the weaker
remedy because it depends on everyone remembering, and that protocol failed
the first day it existed.
**Interim:** commits are held locally for the duration of any live window.

### D9 · An advertising platform was asked no strategic question at all
**Visible evidence:** composing both reads offline from their own filings,
Alphabet and Meta were identical on 10 of 12 projected fields, and one of the
two that differed was the **central question** — which for both read *"What
does the published record establish about <name>, and what would have to be
true before a commitment rests on it?"* That is the epistemic fallback, in the
slot reserved for the one decision worth arguing about.
**Root cause:** `ADVERTISING_PLATFORM` proposes exactly two decision
archetypes, `ENGAGEMENT` and `MONETISATION_RATE`, and **neither** had a row in
`_ARCHETYPE_SUBJECT`, so `_decision_question` fell through.
**Systemic class — the third instance, and the sharpest.** A class was added
and a table keyed on something *that class introduces* never got its rows.
The model-class registry guard could not see it because `_ARCHETYPE_SUBJECT`
is keyed on **archetype**, not on model class. It was discovering tables in
the right way and looking one key-space to the left. The general property is
harder than the one first written: a class needs rows not only in tables
keyed on CLASS, but in every table keyed on anything that class introduces.
**Fix:** both rows written in this business's own variables — Meta now asks
"how much of the audience's attention to convert into inventory, and where,
given that ad load taken today is paid for out of users and their engagement
tomorrow?" A guard discovers every archetype any registered class can propose
and requires each to be able to ask; a break proof adds an archetype to a
class menu and requires the suite to go red.
**Live reproof: NOT YET** — both Meta captures this session were lost or
pre-fix (see D8), which is why Meta is the thinnest-evidenced company here.

### D10 · The article "A" was protected as an initialism
**Visible evidence:** Amazon's opening on `31e6138` — *"contested directly by
A specialist doing one engine better than the bundle"*, capital A mid-sentence.
**Root cause:** `_lower_first` guards initialisms with `head.isupper()`, and
`"A".isupper()` is `True`. Latent and pre-existing; surfaced by a new
`_MODEL_ALTERNATIVES` entry beginning "A specialist…".
**Fix:** a one-letter alphabetic head is an article unless it is "I". `"A."`
keeps the guard because the stop makes it an initial. Found and fixed by the
journey session; carried here to avoid a second mid-window redeploy.

## §45 — the semiconductor bar fails structurally

Composing real reads offline from each company's own filings
(`same_class_read_probe.json`):

| pair | identical projected fields |
|---|---|
| NVIDIA vs AMD | 8 / 12 |
| NVIDIA vs Intel | 8 / 12 |
| Intel vs Micron | 8 / 12 |
| Microsoft vs Salesforce | 8 / 12 |
| Alphabet vs Meta | 10 / 12 |

For the semiconductors the only differences are identity,
`strategic_position`, `level4_competition` and `competitive_rivals` — all four
downstream of the competitive ladder, which quotes each filing's own words.
**Identical:** central question, economic role, business-model statements,
mechanisms, metrics, and "what matters now". NVIDIA and AMD are handed the
same central question and the same six metrics.

**What is established, and what is not.** The structural claim is a code fact
needing no window: every class-keyed table returns one answer per class, so
within a class only run-derived evidence can differentiate, and for
advertising platforms even the ladder is class-derived. The 8/12 and 10/12
corroborate it and give it a magnitude. What is **not** established is that
these companies read alike *on the page* — this measures the read object, and
the object is not the product. The four fields that do differ are exactly the
ones a reader meets first. Batch B should capture the NVIDIA/AMD pair as
evidence beside this number, not as the purpose of a window.

**The wrong fix, named in advance:** a bespoke class per company. §44 forbids
it without evidence and it reproduces the original defect in a new shape.

### D5 (continued) · The ownership repair shipped and was inert — twice
**Visible evidence, on `cec9b2f`, after the class gate deployed:** JPMorgan's
page unchanged — *"Is committing capital to capacity ahead of the demand for
it"*, sourced to **Wells Fargo & Company**'s 10-K. And on Meta:
*"Meta Platforms, Inc. is committing capital to capacity ahead of the demand
for it"*, sourced to **Network-1 Technologies**' 2024 10-K — a patent litigant
whose filing says "our case against Meta Platforms, Inc."
**Root cause 1 — the class gate cannot do this job.**
`edgar.filing_candidates` stamps `"source_class": "investor_material"` on every
filing it proposes, *whoever filed it*. So another registrant's 10-K is
subject-speaking by that test. **`source_class` encodes how a document was
retrieved, not whose it is, and can never carry ownership.** The rendered label
"Regulatory or investor filing" was the visible clue throughout.
**Root cause 2 — a second route entirely.** The Meta case never went through
`build_mental_model`. `narrative.py` renders the mechanism quote under the
heading *"The company's own words:"*, and `reasoning._mechanism_evidence`
supplied whichever observation happened to carry the signal.
**Established by:** a rendered capture, after a code-read assertion by the
repairing session — *"the class filter alone is sufficient"* — was wrong. The
risk was flagged in the same message the error was made in.
**Fix:** ownership is decided in `derive_observations`, at the only layer that
still holds the URL (the EDGAR path names the filer), and carried on the
observation as `subject_owned`. `build_mental_model` sees observations and
never a URL, which is exactly why the first repair was written against the only
signal visible there. Route 2 is filtered at the producer, so the narrative,
the decision's grounding and the citations move together rather than each
growing its own filter.
**Live reproof: PENDING.** Verified by test and 11/11 break proofs — the same
standing the version that shipped inert had. `grep "committing capital to
capacity"` on JPMorgan and Meta is the deciding measurement.

### D11 · Two companies sharing a pattern share the reading
**Visible evidence:** Caterpillar and Exxon Mobil — *different* business-model
classes, different rendered business models — answered **8 of 10** board
questions with the identical sentence, "committing capital to capacity ahead of
uncertain demand". Reproduced on two SHAs.
**Root cause:** `compose_decision`'s own docstring states it: *"nothing here is
per-company"*. Every field is the pattern's static text with only `{company}`
substituted. **This was never code departing from intent — it was the intent,
written down, and nobody read it back against what the product had become.**
**Class is not the axis.** This is the cross-class form of what was measured
offline *within* a class. One statement covers both: wherever two companies
share a top pattern, they share the reading. A seventeenth table row keyed on
class cannot fix it — these two are already in different classes.
**Partially fixed:** the answer's evidence is now grounded in the sentence from
*this* filer's own document (`FounderDecision.grounded_in`, read by Q&A, which
receives a projected `FounderInsight` that never carried the hypothesis).
**Predicted and confirmed:** grounding would *not* move the 8/10, because board
answers route off topic/falsifier/recommendation and never off mechanism. It
did not move. **The template itself is open**, recorded as an
`xfail(strict=True)` so the day it passes is visible.

## Not yet cleared

- **Distinct is not the §22 bar.** Some window-1 answers differ by
  *withholding*: Walmart's "what should management do?" is a refusal,
  JPMorgan's defers to the X-Ray, only NVIDIA states a thesis. Recorded as
  measured, **not** counted toward a pass.
- **20-dimension scorecard:** NOT_MEASURED pending window 2.
- **§23–§35** — presentation, history, Step 6, mobile/desktop, light/dark,
  accessibility, security, zero-Anthropic: NOT_MEASURED.
- **Batch B:** not started. The classification probe is done
  (`batch_b_classification_probe.json`) and names the first pair to run:
  **NVIDIA and AMD back to back on one SHA**, because six of sixteen
  companies share `DESIGN_AND_MANUFACTURE` and an identical menu, and
  same-class differentiation — not menu differentiation — is the §45 bar.
- **§36 security re-proof:** PASS (255 tests) across tenant scope, run-route
  ownership, the redirect wall, SSRF validation and demo mode, plus new
  path-traversal proofs for the cache, which is a filesystem write path named
  from a URL. Nine hostile document names refused, nothing written.
- **§37 zero-Anthropic:** PASS. All six steps plus Q&A, evidence, sources,
  brief and X-Ray render with the credential removed and the `anthropic`
  module raising on use. `REQUIRED_ANTHROPIC_CALLS = 0`.

## Method notes worth carrying forward

0. **Verify the instrument hardest when it agrees with you.** Three of the
   four collapse-measurement errors were self-correcting because the number
   looked wrong. The fourth produced 0/10 — a clean sweep — and was caught
   only by reading the underlying answers before believing it. The flattering
   error is the one that ships.
1. **A guard that enumerates cannot cover what it does not know about.**
   True of the pattern denylist and true of `_tables()`.
2. **AST keyword checks must fail closed.** A starred kwarg makes arguments
   invisible to `ast.Call.keywords` — but `kw.arg` is `None`, so the required
   name is absent and the assertion fails loudly. The lesson is not that such
   checks are unsafe; it is that they must fail closed.
3. **NOT_CAUGHT usually names a weak test, not weak code.** Four break proofs
   came back NOT_CAUGHT in this session. One exposed a cache-poisoning vector
   the test never reached; one, a test that walked past the gate its mutation
   targeted; one, a test that would have accepted a raw dict repr as an answer
   to a chief executive.
4. **Record how a cause was established.** Two wrong turns here were
   mechanisms asserted from code-reading that a capture later contradicted.

---

# Handover

**`BATCH_A_FINAL_UI_COMPLETE` is NOT reached, and should not be recorded as
reached.** Seven of eight companies have been read on a rendered page, across
**four different SHAs**, and the twenty scorecard dimensions are
`NOT_MEASURED` for every one of them. Rounding that up would be the same error
this document spends most of its length describing.

## What is measured, and would be defended

| | |
|---|---|
| Template collapse | 10/10 identical → 1/10 → 0/10 across five, with one 8/10 pair remaining |
| Reliability | 11/11 auto-advanced across three windows; 0 false failures; 0 manual recoveries; 110/110 board questions answered |
| One run destroyed | by a redeploy during an open window (D8) |
| Class gate | closed at source — `capacity_ahead_of_demand` reaches exactly the three companies that commit capital to physical capacity |
| Case A (competitor contradiction) | closed **on the page** |
| Archetype fallback | closed **on the page** — Meta asks a real question in its own variables |
| Claim ownership | **OPEN**, verified by test only, both routes rewired and awaiting a rendered capture |
| §37 zero-Anthropic | PASS — `REQUIRED_ANTHROPIC_CALLS = 0` across all six steps plus Q&A, evidence, sources, brief, X-Ray |
| §36 security | PASS — 255 tests, plus new path-traversal proofs for the cache |

## The next three things, in order

1. **Settle grep 2.** JPMorgan exercises route 1, Meta exercises route 2. Two
   runs. Until then the ownership repair has exactly the standing its
   predecessor had when it shipped inert.
2. **The template itself (D11).** The open half. The axis is *the qualifying
   evidence*, not the class — a bespoke class per company reproduces the
   original defect in a new shape, and §44 forbids it without evidence.
3. **Batch B, live-UI-first.** The classification probe is done and names the
   first pair: NVIDIA and AMD, back to back on one SHA, captured as evidence
   beside the structural claim rather than as the purpose of a window.

## How this session actually went

Nine defects, and the patterns across them are about **who reads what**, not
about any one subsystem. Two related shapes, kept separate because the fix
differs:

**Produced and never read** — nobody called them at all. `MODEL_CLASSES`, a
registry no table consulted. `subject_documents`, written and never imported
by the module that needed it. The retry ledger, wired onto the service and
surfaced nowhere. *The fix is a caller.*

**Read by one consumer and not another** — a subtler shape and the more
dangerous one, because the thing looks alive. `classification_inputs` existed
on the webapp while the ingestion layer kept its own name-only resolution.
`mechanism_evidence` was read correctly by `narrative.py` all along and not by
`decision.py` — a distinction the repairing session initially got wrong,
generalising from the consumer that failed. *The fix is a single owner, not a
second implementation.* Collapsing these two shapes loses exactly the
reasoning that separates a good fix from a duplicate.

**Causal stories asserted and then disproved by execution — six of them.**
Four from the journey session: the SEC block is a burst limit (falsified by a
paced wave); it is document size (falsified by measuring bytes);
`level4_competition` is empty or the gate blocked it (falsified by three
Bounded reads); filter the documents at the `derive_observations` call site
(falsified by the independent-source-class bar going red). Two from the
repairing session: step 1 is overclaiming from manifest peers (falsified by
the captures); `source_class` alone is sufficient (falsified by the JPMorgan
capture). Every one was plausible. None survived execution — and *execution*
is the right word, because two were experiments rather than rendered pages.
That is why each root cause here records how it was established.

**Break proofs that came back `NOT_CAUGHT` or `INVALID`: more than twenty
across both sessions — and not one of them meant the code was fine.** Every
single one named a weak test, a dead guard, or a bound already enforced
elsewhere: a test that passed on an empty list; a fixture whose signal reached
no consumer, so the end-to-end assertion passed for the wrong reason; an
assertion satisfied by a raw dict repr; a test that called the helper and
walked past the call site being repaired; an assertion checking for the
absence of one phrase, where removing the guard produced a *different* wrong
sentence containing none of the words looked for. That last one is the
sharpest: **absence-of-a-phrase is a spelling test, not a property.** A guard
asserts the property, with a positive control beside it, so it can fail in
both directions.

And one about measurement: **verify the instrument hardest when it agrees with
you.** Four instruments were tried on the collapse number. Three of the four
errors were self-correcting because the result looked wrong. The fourth
produced 0/10 — a clean sweep — and was caught only by reading the underlying
answers before believing it. The flattering error is the one that ships.
