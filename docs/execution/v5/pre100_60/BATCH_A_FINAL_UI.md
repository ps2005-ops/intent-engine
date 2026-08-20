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
| `188da7c` | structured rows rendered, one competitive state — **current** |

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

## Not yet cleared

- **Distinct is not the §22 bar.** Some window-1 answers differ by
  *withholding*: Walmart's "what should management do?" is a refusal,
  JPMorgan's defers to the X-Ray, only NVIDIA states a thesis. Recorded as
  measured, **not** counted toward a pass.
- **20-dimension scorecard:** NOT_MEASURED pending window 2.
- **§23–§35** — presentation, history, Step 6, mobile/desktop, light/dark,
  accessibility, security, zero-Anthropic: NOT_MEASURED.
- **Batch B:** not started.

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
