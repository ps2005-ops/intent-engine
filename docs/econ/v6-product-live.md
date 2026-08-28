# The economic world model, wired into the product

*Branch `v6/unified`. This document records the PRODUCT run: what was wired,
what the wiring broke, what was found live, and what is still not proven.*

---

## What this run was for

The previous run ended with a working economic world model and an honest
sentence about it:

> `worldmodel`, `founder_ab`, `forward_engine`, `forward_ledger` and
> `breakproof` are **not imported by the webapp**. Deploying would only prove
> the existing surface still works — that isn't the claim §31 asks for.

So the research/product boundary was the highest-priority defect, and closing
it was the whole job: one vertical seam from the shared economic state to a
sentence a founder reads, deployed, driven against real companies, broken,
repaired and re-proven.

---

## The seam

```
econ.state (shared, public, dated)
    -> external_intel.econ_context        readings
    -> external_intel.econ_decision       the join: state x exposure x mechanism
    -> econ.founder_contract              FounderEconomicContext
    -> founder_brief.dossier              the ECONOMIC IMPACT passage
       founder_brief.qa                   the CEO answers
       webapp.app                         one object per request, memoised
```

The import direction is unchanged and still asserted:
`tests/test_econ_core_is_neutral.py` forbids `econ` from importing either
product, and `founder_contract` is a dataclass module that imports nothing but
`econ.vocabulary`. The founder side consumes the neutral contract; the neutral
core never learns that a founder exists.

### One object, not three derivations

`FounderEconomicContext` is built once per request and memoised on the
per-request thread-local — cleared at the top of `_route` beside the other
memos, because a memo that survives a request is the previous visitor's
company. The brief, the full analysis and the CEO Q&A render *that object*.

§21 — "brief and full may not contradict" — is therefore a property of there
being one object, not of three renderers agreeing. Every previous split in
this product (the brief contradicting the primary screen; Q&A denying a
falsifier step 1 was showing) looked correct on each surface alone.

### What the contract refuses, at construction

| refused | why |
|---|---|
| collective-human constructs | zero of sixteen are PROMOTED; the register is FROZEN_CANDIDATE |
| rehearsal expectations | REHEARSAL proves machinery; it is not a track record |
| a calibration claim with nothing resolved | an accuracy figure with an empty denominator |
| a stale state carrying a material change | §17 |
| a freshness that disagrees with its own dates | added after break proof 8; see below |
| COMPLETE with nothing in it | a heading with no content |
| NO_MATERIAL_ECONOMIC_DELTA carrying a change | a reader cannot tell which is true |

---

## What the parity harness found

`scripts/run_product_parity.py` runs the same sixty A/B cases through the
**product consumer** and compares the verdict case by case against the
research harness. It is not a prose diff — §20 says explicitly that the two
paths compose different sentences by design. It compares the structured
verdict: material stays material, abstention stays abstention, and no
unsupported new delta appears.

It found four things, in this order.

**1. The product was louder than its own research.** 38 material deltas
against 24. It treated any adverse-direction move as adverse; the research arm
had declared a 3% threshold before scoring anything. Same threshold now,
declared in one place.

**2. Which way is adverse is a company fact, not a channel fact.** One sign
per channel told Walmart that rising inflation hurt it, in four of six
regimes — while Walmart's own mechanism says grocery inflation *widens the
everyday-low-price advantage*. The sign now comes from
`company_profile.adverse_direction_for`, keyed on **(channel, business
model)** — the same key as the mechanism, so the two cannot disagree. A pair
whose mechanism states both directions carries **no sign** and can never move
a recommendation. That absence is the design, not an omission.

**3. The research harness's own convention was inverted on demand channels.**
Traced empirically rather than argued: every channel resolved to "adverse when
the driver rises", which is right for unemployment and credit spreads and
backwards for consumption, industrial production and permits. Nike's mechanism
says weaker consumption hits units; falling consumption scored as *not*
adverse for Nike. Union Pacific's says carloads follow permits; rising permits
scored as adverse for it. Corrected at source — the fourth element of a
`COMPANIES` channel now says which way the DRIVER has to move to hurt — and
re-run.

