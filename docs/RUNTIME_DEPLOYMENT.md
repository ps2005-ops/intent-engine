# Runtime deployment & operations

*Written 2026-07-24. Covers the unified-learning runtime: the market
learning loop, scheduler, config health, and the credential-independent
surfaces for synthetic / marketing / Personal AI. Real-money trading is
disabled everywhere; real external publication is disabled until you
explicitly enable and approve it.*

## What is now a real runtime path

| Capability | Before | Now |
|---|---|---|
| prediction → paper position | manual, none | `paper/eligibility.py` + `MarketRuntime.open_paper_from_predictions` (deterministic, provenance-complete, rejections persisted) |
| resolution | human-wired script | `MarketRuntime.resolve_and_link` — resolves due predictions, closes linked paper positions, emits `prediction.resolved` |
| daily learning candidates | none | `MarketRuntime.generate_daily_candidates` (paper losses + calibration drift) |
| weekly evaluation | interface only | `learning/evaluation.py` real expanding-window out-of-sample harness |
| monthly promotion review | none | `learning/promotion_packet.py` persisted packet (never auto-promotes) |
| scheduler | laptop launchd plist | `runtime/scheduler.py` in-process scheduler (cadence-aware, JobLock-guarded, restart-safe) on the always-on web service |
| config health | none | `runtime/config_health.py` preflight + persistent failure events |
| synthetic daily | manual | `python -m intent_engine.runtime synthetic-daily` |
| marketing publish | stopped at handoff | `marketing/publishing.py` dry-run adapter (real disabled) |
| marketing performance→learning | none | `marketing/performance.py` + shared-ledger bridge |
| operator UI | none | `/dashboard`, `/assistant`, `/status.json`, `/version` |

## Exact commands for local verification

```bash
cd intent-engine
python -m intent_engine.runtime preflight --root /tmp/ie        # config health
python -m intent_engine.runtime synthetic-daily --root /tmp/ie  # offline gym
python -m intent_engine.runtime integrity --root /tmp/ie        # data-integrity scan (exit 2 if issues)
python -m intent_engine.runtime health --root /tmp/ie           # job statuses
# market jobs FAIL LOUDLY without keys (by design — not a silent empty day):
python -m intent_engine.runtime market-open --root /tmp/ie
```

## Performance characteristics (measured)

At daily volumes (≈5–20 predictions/day) all jobs are sub-second. Measured on
a 200-record workload: runtime import ≈210 ms, open-200 ≈120 ms, integrity
scan ≈30 ms. `resolve` is ≈1.8 s per 200 because the append-only stores are
re-read per record (O(n²)); this is comfortably within a daily cadence but is
a **scaling limitation** to revisit only if backfilling thousands of records
at once — not before. The `/dashboard` runs a live integrity scan per view;
fine at current scale.

## Production health URLs

- `GET /healthz` — liveness
- `GET /readyz` — config + stores
- `GET /version` — `{app_version, commit}` (safe; no secrets)
- `GET /dashboard` — unified operations (login-gated)
- `GET /status.json` — machine status (login-gated)

## The exact commit to deploy

Deploy `origin/main` HEAD after this work is merged (printed at the end of
the delivery report). `/version` returns Render's `RENDER_GIT_COMMIT`, so you
can confirm the deployed commit equals the tested commit.

---

# MANUAL ACTIONS REQUIRED FROM PRATHAM

Each action is something only you (the account owner) can do. No secret value
ever needs to be shared with me or committed.

### 1. Deploy the Blueprint (one web service + disk; scheduler in-process)
- **Why:** the append-only stores live on a persistent disk. **Render disks
  attach to exactly one service and are never shared**, so the scheduled jobs
  run *inside* the web service (in-process scheduler) — not as separate cron
  services, which could not see the disk. One service owns the disk and the
  schedule.
- **Where:** Render dashboard → **Blueprints** → **New Blueprint Instance** →
  point at this repo (`render.yaml` is committed).
- **Env var:** `SCHEDULER_ENABLED=1` is set in `render.yaml` to turn the
  in-process scheduler on; the instance must be **always-on** (Starter+) or a
  sleeping Free instance never ticks.
- **Secret:** no.
- **Verify:** the service shows "Live"; `GET /version` returns the deployed
  commit; after a market day, `GET /dashboard` shows the daily job's
  last-success time and the scheduler markers (`status/scheduler.json`).
- **Cost:** one always-on web service (~$7/mo Starter) + disk (~$0.25/GB/mo).
  No extra per-cron cost — scheduling is in-process.
- **Free alternative:** a **GitHub Actions scheduled workflow** invoking
  `python -m intent_engine.runtime <job>` on a checked-out copy, committing the
  data root back (or syncing to a bucket). Trade-off: Actions has no
  persistent disk, so the data root must be committed/synced; the in-process
  scheduler on a paid always-on instance is simpler and is the recommended path.

### 2. Set the Tiingo API key
- **Why:** market prices for prediction resolution and paper marks; without
  it the daily market job fails loudly (no silent empty day).
- **Where:** Render dashboard → service **ie-daily-market** and
  **intent-engine-web** → **Environment** → Add.
- **Env var:** `TIINGO_API_KEY` — **secret: yes**.
- **Action:** paste the key from https://www.tiingo.com (free tier exists).
- **Verify:** `python -m intent_engine.runtime preflight` shows
  `TIINGO_API_KEY: unprobed` (present); the next `market-open` run succeeds.
