# FINAL PRE-100 CONVERGENCE — the belief layer, measured

    PRE100_EXECUTIVE_PRODUCT_GATE        = NOT PASS
    PRODUCT_ARCHITECTURE                 = NOT FROZEN
    SAFE_TO_BEGIN_100_COMPANY_PERFECTION = NO
    BREAKER10_STATUS                     = NOT STARTED (freeze did not pass)

Two criteria fail. Both are named in §6 with their measurement and the work
that would close them. Nothing is rounded up, and the gate is not declared
because the cycle ended.

---

## 1. The premise the last cycle recorded was false, and measuring it first
   is what made this cycle work

The previous gate named one blocker — `company_specificity` 8.0 on five of
seven golden companies — and recorded its cause:

> "What would close it: extraction of the Competition section of the
>  subject's own annual filing, which does name rivals under obligation to be
>  accurate."

That was measured before anything was built on it. **It is false.** The
Competition section is retrieved, it is located by the existing extractor, and
it names no company at all:

| Company | What its own Competition section actually says |
|---|---|
| Cloudflare | "on-premises network hardware vendors", "point solution vendors", "content delivery network (CDN) vendors" |
| Bank of America | "banks, thrifts, credit unions, investment banking firms … hedge funds, private equity firms" |
| Johnson & Johnson | "In all of their product lines, the Company's subsidiaries compete with companies both locally and globally" |

Fifteen categories for the bank, zero company names. A modern 10-K names
**classes of rival and the ground they contest**, because naming a firm
invites a claim and naming a category does not.

So retrieval was never the constraint. The **contract** was: a competitor had
to be a company. The extractor accepted only capitalised proper nouns, threw
the company's own account of its market away, and fell back to structural
peers — Adobe, Constellation and Databricks for Cloudflare, a set no
Cloudflare customer has ever chosen between.

    A COMPETITOR IS WHATEVER THE CUSTOMER COULD DO INSTEAD.

---

## 2. The competitive reality ladder

Ten rungs, and the rung records *where the claim came from* rather than how
good it is. Four extractors feed it, and each one was built because a real
company's evidence had a shape the others could not read.

| Source | What it reads | Where it came from |
|---|---|---|
| Contested categories | the classes a filing says it competes with, including the enumeration *inside* a bullet | Cloudflare's "in various categories including … CDN vendors" — five categories that were being discarded with the bullet's tail |
| Named threats | a dated threat to a **named asset of the subject's own** | J&J's Competition section is contentless; the same filing says biosimilar STELARA launches "will continue to negatively impact" sales. A filing can name no competitor and still name the threat exactly. |
| Migrations | what a customer stopped using | Shopify's own site: "migrated from Magento to Shopify in under three months" |
| Model alternatives | buy-versus-build, do-nothing, displacement | §2 requires these to be **searched for**, not merely accepted when a filing volunteers them |

Every row carries identity, kind, mechanism, evidence, independence,
confidence, why it matters and what would disprove it. `Rival` refuses at
construction without a mechanism and a disproof: a competitor with no
mechanism is a logo on a slide, and one that cannot be wrong was never a
claim.

**What it refuses.** Third-party filings are excluded by source class, so a
sentiment-trading company's 10-K cannot supply Cloudflare's competitors again.
"Competitive factors" are not competitors — a section listing "pace of
innovation" yields nothing. Marketing prose is not an incumbent: "replaced
traditional fashion markups with Shopify" reached the table as a named rival
and no longer does. One kind may take at most two of six rows, because Bank of
America's filing lists fifteen direct categories and a table that answers one
question six times has answered one.

---

## 3. The belief layer

The product answered "what does the evidence say?" well and stopped. That is a
good answer to the wrong question: a chief executive is choosing between our
reading and the one already in their head.

    the market appears to believe X          MarketBelief
    the strongest case that X is right       BeliefChallenge.strongest_support
    the evidence that would break it         falsifiers
    the explanations that fit the same facts ExplanationField
    the possibility the model excludes       ImpossibleHypothesis
    what our own argument rests on           AssumptionGraph
    the cheapest way to find out             MinimumViableExperiment

**A belief is not a price.** There is no estimate feed here and inventing one
would be the worst thing this product could do. A belief is INFERRED from the
filed record — the same two-date discipline the expectation model uses — and
the row says so. It is never called a consensus, because nobody polled anyone.
A private company has no series, gets no inferred market expectation, and is
not given a fabricated one.

**Contrarianism is not a result.** `BeliefChallenge` refuses to report a
belief as weakened, revised or retired without naming the evidence that moved
it. STRENGTHENED is a first-class outcome and scores full marks: a
conventional reading that survives a serious attack is the most usable thing a
chief executive can be handed.

**"Impossible" describes the search, not the permission.** Ten hypothesis
families are generated and each is *bound to this company* before it survives
— to a contested category the run found, to the observed trajectory, to the
business model. A family that will not bind produces exactly the generic
sentence `IMPOSSIBLE_HYPOTHESIS_GENERIC` names, so it is not produced.