**4. Two coverage gaps that made real companies structurally unreachable.**
`SCALE_RETAIL` is a class the validation manifest carries and the transmission
table did not, so a scale retailer received no economic reading at all. And
the curve slope and the credit spreads were folded into `MARKET_RATE`, whose
sign for a balance-sheet business is deliberately unestablished — so a **bank
could never receive an economic reading**, which is the clearest case there is
of a condition reaching a business through a named mechanism.

### The offline numbers, after the corrections

| | research arm | product consumer |
|---|---|---|
| cases | 60 | 60 |
| material DecisionDelta | 25 | 19 |
| attributable | 25 / 25 | 19 / 19 |
| abstained | 35 | 41 |
| DecisionDamage | 0 | 0 |

| parity | |
|---|---|
| identical verdict | **52** |
| explained divergence | 8 |
| **unexplained divergence** | **0** |
| **unsupported new delta** | **0** |
| material but unattributed | 0 |

The eight explained divergences are all one shape: the product knows something
the research arm does not. Six are companies whose business model has no
mechanism for the condition that fired (including Meta, which the manifest
does not classify, and which therefore abstains rather than guessing). Two are
NVIDIA, where the research arm's hand-written note calls its
industrial-production exposure MIXED and the canonical
`DESIGN_AND_MANUFACTURE` table signs it — §9 says the reasoning must come from
canonical exposure state, so the product's source is the sanctioned one.

---

## Break proofs

Sixteen new mutations, against the code that runs when a customer presses
Analyse: the router, the context producer, the dossier renderer, the Q&A
router, the durable store.

**16/16 CAUGHT. 0 REFUSED_TAUTOLOGY. 0 NOT_CAUGHT.**
Target kinds: 8 producer, 3 consumer, 2 renderer, 2 call site, 1 persistence.

The mirror carries the **tests** as well as `src`, because several guards here
are structural — "is the renderer handed the context at all" cannot be a
runtime check, since a surface that was never handed it renders a
complete-looking page. A structural test resolving paths against the
repository would read the unmutated file and report green for a mutation it
never saw, so every path is derived from the imported module's own
`__file__`.

Two of the sixteen found real holes rather than confirming a guard.

**Proof 8 — a context could be *told* it was fresh.** The mutation computed
the age against the state's own date instead of the run's, so a 601-day-old
reading arrived labelled CURRENT. The admission wall, the damage detector and
the staleness rule all then worked *correctly* on a false input. The contract
now recomputes freshness from the two dates it carries and refuses a producer
that disagrees — the one place that has both dates and no reason to prefer
either answer.

**Six proofs were refused, and the meta-guard was right to.** They named a
test file as the production call path, and `assert_call_path_exists` reported
that the file "never calls" the test in it. True, and not the question: a
pytest test is invoked by collection, so its definition in a collected file is
its call site. The check now accepts a test definition. §36's anti-tautology
rule (`mutated_symbol != guard_under_test`) is unchanged and still separate.

---

## Failure semantics, preserved

Seven states, and the two that look like nothing are the two that matter most.

| state | what the reader is told |
|---|---|
| `COMPLETE` | the n elements of the recommendation that changed, and why |
| `NO_MATERIAL_ECONOMIC_DELTA` | "Current economic conditions do not materially change the strategic recommendation for this company", then the analysis continues |
| `INSUFFICIENT_EVIDENCE` | this company has no evidenced exposure to anything the state measures — a gap in its exposure map, not a quiet economy |
| `BLOCKED_DATA` | no state is published to this deployment; the analysis rests on the company's own evidence |
| `BLOCKED_EXTERNAL` | the state could not be read; reported as unavailable rather than omitted |
| `NO_NEW_DATA` | the state has not moved |
| `FAILED` | reported as failed rather than omitted |

An abstention renders one line and stops. It does not become a missing
section, and it does not grow a macro paragraph to justify its own heading — a
section that always speaks teaches its reader to stop reading it.

---

## The first live matrix

Deployed SHA `5f21b055`, ten companies, one anonymous session each, driven
through the real entry screen with its CSRF token — `curl` cannot hold the
session and a harness that sends less than the form does is bypassing the
customer flow rather than testing it.

