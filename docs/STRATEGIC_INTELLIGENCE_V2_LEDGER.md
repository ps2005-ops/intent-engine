# Strategic Intelligence V2 — programme ledger

Branch `feat/strategic-intelligence-v2`, cut from `main` @ `ec337f5`.

The starting point was a live Sony Interactive Entertainment report that told a
console and games business it was "turning a people-delivered service into a
repeatable product", named "SMB / Product" as an affected function, and asked
"whether to price the product independently of the engagement".

---

## 1. Defects found, with root cause

Every one was reproduced offline before being fixed.

| # | Defect | Earliest root cause | Fix | Commit |
|---|---|---|---|---|
| 1 | Any company mentioning capital allocation "exposes a surface others can build on" | Detection was `phrase in text`. The signal phrase `"api"` is a substring of **capital**, **rapid**, **therapies** | Word-boundary matching | `947f9c4` |
| 2 | "absorbing adjacent tools until the work lives inside it" | The single word **"unified"** matched `consolidation` | Removed bare generic words as signals | `947f9c4` |
| 3 | "SMB / Product" for a console business | Commerce domain anchors included **cart, checkout, buyer, shopping, retail** — the vocabulary of any storefront. The PlayStation Store page entered a *merchant* pattern library, where "simple"/"easy to" matched `smb_simplicity` | Anchors are merchant-side only | `947f9c4` |
| 4 | "turning a people-delivered service into a repeatable product" | Qualifying evidence was a **careers page** listing job families ("solutions engineering", "professional services") | `page_kind()` — careers/legal/support cannot qualify a hypothesis | `947f9c4` |
| 5 | Marketing snippets pushing hypotheses over threshold | `_signals_present` unioned every observation regardless of quality | Weak observations contribute no qualifying signals | `947f9c4` |
| 6 | Best evidence in a run silently discarded | An observation required a controlled-vocabulary signal match. An independent analysis of console economics matched **zero** | `derive_analyst_evidence()` — separate derivation for the analyst | `be6ad37` |
| 7 | Reports read as templates regardless of company | **Architectural**: a pattern library can only emit sentences written in advance | Grounded analyst + deterministic critic | `be6ad37` |
| 8 | PARTIAL indistinguishable from a good report | One state covered "weak" and "fine" | Six explicit result states; only COMPLETE is presentable | `8ad1a20` |
| 9 | Sound bank analysis discarded whole | The no-invented-numbers rule flagged **"2026"** | Calendar years are temporal references | `996e7af` |

### Not a defect (corrected during the work)

I initially recorded "every agenda item renders with title `None`" as a
product bug. It was my reproduction script reading a `title` key; the renderer
reads `inferred_discussion`, which is always populated. The test was rewritten
to assert the real contract and made non-vacuous.

---

## 2. Architecture

```
evidence acquisition  ->  deterministic   retrieval, EDGAR, provenance, citations
reasoning             ->  the analyst     grounded, cited, structured output
verification          ->  deterministic   the critic
```

The critic runs with no network and no model. It rejects:

- citations that do not resolve to a real observation
- any percentage, currency figure or magnitude absent from the evidence
- headlines not anchored in this company's evidence vocabulary
- headlines that are ≥40% strategy-speak (naming two real products and
  wrapping them in fluff clears the anchor test while saying nothing)
- high confidence drawn from company-owned pages alone
- a subsidiary analysed without naming its parent

**A rejected analysis never falls back to the generic scaffolds.** Every report
carries `reasoning_provenance` (`pattern_library` | `grounded_analyst`) so a
scaffold cannot be mistaken on the page for a finding.

---

## 3. Sony before / after

Same evidence, same pipeline.

**Before** — 3 hypotheses, 2 false, 1 qualified by a careers page:
- turning a people-delivered service into a repeatable product
- running separately-reported businesses as a single portfolio
- committing capital to capacity ahead of uncertain demand
- affected function: **SMB / Product**

**After (deterministic layer alone)** — the false hypotheses are gone; SMB is
never named.

**After (grounded analyst)**:

> Sony keeps its biggest first-party PlayStation Studios titles out of
> PlayStation Plus at launch, betting full-price software sales and
> hardware-loss-leader economics beat Microsoft's Game Pass day-one-inclusion
> model.

with the attach-versus-subscription tension, Game Pass as the named contrast, a
second-order effect on player expectations, a falsifier, plain-language
confidence, and every claim cited. Zero critic findings. It also reported that
**no source in the run has an established publication date**.

---

## 4. Cross-sector validation

Three unrelated industries, real model, checked for wrong-industry vocabulary:

| Company | State | Insight | Contamination |
|---|---|---|---|
| Northvale Bancorp (banking) | COMPLETE | Relationship-deposit franchise as a funding-cost cushion being spent down by margin compression, while carrying above-peer CRE concentration into a repricing wave — and the CRE demand comes from the same relationship customers | none |
| Palantir (analytics) | COMPLETE | The forward-deployed model both wins government contracts and caps gross margin as commercial mix grows | none |
| Meridian Therapeutics (healthcare) | COMPLETE | Pre-approval manufacturing capex concentrates risk in a single regulatory outcome for a small-population indication | none |

