# What the specificity instrument was actually measuring

Run before any of its numbers were reported, because this programme has twice
had an instrument invent a uniform defect and be believed.

The first pass over the 48 existing captures reported **1393 byte-identical
pairs**. Four fields carried almost all of it. Each was checked against the
captured text before being called a defect.

| field | identical pairs | verdict |
|---|---|---|
| `step6` | 1035 | **INSTRUMENT ARTIFACT** |
| `recommendation` | 166 | **INSTRUMENT ARTIFACT** |
| `biggest_risk` | 66 | **INSTRUMENT ARTIFACT** |
| `board_answer` | 4 + 160 near | mostly the Q&A refusal defect, now repaired |
| `business_model` | 70 | REAL, and already repaired — every pair is a capture predating the fix |
| `central_question` | 37 | **REAL** — class-level, unrepaired |
| `competitors` | 15 | **REAL** — class-level, unrepaired |

## Why three of them were artifacts

**`step6`** — the cue matched the section's opening, which is identical on
purpose:

> "What this becomes with your own context. Everything you have just read was
> built from public evidence alone."

The company-specific material begins in the next sentence. 1035 of a possible
1128 pairs is 92%, and a defect that uniform is nearly always the instrument
rather than the product.

**`recommendation`** — the cue's first alternative, `The choice:`, matches a
constant framing line. The substantive sentence is the one after it, and it is
specific:

* Alphabet — "is a measurable and growing share of orders originating from
  AI-agent surfaces rather than human browsing?"
* Amazon — "segment disclosure showing no material inter-segment revenue"

**`biggest_risk`** — the cue matched `_LIKELIHOOD[SUBSTITUTE]` in
`competitive_ground.py`: "the risk is that they are not responding to us at
all". That is a correct constant about a KIND OF RIVAL, not a claim about the
company. Two companies whose nearest rival is a substitute should share it.

## The two that are real

**`central_question`** — American Express, Bank of America and JPMorgan Chase
receive one question verbatim:

> "what to charge, and for what, without losing more spread on assets and
> liabilities than the price gains"

This is the archetype's static text. It is the same defect as the
business-model sentence, in the field one surface up.

**`competitors`** — Chevron, Exxon Mobil and ConocoPhillips share their whole
substitution clause. The class decides the contest rather than the filing.

Both are the shape §7 names: the model class is the PRIOR and must stop being
the ANSWER. The architecture object now exists and carries the measured
particulars; these two fields do not read it yet.

## After the cues were repaired

The three artifact cues were repointed at the substantive passage. Re-measured
over the same 48 captures, unchanged product:

| field | before | after (identical) | after (near) |
|---|---|---|---|
| `step6` | 1035 | 81 | 7 |
| `recommendation` | 166 | 42 | 126 |
| `biggest_risk` | 66 | **0** | 0 |
| `business_model` | 70 | 70 | 7 |
| `central_question` | 37 | 37 | 2 |
| `competitors` | 15 | 15 | 3 |
| `board_answer` | 4 | 4 | 161 |
| **total** | **1393** | **249** | **299** |

`biggest_risk` went to zero, which is the correct answer: every one of its 66
pairs was the same rival-kind constant.

**The instrument was responsible for 82% of the finding it reported.** Nothing
about the product changed between the two rows of this table.

That is the third time in this programme an instrument has produced a uniform
result that was read as a uniform defect. The rule it argues for: when a
measurement comes back near-total, check the matched passage against the
captured text before the number is written down anywhere.
