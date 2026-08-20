# Window 3 — deployed UI, `cec9b2f`

JPMorgan, Meta, Caterpillar, Exxon. **4 of 4 captured.**
4/4 auto-advanced, 40/40 board questions answered, 0 false failures.

| company | seconds |
|---|---|
| JPMorgan | 164 |
| Meta | 228 |
| Caterpillar | 260 |
| Exxon | 179 |

## A prediction made before the measurement, and it held

Recorded before the runs landed, by the session that made the change:

> Caterpillar/Exxon still **8/10** on the ten board questions. Board answers
> route off topic/falsifier/recommendation, not off mechanism.

**Measured: 8/10.** Unchanged from window 2 on a different SHA. The trace is
confirmed, and the `xfail(strict=True)` marking the unclosed half is the right
shape.

A prediction that survives is evidence; a number without one is just a number.

## `GREP 2` FAILS — the claim-ownership repair is deployed and inert

JPMorgan's page, unchanged from `0420fb0`:

> **Distribution model** — *"Is committing capital to capacity ahead of the
> demand for it"*
> evidence — **WELLS FARGO & COMPANY/MN — 10-K (2026-02-24)**

The fix is genuinely deployed — `188da7c` is an ancestor of `cec9b2f`,
`model.py` carries `speaks_for_subject`, `observations.subject_documents`
exists. The code is there; the page did not move.

### Two independent reasons

> **CORRECTION, established later by measurement.** The two sub-sections
> below were my root cause and the first is WRONG. Wells Fargo's document is
> classed `independent_reporting`, not `investor_material` — measured by
> calling `_third_party_filing_candidates` directly. I inferred the class
> from the RENDERED LABEL *"Regulatory or investor filing"* and used that
> inference to overrule a teammate who had said, correctly, that it was not
> `investor_material`. The label was evidence; I treated it as the fact.
>
> The real defect is narrower and stranger: `provenance_label` maps
> `independent_reporting` to *"Independent evidence"* unambiguously, so a row
> reading *"Regulatory or investor filing"* beside a **Wells Fargo** title
> **joins one observation's class to another observation's title**. Two
> observations rendered as one row.
>
> **And `GREP 2` as run below is the wrong test.** JPMorgan's own 10-K
> carries the capacity signal — all three candidates under `/data/19617/`,
> `subject_owned=True`. So the sentence may be correct for JPMorgan, and the
> string's presence proves nothing. The right test is whether the evidence
> row beside it belongs to JPMorgan. The captures still evidence the Wells
> Fargo row, which is the real defect; the framing of what failed was
> imprecise across three runs.

**1. `source_class` cannot carry ownership.** *(superseded — see correction)*

    speaks_for_subject = SOURCE_CLASSES - INDEPENDENT_CLASSES
                       = (company_owned, executive_statement, investor_material)

and `edgar.filing_candidates` stamps **every** SEC filing it proposes with
`"source_class": "investor_material"` — unconditionally, whoever filed it. So
Wells Fargo's 10-K is "subject-speaking". The rendered label *"Regulatory or
investor filing"* was the visible clue throughout: it is the
`investor_material` label.

`source_class` encodes **how a document was retrieved**, not **whose it is**.

**2. The gate that could do the job is never called.**
`observations.subject_documents(documents, *, subject_cik)` exists and its
docstring describes this exact JPMorgan/Wells Fargo case. `model.py` does not
import it — `grep -c` returns 0 on the deployed file. The cross-CIK rule,
described as "belt-and-braces", is the load-bearing part and is not wired in.

**Produced and never read — the fifth this session**, and the first where the
unread producer was written in the same session as the repair that needed it.

### Not one company

Meta, same build:

> **NETWORK-1 TECHNOLOGIES, INC. (NTIP) — 10-K (2024-03-08)**
> *"Meta Platforms, Inc. is committing capital to capacity ahead of the
> demand for it"*

Network-1 is the patent litigant the codebase's own `relationship.py`
docstring cites as the canonical mis-attribution — *"our case against Meta
Platforms, Inc."* This instance is labelled **"Independent evidence"**, so it
reaches the page through a route the class filter should already block —
either the contradiction path or a surface other than `build_mental_model`.
**Not traced.**

## Verified working

**Meta's archetype fix — confirmed on the page.** The central question is now

> *"how much of the audience's attention to convert into inventory, and
> where, given that ad load taken today is paid for out of users and their
> engagement tomorrow?"*

replacing the epistemic fallback (*"what does the published record
establish about X"*) that both Alphabet and Meta shipped with. A real
strategic question in the business's own variables, and the first usable Meta
capture of the session — two of the previous three were lost or pre-fix.

## Not established

* **JPMorgan at 164s is not cache corroboration.** A warm process and a small
  filing set look identical from outside. Recorded; cause unestablished — the
  same standard applied to Lilly's 18s.
* **The evidence-beside-answers prediction could not be tested.**
  `FounderDecision.grounded_in` is absent from `cec9b2f`; it needs the next
  SHA.


---

## Closed, mechanism NOT established

Re-run on `82ffe6f`, run `01M0G9ZW4QBCZB8QMFTVBZCG6X`, 170s, auto-advanced,
10/10 answered. The row changed:

| | |
|---|---|
| `71e4dc0` | WELLS FARGO — 10-K · **Regulatory or investor filing** · *is committing capital to capacity ahead of the demand for it* |
| `82ffe6f` | WELLS FARGO — 10-K · **Independent evidence** · *"Information in response to this Item 7 can be found in the 2025 Annual Report…"* |

The label is now the correct mapping for `independent_reporting`, and the text
beside it is Wells Fargo's own content rather than a claim about JPMorgan's
capital. A same-code-path local run against live SEC confirms the mechanism:
`rows_where_ownership_disagrees_with_the_filer` = 0,
`rows_citing_another_filers_document` = empty, and `distribution_model` cites
`obs-src-b374efb5092e` → filer **19617**, JPMorgan's own 10-K.

The capacity sentence remains, and that is **correct**: JPMorgan's own filing
carries the signal.

### The mechanism is not established, and the record says so

`git diff --stat 71e4dc0 82ffe6f -- src/` is one file — the `elif`→`if` CIK
fix plus an additive read-only route. By elimination the CIK fix moved the
page. But that fix was jointly dismissed as unable to explain these captures,
because the harness posts no `suggest_domain`, so `picked_domain` is empty and
the old `elif` should already have fired.

**Both cannot be true.** One premise is wrong and the run that would settle it
— a pre-fix run whose `subject_cik` could be read — no longer exists.

**Six confident stories about this one defect were wrong before this point.**
The artifact records an unresolved mechanism rather than a seventh.

### The durable fix is observability, not the repair

Record `subject_cik` on the run at creation so it reaches `run_meta` and
`provenance.json` for every run. Every hour spent here traces to one field
being unobservable after the fact.

### A constraint worth naming

`provenance.json` is operator-gated, correctly — it carries tenant data.
Neither agent doing the diagnosis could read it, and neither would enter
credentials to try. The diagnostic built to settle live defects cannot be read
by the people settling them, so run-scoped fields needed for this work must
reach a readable surface or be logged.
