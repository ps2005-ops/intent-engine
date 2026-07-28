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
