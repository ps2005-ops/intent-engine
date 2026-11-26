# Economic-interpretation annotation: 19 ambiguous examples

You are labelling what each passage says about the named company's **demand**,
judged only from the passage, its source and its date. No model output is
included; please do not look anything up beyond the passage.

For each `example_id` in `examples.json`, fill one row of `ANSWER_SHEET.csv`:

| Column | Allowed values |
|---|---|
| `label` | `S` demand strengthening against the company's own past; `W` demand weakening against its own past; `PS` beat against analyst estimates (a surprise, not growth); `NS` miss against estimates; `N` no demand claim is warranted (price, profit, margin, cost, headcount, another company, marketing copy); `INSUFFICIENT` genuinely ambiguous or not enough information |
| `economic_variable` | free text, e.g. `revenue`, `bookings`, `guidance (revenue)`, `volume`, `none` |
| `confidence_1to3` | 1 = unsure, 3 = certain |
| `reviewer` | your initials |
| `notes` | anything that made it hard |

Rules:
* Revenue growth is not automatically demand growth. If price, acquisition
  or currency could explain it, prefer `INSUFFICIENT` or say so in `notes`.
* Guidance is an intention, not an outcome. A raised revenue outlook may be
  `S`, but note "guidance" in `economic_variable`.
* A share-price move is never a demand observation.
* `INSUFFICIENT` is a valid, useful answer. Please do not guess.

Two independent reviewers are ideal. Disagreements are recorded, not averaged.
When done, run `score_annotations.py` (see below).
