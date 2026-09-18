# STRATEGIC REASONING V2 — ARCHITECTURE

What was built, why it was built that way, and what it deliberately does not do.

**Baseline** `db6946faebc128f791220d8f82de60910d7d0401` — the frozen 40-company
qualification. **Branch** `v6/asi-v2`.

---

## 1. THE DEFECT, RESTATED IN ONE LINE

The decision question was `f(archetype, business_model_class)`. Both inputs are
low-cardinality, so 33 companies produced **four** distinct questions and 22 of
them produced one identical string.

Full reconstruction: [`positive_control_mechanism_report.md`](positive_control_mechanism_report.md).

## 2. WHAT WAS ADDED

### 2.1 `executive/decision_object.py` — the company's own variables

Reads the company's own published account for three things a decision question
needs and that genuinely differ between companies:

| slot | what it is | example (measured on live pages) |
|---|---|---|
| `BILLING_UNIT` | what one unit of revenue is counted in | Huntress → *number of endpoints*; NinjaOne → *device* |
| `BUYER` | who decides to pay | Snyk → *AI teams*; Procore → *construction industry* |
| `DEPENDENCY` | what delivery rests on that the company does not own | Obsidian → *API access from SaaS vendors* |

Each slot is `ESTABLISHED` with a quoted sentence, or `NOT_ESTABLISHED` with a
reason. There is no third state and no guess.

**The subject rule.** A phrase counts only when *this company* is the
grammatical subject of the sentence carrying it. This is the positive
controls' lesson paid forward: project44's record is saturated with `carrier`,
`freight` and `customs` because logistics is the domain it **sells into**, and
the old layer read that as "this company is deciding about its own supply
chain".

**Why not more vocabulary.** Giving the other fifteen archetypes object-noun
vocabularies would fire a security vocabulary at twelve security companies and
hand all twelve one *new* constant. That raises `EVIDENCE_LED` counts without
raising specificity — differentiation theatre, and exactly what the 40 rejected.

**Five gates, all grammatical, none about topic.** Written after measuring real
pages, because every one of them was a real false positive first:

| gate | what it caught on a live page |
|---|---|
| prose vs furniture | *"Built for **Outcomes**, Not Optics"* (Huntress slogan) |
| buyer is lower-case | *"Help **center** Find the help you need"* (Vanta heading run) |
| evaluative heads | *"the **world's most innovative companies**"* (Snyk puffery) |
| head-final trim | *"enterprise-wide access governance across all users"* (Veza — a capability, not a who) |
| generic buyer | *"businesses of all sizes"* — names nobody |

### 2.2 `executive/strategic_delta.py` — three measurements of one thing

**`ground()` — the name-swap test (§8, §12).** Remove the company name, then
ask whether anything the company itself published survives in the statement.

- `GROUNDED` — a company-published term is load-bearing
- `NAME_ONLY` — only the name distinguishes this from a competitor's page
- `GENERIC` — not even the name

`NAME_ONLY` is the verdict that matters. It is what 22 of the frozen 40 would
have received, and it is **invisible to any measurement that looks at one
company at a time** — which is why it went twenty-two times unnoticed.

**`StrategicDelta` (§13).** Compares the reading against the reading the class
prior alone gives — produced by running *the same builder* with the company's
record withheld. Comparing against a placeholder measures the placeholder.

`NO_CHANGE` · `REINFORCED` · `REFRAMED` · `REVERSED` · `WEAKENED` ·
`NEW_OPTION` · `ABSTAINED`

`REFRAMED` is new and is the commonest honest outcome: the same decision, now
measured in the company's own terms.

**`InformationPriority` (§14).** When a slot is unestablished, name the question
that would fill it, what it would change, and where to look. The frozen 40 gave
29 companies a confident-sounding question and nothing to do about it.

### 2.3 `executive/learning_rehearsal.py` — the loop, rehearsed and labelled

```
T0   hide everything filed after the cutoff → read → form belief → PREREGISTER
T1   advance the cutoff → observe what arrived → reconcile → read again
     → measure whether the DECISION moved, and say why
```

