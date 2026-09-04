# A markdown commit destroyed a five-minute analysis

Measured 2026-08-20, window 2.

## What happened

Window 2 started against deployed `188da7c`. Partway through, `/version`
began reporting `31e6138` — three **documentation-only** commits had been
pushed to the tracked branches by a parallel session.

Meta's run `01M0FQHQ9T31DH41DWEHVCDEW3` ran the full **556 seconds**, never
auto-advanced, and then returned **404 on all thirteen routes**:

> This session does not have an analysis with that id. Analyses are kept per
> session and are cleared when the service restarts.

The single most valuable run in the window — the direct before/after against
the 10/10 collapse baseline — was lost, along with a slot from a 10-per-hour
quota.

## Why "docs-only" is not a safe category

Render deploys on **any** push to the tracked branch, regardless of what
changed. The restart clears in-memory guest sessions, and every in-flight run
dies with them. **A markdown commit has the same blast radius as a code
commit.**

## Why this is a live-reliability finding, not tooling friction

The customer-visible form of this is a chief executive losing a five-minute
analysis because someone shipped a README. Nothing in the product tells them
what happened beyond "that analysis is not available here", and the run is
unrecoverable — there is no persistence behind it.

Two consequences for the 60-company programme:

1. **A live gauntlet cannot run against a branch anyone is pushing to.**
   Either the artifact branch is separated from the deployed branch, or
   pushes are gated on nobody holding a measurement window.
2. **Run durability is a product question, not just an ops one.** Runs are
   per-session and in-memory; a restart is indistinguishable from a run that
   never existed. `/readyz` already reports
   `"durability": "EPHEMERAL_LIKELY"`, so this is known and unmitigated.

## Cost this window

| | |
|---|---|
| runs destroyed | 1 (Meta) |
| quota consumed with no measurement | 1 of 10 per hour |
| wall-clock lost | 556 s |
| re-runs now owed | Meta, plus JPMorgan for grep 2 |

## Status

Reported to the parallel session with a request to hold pushes until the
window closes. Recorded here because the mitigation is procedural today and
should not be: a run a customer is watching should survive a deploy, or the
product should say so.
