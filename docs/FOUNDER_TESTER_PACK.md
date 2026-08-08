# Founder demo — external tester pack

**Human validation has NOT been performed.** This pack is everything a tester
needs; running it is an owner action. No tester has seen this build and no
result below is filled in.

## For the tester (no technical background needed)

You are looking at a research tool for founders and operators. Spend **60
seconds** on the first screen, then stop and answer from memory.

### The seven questions

1. What does the company do?
2. What changed?
3. Why does it matter?
4. What is the biggest decision this affects?
5. What should be done or watched next?
6. How certain is this analysis?
7. What information is missing?

If you cannot answer one, say so — that is the result we need.

### Then

8. What did you learn that you did not already assume?
9. What surprised you?
10. What was confusing?
11. What did you skip or ignore?
12. Would you come back weekly?
13. Did this save you time? Roughly how much?
14. Did it tell you anything beyond what a generic AI chat would?
15. Which screen mattered most?
16. Would you pay for this result? What would you pay?

## Three representative companies

| # | shape | what it is testing |
|---|---|---|
| 1 | public, information-rich | financial and market context, decision framing |
| 2 | private / mid-size | product and customer evidence without filings |
| 3 | marketing-only site | that a thin company still gets something useful |

Case 3 is the one to watch. The previous version returned a refusal. If a
tester says "it told me nothing", that is a failure regardless of how the other
two went.

## What to measure

| measure | how |
|---|---|
| time to first useful insight | stopwatch from page load to the tester saying something concrete |
| comprehension | how many of the seven they answer unaided |
| action recall | can they name one thing to do next, unprompted |
| perceived usefulness | 1–5 |
| trust | 1–5, and *why* |
| reading completion | did they scroll past the first screen at all |
| return intent | yes / no / maybe |

## Recruiting

At least one founder or small-business owner, one non-technical general user,
and one operator or business student. Three is enough to find the obvious
failures; it is not enough to conclude the product works.

## Recording results

Do not summarise into a score. Record what each person said, including the
parts that contradict each other.

---

## Running it against this build (added for the v3 interface)

### Starting the tester on the founder brief

The analysis form is on the landing page: company name, website, consent. When
it finishes, **the app currently lands on the presentation deck** at
`/runs/<id>/slides`, not the founder brief. Until that default changes, send
the tester to `/runs/<id>` yourself and start the 60-second clock there — the
seven questions above are about the founder brief, and timing them on the deck
measures a different screen.

### The three results to prepare

| # | shape | prepare it as |
|---|---|---|
| 1 | rich public company | see the caveat below — a genuinely rich result cannot be produced live in an environment where `/readyz` reports `strategic_reasoning: false` |
| 2 | private / small company | any small company with a real site |
| 3 | limited result | a JS-rendered site; these reliably produce the limited page |

**Check `/readyz` before you start.** If `strategic_reasoning` is `false`, every
run takes the limited path regardless of the company, and the tester will be
judging the limited experience three times over. That is worth testing, but do
not record it as a verdict on the rich experience.

### Exploring the layers, in this order

1. `/runs/<id>` — the founder brief. Sixty seconds, then the seven questions.
2. `/runs/<id>/dashboard` — ask which tiles they actually read, and whether an
   "Unavailable" tile felt honest or broken.
3. `/runs/<id>/story` — ask them to reach a section from the sticky nav.
4. `/runs/<id>/brief` — the executive brief. **Ask directly: did this repeat
   the first screen?** Repetition is the failure this layer exists to avoid,
   and a tester will excuse it unless asked.

### Three Q&A prompts

Use these verbatim, on the same run:

1. "What does this company do?"
2. "What is the biggest risk here?"
3. "What should I do next?"

Then ask: **did any answer contradict the brief?** On a limited result the
assistant must refuse a strategic conclusion rather than supply one. If it
offers a confident direction the brief withheld, that is the most serious
failure in this pack — record it verbatim.

### Additional things to record

| measure | how |
|---|---|
| repetition | which layers felt like the same text twice, in their words |
| generic-AI comparison | show the same company to a generic chat assistant; ask which they would rather have and why |
| willingness to pay | a number, and what it is anchored on |

Nothing in this file is filled in. No human has run it.
