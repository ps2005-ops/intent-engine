# Deploy B register — defects found on the b0ec8cb canary

## D1. `challenge_block.CSS` renders as literal text on `/full` (CRITICAL, §13 raw leak)

`webapp/app.py` builds the full analysis as:

```python
strat = (fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS + _cb.CSS
         + fd.render_dossier(...))
```

Three of those four constants begin with `<style>`. `challenge_block.CSS`
does not — it is a bare stylesheet string. `_stylize` hoists `<style>`
elements to `<head>`, so the three wrapped ones move and the fourth stays
where it was: as TEXT, immediately after `<main>`.

Measured on Meta's live capture, the first thing inside the analysis:

> `<main> .challenge{border:1px solid var(--rule);border-radius:10px;padding:1rem 1.15rem; …`

Two consequences, and the second is worse than the first:

1. Every reader of `/full` — and every text extractor, accessibility tree and
   screen reader — gets a stylesheet as the opening content of the analysis.
2. The rules never apply, so the `.challenge` block (the belief-challenge
   card) has been rendering **unstyled** on every company.

Fix: wrap it, and add a structural guard that every CSS constant concatenated
into a page body is `<style>`-wrapped — the defect is the asymmetry between
four siblings, so the guard belongs on the set, not on this one constant.

## D2. Raw enum constants shown to the customer on `/evidence` (CRITICAL, §13)

From Meta's live `/evidence`:

> "Search coverage: **DISCOVERY_PARTIAL** · reading: **HAVE_INDEPENDENT**"
> "Independent voice: yes · Relevance: **DIRECTLY_RELEVANT** · Counts as
> corroboration: yes"

Internal enum values rendered as customer copy. §13 names a raw-object leak a
critical defect, and this codebase has shipped one past a green test before —
the detector matched the comment explaining the enum rather than the enum.
The guard must read the rendered page, not the source.

## D3. `economic_reasoning` and `business_model` cannot measure what §15 asks

See INSTRUMENT_DEFECTS.md — these are scorer defects, not product defects, and
they need no deployment. Both are repaired against the 50 captures, not the 1.

## Predicted, from offline measurement on 11 real 10-Ks — see DEPLOY_B_CANDIDATE_C1.md

`what_is_sold` and `revenue_basis` both match mid-sentence relative clauses,
glossary entries and revenue-recognition policy. Sentence-anchoring repairs 4
of 11 outright and turns 4 wrong answers into honest empties.

---

## D4. Substitutes come from a sector prior, not from the company (CRITICAL, §15)

MEASURED across 22 live companies on `589518f`: **8 distinct substitution
clauses for 22 companies**, and they cluster by sector, not by business.

| clause | n | companies |
|---|---|---|
| "rental and used equipment in place of a new purchase" | 8 | NVIDIA, Broadcom, Qualcomm, Micron, Intel, AMD, Texas Instruments, Applied Materials |
| "non-bank providers reaching the customer directly" | 5 | Bank of America, JPMorgan, Goldman Sachs, Visa, Morgan Stanley |
| "automation absorbing the task itself" | 4 | Adobe, Microsoft, ServiceNow, Shopify |
| "another surface holding the same attention hour" | 2 | Alphabet, Meta |

Only Amazon ("publishers, distributors and the shopper buying the same basket
somewhere cheaper") and Salesforce ("cloud computing application service
providers and AI-native companies") received substitutes derived from their
own evidence.

**And one of them is economically wrong.** "Customers can substitute rental
and used equipment in place of a new purchase" is a capital-equipment
substitution. It is defensible for Applied Materials, whose customers really
can buy used fab tools. It is wrong for NVIDIA, Broadcom, Qualcomm, Micron and
Texas Instruments: nobody rents second-hand DRAM or GPUs instead of buying
chips. §13 names "unrelated competitors presented as direct" a critical
defect, and this is its substitution half.

The NAMED-RIVAL half of the same dimension is working and is genuinely
company-specific — Qualcomm gets "HiSilicon and MediaTek", Visa gets "UnionPay
and WeChat Pay", Cloudflare gets "on-premises network hardware vendors, point
solution vendors and network security vendors". So the repair is not to the
competition producer as a whole; it is to the substitution clause, which
reaches for a sector prior when the filing did not yield one.

This is the same failure this codebase has recorded before under "class prior
must not be the answer", where per-class business-model text made five
software companies byte-identical. The prior is being used as the answer
rather than as the fallback, and a wrong prior is worse than an absent one:
an executive reading "your customers can rent used equipment instead" about a
memory business learns something false.

Smallest repair: derive substitutes from the subject's own filing (its
competition and risk-factor language names them), and where none is found,
say so rather than substituting the sector's. `competition` scores 6 on 18 of
22 companies today; this clause is why.

