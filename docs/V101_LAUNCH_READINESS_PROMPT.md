# Session Prompt — V1.0.1: Launch Readiness & Product Polish

*Recorded 2026-07-23 from human review of T023.5 (verdict: 9.8/10, no
architectural changes requested). Status: NEEDS HUMAN START. Run this
session before V2.0.*

## Mission

The mission is **not** to add new capabilities.

The mission is: **make V1 feel like software someone would happily pay for
tomorrow.**

Tighten the product and remove technical debt while V1 is still fresh.

## Governing rules

- no new intelligence;
- no new agents;
- no marketing features;
- no execution;
- no autonomy;
- no architecture rewrites;
- polish only.

## Scope

- polishing the landing page copy and UX;
- deployment (server, hosting, HTTPS, auth);
- browser E2E tests;
- shareable reports;
- performance improvements;
- accessibility audit;
- responsive/mobile polish;
- analytics verification;
- onboarding improvements;
- first-user friction fixes;
- deployment documentation;
- production configuration.

Note: actual public hosting/DNS/TLS provisioning requires human-owned
accounts and infrastructure. The in-repo deliverable is a runnable server,
working auth, production configuration, and deployment documentation; the
final hosting step is a recorded human action, reported honestly per the
T023.5 status discipline (BUILT ≠ DEPLOYED ≠ LAUNCHED).

## Completion gate

- deployable;
- responsive;
- browser-tested;
- authentication working;
- onboarding complete;
- reports polished;
- production config documented;
- launch checklist complete.

## On completion

```text
V1.0
PRODUCT COMPLETE
DEPLOYABLE
READY FOR EARLY USERS
```

Then **freeze V1**. Do not touch it except for bug fixes. T019–T023.5
remain stable; future work builds on top, never rewrites.
