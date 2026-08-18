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
| Meta, Amazon, NVIDIA, JPMorgan, Walmart, Lilly | `BLOCKED_EXTERNAL` | SEC EDGAR answered **HTTP 429** to every source |

**Caterpillar is the decisive case**: it carries all three sub-defects, and
all three are gone from the deployed page while the real rivals survive.

## The block, and why it is not a product number

SEC EDGAR rate-limited the preview's egress. The same primary-document URLs,
with the **same production User-Agent**, answered 200 from a laptop in the
same minutes — so it is a shared cloud IP under sustained automated access,
not a defect and not a demo-quota block.

**This is the binding constraint on the 60-company programme**, not a
nuisance: the gauntlet's own throughput is what trips the fair-access
throttle. A 60-company run needs a retrieval cache or a backoff before it can
be attempted live, or six of every eight companies will be unscoreable.

## Scoring

`§14` forbids scoring a surface that was not read. Two of eight companies
produced a readable executive surface this pass, which is not enough to
freeze a twenty-dimension Batch-A mean, so **no mean is reported**. The
harness that collects the twenty dimensions and the ten board questions
(`scripts/pre100_batch_journey.py`, `scripts/pre100_scorecard.py`) is built
and was exercised; it is retrieval that is missing, not measurement.

## Counts

`SYSTEMIC_DEFECTS_FOUND` 4 · `FIXED` 4 · `REGRESSIONS` 0 ·
`WRONG_COMPETITORS` 0 of 2 scoreable · `WRONG_ATTRIBUTIONS` 0 ·
`BREAK_PROOFS` 25/25 · `KNOWN_SEV1` 0 · `KNOWN_DEMO_BLOCKING_SEV2` 0

`NEXT_NOT_RUN_COMPANY` Meta (retrieval-blocked) ·
`NEXT_NOT_RUN_BATCH` Batch A rescore once SEC clears, then Batch B