Palantir is the load-bearing case: it previously matched **five commerce
patterns** and was handed hypotheses about merchants and storefronts.

---

## 5. Tests

`2540 passed, 14 skipped`. New files:

- `tests/test_strategic_evidence_integrity.py` — 16 cases, each pinning one
  reproduced defect, plus the inverse (real developer surfaces, real merchant
  platforms and real consolidation language still detected)
- `tests/test_strategic_analyst.py` — 23 cases driving a recorded client
- `tests/test_strategic_result_states.py` — 4 end-to-end cases

CI makes **no model calls**.

---

## 6. Production

`ANTHROPIC_API_KEY` is **not provisioned** by `render.yaml` — it appears only
in a comment, and the running free-tier service is not governed by that
blueprint anyway. The deployed service therefore runs deterministic-only and
reports `EVIDENCE_LIMITED` rather than asserting conclusions.

To enable the reasoning layer in production, add to the Render service:

```
ANTHROPIC_API_KEY = <secret>     # sync: false
```

`/readyz` now reports `capabilities.strategic_reasoning`, so this becomes
checkable from outside instead of inferred.

---

## 7. Remaining work

Not attempted in this pass, in rough value order:

1. **Presentation-first flow** (spec §2, §13, §14) — auto-open the deck, final
   slide → executive brief, and a deck rebuilt around the analyst's fields.
   The data is in place; the webapp rendering is not.
2. **Public-company evidence plan** (§5, §6) — EDGAR exists; it is not yet
   driven by a per-company evidence plan with recorded routes.
3. **Follow-up assistant** (§21) — still reads the deterministic report.
4. **Frozen baseline benchmark** (§18) and **human CEO evaluation** (§23) —
   both require work outside a coding session: a reviewed baseline corpus and
   real blind reviewers.
5. **Adversarial suite** (§20) — partially covered by the regression tests;
   not a systematic pass.

---

# Part 2 — Founder value

The architecture was right and the output was still shaped like analysis. A
founder does not need analysis; they need to know what to do, what it costs to
wait, and what a competitor might do first.

## What changed

| Before | After |
|---|---|
| `insights[]` — things that are true | `decisions[]` — forks with two sides, each with urgency, cost of waiting, what a rival may do first, upside, downside, falsifier |
| `business_model` a one-line string | where profit comes from, **where value leaks**, what customers *actually* buy, what management appears to optimise — established *before* any strategy is inferred |
| conclusions buried in sections | **The Insight** — one sentence, its own slide, never truncated |
| second-order asserted in one field | an explicit `consequence_chain` that stops where the evidence stops |
| competitors listed | who is *forcing* the change, who benefits, who loses, who must respond, who can ignore it |
| deck opened with methodology | deck opens with what business they are really in |

## New gates

- `not_a_decision` — "Explore opportunities in X" is a topic, not a decision
- `no_cost_of_waiting` — usually the whole argument
- `software_speak` — "decision affected", "supporting evidence", "likely
  agenda", "affected functions" may never reach a reader
- `repetition` — no idea may appear as the insight *and* a decision *and* a
  question

## Defects found by using it, not by testing it

1. 4000 output tokens truncated on a five-document run — and the retry
   truncated identically, spending two calls to fail the same way. Raised to
   8000; truncation is now recognised as deterministic and not retried.
2. The model cited all decisions and omitted the nested insight's citations.
   The insight and decisions are one argument over one evidence set, so either
   grounds it — every citation must still resolve.
3. **The Insight was being trimmed to the bullet budget**, cutting "...is not
   conservatism" off the end: keeping the setup and deleting the point.
4. Bullets cut mid-clause; now they end on a finished thought and never stop
   inside a bracket.
5. Prefixing produced "Customers are really buying Not a box".

## Founder test, four sectors

| Company | The Insight | Urgency called |
|---|---|---|
| Sony Interactive | Withholding first-party titles from day-one PS Plus is not conservatism — it is the lever protecting the attach economics the discounted-hardware strategy depends on | this year |
| Northvale (bank) | The sticky cheap deposits that are the funding advantage are the same asset making above-peer CRE concentration dangerous — both sit on one balance sheet as loans reprice | this quarter |
| Palantir | The growth story is told in commercial revenue but the cost structure was built for government contracts, and nobody has shown the margin math reconciles | this year |
| Meridian (healthcare) | Spending capital as if approval is a formality, when one rejection strands the manufacturing investment entirely | decide now |

Urgency is calibrated rather than manufactured: Northvale's deposit-pricing
decision self-rates "watch only" with "low near-term cost — this is a pricing
posture question, not a structural one".

## Still not done

- **No human founder has read this.** The stop condition is blind reviewers
  saying they would use it before a major decision. That has not happened, and
  it is the only test that settles the question.
- Presentation-first *routing* — the deck is built and rendered, but the
  webapp still requires a click to reach it; auto-open and the final-slide
  hand-off to the brief are not wired.
- The executive brief and full analysis still render the old structure.
- Follow-up assistant still reads the deterministic report.
- Frozen baseline comparison against a generic prompt.
