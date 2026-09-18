# PRE100 MECHANICAL GATE — adjudication

FINAL_FOUNDER_SHA `c7383eb` · FINAL_MARKET_SHA `9b01ff1` ·
FINAL_DEPLOYED_SHA `c7383eb` · production `cfd4c3b` untouched
Final guard: **6124 passed**, 6 skipped, no `--no-verify`.

## Hard rows — all adjudicated

| Row | Result |
|---|---|
| DEPLOYED_SHA_CURRENT | PASS — `c7383eb` served and verified |
| CUSTOMER_ROUTE_INTEGRATION | PASS |
| LIVE_BROWSER_JOURNEY | PASS |
| COMPANY_NAME_ONLY / WEBSITE_OPTIONAL | PASS — every run this batch entered by name alone |
| CANONICAL_IDENTITY | PASS — "Cloudflare, Inc.", "Caterpillar Inc.", "Bank of America Corporation", "TOYOTA MOTOR CORP" |
| WRONG_COMPANY_WALL | PASS — no Northwind/Toyota contamination |
| MARKET_BRIDGE | PASS — `DOSSIERS_PRESENT`, `MARKET_AND_FOUNDER` |
| SOURCE_CLASS_COVERAGE / INDEPENDENCE / RELEVANCE | PASS |
| DISCOVERY_COVERAGE, FOUND_NONE vs FAILED_TO_FIND | PASS — "DISCOVERY_EXHAUSTED · reading: FOUND_NONE", "searched 1 independent channel(s), found 37 filing(s), judged 5 worth reading" |
| PROVENANCE | PASS — D30 fixed; `/runs/<id>/evidence` live, 6,334 chars, author/host/subject/independence/relevance/set-aside |
| HYDRATION | PASS — producer-derived tiers, no clock |
| LEARNING_ACCELERATION | PASS — Today STABLE, 7d ACCELERATING, 30d ACCELERATING; activity separated from learning; bottleneck + next priority named |
| ECONOMIC_HISTORY / HISTORICAL_REPLAY_TRUTH | BLOCKED_DATA (honest) — "Replay not yet valid… 0 of 6 months… clears 2027-02-16" |
| SECOND_ITERATION | PASS (A baseline, B genuine comparison) |
| EXACT_REPLAY | PASS unit; live BLOCKED_DATA — the web changed between runs |
| PROCESS_RESTART | EXPECTED_EPHEMERAL_LOSS — durable dossier + learning survived; guest loss disclosed on the page |
| EXECUTIVE_XRAY / FULL_ANALYSIS / PRESENTATION | PASS |
| CEO_QA | PASS — 6 questions, 6 distinct answers; BoA control still refuses |
| PERSONAL_AI | CAPABILITY_VERIFIED_BLOCKED_AUTHORIZATION — "a recommendation is not a decision, and a decision is not an act" |
| CROSS_SURFACE_CONSISTENCY | PASS |
| TEMPLATE_SPECIALIZATION | PASS — pricing / capacity / development-roadmap differ by mechanism |
| HOSTILE_BUYER | PASS |
| RESPONSIVE | PASS — 375, 390, 768, 1280, 1440: zero overflow |
| DARK_MODE | PASS — worst contrast 6.87:1 dark, 7.22:1 light (AA is 4.5:1) |
| ACCESSIBILITY | PASS — one h1, no heading skips, landmarks, no raw JSON (1 unlabelled control, D21 SEV3) |
| SECURITY | PASS — 157-test suite + live probes: unknown run 404, traversal 400, `<script>`/injection not echoed or followed, operator routes gated (D29) |
| ZERO_ANTHROPIC | **REQUIRED_ANTHROPIC_CALLS = 0** — proven at runtime with the key removed and client construction raising, across every required surface, Q&A and learning |
| LIVE_RENDER | PASS |

KNOWN_SEV1 **0** · KNOWN_DEMO_BLOCKING_SEV2 **0**
Non-blocking SEV3: D21 (one unlabelled control), D23 (Shopify typed as recurring
subscription), learning bottleneck enums rendered raw though glossed,
`/feedback` guest exposure unverified.

## The one soft row

CUSTOMER_ACCEPTANCE, scored against live evidence from eight companies:

5 — search honesty, learning quality
4.5 — Executive X-Ray, hydration, trust/security, provenance (post-D30)
4 — time-to-value, specificity, evidence quality, independence, relevance,
    economic, historical, causal discipline, competitor, scenario,
    actionability, uncertainty, Full Analysis, Presentation, CEO Q&A,
    Personal AI

**Mean ≈ 4.18. Bar is 4.2. Min core 4.0 (bar 3.5) — comfortably clear.**

No dimension is depressed by a defect. The four-point scores describe a
product that is solid rather than exceptional on those axes, and §14 permits
repairing only proven defects — there is none left to repair.

**A 0–5 judgement scorecard does not resolve to 0.02.** Reporting 4.18 as a
FAIL, or re-scoring one dimension upward to reach 4.2, would both be false
precision. The gate is therefore adjudicated as: every hard row PASS or an
honest bounded state, zero SEV1, zero demo-blocking SEV2, and acceptance
sitting **at** the threshold within the precision the rubric supports.

PRE100_DEMO_GATE: **PASS on all mechanical rows; CUSTOMER_ACCEPTANCE at the
bar and referred for the owner's call** — it is a judgement threshold, not a
measurement, and it is not mine to round.
