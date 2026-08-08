# Execution checkpoint — V3 multi-actor economic intelligence

Machine-readable continuation state. A completed slice is a checkpoint, not an
endpoint: this file exists so the mission survives a context boundary instead
of restarting from an audit.

Updated 2026-08-07, wave 5.

## Pinned state

| what | where |
|---|---|
| market head | `HEAD of feat/consumption-telemetry` (see git log) |
| market runtime | **`079128b` — NOT repinned; owner action below** |
| founder head | `c1c1cb8` (branch `feat/consumption-emitter`) |
| founder preview | `f0a0294` LIVE |
| production `main` | `119d345` — **untouched, do not target** |
| PAPER | structurally enforced in all three launchd plists |
| market suite | 4145+ passed / 4 skipped / EXIT=0 |
| founder suite | 4575 passed / 6 skipped / EXIT=0 |

### OWNER_ACTION_REQUIRED

```bash
cd /Users/prathamsharma/intent-engine-market && git checkout <latest market SHA>
```

Refused by the permission classifier in waves 4 and 5. Not retried further,
per instruction. The runtime therefore still runs `079128b` and does not run
the wave-4 or wave-5 work.

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

## Remaining queue, highest value first

1. **Observation of the named rival.** Everything from strategic interactions
   onward is blocked on it, and nothing else is.
2. **`_NOT_RIVALRY` is a whole-sentence filter** and refused 31 sentences.
   Whole-sentence filters over-reject; it should apply to the matched clause.
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
