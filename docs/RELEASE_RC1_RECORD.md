# Founder Intelligence RC1 — release record

| | |
|---|---|
| Merge commit | `ff4daad` (PR #10, merge commit, not squashed) |
| Deployed commit | `ff4daad` — confirmed via the live `/version` endpoint |
| Previous production commit | `5e9133b` |
| **Rollback point** | `5e9133b` — `git revert -m 1 ff4daad`, then redeploy |
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
observation ids. Fixed on `fix/citations-resolve` (PR #11) with a regression
test confirmed to fail without it. **Not merged.** Production currently serves
`ff4daad`, in which slide citations do not open.
