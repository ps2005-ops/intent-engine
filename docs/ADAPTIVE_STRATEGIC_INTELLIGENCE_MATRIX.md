# Adaptive Strategic Intelligence — the live qualification matrix

## What this measures, and what it deliberately does not

The gates below are about whether the product **understood a particular
company** and said something a strategy executive could act on. They are not
about whether it produced a confident recommendation.

> **10/10 does not mean ten confident theses.** A company whose public record
> cannot support a strategic reading passes by showing the correct company
> model, the correct lens, an explicit statement of what is missing, and what
> it would read next. That is `DEFENSIBLE_ABSTENTION` and it counts. Lowering
> the epistemic standard to turn a cell green would make the matrix a record
> of what we were willing to claim rather than of what the product knows.

## The cohort

The exact ten, not substitutable:

| # | company | domain |
|---|---|---|
| 1 | Highspot | highspot.com |
| 2 | BigID | bigid.com |
| 3 | Cyera | cyera.com |
| 4 | Monte Carlo Data | montecarlodata.com |
| 5 | Veeam | veeam.com |
| 6 | Druva | druva.com |
| 7 | Slalom | slalom.com |
| 8 | Sigma Computing | sigmacomputing.com |
| 9 | ZoomInfo | zoominfo.com |
| 10 | Point B | pointb.com |

None was replaced because its evidence was difficult. That is the thing being
measured.

## The expectations, and their status

`scripts/adaptive_ten_matrix.EXPECTED_LENS` records what a strategist would
expect each company's lens to be. It is a **check**, never an input: the
product is never told the expected answer, and a company that lands elsewhere
is examined rather than corrected. A miss is recorded as `DATA_LIMITATION`
pending examination, not as a product defect and not as a pass.

## The gates

| gate | what has to be true |
|---|---|
| **A. Identity** | canonical company on the page, right entity, no parent/subsidiary confusion, no cross-company leakage |
| **B. Company profile** | business model defensible and evidence-backed, customer job right, assets and dependencies this company's own |
| **C. Decision map** | defensible company-specific opportunities, sane rank order, top decision materially relevant, no boilerplate |
| **D. Strategic lens** | primary defensible, secondaries sensible, `WHY_SELECTED` visible, refusals published, no identical explanation across unrelated companies |
| **E. Differentiation** | materially unique, company mechanism present, not reusable unchanged |
| **F. Causal chain** | change → mechanism → exposure → consequence → decision, evidence-linked, uncertainty explicit |
| **G. Evidence** | supporting and counter-evidence, provenance, source-role diversity, no fabricated quote, no unsupported precision |
| **H. Thesis** | company-specific and evidence-entailing, or a defensible abstention |
| **I. Decision value** | management implication, trade-off, what would make it wrong, information priority |
| **J. Q&A** | 6/6 substantive and company-specific, follow-up retains context |
| **K. Role lens** | CEO and Strategy both pass, same facts, different priority |
| **L. UI** | 375/390/768/1280/1440, light and dark, keyboard-only, no overflow, no invisible text, no spinner after terminal, no raw enums |
| **M. Demo quality** | visibly different from another company's page; lens, decision, chain, why-this-company, provenance, Q&A and uncertainty all visible |

## Defect classification

Counting defects without classifying them produces one number and no next
action. Five kinds, four responses:

- **PRODUCT_DEFECT** — the product did the wrong thing. Fix it.
- **INSTRUMENT_DEFECT** — the harness did. Fix the harness; the row is void.
- **INFRASTRUCTURE** — the deployment or the network. Re-run.
- **EXPECTED_ABSTENTION** — the product correctly declined. Nothing.
- **DATA_LIMITATION** — the public record does not carry it. Examine, record.

## Instrument notes carried forward

- **Drive the real form.** `/analyze` is posted with exactly the fields the
  browser posts — `csrf`, `company`, `website`, `consent`. Sending less than
  the real form does is bypassing the customer flow just as surely as calling
  an internal function would be.
- **One session per company, held open.** `/runs/<id>/conversation` checks run
  ownership, so a second anonymous session cannot ask anything about the run
  the first one created.
- **Persist every row immediately.** A wave that dies on company seven must
  not lose one to six.
- **The demo quota is 10 analyses per IP per rolling hour.** The cohort is
  exactly the budget, so a scorer bug spends the whole hour silently. Run the
  development set first, on a different day-hour, and read the telemetry
  before spending the matrix.

## Results

Filled in from `reports/adaptive_ten_matrix.json` after the frozen run. See
`ADAPTIVE_STRATEGIC_INTELLIGENCE_RESULTS.json` for the machine-readable form
and `ADAPTIVE_STRATEGIC_INTELLIGENCE_UI_PROOF.md` for the responsive, dark and
keyboard sweep.