---

## R3 — progressive first-useful result: BUILT, MEASURED, NOT SHIPPED

PERFORMANCE_GATE fails and the mechanism is exact: `/progress` releases the
reader only when `result_readiness().opens_result` is true, that requires a
composed result, and `_run_analysis` composes only after EVERY approved source
has been fetched. Measured over 49 live companies: p50 165s, p90 377s, p95
480s, fastest 88s, **0 of 49 under 30 seconds**.

The repair was implemented and tested: retrieval in two waves, the first being
the subject's own SEC filing plus its own front page (`fetch_approved` already
accepts an explicit `candidate_ids` subset and is idempotent per
source+content), an early bounded composition between them, then the full
fetch and the final composition. 10 focused tests, all 10 red against
`589518f`.

**It is not in this deploy, deliberately.** Running it against the full suite
turned two existing tests red —
`test_repeated_same_day_analysis_never_500s` and
`test_arbitrary_company_autoruns_recommended_sources` — both with
"analysis worker did not finish", because a second composition roughly doubles
the most expensive step in the worker. That is the honest trade the design
intends for the READER, but it also means total completion time grows, and I
could not establish from the captures what the approved-set-size distribution
is, so any threshold for "when is the split worth a second composition" would
have been a guess.

Shipping an unmeasured change to the core analysis worker on the last
available deploy, against a build that currently runs 50 consecutive live
analyses with zero 500s, is a worse trade than reporting the gate as failed.

Carried forward, complete:

* patch: `R3_progressive_first_useful.patch`
* tests: `R3_test_first_useful.py`

What the next cycle must measure FIRST: the distribution of approved-set size
and the wall-clock split between discover / fetch / compose. If compose is a
large fraction of the 165s, two compositions is the wrong shape and the early
reading needs a cheaper producer than the full one.

---

## D5 — recommendation collapse: cause located, NOT repaired this session

MEASURED over the 50-company baseline. 18 of 50 briefs render the bounded
fallback sentence:

> "What to do now: move on **{LEVER}** at a size that can be reversed inside
> one planning cycle, and instrument it so the result is readable before the
> next commitment."

10 distinct levers across those 18, and they cluster by sector, not company:

| lever | n | companies |
|---|---|---|
| pipeline and development priorities | 4 | Eli Lilly, Johnson & Johnson, Merck, Pfizer |
| pricing of assets and liabilities | 3 | Bank of America, JPMorgan, Morgan Stanley |
| production rate | 2 | Deere, GE Aerospace |
| capital programme and sequencing | 2 | NextEra, Union Pacific |
| pricing and promotion | 2 | Nike, PepsiCo |

Four pharmaceutical companies with materially different economics — Lilly's
incretin concentration, J&J's MedTech half, Merck's Keytruda dependence,
Pfizer's post-COVID base — receive a byte-identical recommendation. By §5's
test (same sentence, same action, same mechanism, economically different
companies) that is a defect.

### Where it comes from, and why it is not a one-line fix

`strategic_read._bounded_action` already has the right precedence:

```python
action_now = recommended or _action_now(profile, selection, lever)
```

`recommended` is `run_decision.recommended_next_move` — derived from THIS
run's evidence — and it wins whenever it exists. It exists for 32 of 50
companies. The collapse is entirely in the fallback taken by the other 18.

The obvious repair looked like a one-line inversion: `_action_now` re-reads
`profile.primary_management_levers[0]` and discards the `lever` it was handed,
which is backwards from the rule stated three lines above it. But the handed
`lever` is `_ARCHETYPE_LEVER.get(archetype)` — **also a class prior**. Every
input available to this fallback is class-keyed, so inverting the precedence
would swap one sector constant for another, change the wording, and close
nothing. That is a cosmetic change dressed as a repair, and it would have
looked like progress in the next matrix.

### The smallest real repair, for the next cycle

Raise the hit rate of `run_decision.recommended_next_move` — the only
company-derived action in this path — rather than improving the fallback.
That is a decision-producer change and needs its own measurement: which of the
18 runs reached no `recommended_next_move`, and what was missing from each.

