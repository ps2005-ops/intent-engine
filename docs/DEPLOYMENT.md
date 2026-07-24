# Deployment — Founder Intelligence web experience (V1.0.1)

The web layer is a stdlib WSGI application (`intent_engine.webapp`). No
framework, no build step, no JavaScript dependencies.

## Environments

| Env | Selected by | Behavior |
|---|---|---|
| `development` | default | debug on, ephemeral secret generated |
| `test` | `WEBAPP_ENV=test` | used by the suite |
| `production` | `WEBAPP_ENV=production` | refuses to start unless valid |

## Required production environment variables

```bash
WEBAPP_ENV=production
WEBAPP_SECRET=<random, >=32 chars — generate with: python3 -c "import secrets; print(secrets.token_urlsafe(48))">
WEBAPP_TRUSTED_HOSTS=app.yourdomain.com
# optional
WEBAPP_STORE=data/webapp.jsonl
WEBAPP_FI_STORE=data/founder_intelligence.jsonl
WEBAPP_CI_STORE=data/company_ingestion.jsonl   # V1.1 real-company runs
WEBAPP_REGISTRATION_OPEN=0        # early access: admin-created accounts
```

There is **no default production secret** — startup fails loudly without
one. Debug is forced off; secure cookies are forced on.

## Install and run

```bash
git clone <repo> && cd intent-engine
python3 -m venv .venv && .venv/bin/pip install -e . -r requirements-dev.txt
export WEBAPP_ENV=production WEBAPP_SECRET=... WEBAPP_TRUSTED_HOSTS=...
PYTHONPATH=src .venv/bin/python -m intent_engine.webapp check-config
PYTHONPATH=src .venv/bin/python -m intent_engine.webapp create-user founder@example.com
PYTHONPATH=src .venv/bin/python -m intent_engine.webapp runserver --host 127.0.0.1 --port 8600
```

Health: `GET /healthz` (liveness), `GET /readyz` (config + stores).

## Render Free: one-time staging-user bootstrap (no shell access)

Render Free provides no interactive shell, so the first early-access
account is created through a one-time, token-gated bootstrap route.
No plaintext password ever reaches Render — only a locally computed
PBKDF2 hash and a random token.

1. Locally, run:

   ```bash
   PYTHONPATH=src python -m intent_engine.webapp generate-bootstrap
   ```

   It prompts for email, password, and confirmation, and prints ONLY
   three environment-variable assignments (email, password hash,
   random token). The plaintext password is never printed or stored.

2. In the Render dashboard, add the three printed values as **secret**
   environment variables:
   `WEBAPP_BOOTSTRAP_EMAIL`, `WEBAPP_BOOTSTRAP_PASSWORD_HASH`,
   `WEBAPP_BOOTSTRAP_TOKEN`.

3. Deploy.

4. Visit `https://<your-app>/bootstrap/<token>` **exactly once**. It
   creates the account (using the precomputed hash), marks the token
   consumed in persistent storage, and directs you to `/login`. It does
   not log you in.

5. Log in at `/login` with the email and the password you chose
   locally.

6. Delete all three bootstrap environment variables from Render.

7. Redeploy.

8. Confirm `https://<your-app>/bootstrap/<old-token>` now returns 404
   (it does even before the variables are removed — the consumption
   record persists across restarts — but removing them retires the
   surface entirely).

Properties: route exists only while all three variables are set;
constant-time token comparison; single use enforced persistently;
generic 404 for missing/invalid/consumed tokens and for an
already-existing account; registration stays closed; no admin panel;
auth/CSRF/session/ownership/trusted-host controls unchanged.

## HTTPS / reverse proxy (EXTERNAL HUMAN ACTION)

The app serves plain HTTP on localhost and expects to sit behind a
TLS-terminating reverse proxy (nginx/caddy) provisioned by a human:

```
caddy:  app.yourdomain.com { reverse_proxy 127.0.0.1:8600 }
```

DNS, TLS certificates, hosting accounts, and process supervision
(systemd) are human-provisioned; example systemd unit:

```ini
[Service]
Environment=WEBAPP_ENV=production
EnvironmentFile=/etc/founder-intelligence.env
ExecStart=/opt/intent-engine/.venv/bin/python -m intent_engine.webapp runserver --port 8600
WorkingDirectory=/opt/intent-engine
Restart=on-failure
[Install]
WantedBy=multi-user.target
```

## Backups

All state is two append-only JSONL files (`data/webapp.jsonl`,
`data/founder_intelligence.jsonl`). Back up by copying them; restore by
putting them back. They are append-only — a partial tail line is
detected loudly at startup (`/readyz` reports not-ready).

## Sessions

Sessions are in-memory per process: a restart logs users out (accepted
for early access; recorded in docs/V101_GAPS.md).
