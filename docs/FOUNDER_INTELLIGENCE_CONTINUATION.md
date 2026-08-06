# Founder Intelligence — continuation checkpoint

**Updated 2026-08-03.** Branch `feat/founder-decision-experience-v3`,
checkpoint commit `8810aaf`, deployed and verified on
<https://intent-engine-preview-v3.onrender.com>.

Everything below was MEASURED on the deployed preview. Re-verify before
relying on it.

---

## 1. Status

`/readyz`: `strategic_reasoning: true`, `reasoning_key_present: true`.
**The rich path works.** Full suite 3131 passed / 14 skipped, guard EXIT=0.

Fixed and verified live this cycle:

| defect | evidence before | after |
|---|---|---|
| citations showed internal ids | `obs-src-eb15293b7148` ×8 | "About Palantir", "Palantir Foundry", … |
| "Why this matters" was a noun fragment | `how much to invest ahead of the transition` | real consequences (Microsoft, Adobe) |

Gates: `tests/test_citations_are_readable.py` (5),
`tests/test_so_what_is_a_consequence.py` (14). Both fail on revert.

---

## 2. THREE OPERATIONAL FACTS THAT INVALIDATE NAIVE MATRIX RUNS

Learned the hard way this cycle. Read before running the matrix again.

### 2.1 Runs do NOT survive a deploy
Storage is ephemeral (`/readyz` says so). A Tesla run started before a deploy
returned **"Not found"** afterwards. **Run the matrix only after the final
deploy of the session**, or every result is lost.

### 2.2 Runs are idempotent per (domain, user, day)
`create_run` derives a stable id from `ci-run:{domain}:{user_id}:{as_of}`.
Re-submitting Shopify returned the **identical run id** and its previous
failed result — not a fresh analysis. To get a genuinely fresh run for a
company already analysed today, start a **new guest session** (`POST /demo`)
so `user_id` differs. "Do not reuse old runs" is otherwise impossible to
satisfy.

### 2.3 Concurrent analyses throttle each other into false failures
Eight analyses launched back-to-back: the first four largely succeeded, the
last four all returned "no approved source could be retrieved" — including
Shopify, a curated company that succeeds when run alone. This is a
single-instance free-tier artifact, **not** a product defect. Space runs out
and run them sequentially, or the matrix measures the harness rather than the
product.

---

## 3. Matrix so far (commit `8810aaf`)

| company | state | note |
|---|---|---|
| Palantir | RICH | thesis, mechanism, decision, 8 named citations |
| Microsoft | RICH | 251 w, "So what?" is a real consequence |
| Adobe | RICH | 320 w, bounded-but-useful framing, real consequence |
| Tesla | BOUNDED (legitimate) | see §4 |
| Datadog, Cloudflare, NVIDIA, Costco, Shopify, Stripe | INVALID | hit §2.3 — re-run sequentially |

Not yet run: Amazon, Apple, Meta, Alphabet, ASML, Toyota, private company,
small business, sparse company, interrupted run.

---

## 4. Tesla/NVIDIA/Costco are bounded for a REAL reason — do not "fix" it

Tesla re-run with grounded reasoning **fully enabled** still returned a
bounded result: `3 page(s) read; 1 carried usable evidence`, because
`www.tesla.com` answers automated requests with HTTP 401/403 and only SEC
exhibits could be read. One usable source is below the evidence bar, so the
analyst is never invoked.

**This is the product legitimately choosing the bounded path.** The reasoning
key was never the constraint for these companies — retrieval is. Any future
cycle that treats "Tesla is not rich" as a reasoning defect is chasing the
wrong thing. The honest options are better retrieval (rendering, alternative
sources) or accepting a high-quality bounded result — which now exists.

---

## 5. Remaining known defects

### 5.1 Executive brief is under target
Prints `191 words (target 500–900)` on Palantir; the goal is 600–1,000 on
rich results. Sections are omitted rather than padded, which is the right
instinct, so **do not pad**. Likely cause: the brief is built with a dedup
ledger pre-loaded with the 60-second brief's sentences, leaving little to say
when the two overlap. Start at `build_executive_brief` in
`src/intent_engine/founder_brief/layers.py`.

### 5.2 `<style>` blocks sit inside `<main>`
`LAYER_CSS` is emitted inside `<main>` on the dashboard/story/brief layers, so
it appears in `main.innerText`. Invisible to readers, but it pollutes
text-based gates and is invalid placement. Move to `<head>`.

---

