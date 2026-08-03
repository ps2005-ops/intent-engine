# Founder Intelligence — continuation checkpoint

**Written 2026-08-03.** Branch `feat/founder-decision-experience-v3`,
checkpoint commit `1047159`, deployed and verified on
<https://intent-engine-preview-v3.onrender.com>.

Everything below was MEASURED on the deployed preview, not inferred. Re-verify
before relying on it — the last three handoffs each contained at least one
claim that did not hold.

---

## 1. What changed this cycle

`ANTHROPIC_API_KEY` reached the preview. `/readyz` now reports
`strategic_reasoning: true`, `reasoning_key_present: true`.

**The rich path works.** Palantir (run `01KZ33Y7ENT5VVPK1RHG98WHVX`, then
`01KZ34ND26JPD4QWCV4RN7QY8X`) produced a real grounded result — thesis,
mechanism, decision, falsifiers, 8–10 evidence citations — across all seven
layers:

| layer | words | state |
|---|---|---|
| `/runs/{id}` (60-second brief) | 212 | rich |
| `/dashboard` | 518 | rich |
| `/story` | 559 | rich |
| `/brief` (executive) | 305 | **under target** |
| `/slides` | 628 | rich |
| `/full` | 880 | rich |
| `/sources` | 212 | rich |

Fixed and deployed this cycle: citations rendered internal identifiers
(`obs-src-eb15293b7148`) instead of page names. Now verified live showing
"About Palantir", "Palantir Foundry", "Gotham | Palantir" with link targets
unchanged. Gate: `tests/test_citations_are_readable.py` (5 tests; all 5 fail
if the wiring is reverted).

---

## 2. Defects MEASURED on the rich path, not yet fixed

These were invisible before the key existed. Each is a real observation from
the Palantir runs above.

### 2.1 Executive brief is under its own stated minimum
The page prints `191 words (target 500–900)` and the mission asks for
600–1,000 on rich results. Sections are being omitted rather than padded —
which is the correct instinct — but the result is a brief thinner than the
story above it. **Do not fix by padding.** The likely real cause is the
dedup ledger: the executive brief is built with a ledger already loaded with
the 60-second brief's sentences, so on a company where the two overlap it has
little left to say. Start at `_limited_brief`/`build_executive_brief` in
`src/intent_engine/founder_brief/layers.py`.

### 2.2 "Why this matters" renders a noun fragment
Live text: `Why this matters — how much to invest ahead of the transition`.
This is the exact fragment the mission names as a reject. It is a noun phrase,
not a consequence. The `so_what` field is being populated with a decision
topic rather than an implication. Fix at the source that fills `key_insight.so_what`,
and gate it — a `so_what` that does not contain a verb phrase asserting a
consequence should be withheld, not shown.

### 2.3 `<style>` blocks sit inside `<main>`
`LAYER_CSS` is emitted inside the `<main>` element on the dashboard/story/
brief layers, so it appears in `main.innerText` extraction. Not visible to a
reader, but it pollutes any text-based gate and is invalid placement. Move
the CSS into `<head>` or before `<main>`.

---

## 3. Credentials — exact state

| key | preview | local `.env` | consequence |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **present** | present | rich path works |
| `TIINGO_API_KEY` | unverifiable from outside | **present** | producer can run locally |
| `FRED_API_KEY` | unverifiable from outside | **absent** | macro (§6) blocked |

`/readyz` reports nothing about Tiingo or FRED. **First task next session:**
add presence booleans for both, following the exact precedent of
`reasoning_key_present` (booleans only, values never read). Without that,
§1.7 cannot be verified at all.

Owner action if FRED is wanted:
```
Render Dashboard → intent-engine-preview-v3 → Environment
  → Add FRED_API_KEY → Save Changes → wait for redeploy
```
FRED is also needed **locally** to generate any macro fixture.

---

## 4. Market data — the exact remaining gap

The ticker step is solved (commit `2b2e437`): listings resolve from the SEC
registrant table. Verified live — Tesla → TSLA/Nasdaq, Costco → COST/Nasdaq.

The next link is **not** wired:

- Producer: `export_company(ticker=, exchange=, closes=, benchmark_closes=,
  as_of=)` and `write_export(payload, root=)` in
  `~/intent-engine-market/src/intent_engine/market/intelligence_export.py`.
- **`export_company` does not fetch prices.** It takes `closes` as input.
  Prices come from `get_prices(...)` in
  `~/intent-engine-market/src/intent_engine/core/market_resolution.py`, which
  requires `TIINGO_API_KEY`.
- Consumer: `WebApp._market_snapshot` reads
  `{runtime_root}/reports/market/export/{TICKER}.json`.

**The deployment problem to solve first:** the preview has ephemeral storage
and runs only what is in the repo. It never runs the producer. So exports must
either be committed as intentionally sanitized fixtures, or generated at
runtime on the preview (needs new code plus Tiingo on Render). Decide this
before writing code — it is the actual design question, not the producer call.

`_assert_sanitized` in the producer already rejects forbidden keys, so the
sanitization requirement is enforced upstream; do not re-implement it.

---

## 5. Not started

§7 shared "So what?" contract · §10 slides audit · §12 full-analysis cleanup ·
§13 Q&A via `POST /conversation` · §14 citation walk beyond Palantir ·
§15 full 21-company matrix (3 companies run) · §17 break-proofs 3,4,6,7,8,10,
11,12 · §20 human review pack.

Break-proofs already proven and passing: #1 (listed-as-private,
`tests/test_public_private_rendering.py`, 6 fail on revert), #2 (identical
bounded output, `tests/test_bounded_is_company_specific.py`, 9 fail on
revert), #9-adjacent (citations, 5 fail on revert).

---

## 6. Invariants to preserve

Full suite 3117 passed / 14 skipped (4 + 10 deselected under hooks); guard
EXIT=0. All 14 skips are environmental and explained: 6 Anthropic-live,
2 Tiingo, 1 FRED, 1 Google Calendar, 4 fixture-logic.

`env="test"` must never reach the network — both the analyst client and the
SEC ticker map are gated on it. Preserve that when adding Tiingo or FRED.

PR #14 stays **draft**. Production stays on `119d345`. Do not merge.
