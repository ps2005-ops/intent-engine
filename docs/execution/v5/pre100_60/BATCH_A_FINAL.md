# Batch A — second pass, and the economic-actor repair

`START_SHA` a9b4857 · `FINAL_SHA` d0b81f8+ · `DEPLOYED` c719979 (d0b81f8 pushed)

## What this pass was for

Close `NON_ACTOR_AS_COMPETITOR` — the last live competitive defect from the
first pass, where Meta's introduction named **S&P**, Walmart's named
**Medicare Part D**, and Caterpillar's named **America Leasing** as the
companies contesting their markets.

## The defect was three defects

Re-measured offline against the same SEC filings the runs read. The cause is
not a missing stoplist; this module's own history records three live rounds
proving word filters cannot separate a filing heading from a company name.

**1 — the "sentence" is a list.** Meta's evidence blob is 2,262 characters
and fifteen bullets. `S&P` sits at character 1,670, inside

> the inclusion, exclusion, or deletion of our stock from any trading
> indices, such as the S&P 500 Index

and the word *competitors* that admitted the whole blob is at character
1,400, in a different bullet. The excerpt quoted to the reader was characters
0–400 — a third bullet, about income tax. Walmart is the same shape: 2,677
characters, seventeen semicolons, `Medicare Part D` inside *"changes in the
scope of or the elimination of Medicare Part D or Medicaid drug programs"*,
and the contest cue five clauses earlier.

**2 — the contest has an owner.** Caterpillar's filing says

> Cat Financial's competitors include Wells Fargo Equipment Finance Inc.,
> Banc of America Leasing & Capital LLC, BNP Paribas Leasing Solutions
> Limited, …

Those firms contest a **captive lender** for a customer's financing, not
Caterpillar for a customer's excavator. Reading the possessor of the verb is
what separates six financiers from Komatsu and Deere.

**3 — selection was alphabetical.** Caterpillar's filing names **43** firms —
Komatsu, Deere, Cummins, Liebherr, Sandvik, Volvo CE. `find_competitors`
sorted by `(relevance, name)` and took four: Alstom, America Leasing, BNP
Paribas, Baker Hughes. The company's real rivals were in the evidence and
lost to the alphabet. This was the largest single cause of a wrong direct
competitor on filings that name their rivals well.

## The repair

`executive/competitive_qualification.py` asks one question — *what economic
need could the customer satisfy with this instead* — and answers it from the
clause the name is in, the noun that governs it, and the possessor of the
verb. Thirteen states; only `DIRECT_COMPETITOR`, `SUBSTITUTE` and
`ADJACENT_THREAT` may make a competitive claim, and only the first two may
say "contested directly by".

**Nothing is deleted (§6).** Each refusal carries the section it belongs
under, the run collects them, the ground carries them, and the Full Analysis
prints them. The lender rule is keyed on what the **subject** sells, never on
the candidate's name — a bank's rivals are banks, and the matrix's negative
control refuses any version that takes them away.

Two more defects were found by this pass and fixed:

* **§8 the sentence contract.** One frame served every kind of alternative,
  so a company with no named firm read *"contested most directly by The
  advertiser spending the budget on its own channels"*. The kind now decides
  the verb.
* **One run may not say two things.** A run that retrieved nothing showed the
  failure page on `/full` and `/slides` and a confident analysis on the other
  four steps — including a business model read off the SIC code alone. The
  check lived in two page functions instead of the guard all six share.
  `/story` needed a second fix: it had kept its own ownership check.

## Live verification

| company | retrieval | result |
|---|---|---|
| **Caterpillar** | **OK** | *"contested directly by CNH Industrial N.V and Deere Construction, and customers can substitute independent service and will-fit parts"* — and, in the Full Analysis, *"Customer financing and purchase enablement: America Leasing, Capital LLC, BNP Paribas Leasing Solutions"* |
| **Exxon** | **OK** | Agnico Eagle gone; `COMMODITY_PRODUCER` correct |
| **Meta** | **OK** (re-run, paced) | S&P is **absent from the introduction** and appears once in the Full Analysis under *"Market, index and capital-market context: S&P"*; the model reads *"attention resold to advertisers: revenue is an auction price per impression"* |
| Amazon, NVIDIA, JPMorgan, Walmart, Lilly | `BLOCKED_EXTERNAL` | SEC EDGAR answered **HTTP 429** to every source during the back-to-back wave |

**Caterpillar is the decisive case**: it carries all three sub-defects, and
all three are gone from the deployed page while the real rivals survive.
**Meta closes the third target**, and closes it the way §6 asked — S&P is not
suppressed, it is filed under capital-market context, where it is true.

## The block, and why it is not a product number

SEC EDGAR rate-limited the preview's egress. The same primary-document URLs,
with the **same production User-Agent**, answered 200 from a laptop in the
same minutes — so it is a shared cloud IP under sustained automated access,
not a defect and not a demo-quota block.

**It is NOT a cadence limit.** That was this session's first conclusion and
a paced wave falsified it. Every outcome observed, by position:

| company | position | result |
|---|---|---|
| Caterpillar | single, and 1st of a 7-company wave | **OK** (2/2) |
| Exxon | **7th and last** of the 7-company wave | **OK** |
| Meta | 1st of two waves / single paced | 429, 429, **OK** |
| Walmart | 2nd of two waves / **1st of a 6-minute-paced wave** | 429 ×3 |
| NVIDIA | single / 3rd of a wave / **2nd of a paced wave** | 429 ×3 |
| Amazon, JPMorgan, Lilly | 4th–6th of the wave | 429 |

