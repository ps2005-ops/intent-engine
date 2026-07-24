# V1.1 — Approved Live Company Analysis

Built 2026-07-23 (human-started). The smallest safe, evidence-backed
path from a real public domain to a useful outside-in report: the user
enters a company, reviews a bounded list of discovered public pages,
explicitly approves the exact source set, and receives a report in
which every major claim resolves to real retrieved source material.

## Statuses (never collapsed)

| Status | Value |
|---|---|
| CODE BUILT | YES |
| REAL-DOMAIN ANALYSIS | **CODE READY; live in-product network acceptance PENDING.** The pipeline analyzed recorded copies of real pages, not live domains through the deployed application. That proves parsing, provenance, report composition, isolation, and source handling — it does not yet prove that real websites work reliably from the eventual hosting environment (TLS variance, redirects in the wild, slow/huge pages, real DNS). |
| MANUAL REAL-COMPANY ACCEPTANCE | RECORDED-PAGE PASS for 3 companies (docs/V11_REAL_COMPANY_ACCEPTANCE.md); **live acceptance PENDING** — it is next-human-action #1 and gates any early-user use |
| CONTROLLED EARLY-USER READY | Pending live network acceptance (auth/ownership/isolation proven in-repo) |
| STAGING DEPLOYED | NO (EXTERNAL HUMAN ACTION) |
| PUBLICLY DEPLOYED | NO |
| PUBLICLY LAUNCHED | NO |

## What is built / not built

- Synthetic demo: available for regression and demonstration (banner permanent)
- Real-domain analysis: **BUILT**
- Arbitrary public-domain intake: **BUILT** (validated, SSRF-walled)
- Same-domain approved retrieval: **BUILT** (bounded discovery, explicit approval, ≤10 sources/run)
- External approved sources: **BUILT for pasted evidence**; external URL approval recorded as gap (per-URL external fetch approval UI not yet built)
- Uploads: **NOT BUILT** (dependency gap — no safe document parser)
- Pasted evidence: **BUILT** (labelled, authorized, secret-scanned)
- Public deployment: NO · Public launch: NO

## Flow

```
validate domain (scheme/host/IP/port/credentials + DNS public-address check)
→ bounded discovery (1 homepage fetch, ≤20 links + ≤10 known paths, ≤20 shown)
→ source review page (type, origin, why useful; nothing pre-fetched)
→ explicit approval (immutable, consent-versioned, owner-checked, ≤10)
→ safe retrieval (manual redirect revalidation, size/time/MIME caps,
  no cookies/auth/JS, honest failures, idempotent by content)
→ parsing (title/meta/headings/text, boilerplate dedupe, hash, parser
  version, modified-date staleness)
→ deterministic claims (quotes verified verbatim, real SourceRefs,
  no-synthetic invariant) → Founder Intelligence composition (unchanged)
→ report: executive overview (≤250 words, every sentence → ClaimSet),
  evidence library (grouped, deduped, failures listed), trust sequence,
  conversation over the run's ClaimSet only
```

## Model boundary

Zero model calls in V1.1 extraction — all claims are deterministic
composition over retrieved text. The bounded `ExtractionCandidate`
contract from the prompt is recorded as available future work; nothing
model-generated ships in this milestone.

## Foundation changes (justified, separate commits)

One narrowly additive change to `personal/records.py`
(`assert_workspace_language`): quoted spans are excluded from the
banned-language scan, because the wall must not erase accurate quoted
evidence (real titles contain words like "Best"). Behavior preserved
for all unquoted text; targeted regression in
`tests/test_personal_language_wall_quotes.py`; committed separately
(`e602838`).
