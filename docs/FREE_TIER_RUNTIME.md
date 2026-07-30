# Free-Tier Hosted Runtime — Operating Model & Manual Actions

**PAPER TRADING — SIMULATED — NO REAL MONEY.** This runtime never touches real
money and has no live-trading endpoint anywhere. `ALPACA_PAPER_BASE_URL` is
validated paper-only in code; a live host aborts the job.

This document explains how the Intent Engine runs **without an always-on paid
Render instance**, and lists the exact steps only *you* (the account owner) can
do. No secret value is ever requested in chat or stored in the repo.

---

## 1. The operating model

| Concern | Where it runs | Why |
|---|---|---|
| Dashboard + Personal AI | **Render FREE web service** (UI only, may sleep) | Reads the durable DB fresh each request; recovers cleanly after sleeping. Runs no scheduler, places no trades. |
| The daily/weekly/monthly cycle | **GitHub Actions** (a fresh runner per job) | Free scheduled compute. Each job connects to the durable DB, does bounded work, exits. |
| Simulated orders & positions | **Alpaca PAPER** | Alpaca holds/updates paper orders through the day; the engine does not need to stay running. |
| All runtime truth | **Durable Postgres** (`DATABASE_URL`) | Survives fresh runners and Render restarts. Local dev uses SQLite automatically. |

Because scheduling lives in GitHub Actions and truth lives in Postgres, **Render
sleeping on the free plan does not interrupt anything.**

### The daily cycle (jobs → workflows)

| Step | GitHub workflow | CLI job |
|---|---|---|
| Research companies (bounded, leakage-checked) | `company-intelligence-refresh` | `company-intelligence-refresh` |
| Generate bounded predictions | `daily-prediction-generation` | `daily-prediction-generation` |
| Convert eligible predictions → Alpaca paper orders | `paper-order-submit` | `paper-order-submit` |
| Mid-session order/position sync | `intraday-paper-reconciliation` | `intraday-paper-reconciliation` |
| After close: fills/positions/equity + score + candidates + report | `after-close-reconciliation-and-learning` | `after-close-reconciliation-and-learning` |
| Resolve predictions whose horizon completed | `prediction-resolution` | `prediction-resolution` |
| Synthetic Worlds from real failures | `synthetic-daily` | `synthetic-daily` |
| Weekly walk-forward evaluation (human-gated) | `weekly-evaluation` | `weekly-evaluation` |
| Monthly promotion packet (human-gated, prepares only) | `monthly-promotion-review` | `monthly-promotion-review` |

Every workflow also has a **“Run workflow” button** (`workflow_dispatch`) with an
optional `as_of` date, for manual testing. Jobs are **idempotent** and
**catch-up**: a re-run never double-orders or loses a record, and a skipped run
is recovered by the next.

Run any job locally against your DB:
```bash
DATABASE_URL=postgresql://… python -m intent_engine.hosted <job> [--as-of YYYY-MM-DD]
```

---

## 2. MANUAL ACTIONS REQUIRED FROM PRATHAM

Do these once. **Never paste a secret value into chat** — enter each secret only
in the provider’s own dashboard (GitHub / Render / Alpaca).

### A. Create the Alpaca **paper** account
- **Why:** the simulated broker that holds orders/positions through the day.
- **Where:** <https://alpaca.markets> → sign up → switch to **Paper Trading** →
  **Generate API Keys** (the paper key pair).
- **You get:** an API Key ID and Secret Key. The base URL is
  `https://paper-api.alpaca.markets`.
- **Verify:** run the on-demand **“Verify Alpaca paper config”** GitHub workflow
  (below) — it authenticates read-only and prints `account_type: PAPER`.
- **Cost:** free. **Free alternative:** none needed (already free).

### B. Add the Alpaca paper secrets to GitHub
- **Why:** the workflows read them as encrypted secrets.
- **Where:** your repo → **Settings → Secrets and variables → Actions → New
  repository secret**.
- **Secrets (names must match exactly):**
  - `ALPACA_PAPER_API_KEY`
  - `ALPACA_PAPER_SECRET_KEY`
  - `ALPACA_PAPER_BASE_URL` = `https://paper-api.alpaca.markets`
- **Verify:** run **verify-alpaca** (Actions tab → *Verify Alpaca paper config* →
  Run workflow). Expect `RESULT: PASS`.
- **Cost:** free.