Until then the fallback should say what it is. It currently reads as a
recommendation derived from this company; it is a reading of its business
model. This codebase already distinguishes those two elsewhere ("read from the
business model, not retrieved") and the same honesty belongs here.

NOT changed in this session: it alters customer-visible copy on 18 of 50
companies and there is no deploy left to prove it live.

---

## D6 — named alternatives include things that are not companies (found, NOT repaired)

Found on Amazon during the D4 reproof, and confirmed **pre-existing**: the
line is byte-identical on `589518f` and `336311b`, so D4 did not cause it.

> "The alternatives this company's own evidence names are **Joint Venture**.
> The closest is **Joint Venture** — competes for the same buyer with a
> comparable product."

"Joint Venture" is a corporate-structure noun lifted from Amazon's own filing,
presented to a chief executive as Amazon's closest competitor.

Prevalence across the baseline 50, counting every rendered
"own evidence names are …" line:

| extracted | company | verdict |
|---|---|---|
| Conagra Brands, Hormel Foods, Keurig Dr Pepper, Link Snacks | (snacks) | good |
| Keurig Dr Pepper Inc, Danone S… | (beverage) | good, truncated |
| Visa Direct, Visa B… | Visa | own products, truncated |
| Joint Venture | Amazon | **corporate structure** |
| The buyer | ×3 | **a role, not a firm** |
| Permian Basin | Exxon | **a place** |
| Sierra Nevada Corporation, L… | (aero) | good, truncated |
| LM | (aero) | **fragment** |

So roughly six of the ten rendered lines carry a degraded name — a generic
noun, a role, a region, or a truncation — and two are genuinely good.

§13 counts "unrelated competitors presented as direct" a critical defect, and
"the closest is Joint Venture" meets it.

NOT repaired here, deliberately. The obvious fix is a stoplist of generic
nouns, and this session has already shown twice why that is the wrong shape:
a stoplist let "Conditions" through as a proper noun in the scorer, and a
sector table put used equipment in front of chip buyers. The right
discriminator is the same one the scorer needed — whether the token is a NAME
rather than a title-cased common-noun phrase — and that needs its own
measurement over the 50 rendered lines plus a positive control that keeps
"Keurig Dr Pepper" and "Hormel Foods".

Smallest next repair: in the named-alternative extractor, require the
candidate to appear elsewhere in the filing as a grammatical subject or with a
corporate suffix, and drop it otherwise. Prevalence ~6/50; impact is high per
occurrence because it lands on the competition dimension a reader trusts most.

---

## D4 LIVE REPROOF RESULT — the gate discriminates, and Qualcomm is a TRUE POSITIVE

Measured on the deployed build, same journey, before (`589518f`) and after
(`336311b`), counting every surface that renders the clause:

| company | before | after | correct? |
|---|---|---|---|
| NVIDIA | intro, slides | **none** | yes — its filing names no second-hand mechanism |
| Micron | intro, slides, full, brief, story | **none** | yes — same |
| QUALCOMM | intro, slides | intro, slides | **yes, and this is the gate working** |

Qualcomm looked at first like a partial failure. It is not. Its own 10-K says,
three separate times, that a shift in consumer demand "in favor of
**refurbished or secondhand devices**" would reduce its revenues and margins.
Qualcomm's chips go into handsets, and second-hand handsets displacing new
ones is a real substitution the company itself names as a risk. The gate found
that evidence and kept the alternative, which is exactly what it was built to
do — the difference between Qualcomm and Micron is a fact about their filings,
not a bug.

Micron's alternatives section was checked for over-correction and is
byte-identical before and after apart from the removed clause: it still
carries "Keeping the existing fleet running longer", correctly labelled "Not a
company — the customer doing nothing, read from how this business model works
rather than from a retrieved source". The dimension was not emptied.

### Residual, smaller defect: the retained clause borrows template wording

Qualcomm's substitution is real but renders as "rental and used equipment in
place of a new purchase" — capital-equipment language inherited from the
`DESIGN_AND_MANUFACTURE` row. The company's own words are "refurbished or
secondhand devices". The mechanism is right and the sentence is not its own.

Smallest next repair: when the gate finds the evidence, render the clause from
the matched span rather than from the table's phrasing — the same principle
already applied elsewhere in this codebase, that the subject's own words win
over the composed fallback. Low severity: the claim is now true for every
company that carries it; only the phrasing is generic.