## 6. Credentials

| key | preview | local `.env` | consequence |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **present** | present | rich path works |
| `TIINGO_API_KEY` | unverifiable | **present** | producer can run locally |
| `FRED_API_KEY` | unverifiable | **absent** | macro blocked |

`/readyz` still reports nothing about Tiingo or FRED. **First task:** add
presence booleans for both, following the `reasoning_key_present` precedent
(booleans only, values never read). Until then §1.7 cannot be verified.

Owner action for macro:
```
Render Dashboard → intent-engine-preview-v3 → Environment
  → Add FRED_API_KEY → Save Changes → wait for redeploy
```
Also needed **locally** to generate any macro fixture.

---

## 7. Market data — the unanswered design question

Ticker resolution is solved (`2b2e437`, SEC registrant table; Tesla → TSLA/
Nasdaq, Costco → COST/Nasdaq, verified live). The next link is not wired:

- `export_company(ticker=, exchange=, closes=, benchmark_closes=, as_of=)` and
  `write_export(payload, root=)` in
  `~/intent-engine-market/src/intent_engine/market/intelligence_export.py`.
- **It does not fetch prices.** `closes` comes from `get_prices(...)` in
  `~/intent-engine-market/src/intent_engine/core/market_resolution.py`, which
  needs `TIINGO_API_KEY`.
- Consumer: `WebApp._market_snapshot` reads
  `{runtime_root}/reports/market/export/{TICKER}.json`.

**Decide before writing code:** the preview has ephemeral storage and runs
only what is in the repo — it never runs the producer. So exports are either
committed sanitized fixtures, or new runtime-generation code plus Tiingo on
Render. §2.1 means committed fixtures are the only option that survives a
deploy. `_assert_sanitized` already enforces forbidden keys; do not
re-implement it.

---

## 8. Not started

Shared "So what?" contract object · slides audit · full-analysis cleanup ·
Q&A via `POST /conversation` · citation walk beyond Palantir · break-proofs
4,6,7,8,10,11,12 · human review pack.

Break-proofs proven and passing: listed-as-private (6 fail on revert),
identical bounded output (9 fail), citations (5 fail), so-what fragment
(14 tests, incl. one pinned to the exact shipped string).

---

## 9. Invariants

`env="test"` must never reach the network — analyst client and SEC ticker map
are both gated on it. Preserve when adding Tiingo or FRED.

Demo limit is 10 analyses/IP/rolling hour (`demo_ip_analyses_per_hour`). It is
an abuse guardrail on a public URL — do not raise it to speed up testing.

PR #14 stays **draft**. Production stays on `119d345`. Do not merge.

---

# 2026-08-05 — filings became readable

Branch `feat/founder-decision-experience-v3`, deployed and verified on
`b6db86d`. Suite 3885 passed, guard EXIT=0. Production and PR #14 untouched.

## 10. THE DEFECT, AND WHY IT LOOKED LIKE SOMETHING ELSE

`parse_html` buffers character data only while a `_BLOCK` tag is open, and its
block set is the vocabulary of a hand-written page: `p`, `h1`-`h6`, `li`, `td`.
Datadog's 2025 10-K contains **zero** `<p>`, **zero** headings, **zero** `<li>`
— 1,878 `<div>` and 4,857 `<span>`. Every narrative paragraph was discarded and
only the 7,147 table cells survived: 25,787 characters of a 2,086,014-byte
document.

It was not truncation. The parser walked the whole document — the last text it
produced was the signature page — and threw away 93% of it. Three cycles read
that 25,787 as "the fetch stopped early" and went looking at byte caps and
document selection. **A short extract is not evidence of a short read.** Check
whether the tags carrying the text are in the block set before touching the
network layer.

| | before | after |
|---|---|---|
| Datadog 10-K extracted | 25,787 | 382,003 |
| sections located | 0 body | 1, 1A, 2, 3, 7, 7A, 8 |
| filing propositions | 0 | 9 (7 survive retention) |
| what a reader saw | company blog | Item 7 MD&A, cited to the 10-K |

## 11. RULES THAT NOW HOLD

**Filings are parsed by `company_ingestion/filing_text.py`, not `parse_html`.**
Gated on the document being served from EDGAR or already identified as a
filing. Ordinary pages are untouched — that separation is deliberate, and
`test_non_filing_extraction_is_unchanged` fails if it erodes.

