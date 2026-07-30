# Learning log

What the engine learned, and what *building* the engine taught. Two different
things, both worth keeping.

`BOTTLENECK_LOG.md` records what was measured and what was built.
This records what is now *known* — the lessons that should be cheaper to reuse
than to rediscover.

---

## About markets

**Nothing yet, and that is the honest entry.**

Zero predictions have resolved. There is no calibration data, no sector
accuracy, no regime accuracy, and no win rate — and there will be none until
the market-evidence adapter exists and predictions start resolving. Any number
in those columns today would be manufactured.

This section stays empty rather than being filled with placeholders. An empty
section is a true statement about a young system; a populated one would be a
false statement about a smart one.

---

## About the engine

### A gate that can never pass is worse than a gate that often fails

`no_outside_source` was reported as the blocker for every readable tradable
company. It read like a hard problem about the world — companies do not have
much independent coverage. It was a `candidates[:8]` slice taking discovery
order, and discovery ranks ~30 company pages above 3 customer-voice ones.

The lesson is not "check your slices". It is that **a metric can look like a
finding about the domain when it is a finding about the code**, and the way to
tell them apart is to inspect the stage *before* the one that failed. The
candidates were there the whole time; only the retrieved documents were not.

### Distinguish "found nothing" from "found plenty and declined"

These shared one gate name (`no_strategic_reading`), which made the entire
`blocked_by` distribution undiagnosable — the two facts need opposite
responses (fix retrieval / do nothing at all). Any metric that merges a
failure with a correct refusal will eventually send work in the wrong
direction.

### Two cycles, two overturned predictions

| cycle | predicted next bottleneck | what measurement found |
|---|---|---|
| 1 | market-evidence adapter | evidence collection returned nothing; the market gate was unreachable |
| 2 | strategic-reading yield | no outside source was ever *approved*; every readable tradable died one gate earlier |

Both predictions were reasonable, drawn from real observations, and wrong.
The observation was right each time; the *inference* about the cause was not.
This is now the strongest argument in the project for measuring first — it has
a 0-for-2 record against intuition.

### Verify the instrument before trusting the reading

Cycle 1's sweep measurement forced every company onto one fixture domain.
Runs key on `(domain, user_id, as_of)`, so they collapsed into a single run and
the numbers understated the effect. The result was reported as measured and the
flaw disclosed, rather than re-run until it looked better — but the cheaper
move is to check what the harness *actually* varies before reading anything
into the output.

### Self-inflicted bottlenecks do not prove a fast loop

Both bottlenecks closed so far were introduced by the immediately preceding
cycle and caught by the next measurement. A half-life of under a day is
flattering and not yet meaningful. The number starts counting for real when a
bottleneck originates outside the code just written.
