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
