# V1.1 — Manual real-company acceptance

Three real public companies were analyzed end-to-end through the full
pipeline (create run → bounded discovery → explicit approval → retrieval
→ parsing → claims → Founder Intelligence composition) on 2026-07-23 by
the manual reviewer, runner: `scripts/v11_real_company_acceptance.py`.

**Environment honesty.** The build/test sandbox's egress policy blocks
arbitrary in-process HTTP (proxy CONNECT 403 for non-allowlisted
domains), so the pipeline ran over **recorded real pages**: verbatim
titles, meta descriptions, and key visible sentences retrieved
2026-07-23 from the live sites via the environment's permitted fetcher.
No access control was bypassed; no evasion was attempted.

**Status precision: this is a RECORDED-PAGE PASS, not live acceptance.**
It proves parsing, provenance, report composition, isolation, and
source handling over genuine page content. It does NOT prove that real
websites retrieve reliably from the eventual hosting environment (live
TLS, real DNS, redirects in the wild, slow or oversized pages,
anti-bot behavior). Real-domain readiness is therefore **CODE READY;
live in-product network acceptance PENDING** — re-running this
acceptance against the live sites through the deployed application is
step 1 of the next human actions and gates early-user use.

No company endorsed these reports. No outreach occurred.

---

## 1. Plausible Analytics — plausible.io

- Run ID: recorded per execution (e.g. `01KY8R69RH…`; deterministic per store)
- Approved sources (2 pages + 1 pasted): `https://plausible.io`,
  `https://plausible.io/about`, pasted public DHH post (labelled
  user-provided public excerpt)
- Successful: 3 · Failed: 0 · Report: COMPLETE
- Major supported observations (manually verified against sources):
  identity and offering quoted verbatim from real title/meta ✓; value
  proposition = real homepage H1 ✓; site language "analytics, cookies,
  data, privacy" accurate ✓; complicating evidence: external post
  emphasizes "reliable", homepage does not — accurate and useful ✓
- Incorrect/rejected candidates: an earlier divergence claim surfaced
  function-word noise ("been", "domains"); fixed by stopword curation
  and meta-aware divergence *before* acceptance, not by rewriting prose
- Verdict: **PASS** — identity correct, description materially correct,
  every quote exists in source, no synthetic refs, no invented numbers
- Remaining limitation: only 2 site pages approved; pricing claim
  conservative (pricing lives on the homepage, not a /pricing page)

## 2. Fathom Analytics — usefathom.com

- Approved sources: `https://usefathom.com`,
  `https://usefathom.com/pricing`, pasted public Huberman Lab
  testimonial (labelled)
- Successful: 3 · Failed: 0 · Report: COMPLETE
- Major supported observations: identity/offering/value proposition all
  directly observed ✓; public pricing page correctly detected and
  quoted ✓; outcome language "simple, insight, privacy, compliance" ✓
- Incorrect/rejected candidates: the external-gap claim retains some
  term noise from the short excerpt ("pleasure", "compared") — recorded
  as a WEAK claim; future improvement: minimum corpus size before
  term-frequency claims (dependency gap, non-blocking)
- Verdict: **PASS with noted weak claim** — nothing false, one
  low-value observation

## 3. Transistor.fm — transistor.fm

- Approved sources: `https://transistor.fm`,
  `https://transistor.fm/about`, pasted public Product Hunt review
  (labelled)
- Successful: 3 · Failed: 0 · Report: COMPLETE
- Major supported observations: identity quotes the real title
  (including "Best…", correctly allowed as quoted source material, not
  workspace voice) ✓; offering from real meta ✓; external evidence
  emphasizes "simple, reliable, tool, customer" vs homepage
  distribution-focused language — a defensible, evidence-backed
  difference ✓
- Incorrect/rejected candidates: an earlier divergence flagged "real,
  support" although the homepage meta says "real human support" —
  caught in manual review and fixed by including title/meta terms in
  the homepage-emphasis set before acceptance
- Verdict: **PASS** — the earlier borderline claim no longer appears

---

## Founder-report quality gate (§37) — checked on all three

Company identity correct ✓ · product description materially correct ✓ ·
visible customer supportable ✓ · zero synthetic evidence (subsystems ==
{company_ingestion}) ✓ · ≥1 observation uses two distinct real sources ✓
· every quoted phrase exists in retrieved text (enforced by
`assert_quotes_exist`) ✓ · no numerical claim beyond quoted source text ✓
· no causal claim ✓ · no invented competitor (OUT_OF_SCOPE) ✓ ·
executive overview readable, ≤250 words, limitation named ✓ · report
states its scope once ✓
