# Deploy B register — defects found on the b0ec8cb canary

## D1. `challenge_block.CSS` renders as literal text on `/full` (CRITICAL, §13 raw leak)

`webapp/app.py` builds the full analysis as:

```python
strat = (fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS + _cb.CSS
         + fd.render_dossier(...))
```

Three of those four constants begin with `<style>`. `challenge_block.CSS`
does not — it is a bare stylesheet string. `_stylize` hoists `<style>`
elements to `<head>`, so the three wrapped ones move and the fourth stays
where it was: as TEXT, immediately after `<main>`.

Measured on Meta's live capture, the first thing inside the analysis:

> `<main> .challenge{border:1px solid var(--rule);border-radius:10px;padding:1rem 1.15rem; …`

Two consequences, and the second is worse than the first:

1. Every reader of `/full` — and every text extractor, accessibility tree and
   screen reader — gets a stylesheet as the opening content of the analysis.
2. The rules never apply, so the `.challenge` block (the belief-challenge
   card) has been rendering **unstyled** on every company.

Fix: wrap it, and add a structural guard that every CSS constant concatenated
into a page body is `<style>`-wrapped — the defect is the asymmetry between
four siblings, so the guard belongs on the set, not on this one constant.

## D2. Raw enum constants shown to the customer on `/evidence` (CRITICAL, §13)

From Meta's live `/evidence`:

> "Search coverage: **DISCOVERY_PARTIAL** · reading: **HAVE_INDEPENDENT**"
> "Independent voice: yes · Relevance: **DIRECTLY_RELEVANT** · Counts as
> corroboration: yes"

Internal enum values rendered as customer copy. §13 names a raw-object leak a
critical defect, and this codebase has shipped one past a green test before —
the detector matched the comment explaining the enum rather than the enum.
The guard must read the rendered page, not the source.

## D3. `economic_reasoning` and `business_model` cannot measure what §15 asks

See INSTRUMENT_DEFECTS.md — these are scorer defects, not product defects, and
they need no deployment. Both are repaired against the 50 captures, not the 1.

## Predicted, from offline measurement on 11 real 10-Ks — see DEPLOY_B_CANDIDATE_C1.md

`what_is_sold` and `revenue_basis` both match mid-sentence relative clauses,
glossary entries and revenue-recognition policy. Sentence-anchoring repairs 4
of 11 outright and turns 4 wrong answers into honest empties.
