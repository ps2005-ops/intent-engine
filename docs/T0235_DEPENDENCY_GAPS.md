# T023.5 Dependency Gaps — the honest infrastructure reality

*The dependency-gap protocol (Session 14). A required capability that does
not exist is recorded here — never silently faked, never invented inside
the public-experience package, never satisfied by autonomous crawling.
"No result" is superior to an invented result.*

## Pre-build audit (stated before coding)

| Question | Finding |
|---|---|
| **Existing frontend / web stack** | **None.** No Flask / Django / FastAPI / Jinja / ASGI / WSGI in `requirements*.txt` or `pyproject.toml`; no HTTP server or template engine anywhere in `src/`. The only HTML in the repo is two *static generated* report mockups. |
| **Chosen implementation path** | **stdlib HTML rendering.** Per the brief's "do not introduce a large frontend framework unless the repository already uses it", the presentation layer is a pure-Python renderer that produces server-renderable HTML strings/files — testable by asserting the rendered output. No framework is added. |
| **Existing ingestion capabilities** | **None for company websites.** The `requests`/`urllib` usages (`core/headline_feed.py`, `core/market_resolution.py`, `core/macro_data.py`) are the market-data feeds for the trading/market-engine work (FRED / Tiingo / news), not a company-website ingestion path. Autonomous crawling is walled off (A3). |
| **Existing company-intelligence inputs** | For an **arbitrary external company**: none — the internal Research/Product/Executive stores hold the founder's OWN company work, not an arbitrary customer's. The supported inputs are **founder-approved pasted/uploaded source material** and a **deterministic demo fixture**. |
| **Existing authentication** | **None.** No login / session / OAuth system exists. |
| **Existing browser test tool** | **None.** No Playwright / Selenium. |
| **Canonical public-run contract** | `founder_intelligence/records.py` — `CompanyInput`, `CompanyIdentity`, `IntelligenceRun`, `IntelligenceSection`, `InsightCard`, `EvidenceView`, `RunStatus`. |
| **Canonical result contract** | `IntelligenceRun` with ordered `IntelligenceSection`s following the trust sequence; every leaf is a T023 `SourceClaim`/`SourceRef`. |
| **How T023 SourceClaims flow into the UI** | ingested/approved source → `SourceClaim` (via a run-scoped adapter) → section assembly (composition only, no domain computation) → `presentation` view-models → HTML. The provenance chain is T023's, unchanged. |

---

## Gaps

### Gap 1 — Live company-website ingestion / public intelligence pass

| | |
|---|---|
| **Capability requested** | fetch and analyze an arbitrary company's live website + public signals |
| **Owning subsystem** | none (no founder-approved retrieval path exists in the repo) |
| **Existing closest contract** | the market-data feeds (FRED/Tiingo/news) — a *different* domain, not company web content |
| **Missing public contract** | a founder-approved, SSRF-safe fetcher + a company-source parser |
| **Degrade honestly?** | **Yes.** T023.5 uses **founder-approved pasted/uploaded** source material and a **deterministic demo fixture**. No external network call is made; no site is crawled. A run over un-ingested inputs renders honest UNAVAILABLE sections. |
| **Smallest future additive** | an approved-fetch adapter with strong URL restrictions + content hashing, recording every source (T023.5 already defines the source-record shape it would populate) |
| **Blocks launch?** | **Yes for a fully public self-serve launch** (a stranger can't yet type any URL and get live results). **No for CONTROLLED DEMO / early-user access** with approved inputs. |

### Gap 2 — Competitor intelligence

| | |
|---|---|
| **Capability requested** | a competitor set for an arbitrary company |
| **Owning subsystem** | none (carried forward from T023 dependency gap 1) |
| **Missing public contract** | a competitor-intelligence read surface |
| **Degrade honestly?** | **Yes.** The Competitors section renders `OUT_OF_SCOPE` with the reason; no competitor list is model-generated. |
| **Smallest future additive** | a competitor-intelligence subsystem, or an approved-source competitor extractor |
| **Blocks launch?** | **No.** The section is honestly empty; the rest of the experience stands. |

### Gap 3 — Authentication & multi-user persistence

| | |
|---|---|
| **Capability requested** | accounts, saved runs per user, secure access |
| **Owning subsystem** | none |
| **Degrade honestly?** | **Yes.** T023.5 runs in a **local / demo mode**; runs are scoped by `run_id` + company identity in the store, and cross-run / cross-company isolation is asserted by test, but there is no login. Saved runs are not exposed publicly. |
| **Smallest future additive** | an auth system + a per-user run index + authorization tests |
| **Blocks launch?** | **Yes for a public multi-tenant launch.** No for a controlled demo. Recorded as a **launch-blocking** dependency. |

### Gap 4 — Public deployment & secure share links

| | |
|---|---|
| **Capability requested** | a deployed public URL; shareable report links |
| **Owning subsystem** | none (no server, no hosting, no share-token system) |
| **Degrade honestly?** | **Yes.** The report is **export/preview only**; sharing is disabled by default. No guessable public URLs are created. |
| **Smallest future additive** | a hosting target + a signed share-token system |
| **Blocks launch?** | **Yes for public deployment/launch** (which is a separate fact from PRODUCT BUILT — see `docs/T0235_PRODUCT_ACCEPTANCE.md`). |

### Gap 5 — Real-browser acceptance

| | |
|---|---|
| **Capability requested** | an automated browser walkthrough of the live pages |
| **Owning subsystem** | none (no Playwright/Selenium; no running server) |
| **Degrade honestly?** | **Yes.** The HTML **renderer output is asserted** in tests (trust-sequence order, cited evidence, honest states, accessibility attributes) — the "acceptance" is over the rendered document rather than a live browser. |
| **Smallest future additive** | a web server + a browser test tool once deployment exists |
| **Blocks launch?** | **No for PRODUCT BUILT.** A real-browser pass is part of DEPLOYMENT READY. |

### Gap 6 — Supported market statistics for a private company

| | |
|---|---|
| **Capability requested** | market/financial statistics for a private company |
| **Owning subsystem** | analytics/market-engine (public-market instruments only) |
| **Degrade honestly?** | **Yes.** Any unsupported statistic renders `UNAVAILABLE` — never a fabricated number. |
| **Blocks launch?** | **No.** |

---

## What this means for the completion status (see §45 of the brief)

- **PRODUCT BUILT** — the evidence-backed experience (contracts, run lifecycle, security, identity, approved ingestion, all trust-sequence sections, conversation, snapshots, HTML presentation, demo) is built and tested.
- **CONTROLLED DEMO READY** — yes, via the deterministic demo fixture and approved-input runs.
- **DEPLOYMENT READY** — **no** (Gaps 1, 3, 4).
- **PUBLICLY DEPLOYED** — **no.**
- **LAUNCHED** — **no.**

No external network call is made in this session; no live company data is used; no authentication exists; the product is not deployed.
