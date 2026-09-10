# Adaptive Strategic Intelligence — UI proof

Two sweeps, and the distinction matters. The **component sweep** measures the
adaptive block in isolation, before it costs a live analysis; the **live
sweep** measures the whole rendered page on the deployed service. A component
that is clean in isolation can still overflow inside a page that constrains
it, so neither replaces the other.

## Component sweep — measured

Rendered from `adaptive.render` with a real analyst fixture, three blocks on
one page (Highspot as CEO, Highspot as Strategy, BigID as CEO), driven in the
browser.

### Horizontal overflow

| width | max overflow | offender |
|---|---|---|
| 375 | **0 px** | — |
| 390 | **0 px** | — |
| 768 | **0 px** | — |
| 1280 | **0 px** | — |
| 1440 | **0 px** | — |

### Contrast, both themes

Every foreground/background pair the block declares, measured against WCAG AA
(4.5:1). **Both themes were measured** — the recorded failure this answers is
a light theme shipping three sub-floor tokens while a suite that only checked
dark stayed green.

| token | light | dark |
|---|---|---|
| body text | 17.76 | 15.29 |
| muted subtitle | 6.60 | 7.97 |
| section label on panel | 6.16 | 7.14 |
| lens accent | 6.70 | 7.70 |
| standing pill | 6.60 | 7.97 |
| disclosure link | 6.70 | 7.70 |
| evidence quote | — | 7.97 |
| genericity flag | — | 10.78 |
| future-role label *(opacity 0.6, blended)* | — | **6.07** |

`below_AA: []` in both themes. The opacity-blended value is computed from the
composited colour, not from the declared one — a token that passes as declared
and fails as rendered is the failure mode that check exists for.

### Structure

- **one `<main>` landmark.** The first implementation wrapped the adaptive
  block in a `<main>` of its own, giving the intro page two — a screen reader
  meets both and "skip to main content" can land on either.
  `test_the_default_run_page_is_the_founder_brief` caught it; the block is now
  passed into the renderer that owns the landmark.
- every section is `<section aria-labelledby>` with a real heading, in
  document order;
- every disclosure is `<details>/<summary>`, keyboard-operable natively;
- the role selector is real links with `aria-current`, not scripted controls;
- `:focus-visible` gives a 3px outline with 2px offset on every link, button
  and summary;
- score bars carry `role="img"` with an `aria-label` stating the value, so the
  ranking is available without colour.

### Adaptation, visible in the DOM

Same company, two roles — **identical facts, different order**:

| | Chief Executive | Strategy |
|---|---|---|
| 1 | Why this analysis is different | **The lens this analysis is using** |
| 2 | Where better intelligence could change a decision | Why this analysis is different |
| 3 | From the change to the decision | From the change to the decision |
| 4 | The lens this analysis is using | Where better intelligence could change a decision |

Top decision, causal chain (8 nodes) and lens are **word-identical** across the
two. The order changes; the facts do not.

Two companies, one engine — **different lens, different emphasis**:

| | Highspot | BigID |
|---|---|---|
| lens | Revenue & Go-To-Market Strategy | Data Security & Governance |
| order | why-different → decisions → chain → lens | why-different → decisions → **lens** → chain |

## Live sweep

Filled in from the frozen matrix run. See
`ADAPTIVE_STRATEGIC_INTELLIGENCE_RESULTS.json`.