```
attempted                10
read a result            10
economic section present 10
spoke (material delta)    0
abstained                 2
cross-surface conflict    0
internal enum leaks       0
requests with a 4xx/5xx   4
```

Ten of ten rendered the section and none of them contradicted itself across
the brief and the full analysis. **And none of them spoke** — which is the
result this run turned on, because five of the six reasons were defects.

### What the matrix found

| sev | defect | evidence |
|---|---|---|
| SEV1 | the published prior was the ADJACENT observation, not a year back | 1 of 13 conditions cleared a threshold declared for year-on-year change, and it was moving the favourable way |
| SEV1 | a page that contradicted itself one sentence later | 5 of 10: "no evidenced exposure to any condition the shared economic state measures", then "the shared economic state reads policy rate…" |
| SEV1 | a ratio taken on a series that crosses zero | the 3m/10y slope was −0.02 a year ago and 0.83 now: a 4,250% "move" |
| SEV1 | half the matrix had no Baseline A | `detect_vulnerabilities` fires only for a hypothesis whose pattern is in the vulnerability playbook |
| SEV2 | a condition in a channel that inverted its sign | `consumer_demand` sat in UNEMPLOYMENT, so a strengthening consumer read as a risk |
| SEV2 | an internal enum in customer copy | "rising to 6.66 percentage_point" |
| SEV2 | a label a reader cannot check | `financial_conditions` is measured here by the 30-year mortgage rate |
| SEV2 | A and B compared two different kinds of thing | a decision question "becomes" a business variable |
| SEV2 | an absent exposure reported as an absent reading | 3 of 10 said "(unavailable)" while the state sat on disk dated the previous day |
| SEV3 | one 500 on a primary screen; four client-side timeouts at 180s | Union Pacific |

Every one of the SEV1s and SEV2s is repaired in the commit that follows the
matrix, and the matrix harness now scores the two contradictions and the enum
leak directly — so the second iteration shows them gone rather than asserting
it.

### The one that is not a defect

`detect_vulnerabilities` returning nothing for a company the pattern library
does not match is upstream of this work and was not invented here. The repair
is a fallback to blind spots — the same shape, resting on the company's own
observations, carried at LOW severity with its source recorded. It is a
genuinely weaker claim than a vulnerability and is not presented as an equal
one.

---

## Live browser inspection

Driven in a real browser against the deployed preview, on a real run
(Cloudflare, `01M13KKFZBN3J72214DCQ5QMY7`) — the entry form filled and
submitted through `form.requestSubmit()`, because a ref-click on the submit
button reports success and silently does nothing at desktop widths.

| check | result |
|---|---|
| economic section on `/brief` | present |
| economic section on `/full` | present, byte-identical text |
| dark mode contrast (section text on body) | 15.8:1 |
| 1440 × 900 light | no horizontal overflow |
| 768 × 1024 dark | no horizontal overflow |
| 375 × 812 dark | **page overflows to 568px** — see below |
| economic section at 375px | 283px wide; does not overflow |
| CEO Q&A, "Which economic factor matters most?" | answered from the context, with provenance |

### The mobile overflow is not this section's

At 375px the full analysis scrolls to 568px. The innermost offenders are an
unbroken company-claim string in the customer-demand section (522px) and five
SVG `<text>` labels in the charts (437–475px). The economic section measures
283px and does not overflow. Both offenders are pre-existing surfaces outside
this seam, and are recorded rather than repaired — widening the change to
every page is exactly the scope this run was told not to take.

### Two copy defects the browser found and the harness could not

**"Policy rate, through policy rate."** The Q&A answer named the CHANNEL as
the thing a factor reaches you through, and the channel and the quantity are
frequently the same word. The useful noun — the variable it moves in *this*
business — was already on the exposure.

**"(current, 1 days old)."** Pluralisation.

Both are repaired and pinned by tests that quote the live string.

---

## The second live iteration

**Type: `SOFTWARE_REPAIR`, not `NEW_EVIDENCE`.** The panel is the same file it
was; nothing new arrived. What changed is how the prior observation is chosen,
how a move is measured, and what the page says. Calling that learning would be
the exact confusion §37 forbids.

