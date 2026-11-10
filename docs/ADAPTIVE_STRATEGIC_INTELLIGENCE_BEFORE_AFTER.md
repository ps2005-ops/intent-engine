# Adaptive Strategic Intelligence — before → after

Frozen SHA: `807a414361b0fbc1999b4595e875c67e2a20524a`


Both sides are recorded artifacts, not recollections.

## BEFORE — the original live Highspot screen

Recorded in `docs/ADAPTIVE_STRATEGIC_INTELLIGENCE_ARCHITECTURE.md`, measured on
the live preview before any change in this phase. The first screen a Highspot
executive met read:

> "Highspot could not be classified into a business model from the public
> record… this company is not in the validation manifest and no regulator
> industry classification was found for it… **Adding this company to the
> validation manifest would resolve it.**"

and the recommendation the product made was *"Classify the business before
commissioning analysis."* The same run had already retrieved Highspot's own
"AI Platform for Revenue Execution" page.

- `business_model_class` = **UNKNOWN** — measured **10 of 10** on this cohort,
  because `profile_for` could only read a curated validation manifest or an
  SEC industry code, and a private company is in neither.
- UNKNOWN switched off all five differentiating tables at once, so the
  differentiation was never suppressed by the writing — it was unreachable.
- The headline was the generic product name, *Economic Decision Intelligence*.
- **The internal artifact was named to the customer.** "Validation manifest" is
  our word for our own file; it is not a thing a Highspot executive can act on,
  and the product asked them to do our data entry.

## MIDDLE — the state this session inherited (`df8830f0`)

Recorded in `reports/dev_highspot.json`. The classification was fixed by then;
the *refusal* was not:

- `business_model` = `SUBSCRIPTION_SOFTWARE`, source `SUBJECT_EVIDENCE` ✔
- `decision_opportunity_count` = 0, and the page said so as:
  > "No decision opportunity cleared the bar. That is a statement about the
  > evidence, not about this company: 3 candidate(s) were built and each was
  > either unevidenced, unactionable, or would have read the same way about an
  > unrelated company."
  followed by the three rejects — a careful refusal rendered as an empty card,
  on the screen that matters most.
- `result` = **PRODUCT_DEFECT**, one leak: the bare token `None` on `/intro`.
- Evidence spans cut by arithmetic: the live page carried
  *"The evidence this rests on omers are transforming GTM performance"*, and
  two of its three quotations came from a press-release index.

## AFTER — `be5fde12`, measured live, run `01M26WYVT48B1EVQNJPC6DH8KH`

Three separate questions, three separate answers:

```
PROFILE AVAILABLE            YES   subscription software, from its own account
LENS AVAILABLE               YES   Revenue & Go-To-Market Strategy, 41.5 vs 21.5
DECISION READING AVAILABLE   NO    the record raised none
```

- `result` = **DEFENSIBLE_ABSTENTION**, **0 defects**, **0 leaks**, CORE 9.4s.
- `decision_map_state` = `POTENTIAL_DOMAINS`, `causal_chain_kind` =
  `INVESTIGATION_CHAIN` — a different *type*, not a low score.
- The page renders *Potential decision domains*, labelled **not current
  recommendations**; an investigation chain drawn so it cannot be read as
  settled causality; and *What we can and cannot say about Highspot*, which
  names the evidence limitation and what would unlock a decision.
- Headline is **"Highspot — Revenue & Go-To-Market Strategy"**: the company and
  the lens, not a product name.
- Q&A 6/6 substantive, 6/6 company-specific, follow-up retains context.
- Roles differ in order; the anchored facts are identical in both.
- The phrase "validation manifest" cannot return: there is a break proof
  against it ("the internal artifact's name returns to customer-facing text").

## Not a Highspot-only repair — the consultancy case

`Slalom` on the same build returned `business_model = UNKNOWN` and
`profile_available = false`. The cause was vocabulary, not judgement: the
subject-owned text the run retrieved says *"personalized consulting services"*,
and the services class held `advisory services` and `consulting firm` and
matched neither, so a consultancy scored **0.0** on the services class.

`Point B` showed the other half — services won at 6.0 but BRANDED_CONSUMER
reached 4.0, on *"Consumer Packaged Goods **industries**"*, a sector it
**serves**. The margin rule correctly refused to separate them.

Measured after the repair, on each company's own published page:

| company | before | after |
|---|---|---|
| Slalom | UNKNOWN (0.0 services) | PEOPLE_OR_ROUTE_BASED_SERVICES **8.5** vs 2.0 |
| Point B | UNKNOWN (6.0 vs 4.0, unresolved) | PEOPLE_OR_ROUTE_BASED_SERVICES **10.0** vs 4.0 |
| BigID | SUBSCRIPTION_SOFTWARE | SUBSCRIPTION_SOFTWARE 7.5 (unmoved) |
| Sigma Computing | SUBSCRIPTION_SOFTWARE | SUBSCRIPTION_SOFTWARE 5.5 (unmoved) |
| Veeam | SUBSCRIPTION_SOFTWARE | SUBSCRIPTION_SOFTWARE 9.5 (unmoved) |

The negative control is a subscription business that also sells implementation
help: it stays `SUBSCRIPTION_SOFTWARE` (9.5 against 3.0), or widening the
services vocabulary would have reached across the margin and taken it.
