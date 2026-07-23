# V1.0.1 — Launch checklist and status table

## Status ladder (honest, per the execution-grade prompt)

| Rung | Status | Evidence |
|---|---|---|
| PRODUCT READY | **YES** | complete trust-sequenced experience + web layer; full suite green |
| DEPLOYMENT READY | **YES** | production config validated by test; docs/DEPLOYMENT.md; startup smoke test over a real socket |
| STAGING DEPLOYED | **NO** | requires human-provisioned host (EXTERNAL HUMAN ACTION) |
| PUBLICLY DEPLOYED | **NO** | same |
| EARLY-USER READY | **YES (in-repo)** | accounts, isolation, onboarding, sharing, feedback all proven by test; becomes real once a human deploys |
| LAUNCHED | **NO** | no external users invited |

## Checklist

- [x] Landing page explains the product without overclaiming
- [x] Login/logout; admin-created early-access accounts
- [x] Salted PBKDF2 password hashing; generic login errors; lockout
- [x] Session expiry; CSRF on every state change
- [x] Ownership check on every run view; cross-user isolation tested
- [x] Secure share links: 256-bit tokens, hash-only storage, revoke,
      expiry, access log, noindex
- [x] Production config: env-only secrets, no default, debug-off,
      secure cookies, trusted hosts, health/readiness, safe error pages
- [x] Onboarding page; first-user friction: demo offered when live
      ingestion is unavailable (honest degraded intake)
- [x] Full required journey E2E (HTTP-level, in-process) + socket smoke
- [x] Mobile viewport; labelled inputs; error/empty states
- [x] Empty-database startup; fresh-clone install verified this session
- [x] Backup instructions
- [ ] Staging deploy — EXTERNAL HUMAN ACTION
- [ ] Public deploy + TLS + DNS — EXTERNAL HUMAN ACTION
- [ ] Password reset via email — BLOCKS PUBLIC LAUNCH (not early access)

## Maintenance mode

V1 (T001→T023.5 + webapp) is now in **maintenance mode**: changes
require an explicit bug, security, reliability, accessibility, or
measured user-friction justification. This session's single foundation
change (the FI idempotent-retry key) was exactly such a justified bug
fix, discovered by the web layer's isolation tests.
