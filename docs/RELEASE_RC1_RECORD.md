# Founder Intelligence RC1 — release record

| | |
|---|---|
| Merge commit | `ff4daad` (PR #10) then `ec337f5` (PR #11 hotfix) — both merge commits, not squashed |
| Deployed commit | `ec337f5` — confirmed via the live `/version` endpoint |
| Previous production commit | `5e9133b` |
| **Rollback point** | `5e9133b` — `git revert -m 1 ec337f5 && git revert -m 1 ff4daad`, then redeploy |
| Tests at merge | 2,494 passed, 14 skipped |
| Customer simulation | 113/113 |
| Environment | `production`, `boot_count: 1`, no boot loop, PDF extraction available |

## Major fixes in this release

Navigation, legal boilerplate and injected instructions no longer become the
company description. Confidence counts vantage points rather than source
labels, so a company's own pages cannot establish a claim about how its market
sees it. Every claim states how it is known. Private and local companies are
held to the evidence they have. Follow-ups no longer error. Where no view is
supported, the product says so.

## Known product decisions

Recorded in full in `RELEASE_READINESS_RC1.md` (D1–D7). In short: a company
that publishes only boilerplate is told so rather than quoted; a single-page
company is declined; evidence under 60% readable declines the analysis; the
slide word budget governs prose, not chrome.

## Feedback durability

**Feedback is honestly disabled in production.** `/readyz` reports
`durability: EPHEMERAL_LIKELY` and `accepting_feedback: false`. The runtime
root is writable but not proven to survive a restart, and the product declines
to promise persistence it cannot demonstrate. This is deliberate and unchanged
by this release.

## Post-deployment defect

The live smoke test found that every citation on the presentation answered 404:
the evidence route searched only legacy claim ids while the deck cites
observation ids. Fixed on `fix/citations-resolve` (PR #11) with a regression test confirmed to
fail without it. **Merged as `ec337f5` and deployed.** Re-verified live: all
six citations on a Palantir deck return 200 with real evidence and no
traceback.

## Live smoke test on `ec337f5`

Palantir: brief by default, deck opens, one slide visible, arrow navigation,
no `:has()` in served CSS, description reads "We make products for
human-driven analysis of real-world data", follow-up answers without internal
wording, all citations resolve. Shopify: 9 slides, none empty, description is
not navigation or legal text. Sony: declines honestly in 332 words, renders no
empty finished-looking report. Unknown run: styled 404, no traceback.
