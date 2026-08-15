# BATCH 20 — PRE100 completion run · LIVE DEFECT BOARD

Starting state: founder `947062b` (both branches) · market `9b01ff1` ·
production `cfd4c3b` untouched · deployed SHA verified `947062b`.

ACQUISITION_PRE100_FROZEN = TRUE (honored; see D3 note).

## §4 LIVE BROWSER JOURNEY — the bottleneck named in batch 19 is CLEARED

Driven through the real browser against the deployed preview, guest session,
real CSRF. Company name only, website blank.

    landing -> analyse -> progress -> analyses -> brief/slides/full

Identity resolved correctly to **Cloudflare, Inc.** from the bare name with no
website. Market bridge live (58.4% 1y, +38.0pp vs S&P, 58% annualised vol,
-37% drawdown). Macro exposure renders real transmission chains. The strategic
read is REFUSED, honestly, and the refusal is legible.

## DEFECT BOARD

| ID | Sev | Surface | Live repro | Root cause | Status |
|----|-----|---------|-----------|------------|--------|
| D1 | SEV2 | /analyze error page | Submit without consent | A validation error ("consent is required") renders the generic fault page, which asserts "This is a fault in the product, not in what you entered" — the opposite of the truth | OPEN |
| D2 | SEV2 | /brief "What this was built from" | "Another registrant's filing — none" with no coverage state anywhere on the page | Producer reached the provenance drawer only; the brief's report never carried `discovery_coverage` | **FIXED** |
| D3 | SEV2 | evidence yield | Live run retrieved 0 third-party filings; offline the same company yields 3 | Not yet diagnosed. NOT reopened: acquisition is frozen, and D2's fix makes the run state itself say which of NOT_RUN / BLOCKED / EXHAUSTED it was. Diagnose from the live sentence, not by re-sweeping | OPEN |
| D4 | SEV3 | /brief "What changed, and when" | Three items all dated 2026-08-15 (today) | Observation time inheriting retrieval time | OPEN |
| D5 | SEV3 | /slides | 7 slides, not the 13-slide story | Presentation not yet built to spec | OPEN |

## §3 ASYNC TEST — REPAIRED
`elapsed < 2.0` replaced with the actual property: the worker is held on a
latch the test controls, and the handler must answer while it is still held.
A synchronous handler cannot pass; no duration is measured. 38 pass.

## NOT DONE
Hydration, economic history, second-iteration, X-Ray polish, Full Analysis,
Presentation, CEO Q&A, Personal AI integration, acceptance, security,
zero-Anthropic, live iterations 2-9.
