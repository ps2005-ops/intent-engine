# POSITIVE CONTROL MECHANISM REPORT

**Question.** Why did project44, Descartes Systems and o9 Solutions become
`EVIDENCE_LED` when 29 other companies did not?

**Baseline.** `db6946faebc128f791220d8f82de60910d7d0401`, the frozen 40-company
qualification. All figures below are read from
`40_company_qualification_matrix.json`, not re-derived.

**Method.** Reconstruct the full selection state of the three controls, compare
against five negative controls (3 × `CLASS_PRIOR_ONLY`, 2 × `NO_DECISION`), then
read the code path that produced them. Nothing here is inferred from prose.

---

## 1. THE ANSWER IN ONE SENTENCE

The three controls won **not** because they had better evidence, but because
`SUPPLY_CHAIN` is the only archetype in the vocabulary whose phrase list is made
of **object nouns** instead of **decision-act phrases** — so it is the only
archetype that a company's ordinary published prose can ever trigger.

## 2. THE MEASUREMENT THAT SETTLES IT

Across all 40 companies, the evidence layer fired **nine phrase matches in
total**:

```
carrier 2 · freight 2 · lead time 1 · customs 1 · logistics 1 ·
shipment 1 · supplier 1          <- all SUPPLY_CHAIN
churn reduction 1 · customer retention 1   <- all RETENTION
```

Seven of the nine belong to one archetype. The other fifteen archetypes
contributed **zero matches across forty companies**.

Distribution of `evidence_term_count`:

| terms | companies |
|------:|----------:|
| 0 | 29 |
| 2 | 1 (Gong) |
| 5 | 1 (o9) |
| 8 | 1 (Descartes) |
| 9 | 1 (project44) |
| n/a (abstained) | 7 |

**29 of the 33 non-abstaining companies had literally no decision-relevant
evidence at all.** Their decision was therefore 100% class prior, by
construction and not by accident.

## 3. WHY THE OUTPUT COLLAPSED

The decision question is a pure function of two variables:

```
decision_question = f(archetype, business_model_class)
```

because `_decision_question()` fills its slots from
`profile.primary_revenue_drivers[0]` and `primary_cost_drivers[0]`, and those
come from `_ECONOMICS[business_model_class]` — a **table keyed on the class**.
Every `SUBSCRIPTION_SOFTWARE` company in existence has
`primary_revenue_drivers[0] == "customer count"`.

With 3 observed model classes and 3 observed archetypes, the reachable output
space over 40 companies was **four strings**:

| n | decision question |
|--:|---|
| 22 | what to charge, and for what, without losing more **customer count** than the price gains? |
| 7 | what to charge, and for what, without losing more **billable headcount or capacity** … |
| 3 | how supply is secured, and at what cost, given what **sales and marketing to acquire an account** allows … |
| 1 | what to spend to keep the customers already won … |

The 47 near-identical X-Ray pairs are not a rendering defect and not a prose
defect. They are the arithmetic consequence of a 4-valued output space.

## 4. THE THREE CONTROLS, RECONSTRUCTED

All three are identical on every structural field that mattered:

| field | project44 | Descartes | o9 |
|---|---|---|---|
| model class | SUBSCRIPTION_SOFTWARE | SUBSCRIPTION_SOFTWARE | SUBSCRIPTION_SOFTWARE |
| class prior would choose | PRICING | PRICING | PRICING |
| archetype won | Supply chain | Supply chain | Supply chain |
| on the standing menu? | **no** | **no** | **no** |
| evidence terms | carrier, freight, lead time (9) | carrier, customs, freight (8) | logistics, shipment, supplier (5) |
| ranked above | pricing | pricing | pricing |
| independent origins | 0 | 0 | 0 |
| economic links | 3 | 0 | 0 |
| history level | B | A (90 docs) | B |
| discovery | results | results | **no results** |
| **decision question** | *(byte-identical across all three)* | ← | ← |

**The structural condition for `EVIDENCE_LED` is therefore exactly:**

> an **off-menu** archetype — one the business-model class does not propose —
> must be introduced by the company's own text and then strictly outrank the
> on-menu default.

Evidence can never produce `EVIDENCE_LED` for an archetype already on the menu,
because reinforcing the default cannot change the answer. That is why Gong,
with real retention evidence, reads `CLASS_PRIOR_REINFORCED_BY_EVIDENCE` and not
`EVIDENCE_LED`: RETENTION was already second on the software menu.

Corroboration, evidence diversity, independent origins, economic links, history
depth and discovery success **played no part**: o9 won with fewer terms, zero
economic links and a failed discovery; Descartes won with 90 documents and
Level A history and got the same reading as o9 with 7 documents.

## 5. THE UNCOMFORTABLE PART

The three controls are logistics **software vendors**. Their published record is
saturated with `carrier`, `freight`, `customs` and `lead time` because that is
**the domain they sell into**, not because they face a freight problem.
project44 does not procure carriers; it sells visibility to people who do.

So the system read *"this company's pages discuss freight"* as *"this company is
deciding about its own supply chain"* — a **subject/object confusion**, the same
family as the recorded lesson *"a page that mentions a subject is not a company
facing a decision"*, one level up.

The reading is not worthless — a company whose entire product is logistics
genuinely is different from a generic data vendor, and the page said truthfully
what the basis was. But it is **not** the mechanism we want to generalise, and
copying it is the trap.

## 6. WHAT MUST NOT BE DONE

The obvious repair — give the other fifteen archetypes object-noun vocabularies
so they fire too — **recreates the defect at higher volume**. Twelve security
companies would all match a security vocabulary, all receive one new constant
question, and the overlap number would not move. It also reintroduces exactly
what the 40 already rejected: GTM vocabulary, compliance words, ASC 805
boilerplate, disclosed SaaS metrics.

Adding vocabulary raises `EVIDENCE_LED` counts without raising specificity. It
is differentiation theatre.

## 7. WHAT THE REPAIR MUST BE

The collapse has one root cause: **the only high-cardinality thing about a
company — its own words about what it sells, to whom, and what it depends on —
never reaches the decision.** Every slot in the question is filled from a
class-keyed table.

So the repair is not a bigger vocabulary. It is a change of **source**:

1. **Decision object.** The question's variable slots must be fillable from the
   company's own record (what it charges for, who buys, what it depends on),
   falling back to the class constant *with the fallback stated*.
2. **Subject/object discipline.** A term found in a company's record counts as
   evidence that **this company faces** the decision only when the record puts
   the company in the deciding position — otherwise it is evidence about the
   market it serves, which is a different (and still useful) reading.
3. **Genericity must be measured and must cost something.** A statement that
   survives a name-swap is not intelligence; it must be detected and the reading
   downgraded, not reworded.
4. **`StrategicDelta` must be observable.** "What would the class prior alone
   have said, and did anything change it?" is already computed per archetype
   (`contributions.class_prior_only`) but is not surfaced as a first-class
   product object.
5. **Abstention must carry information value.** 29 zero-evidence companies got a
   confident-sounding pricing question. The honest output for most of them is a
   class prior *plus what would have to be learned to move off it*.

None of these raises `EVIDENCE_LED` counts by construction. Several of them will
*lower* apparent confidence. That is the intended direction.

---

*Written before any change to scoring, as required. Basis: frozen matrix
`db6946fa` + `src/intent_engine/executive/analysis_selection.py` and
`company_profile.py` at that SHA.*
