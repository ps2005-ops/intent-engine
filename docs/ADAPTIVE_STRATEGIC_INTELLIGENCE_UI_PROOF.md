# Adaptive Strategic Intelligence — live UI qualification

Frozen SHA: `807a414361b0fbc1999b4595e875c67e2a20524a`

## Development gate — live UI qualification (be5fde12)

Driven through the real guest form in a browser (`company_name`, `website`,
consent, CSRF), not through the harness, because the harness posts a field
`/analyze` does not read — see the defect note below.

Subject: **Highspot**, run `01M26WYVT48B1EVQNJPC6DH8KH`, the bounded /
defensible-abstention state, which is the rendering this phase adds.

### Responsive — five widths

Measured in the page, not inferred: document overflow, every element's right
edge against the viewport, and inner horizontal overflow on elements whose
`overflow-x` is `visible`.

| width | doc overflow | elements past the right edge | inner overflow | raw-internal leaks | spinners |
|---|---|---|---|---|---|
| 375 | 0px | 0 | 0 | 0 | 0 |
| 390 | 0px | 0 | 0 | 0 | 0 |
| 768 | 0px | 0 | 0 | 0 | 0 |
| 1280 | 0px | 0 | 0 | 0 | 0 |
| 1440 | 0px | 0 | 0 | 0 | 0 |

Leak probe (word-bounded): `None`, `UNKNOWN`, `PROFILE_SPARSE`,
`SUBJECT_EVIDENCE`, `CLASS_PRIOR`, `NOT_ESTABLISHED`, `ResultState.`,
`SUBSCRIPTION_SOFTWARE`, `PEOPLE_OR_ROUTE_BASED_SERVICES`, `Traceback`,
`&#x27;`, `&amp;` — **none present on the rendered page at any width**.

Three elements render below 11px (10.88px): the standing badges `BOUNDED` and
`STRONGLY INFERRED`. Uppercase letter-spaced badges, deliberate, and they are
not body copy.

### Both themes — contrast measured, not eyeballed

WCAG AA, computed per element from its resolved colour against its nearest
painted ancestor (4.5:1 body, 3.0:1 large/bold).

| theme | body canvas | elements checked | failures |
|---|---|---|---|
| dark | `rgb(15, 20, 28)` | 171 | **0** |
| light | UA canvas (`#fff`) | 171 | **0** |

**An instrument error worth recording.** The first light-mode pass reported 53
failures — every one of them at exactly 1.23. An identical ratio across 53
different colours is a statement about the measurement, not the page: both
`html` and `body` are transparent in light mode, so walking up for a painted
background fell off the top and scored near-black text against
`rgba(0,0,0,0)`. Re-measured against the UA canvas the page actually paints
on: 0 failures. The page sets `color-scheme: normal` and relies on the
browser's default light canvas, which is legitimate and is why dark mode —
where the body *is* painted — measured correctly the first time.

### Keyboard

- Global rule: `:where(a, button, input, select, textarea, summary,
  [tabindex]):focus-visible { outline: 3px solid rgb(29,78,216); outline-offset: 2px }`,
  with a second rule scoped to `.adaptive`.
- Real traversal: Tab ×3 from the document reached `button "Leave demo"` with
  `:focus-visible` true and a solid 3px ring.
- The role switch is an `<a>`; every Q&A control is a real `<form>` posting to
  `/runs/<id>/conversation` with a real `<button>`.
- **0 non-focusable click targets** (`div[onclick]`/`span[onclick]`) in `main`.

### Terminal state

No spinner, no `aria-busy`, no loading element present on the settled page at
any width. The run reached its result and the page stopped.

### Q&A, driven interactively

Asked through the page's own form: *"What is the single biggest uncertainty in
this analysis of Highspot, and why does it matter?"* Answered:

> every source here is published by the company itself, so nothing in this
> reading has been checked against an outside account of it.

Company-aware, evidence-aware, and it names the gap rather than inventing a
finding — which is what an abstaining run's Q&A owes. It is also short (~25
words); the six standard questions all returned substantially longer answers.

---

# Final matrix — all ten, five widths, both themes

Measured on the pages the frozen service actually served. Each run's `/intro`
is saved to `reports/ui/` and audited in a real browser. The pages are
self-contained — **0 external stylesheets, 0 external scripts**, five inline
`<style>` blocks — so an offline render is the served article, and the
measurement costs no analysis quota. A guest run is bound to the session that
created it, so re-driving ten companies through the browser would have spent a
second hourly quota to look at pages already in hand.

## Responsive — 375 / 390 / 768 / 1280 / 1440, light and dark

| width | clean | horizontal overflow |
|---|---|---|
| 375 | 9/10 | Monte Carlo Data: **85px**, 11 elements |
| 390 | 9/10 | Monte Carlo Data: **70px**, 9 elements |
| 768 | 10/10 | — |
| 1280 | 10/10 | — |
| 1440 | 10/10 | — |

Identical in both themes: the overflow is layout, not colour.

**The one defect, named exactly.** It is on the *retrieval-failure* page, and
the bleeding elements are all `<code>`:

```
CODE  https://www.montecarlodata.com/business/success-stories   right=461
CODE  https://www.montecarlodata.com/documentation              right=435
CODE  https://www.montecarlodata.com/developers                 right=412
```

The failure page prints a per-source ledger naming every URL it tried and why
each was refused — which is the right thing to print. The URLs are set in
`<code>` with no `overflow-wrap`, so below ~768px they push the page sideways.
It affects only the failure state; the nine report pages wrap correctly at
375px.

## Contrast — WCAG AA, computed per element

| theme | body canvas | elements checked | failures |
|---|---|---|---|
| light | UA canvas (`#fff`) | 1,554 | **0** |
| dark | `rgb(15, 20, 28)` | 1,554 | **0** |

Per element, resolved colour against its nearest painted ancestor, 4.5:1 for
body text and 3.0:1 for large or bold. Dark mode was confirmed applied inside
each frame (`prefers-color-scheme: dark` true, body painted) rather than
assumed.

## Leaks, spinners, terminal state

| probe | result |
|---|---|
| raw enum / internal terms (11 word-bounded probes) | **0** across all ten, both themes, all widths |
| `&#x27;` / unresolved entities | **0** |
| spinner or `aria-busy` on a settled page | **0** across all ten |

Probes: `None`, `UNKNOWN`, `PROFILE_SPARSE`, `SUBJECT_EVIDENCE`, `CLASS_PRIOR`,
`NOT_ESTABLISHED`, `ResultState.`, `SUBSCRIPTION_SOFTWARE`,
`PEOPLE_OR_ROUTE_BASED_SERVICES`, `Traceback`, `&#x27;`.

## Keyboard

Verified on the live service (development gate, and the same components serve
all ten):

- global `:where(a, button, input, select, textarea, summary,
  [tabindex]):focus-visible { outline: 3px solid rgb(29,78,216) }`, plus a
  second rule scoped to `.adaptive`
- real traversal reached `button "Leave demo"` with `:focus-visible` true
- the role switch is an `<a>`; every Q&A control is a real `<form>` posting to
  `/runs/<id>/conversation` with a real `<button>`
- **0 non-focusable click targets** (`div[onclick]` / `span[onclick]`)
