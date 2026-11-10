# Personal Company AI — the foundation, and what is deliberately not built

## What exists now

`adaptive.roles` declares nine reader roles against **one** world model. Two
are live; seven are declared, ordered, and labelled `FUTURE_ROLE_VIEW` on the
page rather than hidden.

| role | status | reads first |
|---|---|---|
| Chief Executive | **live** | executive change, thesis, why-this-is-different, decision map |
| Strategy | **live** | lens, why-this-is-different, causal chain, alternative interpretation |
| Finance | future | financial sensitivity, economic exposure, scenarios |
| Operations | future | operational picture, supply chain, causal chain |
| Product | future | customer signals, competitive response, data & AI exposure |
| Revenue | future | customer signals, market belief, competitive response |
| Marketing | future | market belief, customer signals |
| Risk & Security | future | regulatory exposure, contradictions, provenance |
| Consultant / Advisor | future | client portfolio, decision map, why-this-is-different |

### One world model, not nine

There is no reasoning engine per role, and there will not be. Nine engines
disagree, and the disagreements reach the customer as the product
contradicting itself. The recorded version of that failure is smaller and the
same shape: a primary screen asserting an industrial capacity mechanism about
a software network while the X-Ray two clicks away read it correctly, because
each page composed its own read.

`role_view` therefore receives an **already-composed** report and returns an
ordering plus a question set. It is handed no evidence, no profile and no
analysis. `test_a_role_view_holds_no_module_bodies` asserts the signature, so
a future change that starts passing facts into it fails the suite rather than
quietly creating a second world model.

## The agent interface

A future company-facing agent reads, and does not re-derive:

```
user identity · role · company · current run
CompanyStrategicProfile · DecisionOpportunityMap · selected lens
canonical evidence · beliefs · causal mechanisms
prior decisions · expectations · learning state
```

Every one of those is a persisted object with a contract string today. **No
autonomous action is implemented**, and none is planned before the decision
loop below closes.

## Current versus future, and why the label matters

Everything the product does today runs on **public, external evidence**. The
`Where Intent Engine could create value` block on every report splits its two
halves explicitly and marks the second `not connected`:

**Current — external evidence only**
- monitoring the outside record for changes that reach this company through
  the stated mechanism
- testing the assumption the current plan rests on against the record
- provenance on every claim, so a disagreement is about the evidence rather
  than about the tool

**Future — with permissioned internal data**
- CRM and pipeline, to test whether the outside reading shows up in this
  company's own funnel
- product usage and support, to see the same change from the customer side
- finance, to attach a magnitude to an exposure that is currently directional
- prior decisions, so a recommendation can be checked against what was
  already tried

No return is claimed for any of it. None has been measured, and a page that
claimed one would be inventing the single number a buyer would check first.

## Consulting / multi-client mode

Two of the ten qualification companies are consultancies, and the value
proposition for them is not "analyse yourself" — it is **use Intent Engine
across client engagements**. That is a distinct lens
(`consulting_portfolio`) and a distinct role (`consultant`), not a distinct
product: same engine, same evidence conventions, same provenance standard.

The `client_portfolio` module is composed only for
`PEOPLE_OR_ROUTE_BASED_SERVICES` businesses and is excluded elsewhere with the
reason printed. It is demonstrated **structurally** — the shape of a client
portfolio read — and does not pretend Intent Engine holds private client data,
because it does not.

## The learning loop this must stay compatible with

```
Evidence → Attribution → Event Typing → Canonical Evidence → Belief
        → Expectation → Decision → Outcome → Calibration → Learning
```

No real outcomes exist for these ten companies yet, so the state is
`PRE_CALIBRATION` and is reported as such. What the product does show, and
what is honest to show, is:

- what it would monitor,
- what expectation the current reading implies,
- what would strengthen or weaken the thesis,
- what it needs to learn next (`information_priority`).

Fabricating learning performance would corrupt the only loop that could ever
tell us whether any of this was right.
