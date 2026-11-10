# Window 1 — three companies, deployed UI, `0420fb0`

JPMorgan, Walmart, NVIDIA. Full journeys captured (18 routes each), all ten
board questions asked through the live `/conversation` route.

## Reliability — clean

| company | auto-advance | seconds | Q&A |
|---|---|---|---|
| JPMorgan | yes | 159 | 10/10 |
| NVIDIA | yes | 249 | 10/10 |
| Walmart | yes | 70 | 10/10 |

3/3 auto-advanced, 0 false failures, 0 manual recoveries, 30/30 answered.
`transient_retry_count` **NOT_MEASURED** — no guest-visible route exposes it.

## Template collapse: 10/10 → 1/10

Same instrument on both sides.

| | identical across companies |
|---|---|
| before, `58ac7ef` (Meta, Caterpillar) | **10 / 10** |
| after, `0420fb0` (JPMorgan, NVIDIA, Walmart) | **1 / 10** |

Three different classes with three different pattern-set sizes (11 / 10 / 7)
now produce nine different answers. `capacity_ahead_of_demand` appears only
for NVIDIA, which genuinely commits capital to physical capacity.

### The instrument was wrong again, and the wrong number was the flattering one

The first run of this measurement reported **0/10** — a clean sweep. It was
false. `"Why this matters"` and `"Low, by construction"` are boilerplate tails
appended after the answer; they vary by run rather than by company, and they
made three **identical** answers to *"Who's the real competitor?"* score as
three distinct ones.

Four instrument errors in this one measurement now, and this is the first that
would have been reported as a **success**:

| method | said | why wrong |
|---|---|---|
| naive similarity | 0.915 | chrome-inflated |
| mask name, byte-equality | 0/10 | chrome-deflated |
| mask name variants from a `set` | 0/10 | iteration order left `" Inc."` |
| truncate at first chrome marker | 0/10 | **boilerplate tails survived** |
| **+ truncate at boilerplate tails** | **1/10** | the number |

## The one that remains — and it is a cross-surface contradiction

*"Who's the real competitor?"* is identical across all three:

> No competitor has been selected for this company from the evidence.

While step 1 of the same run, for the same company, says:

| company | introduction | Q&A |
|---|---|---|
| JPMorgan | *"contested directly by **banks and brokerage firms**"* | no competitor selected |
| NVIDIA | *"contested directly by **Huawei Technologies Co and Open-source AI**"* | no competitor selected |
| Walmart | *"contested directly by **social commerce platforms and delivery services**"* | no competitor selected |

**3 of 3.** A chief executive is told who contests their market, then told one
click later that nobody has been identified. This fails the §34 bar of zero
cross-surface contradictions, and it is the most demo-damaging defect left.

### Settled by execution, and it was none of the obvious candidates

Three mechanisms were proposed and two were wrong. Recording all three,
because the wrong ones were plausible and one was believed by both sessions.

**Rejected — "`level4_competition` is empty on the read Q&A builds."** My own
first guess. All three reads render `Our read: Bounded`, and
`puts_a_strategy_forward` returns True for `READ_BOUNDED`, so the gate was
open on every run.

**Rejected — "step 1 was overclaiming manifest peers."** A parallel session
proposed that `_position` fell through to the manifest's class-level peers and
rendered them with an evidence verb, making Q&A the accurate surface. Checked
against `profile_for`:

| company | manifest peers | what step 1 rendered |
|---|---|---|
| NVIDIA | AMD, Applied Materials, Broadcom, Intel | *Huawei Technologies Co and Open-source AI* |
| JPMorgan | Bank of America, Bank of Montreal, Blackstone | *banks and brokerage firms* |
| Walmart | Couche-Tard, Costco, Dollarama | *social commerce platforms and delivery services* |

**Zero overlap.** And an offline ladder probe emits Walmart's exact strings at
`CONTESTED_CATEGORY`, quoted from Walmart's own filing — the ladder does emit
categories; that is rung 5. Step 1 was right and Q&A was wrong.

**The actual cause**, executed against `qa._route_answer`:

    decision["competitors"] = [{"name": "Huawei"}]   -> "No competitor has been selected..."
    decision["competitors"] = ["Huawei", "Open..."]  -> "Huawei; Open-source AI"
    decision["competitors"] = []  + read has rivals  -> "Huawei Technologies Co: It matches..."

```python
value = decision.get(field)              # list of dicts -> TRUTHY
if not value or (... and not any(value)):
    fallback = _from_read(...)           # SKIPPED, value is truthy
if isinstance(value, (list, tuple)):
    if isinstance(value[0], dict):
        return absent, name              # "No competitor has been selected"
```

A **populated, structured** list renders as "none", and the fallback that
would have answered correctly is skipped **precisely because the data is
there**. That is why it reproduced 3 of 3 across three classes, three ladders
and three Bounded reads: it depends on none of them, only on the composed
decision carrying rows rather than strings.

Repaired at the shape rather than at the question — the branch serves every
intent whose field holds rows — with a fall-through to the read before the
absent copy is ever reached.

**The lesson worth keeping:** returning "absent" for present-but-unformattable
data makes a true statement look like an honest gap. That is strictly worse
than an error, because nothing looks wrong.

## A second observation about the differentiation

Some of the nine differing answers differ by **withholding**, not by content:
Walmart's *"what should management do?"* is a refusal, JPMorgan's is a
deflection to another surface, and only NVIDIA states a thesis. Distinct
answers are necessary but not sufficient for §22 — the bar is materially
distinct *strategic reads*, and two of three currently decline to give one.
Recorded as measured, not scored as a pass.
