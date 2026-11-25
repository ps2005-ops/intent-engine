# MECHANISM_FALSIFIABILITY_AUDIT

16 mechanism families are routed in
`belief_formation._ROUTES`. Of those, **4** are falsifiable
by observation today.

## Why exactly 4, mechanically

`observation_binding.falsifiable_families()` derives the set from the routing
table: a family is bound only when at least one evidence type that routes to
it **also routes the opposite way**. 21 evidence types are
routed; only those carrying two directions produce a bindable family.

This is a deliberate refusal, documented in the module itself: binding an
occurrence-only family would build "a channel that can only ever confirm, and
a test that cannot fail is not a test -- it is a ratchet that would drive
every posterior to 1.0 and call it learning." **The 12 unbound families are
not an oversight and must not be bound bidirectionally on their existing
evidence type.**

## Five-way classification

| family | bound today | class | why |
|---|---|---|---|
| `capacity_expansion` | no | **FALSIFIABLE_BUT_HORIZON_OPEN** | capex ahead of demand resolves over years, beyond any window now preregistered |
| `capacity_hiring` | no | **FALSIFIABLE_BUT_DATA_MISSING** | headcount growth against revenue growth is bidirectional and unavailable here |
| `capital_return_posture` | no | **FALSIFIABLE_BUT_DATA_MISSING** | buyback+dividend against capex is a ratio that can fall; needs XBRL |
| `competitor_aggression` | no | **UNFALSIFIABLE_AS_STATED** | a rival acting is not a claim about the subject that could be wrong |
| `consolidation_posture` | no | **FALSIFIABLE_BUT_HORIZON_OPEN** | further M&A or a divestiture is bidirectional but arrives irregularly |
| `demand_strengthening` | yes | **FALSIFIABLE_AND_OBSERVABLE** | earnings/guidance/inventory route both ways |
| `demand_weakening` | yes | **FALSIFIABLE_AND_OBSERVABLE** | same bidirectional evidence types |
| `leadership_transition` | no | **NOT_A_CAUSAL_MECHANISM** | 'will change what it prioritises' is a prediction of unspecified change -- every outcome satisfies it |
| `margin_protection` | no | **FALSIFIABLE_BUT_DATA_MISSING** | a later operating-margin direction would test it both ways; no financial-series channel exists in this engine |
| `market_share_seeking` | yes | **FALSIFIABLE_AND_OBSERVABLE** | paired against pricing_power |
| `partner_led_distribution` | no | **UNFALSIFIABLE_AS_STATED** | 'reaching its market through partners' has no stated threshold and no negation |
| `pricing_power` | yes | **FALSIFIABLE_AND_OBSERVABLE** | pricing signals route up and down |
| `procurement_momentum` | no | **UNFALSIFIABLE_AS_STATED** | awards accumulate; 'momentum' names no level that could fail to be reached |
| `productization` | no | **UNFALSIFIABLE_AS_STATED** | a launch confirms; no launch refutes nothing |
| `regulatory_pressure` | no | **NOT_A_CAUSAL_MECHANISM** | 'operating under active regulatory pressure' is descriptive context, not a causal claim with a consequence |
| `supply_constraint` | no | **FALSIFIABLE_BUT_DATA_MISSING** | easing is observable in lead times nothing here retrieves |

Totals: {'FALSIFIABLE_BUT_HORIZON_OPEN': 2, 'FALSIFIABLE_BUT_DATA_MISSING': 4, 'UNFALSIFIABLE_AS_STATED': 4, 'FALSIFIABLE_AND_OBSERVABLE': 4, 'NOT_A_CAUSAL_MECHANISM': 2}

## What this means for the gradeability count

- **4** families are testable now.
- **4** have a genuine
  bidirectional observable that this engine cannot currently retrieve. Every
  one of them needs a company financial-series channel (XBRL / companyfacts).
  **No such channel exists anywhere in this repository** -- confirmed by
  search. These are blocked on a data source, not on reasoning.
- **2** are falsifiable but
  resolve beyond any horizon currently preregistered.
- **4** need the proposition
  narrowed before they could be tested at all.
- **2** should be retired as
  predictive claims and kept as descriptive context, preserving their history.

No mechanism was reclassified upward to improve the count.

## The larger finding: discarded evidence

Evidence types present in the ledger but **routed nowhere** -- they propose
nothing and test nothing:

| evidence type | items | share of ledger |
|---|---:|---:|
| `DEMAND_SIGNAL` | 81 | 8.8% |
| `CUSTOMER_COMMENT` | 5 | 0.5% |

`DEMAND_SIGNAL` is the **second most common evidence type in the entire
ledger** and is routed nowhere. It is inherently bidirectional (orders and
bookings against cancellations), and `direction_of` already extracts a
direction for 49 of its 81 items across 18 companies.

**It is nevertheless not safe to route yet.** Of the 49 directional items,
14 are the subject's own marketing copy (`source_role=company_owned`,
independence 0.25) and the direction marker fires on words inside that copy —
one scored `olo` DOWN off the word "decrease" in a third party's product
blurb, and one assigns JPMorgan a demand belief from a story where JPMorgan
is merely the analyst being quoted. `belief_formation` already refuses a
belief whose evidence is *entirely* self-authored, but that gate is an
`all()`, so a single independent item launders a marketing item beside it.

Routing `DEMAND_SIGNAL` would therefore inject attribution noise into
`demand_strengthening` / `demand_weakening` — the only two families currently
carrying real accuracy signal. **Prerequisite: a per-item ownership gate that
decides whether the subject is the grammatical owner of the demand claim.**
That is the highest-value next change and it is specified, measured, and
deliberately not implemented here.
