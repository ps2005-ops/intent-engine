# Adaptive Strategic Intelligence — architecture

## The problem this layer was built for

The product could already analyse a company. What it could not do was explain
why *this* company should care about the analysis rather than a company like
it. Ten reports read like one template with the names swapped.

The cause was structural rather than editorial, and it is worth stating
precisely because it is not what it looks like from the page:

> Every differentiating table in the product — the pattern library, the
> per-class metrics, the macro transmission table, the causal questions, the
> competitor set — is keyed on `business_model_class`. Before this phase,
> `company_profile.profile_for` could produce one from exactly two sources: a
> curated 100-company validation manifest, or an SEC industry code.

A private company is in neither. Measured on the ten companies this phase
qualifies against, **10 of 10** resolved `PROFILE_SPARSE` with
`business_model_class = UNKNOWN`, and `UNKNOWN` switches off all five tables
at once.

So the differentiation was never suppressed by the writing. It was never
reachable. Measured on the live preview before any change, the first screen a
Highspot executive met read:

> "Highspot could not be classified into a business model from the public
> record… this company is not in the validation manifest and no regulator
> industry classification was found for it… **Adding this company to the
> validation manifest would resolve it.**"

and the recommendation the product made to them was *"Classify the business
before commissioning analysis."* The same run had already retrieved
Highspot's own "AI Platform for Revenue Execution" page.

## The shape

```
subject's own published text
        │
        ▼
  classify ──────────────► business model class            (third classifier)
        │
        ▼
  profile  ──────────────► CompanyStrategicProfile         (every field tagged)
        │
        ▼
  lens     ──────────────► primary + secondary + refusals  (routed on evidence)
        │
        ▼
  opportunity ───────────► ranked decision map             (components exposed)
        │
        ▼
  causal   ──────────────► change → … → decision           (each edge labelled)
        │
        ▼
  differentiation ───────► why this company                (+ collapse detector)
        │
        ▼
  composer ──────────────► which modules, order, depth     (every choice cited)
        │
        ▼
  roles    ──────────────► an ORDERING, never a fact
```

`adaptive.engine.build` runs these in exactly this order because each is an
input to the next, and it never raises: a surface that cannot render its
adaptive block shows the ordinary analysis, not a 500. Failures land in
`errors` and surface in telemetry, so a missing block always has a named
cause.

## The third classifier

`adaptive.classify` is ranked **last**, behind both existing classifiers, and
`profile_for` consults it only where both refused:

| rank | source | authority |
|---|---|---|
| 1 | validation manifest | authored, reviewed, version-controlled |
| 2 | SEC industry code, corrected by the filer's own revenue sentence | a third party's judgement about a statutory document |
| 3 | the company's own published material | a first-party statement of how the money works |

Rung 3 trusts the same *kind* of evidence `revenue_model_hint` already trusts.
It applies the same rule: **it may not guess.**

- a signal must be a **whole word or phrase** — substring matching refuses
  real companies (`alpha` inside `Alphabet Inc.`) and invents false ones;
- a signal must carry an **applicability** — every rule needs a MODEL signal
  (how the money works), not only a DOMAIN signal (what the product is
  about), because a library entry firing on signal names alone reaches the
  wrong kind of company;
- a runner-up within `MARGIN_SHARE` of the winner is **unresolved**, not
  rounded up;
- the **matching span is quoted back**;
- `UNKNOWN` stays available and states its reason. Not proven is not
  disproven.

## Why every profile field carries its provenance

`CLASS_PRIOR` is not a defect. *"A subscription software business earns next
period's revenue from the installed base before any new sale"* is true of
subscription software businesses by construction. What is a defect is a class
prior **presented as a finding about this company** — the recorded failure
where per-class text made five software companies byte-identical.

So no field is a bare string. Each is a `Fact` carrying
`value / provenance / basis / evidence`, and `specificity` is the share of
populated fields drawn from this company's own evidence or the analyst's
evidence-cited reconstruction. A profile near zero has learned the company's
name and its industry's economics, and the product says so.

## Why the lens is not routed by industry

Eight of the ten qualification companies are the same business model class.
Routing on the class would give all eight the same analysis.

What separates them is **what decision their customers are buying help with**,
and each states that in its own material: a sales-enablement vendor writes
about quota, ramp and pipeline; a data-governance vendor writes about
discovery, retention and regulation. Same P&L shape, different worlds.

`eligible_business_models` is a **hard gate**, not a weight. *Supply Chain &
External Shock* scores well on a software company writing about "supply chain
security" — and is refused there, because a firm with no physical inputs has
no supply-chain exposure to have and the phrase is about the product.

Every eligible lens that lost is named with the reason it lost. A router that
only shows its winner cannot be audited.

## The decision priority

```
priority = materiality × change × exposure × actionability × evidence
           × (1 − 0.5 × genericity)
           × (1 − 0.15 × evidence_gap)
```

Multiplicative: a decision that is enormously material and completely
unactionable is not half-useful, it is useless, and any component at zero
takes the product to zero. Every component is published beside the result.