### C. Set market-data + LLM secrets
- **Why:** Tiingo = prices (resolution/marks); FRED = macro/regime; Anthropic =
  prediction/research generation.
- **Where:** same GitHub Actions **Secrets** page.
- **Secrets:** `TIINGO_API_KEY`, `FRED_API_KEY`, `ANTHROPIC_API_KEY`.
- **Get keys:** Tiingo <https://www.tiingo.com> (free tier), FRED
  <https://fred.stlouisfed.org/docs/api/api_key.html> (free), Anthropic
  <https://console.anthropic.com> (paid per use).
- **Verify:** run `prediction-resolution` on demand once you have positions; it
  will fetch prices. **Cost:** Tiingo/FRED free; Anthropic pay-per-use (bounded
  by the budgets in step F).

### D. Choose & configure durable Postgres
- **Why:** the single source of runtime truth; must outlive fresh runners.
- **Recommended (free, durable, no expiry):** **Neon** <https://neon.tech> →
  create project → copy the **connection string** (`postgresql://…`).
  Alternatives: **Supabase** (free) or **Render Postgres** (free tier *expires
  after 90 days* — fine for a trial, not for long-term).
- **Add the secret:**
  - GitHub Actions secret **`DATABASE_URL`** = your Postgres connection string.
  - Render env var **`DATABASE_URL`** = the *same* string (Render dashboard →
    your web service → **Environment**).
- **Verify:** `DATABASE_URL=… python -m intent_engine.hosted db-health` →
  `"ok": true, "backend": "postgres"`. (Locally with no `DATABASE_URL` it uses
  SQLite and still reports `ok`.)
- **Cost:** Neon/Supabase free tiers are sufficient. **Migrations** are automatic
  (the schema is created on first connect; safe to re-run).

### E. Select the initial company universe
- **Why:** who the engine researches, predicts, and (for public/tradable ones)
  paper-trades.
- **Default seed:** Shopify (SHOP), Cloudflare (NET), Duolingo (DUOL) — three
  structurally different public companies — plus one **private** company (Stripe,
  never traded) and one **labelled proxy** (IPAY). Defined in
  `src/intent_engine/universe/companies.py::default_universe`.
- **To change it:** edit `default_universe()` (or write your own and save it via
  `UniverseStore(store).save(my_universe)`). Class invariants are enforced —
  a private company can never be made tradable.
- **Verify:** open `/hosted` on the web service, or `db-health` after the first
  `company-intelligence-refresh`. **Cost:** free.

### F. Configure daily budgets (in Canadian dollars)
- **Why:** hard caps so LLM/research spend can never run away.
- **Where:** GitHub repo → **Settings → Secrets and variables → Actions →
  Variables** (not secrets — these are non-sensitive).
- **Variables (all optional; safe defaults shown):**
  - `PREDICTION_GENERATION_ENABLED` = `true`
  - `DAILY_LLM_BUDGET_CAD` = `5`
  - `MAX_DAILY_LLM_CALLS` = `200`
  - `MAX_COMPANIES_PER_DAILY_REFRESH` = `25`
  - `MAX_SOURCES_PER_COMPANY` = `8`
  - `SYNTHETIC_DAILY_BUDGET_CAD` = `1`
  - `SYNTHETIC_WEEKLY_BUDGET_CAD` = `3`
- **Behaviour when a cap is hit:** the job stops safely and persists the skipped
  work (shown on the dashboard); it never issues unbounded retries.
- **Verify:** `/hosted` shows budget usage/remaining. **Cost control:** this *is*
  the cost control.

### G. Enable the scheduled workflows
- **Why:** GitHub disables scheduled workflows on a new/forked repo until enabled.
- **Where:** repo **Actions** tab → if prompted, click **“I understand… enable
  workflows”**. Each workflow then runs on its cron (and via Run workflow).
- **Verify:** the Actions tab lists all nine workflows. **Cost:** GitHub Actions
  free minutes are ample for these short daily jobs.

### H. Run the first workflow manually
- **Where:** Actions → **company-intelligence-refresh** → **Run workflow** (leave
  `as_of` blank). Then run **daily-prediction-generation**, then
  **paper-order-submit**.
- **Verify:** each run is green; open `/hosted` — companies show research
  freshness and a latest prediction.

### I. Confirm the first paper order
- **Where:** after `paper-order-submit`, check the Alpaca **paper** dashboard
  (Orders) *and* `/hosted` (Alpaca reconciliation → open/filled orders).
