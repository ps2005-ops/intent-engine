# The canary found a live reliability defect, and my harness caused the load

## What happened

On the deployed `f8c183f`, in one window:

| run | company | outcome |
|---|---|---|
| canary A | Microsoft | **all six surfaces 200**, real content, 146s |
| canary C | Microsoft | 588s, then **9 of 10 surfaces HTTP 500** |
| canary C | Meta | 535s, then **9 of 10 surfaces HTTP 500** |
| canary C | 5 others | `/analyze` returned **HTTP 500**, 0.9s each |

Same SHA. Same process — `boot_id` unchanged across all of it, so the
instance never restarted or OOM-killed.

`/report` answered 200 while every founder surface answered 500, which points
at the shared founder path (`_strategic_read` / `_founder_layers`) rather than
at any one renderer.

## What it is not

Not this wave's code. Driven locally with a Microsoft-shaped input — twelve
subject filings, fourteen observations, a real CIK:

* `strategic_read.compose` returns cleanly: 3 adversary moves, 5 heresies,
  a measured architecture.
* `build_dossier` assembles both new passages.
* `render_dossier` emits 23,079 characters containing both section headings.
* Every founder surface renders 200 against a run that already has a stored
  dossier — the state the second live run of a company is in.

Not quota either, at the moment it happened: the quota refusal is a clean
**429** with its own page ("Demo analysis limit reached for your network"),
which is what the service returns now. The five failures were **500s**.

## What I did wrong

I relaunched the canary twice without killing the previous batch, so THREE
batches ran concurrently against one IP — up to six simultaneous analyses on
a free instance that is already measured at 13.75x slower than local under
CPU throttling. §20 says respect the quota rather than hammer it.

Two consequences beyond the load itself: one batch's worker hit a directory
another batch had moved (`FileNotFoundError`), and the stale process was
still running the OLD quota detector, so its "quota reached" verdict was
meaningless.

## Open, and honestly unresolved

**A completed nine-minute analysis rendering 500 on nine of ten surfaces is a
SEV1 for the demo.** I could not reproduce it locally and cannot read the
deployed instance's traceback. The one reproducible correlate is concurrency.

It is recorded here rather than guessed at, because the last two defects this
programme closed by guessing both shipped inert.

## Harness changes made because of it

* concurrency defaults to **1**
* a failed capture persists `run.json` — the row carrying the page the
  service actually returned. Five 500s produced nothing to diagnose from.
* a run that never opened is no longer logged as `DONE ... in 1s` beside a
  genuine analysis, and is not scored: that zero belongs to the service, not
  to the company
* three consecutive failures to open a run stop the batch