The first version subtracted absolute penalties and **every opportunity in
the map scored 0.000**, including a high-impact, decide-this-quarter,
verdict-do-it-now decision with two cited observations. Three faults in one
line: uncertainty was counted twice (it is `1 − evidence`, already a factor);
naming a gap was punished, which is the behaviour the analyst contract exists
to encourage; and absolute penalties can exceed a bounded base. Discounts can
reduce a score and can never invert it.

## The role lens invariant

A role may change priority, order, emphasis, framing and which questions are
offered. It **may not change a fact, a number, a citation, a standing label or
a confidence.**

Enforced structurally: `role_view` receives an already-composed report and
returns an ordering plus a question set. It is handed no evidence, no profile
and no analysis, so there is nothing for it to rewrite — pinned by
`test_a_role_view_holds_no_module_bodies`, which asserts the signature.

Nine roles are declared; two (CEO, Strategy) are live because two have
surfaces built for them. The rest are shown as `FUTURE_ROLE_VIEW` rather than
hidden: a reader should see the shape of what is coming without being misled
into thinking it is connected to their systems.

## The genericity detector

The section claims the analysis is different for this company. The detector
answers that claim two ways:

- **single** — what share of the company half is drawn from this company's own
  evidence rather than from its class;
- **pairwise** — after normalising both company names away, how much of two
  companies' composed readings is byte-shared.

The pairwise form is the one that catches template collapse, because a
template is invisible from inside a single report. Normalisation removes **the
subject's identity only** — an earlier version stripped every capitalised
token, deleting the dependencies (`Snowflake`, `Microsoft Azure`) that are
among the most company-specific things on the page, so two genuinely different
reports collapsed onto each other and the detector reported a defect of its
own making.

## What this layer may not do

No company-specific output is hard-coded anywhere in `adaptive/`. Every
company-facing sentence is composed from that company's own evidence, or from
the structural economics of the class its own evidence selected. A claim that
survives being made about an unrelated company is something this package
**detects**, not something it ships.
## Addendum — what the live development run changed (be5fde12 → freeze)

The architecture above was written from the build. This section is written from
the deployed product, and every defect in it was found by reading a real page
rather than by reading telemetry. That distinction matters: the telemetry for
the Highspot run was clean — `0 defects`, `0 leaks` — on the same page that
told its chief executive the company depended on itself.

### The three states, and where each is decided

```
profile_available            profile.known               "what kind of business is this"
lens_available               lens_selection.primary      "which decisions tend to matter for it"
decision_reading_available   opportunity_map.has_reading "what THIS management should consider"
```

`DecisionOpportunityMap.state` is the field every renderer branches on, and
`PotentialDomain` is a different TYPE from `DecisionOpportunity` — not a
low-scoring one — so nothing can rank an area worth investigating beside a
recommendation, whoever renders it.

### Four seams, and the defect each one hid

| seam | what went wrong | why telemetry could not see it |
|---|---|---|
| dependency extractor → page | `partners with ([A-Z]…)` captured the SUBJECT: "Partner with Highspot's services team" | a dependency was found, so the field was populated and the count was right |
| retrieved corpus → classifier | the corpus is observation EXCERPTS, and Slalom's were its CLIENTS' industry pages | the classifier behaved correctly on the text it was given |
| classifier vocabulary | "consulting **services**" and "consulting **company**" were absent; only "advisory services" and "consulting **firm**" were present | a score of 0.0 is indistinguishable from a company that is not a consultancy |
| adaptive block → founder layer | the page abstains, then recommends | each layer's own output is internally consistent |

The last is the one worth remembering. `webapp/app.py` composes the adaptive
block and then the founder brief, and its own comment states the boundary:
"The adaptive block reads that page. **What follows it is unchanged.**" That
was a deliberate, documented decision — and it was made before there was an
abstention for the rest of the page to contradict. A seam is not wrong when it
is drawn; it becomes wrong when one side learns to say something new.

### The span module's own last line

`quote_around` exists because a window of "match minus 220 characters" has no
idea where a word begins. It snaps to sentences — and returned
`clean[:max_chars]`. Six break proofs mutated the START of the span; none
mutated the end; and the test named "never begins **or ends** mid-word" had a
fixture of two short sentences, so the truncation branch never executed. The
half of the name after the "or" asserted nothing for as long as it existed.

The general lesson, and it is the third time this codebase has recorded a
version of it: **a test's name is not a test.** The fixture has to be able to
reach the branch, and the way to know it can is to watch it fail.

### What the environment bounds, and what it does not

The preview reports `DISCOVERY_NOT_RUN` — "no search was run" — so no
independent third-party source can be discovered there. Every source on the
Highspot and Slalom runs was company-owned, which is why `0 of 6` and `0 of 4`
sources were independent, and why neither run could raise a decision-grade
reading. The product reports this as a limit of retrieval rather than as a
finding about the company, which is the correct behaviour and is asserted.

This bounds how many of the ten can reach `DECISION_READING` on this
deployment. It does not bound identity, profile, lens, differentiation,
evidence handling, roles, Q&A or UI, which are what the rest of the matrix
measures.
