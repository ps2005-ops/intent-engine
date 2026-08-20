> # SUPERSEDED IN PART — read `WINDOW_3_UI.md` first
>
> This file was written on `0420fb0`, before the defect was measured. Its
> **symptom** is still accurate and its evidence still stands. Its **mechanism
> is not the whole story**, and one of its premises is wrong:
>
> * It names `derive_observations` accepting all documents as the cause. That
>   was true of one route. It does not know about the second route
>   (`narrative.py` rendering `_mechanism_evidence` under *"The company's own
>   words"*), and it does not know about the **join** — a row that pairs one
>   observation's `source_class` with another observation's `source_title`.
> * It implies Wells Fargo's document is subject-speaking. **It is
>   `independent_reporting`**, measured directly. I inferred the class from
>   the rendered label *"Regulatory or investor filing"* and was wrong; so was
>   the teammate who asserted the opposite without measuring. Both of us
>   reasoned from the label, in opposite directions, and the disagreement felt
>   like scrutiny while resting on the same unexamined inference.
> * Its framing of `GREP 2` is wrong. JPMorgan's own 10-K genuinely carries
>   the capacity signal, so the string's presence proves nothing. The test is
>   whether the **evidence row** beside the sentence belongs to the subject.
>
> Left intact rather than rewritten: a correction that deletes what it
> corrects teaches nothing, and here the superseded reasoning is the more
> instructive half.

# A signal from another company's filing becomes this company's mechanics

Found by the deployed UI, window 1, on `0420fb0`.

## What a customer saw

JPMorgan Chase's Full Analysis, under **How the business actually works →
Distribution model**:

> Is committing capital to capacity ahead of the demand for it.

with the attributed evidence:

> **WELLS FARGO & COMPANY/MN (WFC, …) — 10-K (2026-02-24)** Regulatory or
> investor filing *is committing capital to capacity ahead of the demand for
> it*

A capacity-commitment mechanic, for a bank, sourced from a **different bank's
filing**. The same page carries *Digital Asset Acquisition Corp III*, a
blank-check SPAC whose 10-K opens "We are a blank check company".

## The mechanism

    service.py:1126   derive_observations(documents, company=company_name)

receives **every** retrieved document with no ownership filter.
`strategic_read._named_rivals` filters to
`("investor_material", "executive_statement", "company_owned")` for exactly
this reason — it was repaired earlier when RingCentral's competitor list was
published as Meta's. `observations.py` names `source_class` sixteen times, all
as a recorded field, never as a gate on which documents may describe the
subject.

**Competitors were fixed. Signals were not.** Third instance this session of
one defect with two producers, one fixed:

| defect | producer fixed | producer missed |
|---|---|---|
| model-class gating | `patterns_for` | 8 of 11 model-keyed tables |
| classification inputs | `webapp.classification_inputs` | `service._patterns_for_company` |
| **claim ownership** | **`_named_rivals`** | **`derive_observations`** |

## Why it may be larger than one sentence on one page

`observations.py`'s own docstring: *"an observation is the unit patterns match
against"*. If that holds, signals harvested from other companies' filings can
influence **which hypotheses a company is offered**, upstream of both the
denylist and the classification seam.

**This is stated as a hypothesis with a mechanism, not a measurement.** It has
not been measured end to end. The test is cheap: derive observations for one
company with and without third-party documents, and compare the pattern
matches.

## Scope

Not a one-company quirk. Measured across two companies on two builds:

* **JPMorgan** (`0420fb0`) — Wells Fargo 10-K, a blank-check SPAC
* **Walmart** (`58ac7ef`) — Ranpak Holdings, Ibotta, and a 2023 BitNile
  Metaverse 10-K, with **no Walmart 10-K at all**, and a confident competitive
  claim rendered anyway

Third-party filings entering the subject's own description is by design at the
retrieval layer — EDGAR full-text search finds filings by other registrants
that name the subject, and those are legitimate evidence *about* a company.
What is not legitimate is a claim *by* another registrant becoming a statement
of how **this** company works.

## Status

OPEN. The call site is `company_ingestion/service.py`, owned by the parallel
session; the fix arguably belongs in `observations.py`, since a function that
builds a company's own mechanics should not silently accept documents about
other companies.
