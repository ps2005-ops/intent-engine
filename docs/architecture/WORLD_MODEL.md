# The unified world model

*One closed loop, four state families, one package: `intent_engine.econ`.*

---

## 1. The architectural claim

There is **one** world model. Market Intelligence, Founder Intelligence,
Public Company Intelligence and the collective-human layer are surfaces onto
it, not parallel products.

The thing that makes this real rather than aspirational is a wall: the founder
package may not import the market package, and the market package may not
import the founder package. `tests/test_econ_core_is_neutral.py` parses every
module in `econ/` and refuses any import of either product's internals. So the
shared substrate is *structurally* incapable of reaching either side, and both
cross into a third package instead.

Unification is exactly the change that would have broken that wall, so the
wall is re-asserted rather than relaxed.

## 2. Four state families, kept apart on purpose

```
                         WORLD STATE
                             |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
 ECONOMIC STATE       COMPANY STATE        COLLECTIVE HUMAN STATE
   EconomicState    CompanyEconomicState   CollectiveStateEstimate
   econ/state.py      econ/company.py        econ/collective.py
        |                    |                    |
        +--------------+-----+--------------+-----+
                       |                    |
                       v                    v
                  INCENTIVES            PERCEPTION
                       |                    |
                       +----------+---------+
                                  |
                                  v
                              BEHAVIOUR
                       BEHAVIORAL node class
                                  |
                 +----------------+----------------+
                 |                |                |
                 v                v                v
              SPENDING        INVESTING        EMPLOYMENT
                 |                |                |
                 +----------------+----------------+
                                  |
                                  v
                          COLLECTIVE OUTCOME
                                  |
                  +---------------+---------------+
                  |                               |
                  v                               v
            ECONOMIC EFFECT                  MARKET EFFECT
                                                  |
                                     MarketParticipantState
                                        econ/levelk.py
                  +---------------+---------------+
                                  |
                                  v
                             NEW WORLD STATE
                                  |
                                  +----> learning loop
```

**They do not collapse into each other.** Credit stress is not fear. Market
volatility is not anxiety. A dealer's gamma is not a mood.

`CollectiveHumanState` covers households, consumers, workers, executives and
broad investor cohorts. `MarketParticipantState` covers dealers, CTAs, risk
parity, vol control and systematic flows. They interact — consumer fear →
spending down → retailer earnings down → analyst revisions → systematic factor
flows — but one is not the other, and they are estimated from different
evidence by different modules.

## 3. Five node classes

| class | what it measures | module |
|---|---|---|
| `MACRO` | the economy | 35 kinds |
| `MARKET_STRUCTURE` | prices, positioning, volatility | 13 kinds |
| `COMPANY` | one firm's operations | 22 kinds |
| `STRATEGIC` | competitive moves | 7 kinds |
| **`BEHAVIORAL`** | **what a population did or reported** | **26 kinds** |

`BEHAVIORAL` is deliberately a fifth class rather than a subset of `MACRO`.
A behavioural observation is a measurement *of people*, and the moment it is
filed as macro the engine loses the ability to ask whether people showed
something the aggregates had not. More concretely: if quits arrived as a macro
labour reading, the incremental-value comparison would be scoring a model
against itself.

No kind appears in two classes. No collective construct shares a name with an
economic quantity. Both are asserted by tests that compute the intersection
themselves.

## 4. The closed loop, and where each arrow lives

| step | module | status |
|---|---|---|
| observe world | `evidence`, `market/macro_ingest`, `market/behavioral_ingest` | live |
| estimate observable economic state | `econ/state.py` | live |
| infer collective human state | `econ/estimator.py` | live, 1 construct |
| update company operating states | `econ/company.py` | live |
| form / attack beliefs | `econ/belief.py`, `econ/attacks.py` | live |
| model causal-temporal structure | `econ/causal.py`, `econ/transmission.py` | live |
| detect reflexivity | `econ/reflexivity.py`, `econ/levelk.py` | live |
| identify causal bleeds | `econ/bleed.py` | built |
| choose information | `econ/voi.py` | live |
| preregister expectation | `econ/belief.py` | live |
| paper / no-trade decision | `econ/execution.py`, `econ/zero_trade.py` | live |
| resolve, calibrate, attribute | `econ/calibration.py`, `econ/replay.py` | live |
| **promote / weaken / retire** | `econ/promotion.py`, `econ/construct.py` | live |
| measure learning acceleration | `econ/acceleration.py` | live |
| publish sanitised state | `market/econ_bridge.py` | live |
| founder consumes it | `econ/founder_view.py` | live |

## 5. The two gates

Every path from a psychological construct to a decision passes through both.

**Gate 1 — did it earn its place?** (§18, §42)
The construct must be `PROMOTED`: it beat the base economic model on paired
out-of-sample forecasts, in two distinct regimes, with a bootstrap interval
clear of zero, surviving Benjamini-Hochberg at q=0.10 across the whole test
family, with no forecast scored against an outcome its cutoff did not precede.

**Gate 2 — does it reach this company?** (§13, §50)
The company must have a declared `Exposure`: a named channel and a named
company observable it would show up in. A company with no declared channel
gets **nothing** — not the population average.

Failing gate 1 is a research state. Failing gate 2 is a coverage state. They
call for opposite work — run an experiment, or map the company's exposures —
so `founder_view` reports them separately and names the *dominant* one.

## 6. Lineage and double counting

If company evidence contributes to a `ConsumerStressIndex`, the same report
cannot later treat that index as independent corroboration. Every derived
signal stores `lineage[]` and `depends_on[]`, and `econ/lineage.py` understands
derivation rather than comparing source labels.

This bites the collective layer specifically: company disclosure of customer
trade-down is real evidence, and it enters as `COMPANY` evidence. It may
therefore never corroborate a consumer aggregate built from the same
disclosures. `series.BEHAVIOURAL` records that as the reason `trade_down` has
no behavioural series rather than approximating one.

## 7. The privacy firewall

Public world model: **public evidence only.** Not filtered — *refused*. An
aggregate quietly built from private material and reported as smaller is a
breach that also lies about its own sample.

The collective layer adds one enforcement: the public core cannot construct an
`INDIVIDUAL`-scale population at all. §52's Personal AI will hold individual
and team state inside a tenant; the public core does not trust its callers not
to ask for one, it raises.

Zero cross-tenant learning by default.

## 8. What the model refuses to say

- causal language below evidence level 3 — the string is not constructed on
  that branch, so there is no flag that produces it
- an accuracy figure before the declared minimum forward sample
  (`PRE_CALIBRATION`)
- a posterior over a construct as a fraction of a population
- an untested construct informing any decision
- a derived signal as independent evidence of its own input
- live capital, at this stage, by construction

## 9. Known limitations of the world model as a whole

1. **`CALIBRATION_STATUS = PRE_CALIBRATION`**, n=0 forward resolutions for the
   collective layer. Nothing here has an accuracy claim.
2. **No transmission edge is above level 1.** Every chain reads "ASSOCIATED
   WITH". Raising them needs the historical programme, which needs vintage
   history this deployment cannot read.
3. **One population, one measurable construct.** See
   [`BUILD_STATUS.md`](BUILD_STATUS.md).
4. **The market engine's own cycle path still reads headlines** through its
   ledger-shaped exposure reader. The shared exposure capability is used by
   the founder path, not yet by that one.
5. **§9's state-space engine is partial**: precision-weighted Bayesian updating
   with uncertainty, but no dynamic transition model. A construct's posterior
   does not decay toward a prior between observations.