Exxon succeeded **last** in an unpaced wave and Walmart failed **first** in a
paced one, so position in the wave does not predict the outcome. Three
companies have ever retrieved; five have never retrieved in any position.
**The correlation is with the company, not the cadence.**

**The size hypothesis is dead too.** Measured against EDGAR, bytes fetched
per run:

| company | live | candidates | total fetched |
|---|---|---|---|
| Caterpillar | **OK** | 4 | **13.74 MB** |
| Exxon | **OK** | 4 | **11.58 MB** |
| Meta | 1 of 3 | 4 | 5.73 MB |
| Walmart | never | 4 | 9.53 MB |
| Amazon | never | 4 | 5.56 MB |
| Lilly | never | 4 | 5.24 MB |
| NVIDIA | never | 4 | **4.59 MB** |
| JPMorgan | never | **0** | — |

The two companies that always retrieve fetch the **most** bytes; the one that
never retrieves fetches the **fewest**. Request volume is identical at four
candidates each. Neither cadence, nor volume, nor size explains it — and all
eight URLs answer 200 from a laptop with the production User-Agent.

### What does explain it, and it is in our code

`fetch.py` classifies a 429 as **`retryable=True`** and then returns. Nothing
re-attempts the URL. The flag is consumed at the webapp layer, which offers
the **human** a retry button.

So against an intermittent shared-IP throttle — roughly one attempt in three
succeeding, which is what fifteen observed attempts show — the run makes ONE
attempt per source, gives up, and asks a chief executive to press retry. That
accounts for every row above without needing a story about which companies
SEC dislikes: Caterpillar and Exxon got lucky twice, Meta once in three, and
the rest never got a second draw.

**The fix is a bounded in-run backoff for a transient status**, not pacing
and not a cache. It is a change on the critical path of every run and it is
deliberately not being made at the end of this session: it needs its own
live measurement across the cohort, which is exactly what it would unblock.

`JPMORGAN_ZERO_CANDIDATES` is a separate, unrelated defect found by the same
probe: `filing_candidates` returns **0** for CIK 19617 while every other
company returns 4. Nothing was retrieved because nothing was proposed, so
its 429s were never even the reason.

## Scoring

`§14` forbids scoring a surface that was not read. Three of eight companies
produced a readable executive surface this pass, which is not enough to
freeze a twenty-dimension Batch-A mean, so **no mean is reported**. The
harness that collects the twenty dimensions and the ten board questions
(`scripts/pre100_batch_journey.py`, `scripts/pre100_scorecard.py`) is built
and was exercised; it is retrieval that is missing, not measurement.

## Counts

`SYSTEMIC_DEFECTS_FOUND` 4 · `FIXED` 4 · `REGRESSIONS` 0 ·
`WRONG_COMPETITORS` 0 of 3 scoreable · `WRONG_ATTRIBUTIONS` 0 ·
`BREAK_PROOFS` 25/25 · `KNOWN_SEV1` 0 · `KNOWN_DEMO_BLOCKING_SEV2` 0

`NEXT_NOT_RUN_COMPANY` Walmart (retrieval-blocked in the wave) ·
`NEXT_NOT_RUN_BATCH` Batch A rescore once SEC clears, then Batch B

---

## What the scoring pass found: `TEMPLATE_COLLAPSE`, SEV2, open

Three companies produced a readable executive surface, so the ten board
questions (§29) were asked of all three through the product's own Q&A route.

**Nine of ten answers are byte-identical across Meta, Caterpillar and Exxon**
once the company name is masked and the page chrome after the answer is
stripped. Only *"What would prove this wrong?"* differs.

The shared answer is an industrial capacity thesis:

> Yes — on balance the evidence supports that **committing capital to
> capacity ahead of uncertain demand** …

> **Utilisation, order books and take-or-pay terms are not public.**

Meta is an advertising auction and Exxon is a commodity producer. Neither has
an order book, and neither is deciding how much manufacturing capacity to
commit. The suggested follow-ups collapse the same way — all three companies
are offered *"How is this transition similar to Memory and sensor fabrication
cycles?"*.

**This is a selection defect, not a prose defect**, and the same shape this
codebase has recorded before: the central decision question is collapsing to
one template across business-model classes, and every downstream answer
restates it. `business_model_class` is the field that should separate them
and evidently does not reach this producer.

### Measured, and deliberately not repaired here

§33 says collect the distribution before clustering, and three companies is
not a distribution — a repair aimed at three would be aimed at whichever
template these three happen to share. It needs the paced Batch-A rescore
first, which is also what unblocks the twenty-dimension mean.

`COMPANY_SPECIFICITY` (share of executive sentences carrying a
company-specific token or figure): Meta **0.77**, Caterpillar **0.27**, Exxon
**0.17**. The two low ones are consistent with the collapse above rather than
independent of it.

### A second finding inside the first

*"Who's the real competitor?"* answers **"No competitor has been selected for
this company from the evidence"** — on the same Caterpillar run whose
introduction reads *"contested directly by CNH Industrial N.V and Deere
Construction"*. That is a cross-surface contradiction of the same class as
the failed-run one closed this session.

Narrowed but NOT concluded: `_route_answer` does fall back to
`_from_read("competitor", read)`, the call site does pass the read, and
`puts_a_strategy_forward` is true for a bounded read — so the remaining
candidates are `level4_competition` being empty on the read instance Q&A
builds, or `_ground` having thrown on that request and been swallowed. It is
recorded at this depth rather than guessed at.