**The weakest link is found, not asserted.** Weak in the way that matters
means poorly supported **and** load-bearing, so it is ranked on the product of
standing and downstream load. A contradicted link is reported rather than
ranked, because a broken chain is not a weak one. A fully supported chain
names no weakest link at all.

---

## 4. What reading the pages found, all green in tests

Every one of these was invisible to the suite and visible in output.

1. **"That Cloudflare's the margin story continues"** — half the stored
   clauses began with a noun and half with an article, and the frame fitted
   neither.
2. **"Your real competitor is not a company — it is banks"** — the filter
   keyed on the *rung* rather than the *kind*. Banks are companies.
3. **"the contest Shopify has to win is against magento"** — the sentence
   frame lowercased whatever it was handed, and it was handed a name.
4. **The four readings collapsed onto one.** `most_dangerous` ranked by the
   LENGTH of the cost sentence, which is a property of the writing.
5. **One identical experiment for four different companies** with four
   different questions — the MVE took the challenge's own test instead of the
   observation the two live readings disagree about.
6. **"Bank of america"** — `str.capitalize` lower-cases the remainder, inside
   the company's own basis note.
7. **A note contradicting the table beneath it** — "No competitive statement
   by Shopify was retrieved" directly above "Magento — named by a customer".
8. **"Measure the direction shown in the record persists into the next period
   against net revenue retention is the measure that moves first"** — the
   graph's nodes are clauses, and clauses do not concatenate into a sentence.
9. **A dead end I introduced** — "…more weight than anything else that is not
   established" was caught by the customer-copy sweep, correctly.
10. **`full_analysis_quality` fell from 10.0 to 6.0 on two companies** whose
    full analysis was not at fault: structural findings about the *read* were
    reported on surface `full`, and every finding on a surface is charged
    against that surface's writing.

---

## 5. Break proofs — 23/23 held

Four came back NOT_CAUGHT on the first run. **All four were weak proofs, not
weak code**, and each named something real:

* two cases were blocked by *two* guards, so removing either left the test
  passing — isolating fixtures were added (a migration between two other
  companies; a price offered as a competitor);
* "competitive factors" is protected by the lead-in gate, not by the head-noun
  test the proof claimed — so the proof was pointed at a case only the head
  noun protects;
* a CONTRADICTED link sorts first under the ranking path too, so asserting the
  standing passed whichever branch ran. What differs is what the reader is
  told to do — reconcile, not check — and that is now asserted.

---

## 6. THE TWO FAILURES, STATED EXACTLY

### `company_specificity` — mean 9.71, **minimum 8.0**, bar 8.5

Six of seven companies read 10.0, up from two of seven. **Stripe reads 8.0.**

Stripe is private: no filed Competition section exists and none ever will.
The run *did* retrieve its customer stories — `/customers/anthropic` and
`/customers/amazon` were selected and fetched, so this is not a coverage
failure. Those stories describe what the customer **gained**, not what they
weighed. The nearest signal is Anthropic "wanting to monetise Claude while
reserving its team members' time for product development" — a buy-versus-build
statement in everything but its grammar.

**What would close it**: an avoided-build extractor over customer stories
("rather than build", "without having to build", "instead of hiring"), gated
as tightly as the migration extractor is. It was **not attempted**, because
the one case motivating it does not contain the words such a rule can safely
match, and widening the rule until it does is how a fabricated competitor
reaches a chief executive.

### `competitive_specificity` — mean 7.86, **minimum 5.0**, bar 9.0

This dimension did not exist before this cycle. It counts alternatives resting
on the company's own account or an attributed source, against a denominator of
two. Johnson & Johnson and Shopify each ground exactly one — biosimilar
STELARA, and Magento — and score 5.0.

The instrument was **not retuned to pass**. One grounded competitive fact is
genuinely better than none and genuinely thinner than two, and a stricter
measurement revealing more is the measurement working.

**What would close it**: rung 3 (`NAMED_BY_RIVAL`) is declared in the ladder
and has no producer. Third-party filings are already retrieved and already
carry a `title` naming the filer; a filing whose competition passage names the
subject makes its filer a rival, attributable and quotable. Measured on
Stripe's three third-party filings: **zero** of them mention Stripe in a
competition passage — they cite it as a payment vendor. So the producer must
be built and measured across a wider set before it can be claimed.

---

## 7. Known and non-blocking

* `macroeconomics` 6.0 — unchanged, and correct when no macro channel has a
  mechanism for the company.
* `qa_quality` 7.0 — pre-existing, unchanged by this cycle.
* `INTERNAL_BUILD_IGNORED` clusters on Caterpillar and Johnson & Johnson
  (SEV3): neither business model table offers a buy-versus-build alternative,
  which is arguably right for a pharmaceutical company and arguably wrong for
  heavy equipment. It is a cluster of two with five unaffected controls, so it
  is a real cluster and it is recorded rather than patched at the end of a
  cycle.
