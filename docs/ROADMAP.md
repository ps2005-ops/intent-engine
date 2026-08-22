# Phase 2 roadmap — derived from measurement

Not a plan. A **ranking**, and it is re-derived from evidence at the start of
every cycle rather than worked through in order.

Distinct from the root [`ROADMAP.md`](../ROADMAP.md), which is the nightly
agent's task queue for the wider platform. This file covers one question: what
would most increase the Intent Engine's learning tomorrow.

Source of truth for every ranking here is
[`BOTTLENECK_LOG.md`](BOTTLENECK_LOG.md). Anything not backed by a measurement
in that file is a hypothesis and is labelled as one.

Reproduce the current numbers with:

```bash
PYTHONPATH=src python scripts/measure_yield.py
```

---

## Current ranking (after cycle 2, 2026-07-30)

### 1 — Strategic-reading yield · *measured*

**3 of 8 companies that produced evidence still produce no view**
(`view_withheld`). Now the top gate for companies that actually have something
to reason over.

Open question, and it must be settled by measurement before anything is built:
is a withheld view *correct* for those companies, or is the strategic gate too
strict for this use? Founder Intelligence's gate was tuned for a founder
reading one company deeply, where refusing is cheap and being wrong is
expensive. A research organisation evaluating fifty companies a day may want
the same evidence to yield a weaker, explicitly-labelled reading rather than
silence. **Do not assume it is too strict.** Sampling the withheld cases and
checking whether a defensible view was actually available is the next
measurement.

### 2 — Universe breadth · *measured*

4 tradable companies and 3 sectors, against a mission asking for 20–50 per day
across 7+ sectors, multiple market caps and regions.

Genuinely a multiplier now — the pipeline can reach its deepest gate, so more
companies produce more real evaluations rather than more empty rows. It was
correctly deprioritised twice while that was not true.

### 3 — Market-evidence adapter · *now reachable*

The gate one company already reaches with nothing else blocking it. Twice
deferred because it sat behind gates that could not pass; that is no longer
the case, which makes it buildable rather than speculative.

Constraint that does not change: it must be a **separate input** from the
strategic reading. A direction inferred from a strategic thesis is a
fabrication, and records made that way are indistinguishable from noise at
post-mortem.

### 4 — Retrieval on JS-rendered sites · *external*

3 of 11 fixtures produce no evidence at all; production `/readyz` reports
`browser_rendering: false`. Carried over from Founder Intelligence and
unchanged. Needs a rendering capability the project does not have.

---

## Not on this list, deliberately

- **Calibration feedback into reasoning.** Zero predictions have resolved, so
  there is nothing to calibrate against. `A-M5` gates accuracy claims behind
  ≥30 live-resolved predictions plus a human review. Calibration inputs are
  recorded on every opportunity so this can open deliberately, later.
- **Post-mortems, knowledge extraction, weekly meta-review.** All require
  resolved outcomes. They are downstream of item 3 and building them now would
  be speculative infrastructure.
- **Anything measured as fixed.** Evidence collection (cycle 1) and outside-
  source approval (cycle 2) are closed, with before/after numbers in the log.

---

## How an item leaves this list

It does not leave when the code exists. It leaves when the metric it was
ranked on has moved, measured the same way it was measured before, with the
result written into `BOTTLENECK_LOG.md`. If the metric does not move, the item
is reopened and the root cause was wrong.