Runs the **real** decision path twice: `read` is injected, and production passes
`analysis_selection.select` — the same function every surface uses. A rehearsal
of a different reasoner would prove nothing about this one.

**§22 is enforced in code, not prose.** `as_dict()` overwrites `label` with
`HISTORICAL_REHEARSAL` unconditionally, so a caller that constructs a row with
`label="REAL_FORWARD"` is not believed. Break proof 03 mutates that line and
the guard fires.

**§24 is enforced by construction.** No branch produces a reversal the evidence
did not produce. `NO_MATERIAL_CHANGE` is a legitimate end state. `REVERSED` is
reserved for a decision that became a *different* decision; a decision
re-measured in new terms is `MEASURE_REVISED`, because inflating the one count
a reader trusts most is the failure mode here.

### 2.4 Surfaces

| surface | what it answers |
|---|---|
| X-Ray → *Why this reading is this company's* | §12. Shows an ungrounded reading **as** ungrounded, and prints the question the class prior alone would have asked. |
| X-Ray → *What we would have to learn next* | §14, ranked by what each fact would change. |
| `/runs/<id>/learning` | §27. Believed → why → expected → happened → changed → how the reading changed → watching next. Badged `HISTORICAL REHEARSAL` and `NOT FORWARD CALIBRATION`, never blended. |

## 3. WHAT WAS DELIBERATELY NOT DONE

- **No new archetype vocabulary.** The archetype menu is unchanged.
- **No company-specific branches.** No `if company == …` anywhere. Every repair
  is an invariant that applies to an unseen 26th company.
- **The billing unit measures a decision; it may not select one.** Break proof
  08 mutates the scorer so a stated unit moves the archetype, and the guard
  fires. Without this the repair would be a new keyword channel into the one
  place the 40 proved must not have one.
- **The buyer reaches only decisions whose *outcome* depends on who buys**
  (`_BUYER_BEARS_ON`). Naming a customer inside "where the next increment of
  capital goes" adds a noun and no meaning. Break proof 07.
- **No manufactured specificity.** Where nothing is established, the page says
  so and asks for what is missing.

## 4. WHAT THIS PREDICTS, BEFORE THE LIVE RUN

Measured on twelve of the twenty-five companies' live pages through a crude
fetch (the product's own retriever reads more, including filings), the slots
fired for a **minority**. That is a true property of the corpus, not only of
the extractor: most companies do not state in extractable prose who buys them
or what they charge for.

So the honest expectation is:

- a **minority** of the 25 reach `GROUNDED`
- the **majority** keep the class prior, say that they are keeping it, and
  carry an information priority naming what would move them
- `EVIDENCE_LED` counts should **not** rise much, and a large rise would be
  evidence the vocabulary leaked back in

§41 is the standard being aimed at: false differentiation stays gone while real
company-specific reasoning increases materially. Not "25 EVIDENCE_LED".

## 5. PROOF CARRIED

| kind | count | file |
|---|---|---|
| focused + adversarial tests | 19 | `tests/test_decision_is_measured_in_this_company_s_own_unit.py` |
| §18 regression control | 11 | `tests/test_v2_does_not_reopen_the_forty_s_closed_defects.py` |
| rehearsal wall + label | 10 | `tests/test_historical_learning_rehearsal_is_labelled_and_walled.py` |
| break proofs | 12/12 HELD | `scripts/break_proofs_asi2.py` |

Every break proof declares its mutated symbol, the guard expected to fire and
the production call path, and is **refused before it runs** if the mutated
symbol is the guard. Each also runs a positive control on clean code first: a
guard that fires before the mutation is `UNRELIABLE`, not passing.

Three proofs were `NOT_CAUGHT`/`NOT_APPLIED` on first run. All three were
defects **in the proofs** — a mutation string that did not match, a check that
could not fail, and a mutation that appended a newline to a frozenset literal
and emptied nothing. Each is recorded here rather than quietly fixed, because
a break-proof harness whose failures are always the product's is not measuring
itself.
