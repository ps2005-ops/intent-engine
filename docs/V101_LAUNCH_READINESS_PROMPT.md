# Session Prompt — V1.0.1: Early-Access Readiness (execution-grade)

*Recorded 2026-07-23; upgraded to execution-grade 2026-07-23 by human
review. Status: NEEDS HUMAN START. Renamed from "Launch Readiness &
Product Polish" — the focus is real early users, not abstract polish.*

## Mission

Make V1 feel like software someone would happily pay for tomorrow.
Not new capabilities — readiness. But be honest that server, auth,
deployment, browser tests, and sharing are **new infrastructure**, not
polish, and hold them to full engineering discipline.

## Governing rules

No new intelligence; no new agents; no marketing features; no execution;
no autonomy; no architecture rewrites; T019–T023.5 intelligence frozen.

## Deployment-state ladder (never conflate)

```text
PRODUCT READY          — experience complete and tested in-repo
DEPLOYMENT READY       — server + config + docs let a human deploy it
STAGING DEPLOYED       — running on human-provisioned staging
PUBLICLY DEPLOYED      — running on human-provisioned production
EARLY-USER READY       — accounts + isolation + onboarding proven
LAUNCHED               — real external users invited
```

A server starting locally is NOT "DEPLOYABLE". Each rung above
DEPLOYMENT READY requires human-provisioned infrastructure and must be
reported honestly.

## Mandatory stack audit (before coding)

Inspect and state findings for: existing packaging/entrypoints; the
static HTML renderer; environment-variable handling; user/account
models; database/storage choices; session/cookie facilities; testing
dependencies; supported deployment targets; frontend build tooling;
analytics event store. Choose the **smallest compatible production
path**; do not introduce a large framework automatically.

## Authentication scope (minimum, explicit)

Administrator-created early-access accounts or registration; login and
logout; secure password hashing (salted, standard KDF); session
expiration; CSRF protection on state-changing forms; bounded login
attempts (rate limiting); ownership checks on every run; no cross-user
run or report access; password-reset status explicitly reported. If
external identity providers or email delivery are unavailable, do not
fake them — record the gap.

## Shareable-report security

Random unguessable tokens (>=128 bits); disabled by default; explicit
creation and revocation; expiry support; no private notes; no raw
internal metadata; access logging; noindex; tests proving another
report cannot be reached by guessing or enumeration.

## Production configuration rules

Three environments: `development`, `test`, `production`. Secrets only
from environment variables; no default production secret (refuse to
start); secure cookies in production; trusted-host configuration;
explicit debug-off assertion; structured logs; startup validation;
health and readiness endpoints; safe error pages (no tracebacks);
data-backup instructions.

## Browser acceptance journeys (required)

```text
landing → sign up/login → start demo run → view progress → open result
→ inspect evidence → ask a follow-up → create report share link
→ revoke link → log out → confirm protected page is inaccessible
```

Plus: mobile viewport, keyboard navigation, error state, partial
result, expired share link. Use the lightest tool consistent with the
stack; if no real-browser tool is available, full HTTP-level journey
tests against a live local server are the floor, and real-browser
automation is recorded as a classified gap.

## Launch-blocker classification

Every gap must be classified exactly one of:

```text
BLOCKS CONTROLLED EARLY ACCESS
BLOCKS PUBLIC LAUNCH
NON-BLOCKING POLISH
EXTERNAL HUMAN ACTION
```

DNS/hosting-account setup is EXTERNAL HUMAN ACTION, not a repo defect.

## Completion gate

Clean baseline and captured commit; full regression; browser/journey
E2E green; security/isolation tests green; production startup smoke
test; empty-database startup test; fresh-clone installation test;
documentation test (README steps actually work); two stability runs;
explicit status table (built/deployment-ready/staged/deployed/
launched); zero T019–T023.5 intelligence changes.

## On completion

```text
V1.0 — PRODUCT COMPLETE / DEPLOYMENT READY / EARLY-USER READY (in-repo)
```

Then V1 enters **maintenance mode**: changes require an explicit bug,
security, reliability, accessibility, or measured user-friction
justification. (Not an absolute freeze — early users will reveal
usability problems that are not strictly bugs.)
