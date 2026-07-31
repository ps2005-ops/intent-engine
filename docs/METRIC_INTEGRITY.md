# Metric integrity

> **Never optimize a metric directly. Optimize the capability the metric is
> attempting to measure.**
>
> Whenever a metric improves, ask: *did the engine actually become more
> intelligent, or did we merely become better at scoring this metric?*
>
> If those differ, the capability always wins.
>
> Every KPI is a proxy. Continuously verify that the proxy still represents
> the capability. When it stops, replace the metric. Never let the project
> optimize against a stale measurement.

This is not aspirational. Below is the worked example, run against this
project's own primary metric, on the day after it was adopted.

---

## Worked example: Learning Velocity failed its own test

Cycle 3 adopted **LV = resolvable evaluations per cycle** and moved it from 0
to 1. Good metric, real improvement — and trivially gameable.

Ten companies whose prices move *inside the noise floor*, so there is nothing
to learn from any of them:

| `MIN_ABS_RETURN` | Learning Velocity |
|---|---|
| `0.02` (shipped) | **0** |
| `0.0001` (one edit) | **10** |

Same evidence. Same reasoning. Same prices. **The only change is one constant,
and it is a constant this project controls.** LV rose 10× while the engine
learned exactly nothing — in fact it got worse, because it would now be making
ten confident predictions about noise.

That is Goodhart's law arriving on schedule: LV became a target on Monday and
stopped measuring the thing it was chosen for by Tuesday.

### What that does and does not mean

It does **not** mean cycle 3 was wrong. Closing the loop was the right build
and the metric correctly identified it. A proxy can be right about the
direction and still be unsafe as a target.

It means LV cannot be the objective function on its own, and specifically
cannot be maximised.

---

## The rule this produces

**A metric is only safe as a target if improving it is harder than improving
the capability.**

LV fails: raising it costs one character. Any metric that can be moved by
editing a threshold, widening a filter, or lowering a bar is a scoreboard, not
a measurement.

Every metric adopted here is tested against this before it is used to rank
work, and the test is written down next to it.

---

## Unmeasurable factors must stay unmeasurable

The successor to LV is **Learning Value**, weighted by resolution quality,
information gain, novelty and calibration impact. Three of those four cannot
be measured today — there are zero resolved predictions, no knowledge base,
and calibration is gated behind `A-M5` until ≥30 resolutions.

The tempting move is to implement the formula anyway with estimates. **That is
strictly worse than the metric it replaces.** A multiplicative score built from
self-assigned factors is not a measurement of anything; it is a number the
author controls completely, wearing the costume of rigour. It would fail the
test above more badly than LV does, because LV at least requires editing a
constant, whereas an estimated factor requires only an opinion.

So: factors that cannot be measured return an explicit `UNMEASURABLE` state,
and Learning Value **refuses to produce a scalar** while any factor is in it.
It reports the components it can actually measure and says which are missing.

An honest partial measurement beats a complete fabricated one. A metric that
declines to score itself is behaving correctly, not failing.

---

## Standing questions, asked every cycle

1. Did the capability improve, or only the score?
2. Could this metric be moved by editing a constant? If yes, it may inform a
   ranking but must never be the target.
3. Does the proxy still represent the capability, given what changed?
4. Which factor is doing the work — and is it the one that matters?
5. What would this metric say about a system that was obviously worse?

Question 5 is the cheapest and catches the most. LV would have scored a
noise-predicting system 10× higher than the real one.

---

## The evidence bar rises with confidence in the system

Adopted Day 12, from eleven days of measured experience.

**Architectural changes require stronger evidence than operational ones.**

| change type | examples | required evidence |
|---|---|---|
| **Operational** | a new evidence adapter, a new source, a new hypothesis, wiring a validated component | **one measured bottleneck** |
| **Architectural** | the reasoning model, the evidence model, the decision graph, the metric definitions | **all three**: (1) a measured failure in production, (2) a falsification showing the current architecture is inadequate, (3) proof the replacement resolves it *without weakening any integrity guarantee* |

The asymmetry is the point. Early on, architecture was changed almost every
cycle and each change was right — the model was genuinely wrong. That cannot
remain true indefinitely, and a system that keeps redesigning itself at the
same rate after its architecture is sound is not learning, it is churning.

Day 11 is the template for what an architectural change must look like at this
stage: a measured inadequacy (13 source/subject mismatches in 175 real
documents), a falsification attempt that failed, and a validation proving
**zero reasoning outcomes changed**. Semantic precision improved; nothing was
loosened.

**Engineering is now exceptional.** Before writing code, prove operation is
blocked AND that the blocker cannot be resolved by continuing to operate.
Otherwise the answer is to operate.

---

## The default output is uncertainty

Adopted Day 14.

**A conclusion must earn its way out of uncertainty through repeated, stable
measurement.** Until it does, the honest output is that the engine does not
know — and saying so is a result, not a failure to produce one.

### Bottleneck promotion

A stage may be promoted to **#1 bottleneck** only when **both** hold:

1. **Sufficient history** — at least 5 observations, below which no dispersion
   estimate is worth reading.
2. **Statistical stability** — coefficient of variation ≤ 40%. A stage swinging
   ±40% of its own mean is measuring market conditions, not capability.

Otherwise the output is **CANDIDATE BOTTLENECK**, with the reason stated.

### Why this replaced the calendar rule

Day 13 required three operating days. Better than one, and still wrong:

```
Day 1: 3%   Day 2: 8%   Day 3: 4%
```

satisfies "three days" and establishes nothing. **Calendar time is not
evidence.** The test is dispersion, not duration.

### The record this rule is built on

Three self-corrections, each catching a conclusion before it was optimised
around:

| day | the conclusion | what corrected it |
|---|---|---|
| 3 | a 0.359 signal, apparently significant | clustering — 64 rows in 15 windows |
| 9 | Day 8's "the adapter unlocks nothing" | my own simulation omitted the wired signal |
| 13 | "strategic-reading yield is #1" | one cycle cannot separate deficiency from conditions |

Each time the corrected answer was *less* conclusive than the original. That is
the direction an honest instrument moves in, and it is the reason this rule
exists.