Deployed SHA `27064b93`, nine companies through the harness (the tenth,
Cloudflare, was driven in the browser so one hour's quota covered both).

| | first (`5f21b055`) | second (`27064b93`) |
|---|---|---|
| attempted | 10 | 9 |
| read a result | 10 | 9 |
| economic section present | 10 | 9 |
| **spoke — material delta** | **0** | **2** |
| abstained | 2 | 1 |
| cross-surface conflict | 0 | 0 |
| internal enum leaks | 0 | 0 |
| **denies exposure then shows one** | **5** | **0** |
| **reading called "unavailable"** | **3** | **0** |
| server errors (4xx/5xx) | 1 | **0** |
| client timeouts | 4 @ 180s | 2 @ 300s |

Every defect the first matrix found is measured directly in the second, and
every one of them is zero.

### Nine companies, seven mechanisms, no two alike

| company | model class | what the page says the economy reaches it through |
|---|---|---|
| Walmart | SCALE_RETAIL | "rates set the carry on the inventory in the stores" |
| Nike | BRANDED_CONSUMER | "rates reach household discretionary spending" |
| JPMorgan | BALANCE_SHEET_OR_NETWORK | "rates move the cost of funds and the yield on assets at different speeds" |
| Visa | BALANCE_SHEET_OR_NETWORK | abstains — nothing it is exposed to moves adversely |
| Caterpillar | MANUFACTURE_AND_AFTERMARKET | no evidenced exposure; says so, and says it is a gap in the map |
| Meta | *unclassified* | no mechanism established; asks whether policy rate reaches it at all |
| NVIDIA | DESIGN_AND_MANUFACTURE | "rates set the hurdle on capacity commitments made years before the revenue they carry" |
| Salesforce | SUBSCRIPTION_SOFTWARE | "rates set the discount rate on customers' own investment cases" |
| Union Pacific | CONTRACTED_OR_RATE_BASE_ASSETS | "the capital programme is debt-financed" |

JPMorgan is the interesting one: it has the mechanism and does **not** speak,
because the sign of the rate LEVEL for a balance-sheet business is
deliberately unestablished — the mechanism itself says the two legs move at
different speeds. A single sign per channel would have made it speak, wrongly.

### What the second matrix found

| sev | defect | status |
|---|---|---|
| SEV2 | internal risk IDs in customer copy: "Changes top risks company:blind:0 becomes econ:financial_conditions" | repaired |
| SEV2 | the section explained the change through `company_exposures[0]` rather than the exposure the change rests on | repaired — the lead exposure is carried on the contract |
| SEV2 | the harness's own self-contradiction check read the whole joined page, so Caterpillar was reported as contradicting itself when its section is consistent | instrument repaired, and the report re-scored |
| SEV3 | two client timeouts at 300s on the full analysis | not repaired — measured locally at 0.86s with the context and 0.73s without, so it is the free instance's CPU quota |
| SEV3 | the blind-spot fallback imports the pattern library's generic language into Baseline A's `top_priority` | **named, not repaired** — see below |

### The limitation this run did not fix

Baseline A's risks now fall back to blind spots when the vulnerability
playbook does not match, which is what made a delta measurable at all. Blind
spots come from the pattern library, and the library's sentences are not
always company-specific: NVIDIA's `top_priority` "before" value read
"Consolidating checkout/identity/data rails may encroach on layers partners
currently monetize", which is commerce language on a chip designer.

The delta itself is sound — the AFTER value, the trigger, the mechanism and
the provenance are all this company's — but the BEFORE value inherits
whatever the library said. Repairing `_build_blind_spots` is upstream of this
seam and is recorded rather than attempted, because widening the change to
the pattern library is the scope this run was told not to take.

---

## §40 The demo, chosen after the matrix

The strongest real case is **Salesforce**, run `01M13PFD24FB0SFQXSVHJ95365`
on the deployed preview. It is chosen because the whole chain is present and
checkable, not because it is flattering.

**1. The company question** — the run's own decision, composed from
Salesforce's retrieved evidence before any economic reading is applied.

**2. The public evidence** — filings and investor material retrieved for this
run; the evidence appendix lists what was read and what was not.

**3. What the company-only analysis sees** — Baseline A: `top_priority` =
*demand capture at the storefront*, and one company risk from its own
evidence.

**4. The current economic state** — "As of 2026-08-27 the shared economic
state reads policy rate falling; financial conditions rising." Published from
`reports/panel/historical_panel.jsonl` by `econ_panel_publisher.v1`, thirteen
conditions, each dated with a year-earlier prior.

**5. How that state transmits to this company** — "rates set the discount rate
on customers' own investment cases, so higher rates lengthen procurement and
slow new bookings without touching the contracted base." That sentence comes
from `(MARKET_RATE, SUBSCRIPTION_SOFTWARE)` in the canonical transmission
table. Nike's page, from the same state, says something else entirely.

**6. The exact decision delta** — three structured fields:

```
top_priority          demand capture at the storefront
                   -> cost of funds and the hurdle rate on committed capital
top_risks             a company risk from its own evidence
                   -> the economic risk to financial conditions,
                      a company risk from its own evidence
information_priority  <the run's own gap>
                   -> how much of cost of funds and the hurdle rate on
                      committed capital is already contracted or hedged
```

**7. Why it is material** — the channel a founder looks at first changed, and
the most valuable missing information changed with it. Both are in the
preregistered `MATERIAL_FIELDS` list, frozen before any pair was scored.

**8. Evidence and provenance** — "financial conditions is rising to 6.66
percentage points from 6.58 a year earlier (2025-08-21) (as of 2026-08-27,
MORTGAGE30US, FRED)". The series is named because "financial conditions" is a
label a reader cannot otherwise check.

**9. What could make it wrong** — "Salesforce reports cost of funds and the
hurdle rate on committed capital holding while financial conditions continues
up."

**10. What the system wants to learn next** — "How much of cost of funds and
the hurdle rate on committed capital is already contracted, hedged or
repriced." Not "more research is needed".

**11. The forward expectation being tracked** — three open predictions, each
with a resolution rule and an expiry, appended to an immutable ledger.

**12. Status** — `PRE_CALIBRATION`, rendered as "none has come due, so there
is no accuracy record to quote yet". No percentage appears anywhere.

### And the abstention, which is the better half of the demo

**Visa**, same state, same deployment, same hour:

> Current economic conditions do not materially change the strategic
> recommendation for this company. Policy rate was read against this
> company's own exposures and none of them moves adversely through a channel
> that reaches this business, so the recommendation is unchanged.

One line, then the analysis continues. The system had the macro information,
read it against Visa's own evidenced exposures, and deliberately did not
change the recommendation.

**JPMorgan is the same point made harder.** It has the mechanism — "rates
move the cost of funds and the yield on assets at different speeds, so the
spread reprices" — and still does not speak, because that mechanism states
both directions and therefore carries no sign. A product willing to say
something about every company would have spoken there and been wrong.

---

## §46 Release gate

| capability | status |
|---|---|
| EconomicState → Founder, deployed and executing on real HTTP requests | **LIVE_PROVEN** |
| rendered output exposes it on `/brief` and `/full` | **LIVE_PROVEN** |
| multi-company matrix (10, then 9) | **LIVE_PROVEN** |
| provenance survives to the page | **LIVE_PROVEN** |
| abstention survives productization | **LIVE_PROVEN** |
| CEO Q&A off the same object | **LIVE_PROVEN** |
| forward status / `PRE_CALIBRATION` language | **LIVE_PROVEN** |
| unsupported human state remains blocked | **REFUSED**, by construction |
| offline semantic parity | **BUILT_NOT_LIVE_PROVEN** (an offline instrument by design) |
| operator learning panel | **BUILT_NOT_LIVE_PROVEN** (added after the second deploy) |
| economic History Rewind | **PARTIAL** |

**The economic Founder integration is `LIVE_PROVEN`.**

### What is NOT claimed

A material live DecisionDelta requires three things at once: the company's own
filings must establish an exposure to a condition the shared state measures,
that condition must currently be moving adversely through a mechanism this
business model has, and the run must also have produced a Baseline A. Two of
nine companies met all three. That is a fact about the world and about the
evidence this deployment can read, and it is reported as two of nine rather
than dressed up.

`CALIBRATION_STATUS = PRE_CALIBRATION` at **n = 0** resolved forward
predictions. Nothing here carries an accuracy claim and the contract raises if
one is asserted.