- **Verify:** an order exists for a public/tradable company; **no order exists
  for the private company** (Stripe).

### J. Confirm after-close reconciliation
- **Where:** run **intraday-paper-reconciliation** then
  **after-close-reconciliation-and-learning** (or wait for their crons).
- **Verify:** `/hosted` shows filled orders, marked positions, and an equity
  snapshot.

### K. Confirm the nightly company-learning report
- **Where:** after **after-close-reconciliation-and-learning**, open `/hosted`
  (Latest report) or query the `daily_report` stream.
- **Verify:** the report’s `as_of` is today and it lists per-company rows.

### L. Check that Render sleeping does not interrupt the workflow
- **How:** let the Render free service sleep (no traffic ~15 min), then run any
  GitHub workflow on demand. It completes normally (it never touches Render).
  Re-open `/hosted`: it loads fresh from Postgres (the wake may take a few
  seconds on free tier).
- **Verify:** the workflow run is green while Render was asleep; the dashboard
  reflects the new data after waking.

### M. Rotate credentials
- **When:** on any suspected exposure, and periodically.
- **How:** regenerate the key in the provider (Alpaca / Tiingo / FRED / Anthropic
  / Postgres), then update the matching GitHub secret and Render env var. Delete
  the old key at the provider. Errors are redacted before any persistence, so a
  leaked-key-in-URL never lands in the DB or dashboard.

---

## 3. FINAL STANDARD — honest evidence

| Requirement | Status | Evidence |
|---|---|---|
| Render free sleeping doesn’t stop scheduled execution | **Architecturally guaranteed** | Scheduler is GitHub Actions; truth is Postgres. Render is UI-only (`render.yaml` `plan: free`, no disk, no scheduler). *Final proof needs your Render+GitHub accounts (step L).* |
| GitHub Actions runs jobs independently | **Built** | 9 workflows + reusable runner (`.github/workflows/`), each `python -m intent_engine.hosted <job>`. *Green runs need your secrets.* |
| Alpaca retains/reports paper orders through the day | **Built + tested (fake)** | `paper/broker.py` (real + fake), reconciliation jobs; `test_paper_broker.py`, `test_paper_execution.py`. *Live paper proof needs your Alpaca keys (steps A/B/I).* |
| Durable state survives fresh runners + Render restarts | **Built + tested** | `storage/durable.py`; `test_storage_durable.py::test_persistence_survives_new_store_instance`. |
| Company-specific predictions & outcomes linked | **Built + tested** | `predictions/`, `universe/learning.py`; acceptance test links prediction→order→outcome→scoring. |
| Nightly learning reports created | **Built + tested** | `hosted/reports.py`; acceptance test asserts a report is written. |
| Cross-company learning preserves company-specific evidence | **Built + tested** | `universe/learning.py`; requires ≥2 supporting companies, records contradictors; `test_predictions_learning.py`. |
| No private company generates a direct stock trade | **Built + tested (enforced invariant)** | `universe/companies.py` (`may_generate_order`), execution backstop; acceptance test asserts Stripe never orders. |
| No live-money endpoint exists | **Built + tested** | `assert_paper_only` rejects the live host; `test_paper_broker.py`. |
| All production-rule changes remain human-gated | **Built + tested** | Candidates/eval/packets never auto-promote; `promote()` is human-only; acceptance test asserts `promoted == 0, human_gated`. |

**Test evidence:** 48 new tests across storage, broker, universe, execution,
predictions/learning, the full **section-18 acceptance test** (3 public + 1
private, injected fakes, no network), dashboard, and bootstrap/synthetic — all
green, and the full offline suite (**1915 passed**) with no regressions.

## 4. Honestly NOT done in this pass (needs your accounts, or deferred)
- **Live production verification** (a real Postgres, real Alpaca paper fills, a
  real GitHub-Actions green run, a real sleeping-Render check) — blocked on your
  accounts; steps A–L are the exact path.
- **Real LLM research/prediction adapters** are placeholders (return “no signal”
  until wired), so with generation on but no adapter the loop simply makes no new
  predictions — safe. The deterministic fakes prove the wiring end-to-end.
- The legacy file-based stores (prediction/learning ledgers) still exist for
  local/dev; the hosted cycle runs on the durable store. Converging them fully is
  future work, not required for this model.