- **Cost:** Tiingo has a **free** tier (rate-limited) sufficient for daily EOD.

### 3. Set the FRED API key
- **Why:** macro series (e.g. UNRATE) for level-rule predictions.
- **Where:** same services → Environment.
- **Env var:** `FRED_API_KEY` — **secret: yes**.
- **Action:** free key from https://fred.stlouisfed.org/docs/api/api_key.html
- **Verify:** preflight shows it present; `resolve` job succeeds.
- **Cost:** free.

### 4. (Optional) LLM key for the Synthetic Worlds `--live` leg
- **Why:** the offline synthetic gym needs no key; the live reasoning leg does.
- **Env var:** `ANTHROPIC_API_KEY` — **secret: yes**. Also set a cost ceiling
  in your Anthropic console.
- **Verify:** preflight shows it present.
- **Cost:** usage-based; the offline daily job is **free** and already runs.
- **Free alternative:** keep running only the offline leg (default).

### 5. Web production secret + trusted host
- **Env vars:** `WEBAPP_SECRET` (**secret: yes**, ≥32 chars —
  `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`),
  `WEBAPP_TRUSTED_HOSTS` (your Render hostname, not secret),
  `WEBAPP_ENV=production`.
- **Verify:** `GET /readyz` returns ready.
- **Cost:** none.

### 6. (Only when you want real marketing publishing) Publer + enable flag
- **Why:** real external publication is disabled until you turn it on AND
  approve a first controlled post.
- **Env vars:** `PUBLISHING_ENABLED=1` (not secret), `PUBLER_API_KEY`
  (**secret: yes**). Leave `MARKETING_TRUSTED_AUTONOMY` unset (autonomy stays
  locked).
- **Action:** before this is usable I must (a) verify Publer's current API,
  (b) implement the real provider client, and (c) get your explicit approval
  for one controlled test post. Until then the adapter is **dry-run only**.
- **Verify:** a dry-run publish returns a `sim_…` id and emits
  `content.publish_dry_run`, never `content.published`.
- **Cost:** Publer plan-dependent.

### 7. Portfolio capital & risk limits (your call)
- **Why:** the shadow book uses defaults (`STARTING_EQUITY=100000`,
  max 10% per position, ≥0.60 confidence, ≤25 open). Adjust to your intent.
- **Where:** `paper/portfolio.py` and `paper/eligibility.py` constants (a
  config change; tell me your numbers and I'll wire them as env-configurable).
- **Secret:** no.

## First-run checklist (controlled)
1. Deploy the Blueprint; confirm `/version` = intended commit; `/healthz` ok.
2. Set `TIINGO_API_KEY` + `FRED_API_KEY`; run **preflight** — expect healthy.
3. **Prediction generation is a separate, cost-capped step.** The scheduled
   `daily` job opens paper positions from *existing* predictions and resolves
   due ones; it does **not** itself call the model to CREATE predictions
   (that is `scripts/daily_market_predictions.py`, which makes budgeted model
   calls). Schedule/run that first so `market-open` has predictions to act on
   — this boundary is deliberate so the in-process web scheduler never makes
   unbudgeted paid model calls without your decision.
4. With `SCHEDULER_ENABLED=1`, the in-process scheduler fires `daily` on
   market days, `synthetic-daily` daily, `weekly-eval` weekly, `monthly-packet`
   monthly. Confirm on `/dashboard` (job last-success + `status/scheduler.json`
   markers). You do **not** run these by hand after deploy.
5. Manual/on-demand: `python -m intent_engine.runtime <job> --root /var/data`.
6. `monthly-packet` → review the packet; promote (if any) via the human path.

## Recovery runbook

Every failure is persistent (a `job.failed`/`config.preflight_failed` event +
a status file) and surfaced on `/dashboard`. Recovery is always a re-run —
all jobs are idempotent, so re-running never double-acts.

| Symptom (on `/dashboard` or `integrity`) | Why | Recovery |
|---|---|---|
| `config.preflight_failed`, job "failed: missing credentials" | a required key is unset/invalid | set the env var (see MANUAL ACTIONS), then `runtime preflight` — expect healthy |
| a daily job shows `failed` with a network/timeout error | transient upstream (Tiingo/FRED) | re-run `runtime daily` (idempotent); the retry usually clears it; if persistent, check the provider status |
| open positions not opening; `data_error` rejections logged | one instrument's price gap | isolated by design — the rest opened; the failed one retries next run automatically |
| integrity: `stranded_open_position` | a close failed after the prediction resolved | `runtime resolve` (or a plain reconcile run) closes it at the next available price — self-healing; no manual data edit |
| integrity: `orphan_evaluation` / `orphan_promotion` | a learning record references a missing candidate | do NOT mutate the append-only store; investigate the producing code path; the record is inert (candidate state is folded from candidates only) |
| a job stuck "locked" | a previous run crashed holding the lock, OR one is genuinely running | the flock is released on process death — if no process is running, the next scheduled run acquires it cleanly; no manual unlock needed |
| duplicate scheduler trigger | two runs fired at once | the second reports `locked` and no-ops — no duplicate trades/actions |

## Rollback
- **App:** Render dashboard → service → **Rollback** to the previous deploy,
  or `git revert <commit> && git push origin main`.
- **Data:** stores are append-only; nothing is destructively mutated. A bad
  candidate is never in production (promotion is human-gated), so "rollback"
  of learning is simply not promoting, or promoting a superseding candidate.
- **Scheduler:** suspend the cron services in the Render dashboard.
