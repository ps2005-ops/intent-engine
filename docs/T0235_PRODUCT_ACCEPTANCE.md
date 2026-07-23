# T023.5 Product Acceptance — Founder Intelligence Experience

*Written 2026-07-21 at the close of Session 14. This records what the
product IS and, separately, what it is NOT — because per the brief's §45,
"PRODUCT BUILT", "DEPLOYMENT READY", "PUBLICLY DEPLOYED", and "LAUNCHED"
are different facts and must never be conflated.*

---

## Status — stated as separate facts

| Fact | Status |
|---|---|
| **PRODUCT BUILT** | **Yes.** The evidence-backed experience — contracts, run lifecycle, security walls, identity, approved-input ingestion, the full trust-sequenced result, public conversation, snapshots, and a stdlib HTML presentation — is built and tested (`src/intent_engine/founder_intelligence/`, 42 tests). |
| **CONTROLLED DEMO READY** | **Yes.** The deterministic synthetic demo company runs end to end and renders an openable HTML result page. |
| **DEPLOYMENT READY** | **No.** No web server, no authentication, no live ingestion (Gaps 1, 3, 4 in `docs/T0235_DEPENDENCY_GAPS.md`). |
| **PUBLICLY DEPLOYED** | **No.** |
| **LAUNCHED** | **No.** |

## What was actually used (stated plainly)

- **Any live data source used?** **No.** No external network call was made.
  The experience runs on the deterministic demo fixture and on
  founder-approved pasted/uploaded input; live company-website ingestion is
  a recorded dependency gap.
- **Any external network call?** **No.**
- **Authentication exists?** **No** — local/demo mode only.
- **Deployed / publicly accessible / launched?** **No** to all three.
- **Any test expectation changed?** Only the once-per-session
  `test_pick_next_task` marker (unchanged this session — the numbered queue
  was already terminated at T023; T023.5 is a version-roadmap milestone,
  not a `## T0NN` heading). No other expectation changed.
- **Any T019–T023 source file changed?** **No** — the frozen-foundation
  diff is empty (asserted in the completion gate).
- **Marketing/Growth systems touched?** **No** — not exposed, not modified.
  Reserved for V2.0.
- **Trading/market-intelligence training verified as running?** **No** —
  not claimed. Any unsupported market statistic renders UNAVAILABLE.

---

## The trust sequence (proven by test)

The completed result follows the exact product order, and no perspective
section precedes Proof of Understanding (`assert_trust_sequence`):

1. Company Understanding — every field cited, external-view qualified
2. Evidence and Analytics — unavailable ≠ zero; conflicted preserved
3. What Stood Out — one supported hook (or an honest "not enough evidence")
4. Market View — company vs. market language, no causality added
5. Possible Blind Spots — each with an alternative explanation + a question
6. Assumptions We Would Investigate — never declared false
7. Executive Attention — owner order preserved, no combined score
8. Executive Confidence — known / partial / disagree / cannot-determine
9. What We Do Not Believe Yet — first-class skepticism
10. Leadership Questions — traceable, supportive
11. Competitors — OUT_OF_SCOPE (Gap 2), never invented
12. Opportunities — observed / hypothesis / decision-ready kept distinct
13. Conversation — the T023 closed-ClaimSet chain, run-scoped

## The refusals (each proven by test)

Unsupported insight → fewer, not filled. Invented statistic → rejected
(closed ClaimSet). Unsupported causality → rejected. Wrong-company identity
→ stopped, not merged. Internal/loopback/private URL → rejected before
retrieval. Competitor invention → OUT_OF_SCOPE. Hidden action (publish /
email / change homepage / launch) → no surface exists. Cross-company
leakage → isolation asserted. Confidence laundering → CONFLICTED preserved,
never averaged. Stale evidence → labelled, never shown as current.

## Governing product properties (proven by test)

Every present insight resolves to SourceClaims → SourceRefs; the store
subclasses the kernel; no domain intelligence is computed in the package;
no unrestricted URL retrieval exists; no company master score exists
anywhere; presentation computes nothing; Marketing/Growth are untouched.

---

## Remaining launch infrastructure (honest)

- A web server + hosting (Gap 4).
- Authentication + per-user run index (Gap 3).
- A founder-approved, SSRF-safe live fetcher + company-source parser (Gap 1).
- A signed share-token system (Gap 4).
- A real-browser acceptance pass once a server exists (Gap 5).

The next human-controlled milestone is **V2.0 — Founder Growth Studio**
(NEEDS HUMAN START): reuse the existing Marketing/Growth foundations to
market and grow this product through an evidence-backed, approval-gated
Creative Strategy Loop. V2.0 is internal, product-specific, proposal-first;
the external execution layer (V2.5) remains separate.
