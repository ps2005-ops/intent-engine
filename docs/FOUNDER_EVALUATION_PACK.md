# Founder evaluation pack

Everything below is ready to run. **Nothing in it has been run.** No founder,
operator or executive has seen any output from this product, so every claim in
the programme ledger about quality is my judgement and the critic's, not a
user's.

That is the gap that matters now. The engineering is not the bottleneck.

---

## 1. What is being tested

Not "is this good". The question is narrower and harder:

> Would this change a decision a founder was about to make, in a way a generic
> AI assistant would not?

## 2. Blind protocol

For each company, prepare four artefacts with **no product labels, no
branding, no citation markers**, in randomised order:

| Arm | Source |
|---|---|
| A | Founder Intelligence — the daily view + deck |
| B | ChatGPT, prompt: *"Analyse this company's strategy, competitive position, risks and likely leadership priorities using public information."* |
| C | Claude, same prompt |
| D | Perplexity, same prompt |

Strip citation markers from A — they are a visible tell, and a reviewer who
spots which arm is "the tool" stops evaluating and starts comparing brands.

**Reviewers:** 8–12, mixed. Target at least 3 who have sat on a board and at
least 3 operating founders. Each reviewer sees one company only, all four arms.

## 3. Questions (in this order)

Ask about the artefact in front of them before asking them to compare.

1. What is the single most useful sentence here?
2. Did anything change how you were thinking about this company? What?
3. Which claim felt generic — true of any company in this industry?
4. Which claim felt unsupported?
5. If this company were yours, what would you do differently on Monday?
6. Which one decision here would you take to your next leadership meeting?
7. What is missing that you would need before acting?

Then, across all four:

8. Which one changed your thinking most?
9. Which would you pay for? What would you pay?
10. Which would you put in front of a board?
11. **Did any of them identify a decision you had missed?** ← the whole
    programme rests on this one
12. Which felt like it was written by software?

## 4. What counts as passing

The stop condition is not "A wins". A generic assistant writes fluently and
will often read better. The bar is:

- **≥60%** of reviewers name arm A on Q11 (identified a missed decision)
- **≥60%** name arm A on Q8 (changed their thinking most)
- **Zero** unsupported-claim reports on arm A that turn out to be real
  fabrications — one invented fact is worse than losing on every other axis,
  because it removes the reason to trust any of it
- Arm A's genericity complaints (Q3) **fewer** than every other arm

If A wins on fluency and loses on Q11, the programme has failed and should not
ship. Q11 is the product.

## 5. Companies

Use a spread so a single sector's luck cannot carry the result: Sony
Interactive Entertainment, Palantir, Shopify, Nintendo, one regional bank, one
healthcare developer, one industrial manufacturer, one private company with
thin evidence.

Include the thin-evidence company deliberately. Arms B–D will produce a
confident-sounding answer anyway. Arm A should return `EVIDENCE_LIMITED` and
decline. **A reviewer preferring the confident wrong answer is the most
important thing this study can discover**, and it is not obvious in advance
which way that goes.

## 6. What to record

Per reviewer, per arm: the sentence they picked (Q1), verbatim; every claim
flagged generic or unsupported, verbatim; and their Q11 answer verbatim.

Verbatim matters. Aggregated scores will say A scored 4.1 and C scored 3.8,
which is unactionable. "The only thing I hadn't thought of was the incentive
conflict between studios and the subscription business" is actionable.

## 7. Then what

Every claim a reviewer flags as generic becomes a genericity-gate test case.
Every claim flagged unsupported becomes a critic test case. Every section no
reviewer mentions in Q1 across all companies is a candidate for deletion —
measure attention, not coverage.