**Extraction quality is explicit.** Nine states. "We retrieved the 10-K" and
"we can read the 10-K" were the same fact to every gate, which is how a cover
page travelled as an annual report for three cycles. `COVER_ONLY` is a claim
about volume, never about Item numbering — a 10-K/A carries only the items it
amends and is a complete read of itself.

**Retention is section-aware and every section gets an equal reserve first.**
Front truncation at 120,000 carries 4 of the 9 propositions the Datadog 10-K
supports; the equal-reserve allocation carries 7 under the same bound. Item 1
runs to 39,000 characters and Item 1A to 149,000 — either could eat the budget,
and neither may.

**Topical spans are funded from their own reserve.** Item 1A's reserve buys its
first 24,000 characters, so customer concentration and supplier dependency —
tens of thousands of characters in — are only reachable by looking for them.
Sharing one pool with the Items cost six of nine propositions when measured.

**A cross-reference is not a heading, and a heading is not a section.** "See
Part I, Item 1A" inside MD&A ended MD&A at 4,263 characters and labelled 23,410
characters of it as Risk Factors. A real heading starts its line. A 10-Q prints
"Item 2" twice and only one of them is MD&A.

**Which Item carries MD&A depends on the form.** 7 in an annual report, 2 in a
quarterly one. Read with the annual order a 10-Q reaches Financial Statements
and serves litigation boilerplate.

**Prose about the document is not prose about the company.** This is the one to
remember. Filtering a section's opening framing phrase by phrase does not
converge — removing one promotes the next, measured across five filers and
three deploys. Substance begins at the first real subheading; go there.

**Public identifiers are not credentials.** A cover page prints the commission
file number beside the IRS employer number and the naive card pattern matched
the pair, dropping a whole 8-K. Luhn separates the shape from the thing without
weakening detection.

**Say only what was established.** A registrant whose filing names the subject
is not thereby a competitor; it is "Another registrant's filing".

## 12. MEASURED THIS CYCLE

Extraction, seven filers, all `FULL_BODY_CONFIRMED` with all seven sections
except where noted:

| filer | raw | old | new |
|---|---|---|---|
| Datadog 10-K | 2,086,014 | 25,787 | 382,003 |
| Microsoft 10-K | 8,585,501 | 268,258 | 319,417 |
| Caterpillar 10-K | 6,100,469 | 71,013 | 428,519 |
| NVIDIA 10-K | 1,967,816 | 24,899 | 334,003 |
| Amazon 10-K | 1,968,342 | 33,724 | 279,996 |
| Caterpillar 2007 (pre-XBRL) | 619,098 | 30,304 | 97,845 |
| Shopify 10-K/A | 741,610 | 49,032 | 145,228 (partial, correctly) |

Edge cases classified correctly: EDGAR index → `INDEX_ONLY`; XBRL schema →
`XBRL_METADATA_ONLY`; 8-K → `FULL_BODY_CONFIRMED` (no Items, by design).

Deployed gate on `b6db86d`, sequential, fresh guest session each:

| company | outcome | first evidence |
|---|---|---|
| Datadog | FULL, 973 w | 10-K Item 7 — "Datadog is the AI-powered observability…" |
| Microsoft | FULL, 1,004 w | 10-K Item 7 — "Microsoft is a technology company…" |
| Shopify | FULL, 1,123 w | 10-K — "We believe we can help merchants of all verticals…" |
| Stripe | FULL, 831 w | another registrant's filing (see §13) |
| Constellation Software | WITHHELD, correctly | no SEC filings exist — TSX-only issuer |
| Caterpillar | BOUNDED, legitimately | caterpillar.com timed out; both filings read |

No raw `Bad Request` in any run. Dark and light both pass at 390 px: 42 text
elements, 0 below WCAG AA 4.5:1, `scrollWidth == 390` in both themes.

## 13. STILL OPEN

**Third-party filings surface the filer, not the mention.** Stripe's run cites
Infinite Group's 10-K and shows Infinite Group describing *itself*. The label
is now honest and the excerpt is no longer boilerplate, but the adapter should
return the span that names the subject. Start at `classify_mention`.

**A filings-shaped limitation is used where there are no filings.**
Constellation Software's withheld page says "the company's filings carry this,
so it is stated under legal obligation" as the minimum needed — for a company
with no SEC filings in the run. The template is unconditional.

**Not attempted this cycle:** the authenticated acceptance runner, the
20-company matrix, and the ≥90% useful-rate measurement. §5.1 (brief under
word target) and §5.2 (`<style>` inside `<main>`) are unchanged.
