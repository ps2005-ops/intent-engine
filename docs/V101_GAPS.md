# V1.0.1 — Gap register with launch-blocker classification

Every known gap, classified exactly one of: BLOCKS CONTROLLED EARLY
ACCESS | BLOCKS PUBLIC LAUNCH | NON-BLOCKING POLISH | EXTERNAL HUMAN
ACTION. Nothing here is pretended closed.

| Gap | Classification | Notes |
|---|---|---|
| DNS, TLS certificate, hosting account, reverse proxy | EXTERNAL HUMAN ACTION | docs/DEPLOYMENT.md gives the exact steps; not a repo defect |
| Process supervision (systemd) on a host | EXTERNAL HUMAN ACTION | example unit provided |
| Live ingestion of arbitrary company websites | BLOCKS PUBLIC LAUNCH | early access runs the labelled synthetic demo; intake says so honestly instead of inventing an analysis (carried from T023.5) |
| Password reset | BLOCKS PUBLIC LAUNCH | requires email delivery, which does not exist; admin issues a new password out of band in early access; status shown in-product |
| External identity providers (OAuth) | NON-BLOCKING POLISH | password accounts are sufficient for early access |
| Real-browser automation (Playwright etc.) | NON-BLOCKING POLISH | full HTTP-level journey tests cover every required journey in-process plus one live-socket smoke test; a JS-executing browser adds value only when client-side JS exists — this UI has none |
| Sessions are in-memory (restart logs users out) | NON-BLOCKING POLISH | acceptable for early access; move to signed cookies or a session file later |
| Rate limiting beyond login attempts | BLOCKS PUBLIC LAUNCH | login lockout exists; general request throttling should live in the reverse proxy at public scale |
| Billing / payments | BLOCKS PUBLIC LAUNCH (commercial) | out of V1.0.1 scope by design |
| Multi-run history UI per account | NON-BLOCKING POLISH | one demo run per account in early access |
| Email notifications of any kind | NON-BLOCKING POLISH | none exist; none claimed |

Nothing currently known **BLOCKS CONTROLLED EARLY ACCESS**: an admin can
install, configure production, create accounts, and early users can run
the complete demo experience with isolation, sharing, and feedback.
