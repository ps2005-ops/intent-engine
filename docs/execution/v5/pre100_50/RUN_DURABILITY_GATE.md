# Run durability gate — what was measured, repaired, and what remains true

Frozen at the start of the 50-company programme. Every number here is a
measurement; where something is unproven it says so rather than rounding to
a claim.

## The failure this gate exists to close

Two of two live canary runs on `intent-engine-preview-bridge` disappeared
between the six customer steps and the Q&A step, in a window with no deploy.
Every request after the loss answered:

    This session does not have an analysis with that id.

The capture harness classified them `UNREADABLE` rather than storing them,
which is the only reason the wave was not scored as a catastrophic quality
regression.

## Cause, measured not inferred

`/readyz` on the deployed preview reports:

    durability            EPHEMERAL_LIKELY
    separate_filesystem   false
    boot_count            1
    degraded_reason       storage is not durable: completed analyses are lost
                          on every deploy

The ownership record, the retrieved evidence and the composed decision all
live in `data/` inside the container image. There is no persistent disk on
this service. When the instance is replaced they go with it, and `_owned`
correctly answers "no" — the refusal was right and the page was wrong.

`boot_count` cannot report this. Its ledger lives inside the runtime root, so
on an ephemeral filesystem it dies with the instance whose replacement is the
question. It reads 1 on every boot and can never rise. It is a durability
proof and it was the wrong instrument.

## What was and was not fixed

NOT FIXED, and not fixable from inside this repository: a destroyed analysis
does not come back. Real durability needs a persistent disk attached to the
service and `RUNTIME_ROOT` pointed at its mount — a Render dashboard change on
a paid plan, which `render.yaml` already declares for the production service
(`/var/data`). `/readyz` now also reports `persistent_mounts`, so the next
reader can tell "no disk is attached" from "a disk is attached and
RUNTIME_ROOT was never set to it". Those have very different fixes and had
identical symptoms.

FIXED: the customer's journey now terminates visibly in every case.

| state | what the reader gets |
|---|---|
| `RUN_READY` | the analysis |
| `RUN_FAILED_FINAL` | the honest failed-run page, unchanged |
| `RUN_RESTART_LOST` | **new** — named, explained, one click to re-run the same company |
| `RUN_NOT_OWNED` | the ordinary refusal, unchanged |
| `RUN_NOT_FOUND` | the ordinary refusal, unchanged |

The three on the right used to render the same page.

## How a lost run is recognised without the record that was lost

A signed claim (`webapp.run_recovery`) minted into an HttpOnly cookie the
moment a run opens, carrying `user_id`, `run_id` and the company name, HMAC'd
with `WEBAPP_SECRET`. The browser holds it, so it survives the event that
destroys the server-side record.

It is consulted only after ownership has already failed, so it can never widen
access to a run that still exists — only what a reader is TOLD about one that
is already gone. It names the `user_id` it was minted for, so a copied cookie
proves nothing for another session. Both properties are pinned by tests and
both mutations are caught (C, D in the break proofs).

## Instrument defects found while doing this

Fifth in this programme, and it would have corrupted the entire 50-company
measurement: `pre100/capture.py` posted all ten board questions to
`/runs/<id>/answer`. That route is served GET-only; the product's own Q&A form
posts to `/runs/<id>/conversation`. Every POST returned "page not found", and
the harness stored those pages as the company's strategic answers. Fifty
companies of identical 404 text would have scored as total cross-company
collapse.

Two guards now stand where that was: `capture.not_an_answer` names an
unrecognised page at capture time, and `audit.load_qa` refuses it again at
read time — the second one is what protects captures already on disk, which
were written before any filter existed.

The new recovery page is also refused as an answer. Without that, the
reliability repair would have created the sixth instrument defect: fifty
recovery screens are fifty identical strings.

## Restart attribution

`/version` now carries `process.boot_id` and `uptime_seconds`, and the route
touches no storage so it is safe to poll during a run. The capture harness
samples it before each company and again at the moment a run is lost, and
records `restart_observed` as `true` / `false` / `null`. An unknown is not a
no. "The run disappeared" was a hypothesis; "the run disappeared and the boot
id changed" is a measurement.

## Guards

- Focused: `tests/test_webapp_run_durability.py` (17), and
  `tests/test_pre100_harness_reads_real_pages.py` (9).
- Break proofs: `scripts/break_proofs_run_durability.py` — 10 mutations,
  10 caught, source tree byte-identical after the run. Mutations are applied
  to a copied tree, never to shared `src/`.
