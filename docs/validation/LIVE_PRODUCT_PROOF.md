# Live product proof — what runs on the deployed service

*Canonical. `reports/live_econ_matrix*.json` and `reports/live_matrix_wave*.json`
are the records. This explains the harness, the quota, and what LIVE_PROVEN
does and does not mean.*

---

## What is deployed

`intent-engine-preview-bridge`, tracking `feat/founder-market-integration`.
Its runtime root is the repository checkout — `RUNTIME_ROOT` is unset there —
so `data/econ/` ships with the build and the shared economic state is
readable without a mounted disk.

Verify what is actually serving with `/version` **before** starting a run you
intend to read. A push redeploys, and guest runs live in process memory: a
redeploy loses them mid-journey. A markdown-only push has the same blast
radius as a code push.

## The harness

`scripts/live_econ_matrix.py` drives the real customer flow: GET `/demo`,
scrape the CSRF token, POST `/analyze` with a real cookie jar, poll
`/runs/<id>/brief`, then read the primary screen, `/brief` and `/full`.

`curl` cannot do this. The anonymous session is minted in the 303 that answers
`POST /analyze`, and a client that follows the redirect without a cookie jar
lands on `/login`, reports "no run" for every company, and still spends one of
the ten analyses the deployment allows per IP per hour — a failure that looks
exactly like a product failure and is not one.

**The quota is the budget: ten analyses per client IP per rolling hour.**
`--slice i:n` runs the 24-company list in waves, strided rather than blocked
so a failed wave cannot be mistaken for a failed sector.

## What the harness scores, and what it must not conflate

- **BROKEN vs SLOW.** Status 0 is this client giving up; a 4xx/5xx is the
  server answering badly. The first matrix reported "4 requests with a
  4xx/5xx" when there was one. Measured locally, the primary screen and the
  full analysis cost 0.86s each *with* the economic context and 0.73s
  without, so the live figure is the free instance's CPU quota rather than
  the work this seam added.
- **Self-contradiction is scored against the SECTION**, not the joined page.
  Scoring it against everything reported Caterpillar as contradicting itself
  when its economic section is internally consistent and the phrase appeared
  elsewhere on the full analysis.
- Comments and `<script|style>` blocks are stripped **before** tags, or the
  shared shell's developer note — which names another company — becomes
  "visible text" and every subject reports a cross-company leak.

## What LIVE_PROVEN means here

It is claimed for the **EconomicState → Founder seam**, capability by
capability in `docs/architecture/BUILD_STATUS.md`, and not for all of V3.
Forward resolution is LIVE_PROVEN as machinery while forward calibration
remains `PRE_CALIBRATION`; Collective Human State remains
`FROZEN_CANDIDATE` and its Founder integration `REFUSED`.

A capability is LIVE_PROVEN when the deployed SHA contains it, real HTTP
requests execute it, and the rendered output exposes it. Tests passing is not
that.

## The conjunction that governs a live material delta

Three things must hold at once:

1. the company's own filings establish an exposure to a condition the shared
   state measures;
2. that condition is currently moving adversely **through a mechanism this
   business model has**;
3. the run also produced a Baseline A.

Companies fail (1) and say so as a gap in their exposure map; fail (2) and
abstain; fail (3) and report that no recommendation exists to compare
against. All three are rendered distinctly, and none of them is a blank
section.
